#![no_main]

// Use the Solana Program SDK for entrypoint, base types etc.
use solana_entrypoint;
use solana_entrypoint::entrypoint;
use solana_account_info::AccountInfo;
use solana_pubkey::Pubkey;

// Simple debug logging macro: compiles away in release builds.
#[cfg(debug_assertions)]
macro_rules! debug_msg {
    ($($arg:tt)*) => {
        // Using core::fmt machinery here would be expensive; keep as no-op for now
    };
}

#[cfg(not(debug_assertions))]
macro_rules! debug_msg {
    ($($arg:tt)*) => {};
}

// Directly import ProgramResult from solana_program_error as requested
// This assumes solana_program_error crate v2.2 exports this type.
use solana_program_error::ProgramResult;

// Import the function to be benchmarked
use %%RUST_IMPORT_CRATE_NAME%%::%%BENCHMARK_FUNCTION_MODULE%%::%%BENCHMARK_FUNCTION_NAME%% as benchmark_function_to_call;

// Solana Program entrypoint
entrypoint!(process_instruction);

// Declare a default program ID. This might be replaced during build or deployment.
// ... existing code ...

// The benchmark function wrapper
#[inline(always)]
pub fn process_instruction(
    _program_id: &Pubkey,
    _accounts: &[AccountInfo],
    _instruction_data: &[u8],
) -> ProgramResult {
    // Call the benchmarked function directly
    benchmark_function_to_call(_program_id, _accounts, _instruction_data)
}