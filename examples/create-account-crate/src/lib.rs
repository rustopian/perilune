use solana_program::{
    entrypoint::ProgramResult,
    pubkey::Pubkey,
    account_info::AccountInfo,
    instruction::{AccountMeta, Instruction},
    account_info::Account as CpiAccount,
    program::invoke_signed,
    program_error::ProgramError,
};

const CREATE_ACCOUNT_INSTRUCTION_TAG: u8 = 0;
const LAMPORTS_OFFSET: usize = 1;
const SPACE_OFFSET: usize = 9;
const REQUIRED_INSTRUCTION_DATA_LEN: usize = 17;

#[cfg(all(feature = "std"))]
pub mod create_account_benches {
    use {
        solana_account_info::{AccountInfo, next_account_info},
        solana_program_error::{ProgramResult, ProgramError},
        solana_cpi::invoke,
        solana_pubkey::Pubkey,
        solana_system_interface::{instruction, program},
    };
    use super::{CREATE_ACCOUNT_INSTRUCTION_TAG, LAMPORTS_OFFSET, SPACE_OFFSET, REQUIRED_INSTRUCTION_DATA_LEN};

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

        let lamports = u64::from_le_bytes(instruction_data[LAMPORTS_OFFSET..SPACE_OFFSET].try_into().unwrap());
        let space = u64::from_le_bytes(instruction_data[SPACE_OFFSET..REQUIRED_INSTRUCTION_DATA_LEN].try_into().unwrap());

        let account_iter = &mut accounts.iter();
        let funder_account = next_account_info(account_iter)?;
        let new_account = next_account_info(account_iter)?;
        let system_program_account = next_account_info(account_iter)?;
        
        if system_program_account.key != &program::ID {
            // Optional: Add a specific error if system program ID is not as expected
            // return Err(ProgramError::IncorrectProgramId);
        }

        invoke(
            &instruction::create_account(
                funder_account.key,
                new_account.key,
                lamports,
                space,
                program_id,
            ),
            &[
                funder_account.clone(),
                new_account.clone(),
                system_program_account.clone(),
            ],
        )
    }
}

#[cfg(all(feature = "no_std"))]
pub mod create_account_benches {
    use {
        solana_program_error::{ProgramResult, ProgramError},
        solana_pubkey::Pubkey,
        solana_nostd_entrypoint::{NoStdAccountInfo as AccountInfo, InstructionC},
        solana_cpi::syscalls,
        SystemPubkey,
    };
    use super::{CREATE_ACCOUNT_INSTRUCTION_TAG, LAMPORTS_OFFSET, SPACE_OFFSET, REQUIRED_INSTRUCTION_DATA_LEN};

    // Use the correct Pubkey type for InstructionC (system program is all zeros)
    const SYSTEM_PROGRAM_ID: SystemPubkey = SystemPubkey::new_from_array([0u8; 32]);

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

        let lamports = u64::from_le_bytes(instruction_data[LAMPORTS_OFFSET..SPACE_OFFSET].try_into().unwrap());
        let space = u64::from_le_bytes(instruction_data[SPACE_OFFSET..REQUIRED_INSTRUCTION_DATA_LEN].try_into().unwrap());

        // Use array destructuring instead of next_account_info
        let [funder_account, new_account, _system_program] = match accounts {
            [funder, new, system, ..] => [funder, new, system],
            _ => return Err(ProgramError::NotEnoughAccountKeys),
        };

        // Build instruction data for system program create_account
        let mut system_instruction_data = [0u8; 52];
        system_instruction_data[0..4].copy_from_slice(&0u32.to_le_bytes()); // CreateAccount discriminator
        system_instruction_data[4..12].copy_from_slice(&lamports.to_le_bytes());
        system_instruction_data[12..20].copy_from_slice(&space.to_le_bytes());
        system_instruction_data[20..52].copy_from_slice(program_id.as_ref());

        // Prepare accounts for CPI
        let instruction_accounts = [
            funder_account.to_meta_c(),
            new_account.to_meta_c(),
        ];

        let instruction = InstructionC {
            program_id: &SYSTEM_PROGRAM_ID,
            accounts: instruction_accounts.as_ptr(),
            accounts_len: instruction_accounts.len() as u64,
            data: system_instruction_data.as_ptr(),
            data_len: system_instruction_data.len() as u64,
        };

        let infos = [funder_account.to_info_c(), new_account.to_info_c()];

        // Use direct syscall for CPI
        #[cfg(target_os = "solana")]
        unsafe {
            syscalls::sol_invoke_signed_c(
                &instruction as *const InstructionC as *const u8,
                infos.as_ptr() as *const u8,
                infos.len() as u64,
                core::ptr::null(),
                0,
            );
        }

        Ok(())
    }
} 