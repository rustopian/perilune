use {
    solana_account_info::AccountInfo,
    solana_entrypoint::ProgramResult,
    solana_program_error::ProgramError,
    solana_pubkey::Pubkey,
};


/// Processes a benchmark instruction to read a specified number of accounts.
///
/// This function is designed to be called from both Solana (solana-program) and Pinocchio (no_std)
/// entrypoint harnesses. It uses feature gating to adapt to the specific types and error
/// handling of each environment.
///
/// # Arguments
/// * `_program_id` - The public key of the currently executing program (often unused in simple benchmarks).
/// * `accounts` - A slice of `AccountInfo` (which resolves based on features).
/// * `instruction_data` - A byte slice where the first byte is expected to be the number
///   of accounts to read.
///
/// # Returns
/// * `ProgramResult` - Ok if successful, or a `ProgramError` variant on failure.
#[cfg(all(feature = "no_std"))]
pub fn process_account_reads(
    _program_id: &pinocchio::pubkey::Pubkey,
    accounts: &[pinocchio::account_info::AccountInfo],
    instruction_data: &[u8],
) -> pinocchio::ProgramResult {
    // msg!("Executing account_read [no_std]..."); // Keep logs minimal for benches

    if instruction_data.is_empty() {
        pinocchio::msg!("Error: no_std - Instruction data is empty.");
        return Err(pinocchio::program_error::ProgramError::InvalidInstructionData);
    }

    let num_accounts_to_read = instruction_data[0] as usize;

    if accounts.len() < num_accounts_to_read {
        pinocchio::msg!("Error: no_std - Not enough accounts provided.");
        return Err(pinocchio::program_error::ProgramError::Custom(1));
    }

    for i in 0..num_accounts_to_read {
        let account = &accounts[i];
        let data_slice = unsafe { account.borrow_data_unchecked() };
        if !data_slice.is_empty() {
            let _first_byte = data_slice[0];
        }
    }
    Ok(())
}

#[cfg(all(feature = "std"))]
pub fn process_account_reads(
    _program_id: &Pubkey,
    accounts: &[AccountInfo],
    instruction_data: &[u8],
) -> ProgramResult {
    // debug_msg!("Executing account_read [std]...");

    if instruction_data.is_empty() {
        // debug_msg!("Error: Instruction data is empty. Expected 1 byte specifying number of accounts to read.");
        return Err(ProgramError::InvalidInstructionData);
    }

    let num_accounts_to_read = instruction_data[0] as usize;

    if accounts.len() < num_accounts_to_read {
        // debug_msg!(
        //     "Error: Not enough accounts provided. Expected at least {}, found {}.",
        //     num_accounts_to_read,
        //     accounts.len()
        // );
        return Err(ProgramError::NotEnoughAccountKeys);
    }

    for i in 0..num_accounts_to_read {
        let account = &accounts[i];
        let account_data = account.try_borrow_data()?;
        if !account_data.is_empty() {
            let _first_byte = account_data[0];
        }
    }
    Ok(())
}
