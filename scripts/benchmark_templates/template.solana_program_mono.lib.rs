#![no_main]

// Use the monolithic Solana Program SDK for entrypoint, base types etc.
use solana_program::{
    entrypoint,
    entrypoint::ProgramResult,
    account_info::AccountInfo,
    pubkey::Pubkey,
    program_error::ProgramError,
};

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

// Import the function to be benchmarked
// These placeholders will be replaced by the script
#[cfg(not(feature = "no_bench_function"))] // Conditionally compile based on presence of placeholders
use %%RUST_IMPORT_CRATE_NAME%%::%%BENCHMARK_FUNCTION_MODULE%%::%%BENCHMARK_FUNCTION_NAME%% as benchmark_function_to_call;

// Solana Program entrypoint
entrypoint!(process_instruction);

// Declare a default program ID. This might be replaced during build or deployment.
// ... existing code ...

// The entrypoint function required by Solana Program SDK
// Signature matches the standard Solana entrypoint
#[inline(always)]
pub fn process_instruction(
    _program_id: &Pubkey,
    _accounts: &[AccountInfo],
    _instruction_data: &[u8],
) -> ProgramResult { // This now uses solana_program::entrypoint::ProgramResult
    debug_msg!("Executing benchmark function..."); // Example logging

    // TODO: Add logic here to load/deserialize input_data if specified in the config
    // For ping, no input data is needed.

    // Call the benchmarked function (using the alias)
    match benchmark_function_to_call(_program_id, _accounts, _instruction_data) {
        Ok(()) => {
            debug_msg!("Benchmark function executed successfully.");
             Ok(())
        },
        Err(e) => {
            // Assuming the error `e` from the benchmarked function is compatible
            // with the ProgramError defined in solana_program::program_error
            // If the benchmarked function returns solana_program::ProgramResult,
            // its error type (solana_program::program_error::ProgramError) should
            // be compatible with solana_program::program_error::ProgramError.
            Err(e)
        }
    }

    // We might want to serialize/log output here if needed in the future
} 