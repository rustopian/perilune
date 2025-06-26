#![cfg_attr(not(feature = "host"), no_std)]

#[cfg(not(feature = "host"))]
use pinocchio::{no_allocator, nostd_panic_handler};

#[cfg(not(feature = "host"))]
no_allocator!();

#[cfg(not(feature = "host"))]
nostd_panic_handler!();

use pinocchio::{
    ProgramResult,
    pubkey::Pubkey,
    account_info::AccountInfo,
    sysvars::slot_hashes::SlotHashes,
    program_error::ProgramError,
};

fn load_slot_hashes<'a>(
    acc: &'a AccountInfo,
) -> Result<SlotHashes<impl core::ops::Deref<Target=[u8]> + 'a>, ProgramError> {
    #[cfg(feature = "std")]
    {
        let bytes = acc.try_borrow_data().map_err(|_| ProgramError::InvalidAccountData)?;
        return SlotHashes::new(bytes.to_vec().into_boxed_slice());
    }
    #[cfg(not(feature = "std"))]
    {
        return SlotHashes::from_account_info(acc);
    }
}

// Helper functions for parsing SlotHashes without expensive bincode
#[cfg(feature = "std")]
fn parse_slot_hashes_raw(data: &[u8]) -> Result<(usize, &[(u64, [u8; 32])]), ProgramError> {
    if data.len() < 8 {
        return Err(ProgramError::InvalidAccountData);
    }
    
    // Read the length as little-endian u64
    let len_bytes = data.get(0..8).ok_or(ProgramError::InvalidAccountData)?;
    let len = u64::from_le_bytes([
        len_bytes[0], len_bytes[1], len_bytes[2], len_bytes[3],
        len_bytes[4], len_bytes[5], len_bytes[6], len_bytes[7],
    ]) as usize;
    
    if len > 512 { // MAX_ENTRIES
        return Err(ProgramError::InvalidAccountData);
    }
    
    // Each entry is 40 bytes (8 bytes slot + 32 bytes hash)
    let expected_data_len = 8 + (len * 40);
    if data.len() < expected_data_len {
        return Err(ProgramError::InvalidAccountData);
    }
    
    // Cast the entries section directly (zero-copy!)
    let entries_data = &data[8..8 + (len * 40)];
    let entries = unsafe {
        core::slice::from_raw_parts(
            entries_data.as_ptr() as *const (u64, [u8; 32]),
            len
        )
    };
    
    Ok((len, entries))
}

#[cfg(feature = "std")]
fn find_slot_in_entries(entries: &[(u64, [u8; 32])], target_slot: u64) -> Option<&[u8; 32]> {
    // Binary search since slots are in descending order
    entries.binary_search_by(|entry| entry.0.cmp(&target_slot).reverse())
        .ok()
        .map(|index| &entries[index].1)
}

// Define instruction module that contains the main benchmarkable function
pub mod instruction {
    // Bring crate-level items into scope based on feature flags
    use crate::{Pubkey, AccountInfo, ProgramResult, ProgramError};
    use crate::processor;

    /// Main instruction processor that dispatches to specific SlotHashes functions
    pub fn process_instruction(
        program_id: &Pubkey, 
        accounts: &[AccountInfo],
        instruction_data: &[u8],
    ) -> ProgramResult { 
        // Parse instruction data to determine which function to benchmark
        let instruction_tag = instruction_data.get(0).copied().unwrap_or(0);
        
        match instruction_tag {
            0 => processor::process_from_account_info(program_id, accounts, instruction_data),
            1 => processor::process_get_entry_early(program_id, accounts, instruction_data),
            2 => processor::process_get_entry_middle(program_id, accounts, instruction_data), 
            3 => processor::process_get_entry_late(program_id, accounts, instruction_data),
            4 => processor::process_get_entry_missing(program_id, accounts, instruction_data),
            5 => processor::process_get_entry_early_unchecked(program_id, accounts, instruction_data),
            6 => processor::process_get_entry_middle_unchecked(program_id, accounts, instruction_data),
            7 => processor::process_get_entry_late_unchecked(program_id, accounts, instruction_data),
            8 => processor::process_iterator(program_id, accounts, instruction_data),
            9 => processor::process_entries_slice(program_id, accounts, instruction_data),
            10 => processor::process_get_hash(program_id, accounts, instruction_data),
            11 => processor::process_position(program_id, accounts, instruction_data),
            12 => processor::process_fetch_std(program_id, accounts, instruction_data),
            13 => processor::process_fetch_into(program_id, accounts, instruction_data),
            14 => processor::process_fetch_into_unchecked(program_id, accounts, instruction_data),
            15 => processor::process_entries_slice_repeat(program_id, accounts, instruction_data),
            16 => processor::process_entries_slice_blackbox(program_id, accounts, instruction_data),
            _ => {
                return Err(ProgramError::InvalidInstructionData);
            }
        }
    }
}

// Define processor module that contains the benchmarkable functions
pub mod processor {
    // Bring crate-level items into scope based on feature flags
    #[cfg(all(feature = "no_std"))]
    use crate::{Pubkey, AccountInfo, ProgramResult, ProgramError, SlotHashes};
    #[cfg(feature = "std")]
    use crate::{Pubkey, AccountInfo, ProgramResult, ProgramError, parse_slot_hashes_raw, find_slot_in_entries};
    #[cfg(feature = "std")]
    const MAX_SIZE: usize = 20_488; // 8 + 512 * 40 – canonical sysvar size
    #[cfg(feature = "std")]
    const SLOTHASHES_ID: [u8; 32] = [
        6, 167, 213, 23, 25, 47, 10, 175, 198, 242, 101, 227, 251, 119, 204, 122,
        218, 130, 197, 41, 208, 190, 59, 19, 110, 45, 0, 85, 32, 0, 0, 0,
    ];
    #[cfg(feature = "std")]
    extern "C" {
        fn sol_get_sysvar(
            sysvar_id_addr: *const u8,
            result: *mut u8,
            offset: u64,
            length: u64,
        ) -> u64;
    }
    
    /// Benchmark SlotHashes::from_account_info() construction
    pub fn process_from_account_info(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;

        if slot_hashes.len() == 0 {
            return Err(ProgramError::InvalidArgument);
        }

        Ok(())
    }

    /// Benchmark SlotHashes::get_entry() for EARLY position (slot 10000 - first entry)
    pub fn process_get_entry_early(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 10000u64;
        if let Some(hash) = slot_hashes.get_hash(target_slot) {
            if hash.iter().all(|&b| b == 0) {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes::get_entry() for MIDDLE position (slot 9750 - middle depth)
    pub fn process_get_entry_middle(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or_else(|| {
            return ProgramError::NotEnoughAccountKeys;
        })?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 9750u64;
        if let Some(hash) = slot_hashes.get_hash(target_slot) {
            if hash.iter().all(|&b| b == 0) {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes::get_entry() for LATE position (slot 9100 - deep search)
    pub fn process_get_entry_late(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or_else(|| {
            return ProgramError::NotEnoughAccountKeys;
        })?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 9100u64;
        if let Some(hash) = slot_hashes.get_hash(target_slot) {
            if hash.iter().all(|&b| b == 0) {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes::get_entry() for MISSING slot (full tree traversal)
    pub fn process_get_entry_missing(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 8000u64;
        if slot_hashes.get_hash(target_slot).is_some() {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }

    /// Benchmark SlotHashes iterator (baseline iteration benchmark)
    pub fn process_iterator(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let count = slot_hashes.into_iter().take(10).count();
        if count == 0 {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }

    /// Benchmark SlotHashes UNCHECKED get_entry() for EARLY position (slot 10000)
    pub fn process_get_entry_early_unchecked(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 10000u64;
        if let Some(position) = slot_hashes.position(target_slot) {
            let entry = unsafe { slot_hashes.get_entry_unchecked(position) };
            if entry.slot() != target_slot {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes UNCHECKED get_entry() for MIDDLE position (slot 9750)
    pub fn process_get_entry_middle_unchecked(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 9750u64;
        if let Some(position) = slot_hashes.position(target_slot) {
            let entry = unsafe { slot_hashes.get_entry_unchecked(position) };
            if entry.slot() != target_slot {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes UNCHECKED get_entry() for LATE position (slot 9100)
    pub fn process_get_entry_late_unchecked(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let target_slot = 9100u64;
        if let Some(position) = slot_hashes.position(target_slot) {
            let entry = unsafe { slot_hashes.get_entry_unchecked(position) };
            if entry.slot() != target_slot {
                return Err(ProgramError::InvalidArgument);
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes get_hash() method (binary search)
    pub fn process_get_hash(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        if let Some(first_entry) = slot_hashes.get_entry(0) {
            let target_slot = first_entry.slot();
            slot_hashes.get_hash(target_slot).ok_or(ProgramError::InvalidArgument)?;
        } else {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }

    /// Benchmark SlotHashes position() method (binary search)
    pub fn process_position(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        if let Some(first_entry) = slot_hashes.get_entry(0) {
            let target_slot = first_entry.slot();
            slot_hashes.position(target_slot).ok_or(ProgramError::InvalidArgument)?;
        } else {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }

    /// Benchmark SlotHashes entries() slice access
    pub fn process_entries_slice(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes_account = accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?;

        let slot_hashes = super::load_slot_hashes(slot_hashes_account)?;
        let entries = slot_hashes.entries();
        if entries.len() != slot_hashes.len() {
            return Err(ProgramError::InvalidArgument);
        }
        if !entries.is_empty() {
            let first_slot = entries[0].slot();
            if entries.len() > 1 {
                let second_slot = entries[1].slot();
                if first_slot <= second_slot {
                    return Err(ProgramError::InvalidArgument);
                }
            }
        }
        Ok(())
    }

    /// Benchmark SlotHashes::fetch() (std only)
    pub fn process_fetch_std(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        #[cfg(feature = "std")]
        {
            let mut buffer = vec::vec![0u8; MAX_SIZE];
            // SAFETY: buffer length matches request length
            let rc = unsafe {
                sol_get_sysvar(
                    SLOTHASHES_ID.as_ptr(),
                    buffer.as_mut_ptr(),
                    0,
                    MAX_SIZE as u64,
                )
            };
            if rc != 0 {
                return Err(ProgramError::InvalidArgument);
            }
            // Basic sanity – first 8 bytes = len ≤ 512
            let len = u64::from_le_bytes(buffer[0..8].try_into().unwrap()) as usize;
            if len == 0 || len > 512 {
                return Err(ProgramError::InvalidArgument);
            }

            let _ = accounts; // silence unused
        }
        Ok(())
    }

    /// Benchmark SlotHashes::fetch_into() (std only)
    pub fn process_fetch_into(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        #[cfg(feature = "std")]
        {
            let mut buffer = vec::vec![0u8; MAX_SIZE];
            let rc = unsafe {
                sol_get_sysvar(
                    SLOTHASHES_ID.as_ptr(),
                    buffer.as_mut_ptr(),
                    0,
                    MAX_SIZE as u64,
                )
            };
            if rc != 0 {
                return Err(ProgramError::InvalidArgument);
            }
            let (len, _entries) = parse_slot_hashes_raw(&buffer)?;
            if len == 0 { return Err(ProgramError::InvalidArgument); }

            let _ = accounts;
        }
        Ok(())
    }

    /// Benchmark SlotHashes::fetch_into_unchecked() (std only)
    pub fn process_fetch_into_unchecked(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        #[cfg(feature = "std")]
        {
            let mut buffer = vec::vec![0u8; MAX_SIZE];
            let rc = unsafe {
                sol_get_sysvar(
                    SLOTHASHES_ID.as_ptr(),
                    buffer.as_mut_ptr(),
                    0,
                    MAX_SIZE as u64,
                )
            };
            if rc != 0 {
                return Err(ProgramError::InvalidArgument);
            }
            let (len, _entries) = parse_slot_hashes_raw(&buffer)?;
            if len == 0 { return Err(ProgramError::InvalidArgument); }

            let _ = accounts;
        }
        Ok(())
    }

    /// Benchmark SlotHashes::process_entries_slice_repeat() (std only)
    pub fn process_entries_slice_repeat(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        let slot_hashes = super::load_slot_hashes(accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?)?;
        let mut checksum: u64 = 0;
        for _ in 0..1_000 {
            let entries = slot_hashes.entries();
            if let Some(first) = entries.get(0) {
                checksum |= first.slot();
            }
        }
        if checksum == 0 {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }

    /// Benchmark SlotHashes::process_entries_slice_blackbox() (std only)
    pub fn process_entries_slice_blackbox(
        _program_id: &Pubkey,
        accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult {
        use core::hint::black_box;
        let slot_hashes = super::load_slot_hashes(accounts.get(0).ok_or(ProgramError::NotEnoughAccountKeys)?)?;
        let entries = slot_hashes.entries();
        if entries.is_empty() {
            return Err(ProgramError::InvalidArgument);
        }
        let mut checksum: u64 = 0;
        let len = entries.len();
        for i in 0..1_000 {
            let idx = i % len;
            checksum ^= black_box(entries[idx].slot());
        }
        if checksum == 0 {
            return Err(ProgramError::InvalidArgument);
        }
        Ok(())
    }
} 