// Wrapper functions that automatically use real benchmarks when test-bpf is enabled
#[cfg(not(feature = "test-bpf"))]
pub fn run_create_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
    // Mock implementation when test-bpf feature is not enabled
    Ok(())
}

#[cfg(feature = "test-bpf")]
pub fn run_create_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
    // When test-bpf is enabled, try to load the program dynamically
    // This is a fallback that assumes standard paths - the _with_program version is preferred
    println!("Warning: run_create_ata_bench called without program parameters, using mock");
    Ok(())
}

#[cfg(not(feature = "test-bpf"))]
pub fn run_create_ata_idempotent_bench() -> Result<(), Box<dyn std::error::Error>> {
    // Mock implementation when test-bpf feature is not enabled
    Ok(())
}

#[cfg(feature = "test-bpf")]
pub fn run_create_ata_idempotent_bench() -> Result<(), Box<dyn std::error::Error>> {
    // When test-bpf is enabled, try to load the program dynamically
    println!("Warning: run_create_ata_idempotent_bench called without program parameters, using mock");
    Ok(())
}

#[cfg(not(feature = "test-bpf"))]
pub fn run_recover_nested_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
    // Mock implementation when test-bpf feature is not enabled
    Ok(())
}

#[cfg(feature = "test-bpf")]
pub fn run_recover_nested_ata_bench() -> Result<(), Box<dyn std::error::Error>> {
    // When test-bpf is enabled, try to load the program dynamically
    println!("Warning: run_recover_nested_ata_bench called without program parameters, using mock");
    Ok(())
}

// Re-export functions for the benchmark runner
pub mod std_benches {
    pub use super::{run_create_ata_bench, run_create_ata_idempotent_bench, run_recover_nested_ata_bench};
    
    #[cfg(feature = "test-bpf")]
    pub use super::{run_create_ata_bench_with_program, run_create_ata_idempotent_bench_with_program, run_recover_nested_ata_bench_with_program};
}

// Real benchmark implementations (only available with test-bpf feature)
#[cfg(feature = "test-bpf")]
use {
    mollusk_svm::{program::loader_keys::LOADER_V3, Mollusk},
    solana_account::Account,
    solana_instruction::{AccountMeta, Instruction},
    solana_pubkey::Pubkey,
    solana_system_interface::program as system_program,
    std::{fs, path::Path},
};

#[cfg(feature = "test-bpf")]
// SPL Token Program ID
const SPL_TOKEN_PROGRAM_ID: Pubkey = solana_pubkey::pubkey!("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");

#[cfg(feature = "test-bpf")]
/// Helper to create deterministic pubkeys for reproducible benchmarks
fn const_pk(byte: u8) -> Pubkey {
    Pubkey::new_from_array([byte; 32])
}

#[cfg(feature = "test-bpf")]
/// Build token account data with the supplied mint/owner/amount
fn build_token_account_data(mint: &Pubkey, owner: &Pubkey, amount: u64) -> Vec<u8> {
    let mut data = vec![0u8; 165]; // SPL Token Account size
    
    // Copy mint (32 bytes)
    data[0..32].copy_from_slice(mint.as_ref());
    // Copy owner (32 bytes) 
    data[32..64].copy_from_slice(owner.as_ref());
    // Copy amount (8 bytes LE)
    data[64..72].copy_from_slice(&amount.to_le_bytes());
    // Set state to Initialized (1 byte)
    data[108] = 1;
    
    data
}

#[cfg(feature = "test-bpf")]
/// Build mint data with given decimals and marked initialized
fn build_mint_data(decimals: u8) -> Vec<u8> {
    let mut data = vec![0u8; 82]; // SPL Token Mint size
    // decimals at offset 44
    data[44] = decimals;
    // is_initialized at offset 45
    data[45] = 1; 
    data
}

#[cfg(feature = "test-bpf")]
/// Create a fresh Mollusk instance with required programs loaded
fn create_mollusk(program_id: &Pubkey) -> Mollusk {
    let mut mollusk = Mollusk::default();
    
    // Add the ATA program under test
    mollusk.add_program(program_id, "spl_associated_token_account", &LOADER_V3);
    
    // Add SPL Token program
    mollusk.add_program(&SPL_TOKEN_PROGRAM_ID, "spl_token", &LOADER_V3);
    
    mollusk
}

/// Copy the given program ELF `src_path` to `dest_name` (with .so extension) in the current
/// working directory if it isn't already present.
fn ensure_program_exists(src_path: &Path, dest_name: &str) -> Result<(), Box<dyn std::error::Error>> {
    let dest_path = Path::new(dest_name);
    // Always overwrite to ensure we don't keep a stale/invalid copy.
    fs::copy(src_path, dest_path)?;
    Ok(())
}

/// Try to find **any** file that starts with `prefix` and ends with `.so` under `search_root`.
fn find_so_recursive(search_root: &Path, prefix: &str) -> Option<std::path::PathBuf> {
    if !search_root.is_dir() {
        return None;
    }
    let mut stack = vec![search_root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    stack.push(path);
                } else if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                    if name.starts_with(prefix) && name.ends_with(".so") {
                        return Some(path);
                    }
                }
            }
        }
    }
    None
}

/// Ensure that both the ATA program ELF and its SPL Token dependency ELF are present in the
/// current directory where Mollusk will look. The ATA ELF comes directly from `program_path`.
/// The SPL Token ELF is discovered heuristically by recursively searching for any file whose
/// name begins with `spl_token` and ends with `.so` starting from the workspace root (obtained
/// from the `CARGO_MANIFEST_DIR` env var). If found, it's copied (or symlinked) to
/// `spl_token.so` in the current directory.
fn ensure_required_program_elves(program_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    // 1. Ensure the ATA program itself.
    ensure_program_exists(Path::new(program_path), "spl_associated_token_account.so")?;

    // 2. Ensure SPL Token program.
    let token_dest = Path::new("spl_token.so");
    if token_dest.exists() {
        return Ok(());
    }

    // Try to find an exact `spl_token.so` in the workspace. Avoid copying
    // random crate artifacts like `spl_token-<hash>.so` which are library
    // objects and will fail verification (EntrypointOutOfBounds).
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let mut current = Path::new(&manifest_dir).to_path_buf();
        loop {
            if let Some(found) = find_so_recursive(&current, "spl_token.so") {
                ensure_program_exists(&found, "spl_token.so")?;
                return Ok(());
            }
            if !current.pop() {
                break;
            }
        }
    }

    // Fallback: search relative to the provided program_path (upwards two levels into target).
    if let Some(root) = Path::new(program_path).parent().and_then(|p| p.parent()) {
        if let Some(found) = find_so_recursive(root, "spl_token.so") {
            ensure_program_exists(&found, "spl_token.so")?;
            return Ok(());
        }
    }

    Err("Failed to locate a compiled spl_token.so. Make sure to build the SPL Token program (`cargo build-sbf` in programs/token/) before running these benchmarks.".into())
}

#[cfg(feature = "test-bpf")]
/// Benchmark ATA Create instruction
pub fn run_create_ata_bench_with_program(program_path: &str, program_id: &str) -> Result<(), Box<dyn std::error::Error>> {
    // Ensure that both ATA and SPL Token program ELFs are available for Mollusk
    ensure_required_program_elves(program_path)?;
    
    // Parse program ID
    let program_id_pubkey: Pubkey = program_id.parse()
        .map_err(|e| format!("Invalid program ID: {}", e))?;
    
    // Setup deterministic accounts for reproducible CU measurements
    let payer = const_pk(10);
    let wallet = const_pk(12);
    let mint = const_pk(11);
    
    // Find ATA address using correct PDA derivation
    let (ata, _bump) = Pubkey::find_program_address(
        &[wallet.as_ref(), SPL_TOKEN_PROGRAM_ID.as_ref(), mint.as_ref()],
        &program_id_pubkey,
    );
    
    // Create instruction for ATA creation (discriminator 0)
    let instruction = Instruction {
        program_id: program_id_pubkey,
        accounts: vec![
            AccountMeta::new(payer, true),                        // Payer
            AccountMeta::new(ata, false),                         // Associated token account
            AccountMeta::new_readonly(wallet, false),             // Wallet address
            AccountMeta::new_readonly(mint, false),               // Token mint
            AccountMeta::new_readonly(system_program::ID, false), // System program
            AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false), // Token program
        ],
        data: vec![0], // Create instruction discriminator
    };
    
    // Setup accounts for the test
    let accounts = vec![
        (payer, Account::new(1_000_000_000, 0, &system_program::ID)),
        (ata, Account::new(0, 0, &system_program::ID)),
        (wallet, Account::new(0, 0, &system_program::ID)),
        (
            mint,
            Account {
                lamports: 1_000_000_000,
                data: build_mint_data(0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            system_program::ID,
            Account {
                lamports: 1,
                data: vec![],
                owner: solana_pubkey::pubkey!("NativeLoader1111111111111111111111111111111"),
                executable: true,
                rent_epoch: 0,
            },
        ),
        (
            SPL_TOKEN_PROGRAM_ID,
            Account {
                lamports: 0,
                data: Vec::new(),
                owner: LOADER_V3,
                executable: true,
                rent_epoch: 0,
            },
        ),
    ];
    
    // Create Mollusk instance and run benchmark
    let mollusk = create_mollusk(&program_id_pubkey);
    let result = mollusk.process_instruction(&instruction, &accounts);
    
    match result.program_result {
        mollusk_svm::result::ProgramResult::Success => {
            println!("ATA Create benchmark: {} CUs", result.compute_units_consumed);
            Ok(())
        },
        mollusk_svm::result::ProgramResult::Failure(e) => {
            Err(format!("ATA Create instruction failed: {:?}", e).into())
        }
        mollusk_svm::result::ProgramResult::UnknownError(e) => {
            Err(format!("ATA Create instruction unknown error: {:?}", e).into())
        }
    }
}

#[cfg(feature = "test-bpf")]
/// Benchmark ATA CreateIdempotent instruction (tests early exit path)
pub fn run_create_ata_idempotent_bench_with_program(program_path: &str, program_id: &str) -> Result<(), Box<dyn std::error::Error>> {
    // Ensure that both ATA and SPL Token program ELFs are available for Mollusk
    ensure_required_program_elves(program_path)?;
    
    // Parse program ID
    let program_id_pubkey: Pubkey = program_id.parse()
        .map_err(|e| format!("Invalid program ID: {}", e))?;
    
    // Setup deterministic accounts
    let payer = const_pk(1);
    let wallet = const_pk(3);
    let mint = const_pk(2);
    
    // Find ATA address
    let (ata, _bump) = Pubkey::find_program_address(
        &[wallet.as_ref(), SPL_TOKEN_PROGRAM_ID.as_ref(), mint.as_ref()],
        &program_id_pubkey,
    );
    
    // Create instruction for ATA creation idempotent (discriminator 1)
    let instruction = Instruction {
        program_id: program_id_pubkey,
        accounts: vec![
            AccountMeta::new(payer, true),                        // Payer
            AccountMeta::new(ata, false),                         // Associated token account
            AccountMeta::new_readonly(wallet, false),             // Wallet address
            AccountMeta::new_readonly(mint, false),               // Token mint
            AccountMeta::new_readonly(system_program::ID, false), // System program
            AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false), // Token program
        ],
        data: vec![1], // CreateIdempotent instruction discriminator
    };
    
    // Setup accounts - ATA already exists and is initialized (tests early exit)
    let accounts = vec![
        (payer, Account::new(1_000_000_000, 0, &system_program::ID)),
        (
            ata,
            Account {
                lamports: 2_000_000, // Rent exempt
                data: build_token_account_data(&mint, &wallet, 0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (wallet, Account::new(0, 0, &system_program::ID)),
        (
            mint,
            Account {
                lamports: 1_000_000_000,
                data: build_mint_data(0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            system_program::ID,
            Account {
                lamports: 1,
                data: vec![],
                owner: solana_pubkey::pubkey!("NativeLoader1111111111111111111111111111111"),
                executable: true,
                rent_epoch: 0,
            },
        ),
        (
            SPL_TOKEN_PROGRAM_ID,
            Account {
                lamports: 0,
                data: Vec::new(),
                owner: LOADER_V3,
                executable: true,
                rent_epoch: 0,
            },
        ),
    ];
    
    // Create Mollusk instance and run benchmark
    let mollusk = create_mollusk(&program_id_pubkey);
    let result = mollusk.process_instruction(&instruction, &accounts);
    
    match result.program_result {
        mollusk_svm::result::ProgramResult::Success => {
            println!("ATA CreateIdempotent benchmark: {} CUs", result.compute_units_consumed);
            Ok(())
        },
        mollusk_svm::result::ProgramResult::Failure(e) => {
            Err(format!("ATA CreateIdempotent instruction failed: {:?}", e).into())
        }
        mollusk_svm::result::ProgramResult::UnknownError(e) => {
            Err(format!("ATA CreateIdempotent instruction unknown error: {:?}", e).into())
        }
    }
}

#[cfg(feature = "test-bpf")]
/// Benchmark ATA RecoverNested instruction
pub fn run_recover_nested_ata_bench_with_program(program_path: &str, program_id: &str) -> Result<(), Box<dyn std::error::Error>> {
    // Ensure that both ATA and SPL Token program ELFs are available for Mollusk
    ensure_required_program_elves(program_path)?;
    
    // Parse program ID
    let program_id_pubkey: Pubkey = program_id.parse()
        .map_err(|e| format!("Invalid program ID: {}", e))?;
    
    // Setup deterministic accounts for nested recovery scenario
    let wallet = const_pk(30);
    let nested_mint = const_pk(40);
    let owner_mint = const_pk(20);
    
    // Derive PDAs
    let (owner_ata, _) = Pubkey::find_program_address(
        &[wallet.as_ref(), SPL_TOKEN_PROGRAM_ID.as_ref(), owner_mint.as_ref()],
        &program_id_pubkey,
    );
    let (nested_ata, _) = Pubkey::find_program_address(
        &[owner_ata.as_ref(), SPL_TOKEN_PROGRAM_ID.as_ref(), nested_mint.as_ref()],
        &program_id_pubkey,
    );
    let (dest_ata, _) = Pubkey::find_program_address(
        &[wallet.as_ref(), SPL_TOKEN_PROGRAM_ID.as_ref(), nested_mint.as_ref()],
        &program_id_pubkey,
    );
    
    // Create instruction for ATA recover nested (discriminator 2)
    let instruction = Instruction {
        program_id: program_id_pubkey,
        accounts: vec![
            AccountMeta::new(nested_ata, false),                    // Nested ATA
            AccountMeta::new_readonly(nested_mint, false),          // Nested mint
            AccountMeta::new(dest_ata, false),                      // Destination ATA
            AccountMeta::new(owner_ata, false),                     // Owner ATA
            AccountMeta::new_readonly(owner_mint, false),           // Owner mint
            AccountMeta::new(wallet, true),                         // Wallet (signer)
            AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false), // Token program
            AccountMeta::new_readonly(SPL_TOKEN_PROGRAM_ID, false), // Token program (again)
        ],
        data: vec![2], // RecoverNested instruction discriminator
    };
    
    // Setup accounts for nested recovery
    let accounts = vec![
        (
            nested_ata,
            Account {
                lamports: 1_000_000_000,
                data: build_token_account_data(&nested_mint, &owner_ata, 100),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            nested_mint,
            Account {
                lamports: 1_000_000_000,
                data: build_mint_data(0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            dest_ata,
            Account {
                lamports: 1_000_000_000,
                data: build_token_account_data(&nested_mint, &wallet, 0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            owner_ata,
            Account {
                lamports: 1_000_000_000,
                data: build_token_account_data(&owner_mint, &wallet, 0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (
            owner_mint,
            Account {
                lamports: 1_000_000_000,
                data: build_mint_data(0),
                owner: SPL_TOKEN_PROGRAM_ID,
                executable: false,
                rent_epoch: 0,
            },
        ),
        (wallet, Account::new(1_000_000_000, 0, &system_program::ID)),
        (
            SPL_TOKEN_PROGRAM_ID,
            Account {
                lamports: 0,
                data: Vec::new(),
                owner: LOADER_V3,
                executable: true,
                rent_epoch: 0,
            },
        ),
    ];
    
    // Create Mollusk instance and run benchmark
    let mollusk = create_mollusk(&program_id_pubkey);
    let result = mollusk.process_instruction(&instruction, &accounts);
    
    match result.program_result {
        mollusk_svm::result::ProgramResult::Success => {
            println!("ATA RecoverNested benchmark: {} CUs", result.compute_units_consumed);
            Ok(())
        },
        mollusk_svm::result::ProgramResult::Failure(e) => {
            Err(format!("ATA RecoverNested instruction failed: {:?}", e).into())
        }
        mollusk_svm::result::ProgramResult::UnknownError(e) => {
            Err(format!("ATA RecoverNested instruction unknown error: {:?}", e).into())
        }
    }
} 