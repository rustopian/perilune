#![no_std]
#![no_main]

use solana_nostd_entrypoint::{
    entrypoint_nostd, basic_panic_impl, noalloc_allocator, NoStdAccountInfo,
    solana_program::pubkey::Pubkey,
};
use solana_program_error::ProgramResult;

// Import the function to be benchmarked
use %%RUST_IMPORT_CRATE_NAME%%::%%BENCHMARK_FUNCTION_MODULE%%::%%BENCHMARK_FUNCTION_NAME%% as benchmark_function_to_call;

// Solana NoStd Entrypoint setup
entrypoint_nostd!(process_instruction, 64);
noalloc_allocator!();
basic_panic_impl!();

// The entrypoint function required by solana-nostd-entrypoint
#[inline(always)]
pub fn process_instruction(
    _program_id: &Pubkey,
    _accounts: &[NoStdAccountInfo],
    _instruction_data: &[u8],
) -> ProgramResult {
    // Cast the types to match what the benchmark function expects
    // All these types should be repr(C) compatible
    let program_id_cast = unsafe { 
        core::mem::transmute(_program_id) 
    };
    
    let accounts_cast = unsafe {
        core::mem::transmute(_accounts)
    };
    
    benchmark_function_to_call(program_id_cast, accounts_cast, _instruction_data)?;
    Ok(())
} 