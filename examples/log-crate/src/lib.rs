use pinocchio::{
    ProgramResult,
    no_allocator,
    nostd_panic_handler,
    pubkey::Pubkey,
    account_info::AccountInfo,
};

#[cfg(any(feature = "std", feature = "solana-nostd-entrypoint"))]
pub mod log_benches {
    pub fn run_log_bench(_program_id: &Pubkey, _accounts: &[AccountInfo], _instruction_data: &[u8]) -> ProgramResult {
        // Use msg! macro for logging in BPF programs
        msg!("Hello from Solana BPF log benchmark!");
        Ok(())
    }
}

#[cfg(feature = "no_std")]
pub mod log_benches {
    pub fn run_log_bench(
        _program_id: &Pubkey, 
        _accounts: &[AccountInfo],
        _instruction_data: &[u8]
    ) -> ProgramResult {
        sol_log("Hello from Pinocchio log benchmark!");
        Ok(())
    }
}
