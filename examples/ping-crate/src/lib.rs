use {
    solana_account_info::AccountInfo,
    solana_entrypoint::ProgramResult,
    solana_pubkey::Pubkey,
};

pub mod instruction {
    use crate::{Pubkey, AccountInfo, ProgramResult};

    pub fn process_instruction(
        _program_id: &Pubkey, 
        _accounts: &[AccountInfo],
        _instruction_data: &[u8],
    ) -> ProgramResult { 
        Ok(())
    }
} 