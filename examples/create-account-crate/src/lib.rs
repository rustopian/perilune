#![cfg_attr(not(feature = "host"), no_std)]

// -----------------------------------------------------------------------------
// no_std setup (allocator & panic handler stubs)
// -----------------------------------------------------------------------------
#[cfg(not(feature = "host"))]
use pinocchio::{no_allocator, nostd_panic_handler};

#[cfg(not(feature = "host"))]
no_allocator!();
#[cfg(not(feature = "host"))]
nostd_panic_handler!();

// -----------------------------------------------------------------------------
// Common imports & constants
// -----------------------------------------------------------------------------
use pinocchio::{
    account_info::AccountInfo,
    cpi::invoke,
    instruction::{AccountMeta, Instruction},
    program_error::ProgramError,
    pubkey::Pubkey,
    ProgramResult,
};

/// System program id – the BPF loader substitutes all-zero bytes for the well-known
/// `11111111111111111111111111111111` base-58 address. Using a zeroed array keeps
/// the constant valid for on-chain (`target_os = "solana"`) and off-chain builds.
pub const PINOCCHIO_SYSTEM_PROGRAM_ID: Pubkey = [0u8; 32];

// Instruction layout offsets (see README for details)
const CREATE_ACCOUNT_INSTRUCTION_TAG: u8 = 0;
const LAMPORTS_OFFSET: usize = 1;
const SPACE_OFFSET: usize = 9;
const REQUIRED_INSTRUCTION_DATA_LEN: usize = 17;

// -----------------------------------------------------------------------------
// Std (host) benchmarks – used by `pinocchio-std` entrypoint
// -----------------------------------------------------------------------------
#[cfg(feature = "std")]
pub mod std_benches {
    use super::*;

    /// Bench implementation for a `system_instruction::create_account` CPI.
    ///
    /// * `program_id` – id of the program being benchmarked (passed through to the CPI data).
    /// * `accounts` – `[funder, new_account, system_program, ..]`.
    /// * `instruction_data` layout:
    ///   byte 0   – discriminator (must be 0 for this bench)
    ///   bytes 1-8  – lamports (u64 LE)
    ///   bytes 9-16 – space    (u64 LE)
    pub fn run_create_account_bench(
        program_id: &Pubkey,
        accounts: &[AccountInfo],
        instruction_data: &[u8],
    ) -> ProgramResult {
        // ----------------------------
        // Validate instruction data
        // ----------------------------
        if instruction_data.is_empty() || instruction_data[0] != CREATE_ACCOUNT_INSTRUCTION_TAG {
            return Err(ProgramError::InvalidInstructionData);
        }
        if instruction_data.len() < REQUIRED_INSTRUCTION_DATA_LEN {
            return Err(ProgramError::InvalidInstructionData);
        }

        let lamports = u64::from_le_bytes(
            instruction_data[LAMPORTS_OFFSET..SPACE_OFFSET]
                .try_into()
                .unwrap(),
        );
        let space = u64::from_le_bytes(
            instruction_data[SPACE_OFFSET..REQUIRED_INSTRUCTION_DATA_LEN]
                .try_into()
                .unwrap(),
        );

        // ----------------------------
        // Destructure & validate accounts
        // ----------------------------
        let [funder, new_account, system_program] = match accounts {
            [f, n, s, ..] => [f, n, s],
            _ => return Err(ProgramError::NotEnoughAccountKeys),
        };

        // Ensure the supplied system program account is correct
        if system_program.key() != &PINOCCHIO_SYSTEM_PROGRAM_ID {
            return Err(ProgramError::IncorrectProgramId);
        }

        // ----------------------------
        // Build raw `create_account` instruction
        // ----------------------------
        let mut data = [0u8; 52];
        data[0..4].copy_from_slice(&0u32.to_le_bytes()); // discriminator for `create_account`
        data[4..12].copy_from_slice(&lamports.to_le_bytes());
        data[12..20].copy_from_slice(&space.to_le_bytes());
        data[20..52].copy_from_slice(program_id);

        let metas = [
            AccountMeta::new(funder.key(), /*is_writable=*/ true, /*is_signer=*/ true),
            AccountMeta::new(new_account.key(), true, true),
        ];

        let ix = Instruction {
            program_id: &PINOCCHIO_SYSTEM_PROGRAM_ID,
            accounts: &metas,
            data: &data,
        };

        // ----------------------------
        // Invoke system program
        // ----------------------------
        invoke(&ix, &[funder, new_account, system_program])
    }
}

// -----------------------------------------------------------------------------
// no_std benchmarks – used by pure Pinocchio / solana-nostd entrypoints
// -----------------------------------------------------------------------------
#[cfg(feature = "no_std")]
pub mod nostd_benches {
    use super::*;
    use pinocchio::cpi::invoke_signed_unchecked;

    /// Same logic as `std_benches`, but minimises dependencies and avoids heap usage.
    pub fn run_create_account_bench(
        program_id: &Pubkey,
        accounts: &[AccountInfo],
        instruction_data: &[u8],
    ) -> ProgramResult {
        if instruction_data.is_empty() || instruction_data[0] != CREATE_ACCOUNT_INSTRUCTION_TAG {
            return Err(ProgramError::InvalidInstructionData);
        }
        if instruction_data.len() < REQUIRED_INSTRUCTION_DATA_LEN {
            return Err(ProgramError::InvalidInstructionData);
        }

        let lamports = u64::from_le_bytes(
            instruction_data[LAMPORTS_OFFSET..SPACE_OFFSET]
                .try_into()
                .unwrap(),
        );
        let space = u64::from_le_bytes(
            instruction_data[SPACE_OFFSET..REQUIRED_INSTRUCTION_DATA_LEN]
                .try_into()
                .unwrap(),
        );

        let [funder, new_account, _system_program] = match accounts {
            [f, n, s, ..] => [f, n, s],
            _ => return Err(ProgramError::NotEnoughAccountKeys),
        };

        let mut data = [0u8; 52];
        data[0..4].copy_from_slice(&0u32.to_le_bytes());
        data[4..12].copy_from_slice(&lamports.to_le_bytes());
        data[12..20].copy_from_slice(&space.to_le_bytes());
        data[20..52].copy_from_slice(program_id);

        let metas = [
            AccountMeta::new(funder.key(), true, true),
            AccountMeta::new(new_account.key(), true, true),
        ];

        let ix = Instruction {
            program_id: &PINOCCHIO_SYSTEM_PROGRAM_ID,
            accounts: &metas,
            data: &data,
        };

        unsafe {
            // No borrow-checking validation to keep CU usage minimal.
            use pinocchio::instruction::Account as CpiAccount;
            let accounts_array: [CpiAccount; 2] = [CpiAccount::from(funder), CpiAccount::from(new_account)];
            invoke_signed_unchecked(&ix, &accounts_array, &[]);
        }
        Ok(())
    }
}

// -----------------------------------------------------------------------------
// Provide a unified alias so the benchmark harness can `use` the same symbol
// -----------------------------------------------------------------------------
#[cfg(feature = "std")]
pub use std_benches as create_account_benches;

#[cfg(all(feature = "no_std"))]
pub use nostd_benches as create_account_benches; 