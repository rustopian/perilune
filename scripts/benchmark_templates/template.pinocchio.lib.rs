#![no_std]
#![no_main]

use pinocchio::{
    program_entrypoint,
    ProgramResult,
    account_info::AccountInfo,
    pubkey::Pubkey
};

// Import the function to be benchmarked
use %%RUST_IMPORT_CRATE_NAME%%::%%BENCHMARK_FUNCTION_MODULE%%::%%BENCHMARK_FUNCTION_NAME%% as benchmark_function_to_call;

// Pinocchio entrypoint setup
program_entrypoint!(process_instruction);

// REMOVED: Handlers are now provided by the benchmarked crate via the 'provide-handlers' feature.
// no_allocator!();
// nostd_panic_handler!();

// The entrypoint function required by Pinocchio
#[inline(always)]
pub fn process_instruction(
    _program_id: &Pubkey,
    _accounts: &[AccountInfo],
    _instruction_data: &[u8],
) -> ProgramResult {
    // TODO: Add logic here to load/deserialize input_data if specified in the config
    // For ping, no input data is needed.

    // Call the benchmarked function (using the alias)
    benchmark_function_to_call(_program_id, _accounts, _instruction_data)?;

    Ok(())
    // We might want to serialize/log output here if needed in the future
}

// REMOVED Manual Panic Handler as nostd_panic_handler!() provides it.
// #[panic_handler]
// fn panic(_info: &core::panic::PanicInfo) -> ! {
//     loop {}
// } 