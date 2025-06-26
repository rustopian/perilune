// ATA benchmark test functions - these run against a compiled ATA program using Mollusk SVM
#![allow(unused_imports)]

use std::collections::HashMap;
use mollusk_svm::{Mollusk, result::Check};
use solana_account::{Account, AccountSharedData};
use solana_instruction::{AccountMeta, Instruction};
use solana_pubkey::Pubkey;
use solana_system_interface::program as system_program;

// ATA Program ID
const ATA_PROGRAM_ID: Pubkey = Pubkey::new_from_array([
    140, 151, 37, 143, 78, 36, 137, 241, 187, 61, 16, 41, 20, 142, 13, 131,
    11, 90, 19, 153, 218, 255, 16, 132, 4, 142, 123, 216, 219, 233, 248, 89
]);

// SPL Token Program ID
const SPL_TOKEN_PROGRAM_ID: Pubkey = Pubkey::new_from_array([
    6, 221, 246, 225, 215, 101, 161, 147, 217, 203, 225, 70, 206, 235, 121, 172,
    28, 180, 133, 237, 95, 91, 55, 145, 58, 140, 245, 133, 126, 255, 0, 169,
]);

pub mod std_benches {
    use super::*;

    /// Benchmark Create ATA instruction
    /// Sets up a Mollusk SVM environment and tests ATA account creation
    pub fn run_create_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
        // Create Mollusk SVM instance
        let mut mollusk = Mollusk::new(&ATA_PROGRAM_ID, "spl_associated_token_account");
        
        // Generate test keypairs
        let funding_account = Pubkey::new_unique();
        let wallet_account = Pubkey::new_unique();
        let mint_account = Pubkey::new_unique();
        
        // Derive ATA address
        let (ata_address, _bump) = Pubkey::find_program_address(
            &[
                wallet_account.as_ref(),
                SPL_TOKEN_PROGRAM_ID.as_ref(),
                mint_account.as_ref(),
            ],
            &ATA_PROGRAM_ID,
        );

        // Create Create ATA instruction
        let instruction = Instruction {
            program_id: ATA_PROGRAM_ID,
            accounts: vec![
                AccountMeta::new(funding_account, true),
                AccountMeta::new(ata_address, false),
                AccountMeta::new_readonly(wallet_account, false),
                AccountMeta::new_readonly(mint_account, false),
                AccountMeta::new_readonly(system_program::ID, false),
                AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false),
            ],
            data: vec![], // Empty data = Create instruction
        };

        // Set up accounts
        let mut accounts = HashMap::new();
        
        // Funding account (needs SOL)
        accounts.insert(
            funding_account,
            AccountSharedData::new(1_000_000_000, 0, &system_program::ID),
        );

        // ATA account (uninitialized)
        accounts.insert(
            ata_address,
            AccountSharedData::new(0, 0, &system_program::ID),
        );

        // Wallet account
        accounts.insert(
            wallet_account,
            AccountSharedData::new(0, 0, &system_program::ID),
        );

        // Mock mint account (simplified)
        accounts.insert(
            mint_account,
            AccountSharedData::new(1_000_000, 82, &SPL_TOKEN_PROGRAM_ID),
        );

        // Execute instruction
        let result = mollusk.process_instruction(&instruction, &accounts);
        
        // Verify success
        match result.program_result {
            Ok(()) => Ok(()),
            Err(e) => Err(format!("ATA Create instruction failed: {:?}", e).into()),
        }
    }

    /// Benchmark CreateIdempotent ATA instruction
    pub fn run_create_ata_idempotent_bench() -> Result<(), Box<dyn std::error::Error>> {
        let mut mollusk = Mollusk::new(&ATA_PROGRAM_ID, "spl_associated_token_account");
        
        let funding_account = Pubkey::new_unique();
        let wallet_account = Pubkey::new_unique();
        let mint_account = Pubkey::new_unique();
        
        let (ata_address, _bump) = Pubkey::find_program_address(
            &[
                wallet_account.as_ref(),
                SPL_TOKEN_PROGRAM_ID.as_ref(),
                mint_account.as_ref(),
            ],
            &ATA_PROGRAM_ID,
        );

        let instruction = Instruction {
            program_id: ATA_PROGRAM_ID,
            accounts: vec![
                AccountMeta::new(funding_account, true),
                AccountMeta::new(ata_address, false),
                AccountMeta::new_readonly(wallet_account, false),
                AccountMeta::new_readonly(mint_account, false),
                AccountMeta::new_readonly(system_program::ID, false),
                AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false),
            ],
            data: vec![1], // Data = 1 means CreateIdempotent instruction
        };

        let mut accounts = HashMap::new();
        accounts.insert(
            funding_account,
            AccountSharedData::new(1_000_000_000, 0, &system_program::ID),
        );
        accounts.insert(
            ata_address,
            AccountSharedData::new(0, 0, &system_program::ID),
        );
        accounts.insert(
            wallet_account,
            AccountSharedData::new(0, 0, &system_program::ID),
        );
        accounts.insert(
            mint_account,
            AccountSharedData::new(1_000_000, 82, &SPL_TOKEN_PROGRAM_ID),
        );

        let result = mollusk.process_instruction(&instruction, &accounts);
        
        match result.program_result {
            Ok(()) => Ok(()),
            Err(e) => Err(format!("ATA CreateIdempotent instruction failed: {:?}", e).into()),
        }
    }

    /// Benchmark RecoverNested ATA instruction
    pub fn run_recover_nested_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
        // This is a more complex test that requires setting up nested ATA accounts
        // For now, return a simple success to show the pattern
        println!("RecoverNested benchmark not yet implemented");
        Ok(())
    }
} 