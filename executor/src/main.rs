use clap::Parser;
use mollusk_svm::{program::keyed_account_for_system_program, Mollusk};
use mollusk_svm_bencher::MolluskComputeUnitBencher;
use solana_account::Account;
use solana_instruction::{AccountMeta, Instruction};
use solana_pubkey::Pubkey;
use solana_system_program;
use std::{collections::HashMap, path::PathBuf, str::FromStr};

// SlotHashes sysvar ID for detection - matches exactly what Pinocchio defines
const SLOTHASHES_ID: [u8; 32] = [
    6, 167, 213, 23, 25, 47, 10, 175, 198, 242, 101, 227, 251, 119, 204, 122, 218, 130, 197, 41,
    208, 190, 59, 19, 110, 45, 0, 85, 32, 0, 0, 0,
];

// Sysvar program ID
const SYSVAR_PROGRAM_ID: [u8; 32] = [
    6, 167, 213, 23, 25, 47, 10, 175, 198, 242, 101, 227, 251, 119, 204, 122, 218, 130, 197, 41,
    208, 190, 59, 19, 110, 45, 0, 85, 32, 0, 0, 1,
];

const NUM_BENCH_SLOT_HASH_ENTRIES: usize = 512;
const BENCH_SLOT_HASH_START_SLOT: u64 = 10000;

// Simple deterministic PRNG for varied decrements (copied from mod.rs)
fn simple_prng(seed: u64) -> u64 {
    const A: u64 = 16807; // Multiplier
    const M: u64 = 2147483647; // Modulus (2^31 - 1)
    let initial_state = if seed == 0 { 1 } else { seed };
    (A.wrapping_mul(initial_state)) % M
}

// Generate mock SlotHashes data (copied and simplified from mod.rs)
fn generate_mock_slot_hashes_data() -> Vec<u8> {
    let mut entries = Vec::with_capacity(NUM_BENCH_SLOT_HASH_ENTRIES);
    let mut current_slot = BENCH_SLOT_HASH_START_SLOT;

    for i in 0..NUM_BENCH_SLOT_HASH_ENTRIES {
        let hash_byte = ((i % 256) + 1) as u8; // Add 1 to avoid all-zero hashes
        let hash = [hash_byte; 32];
        entries.push((current_slot, hash));

        let random_val = simple_prng(i as u64);
        let decrement = if random_val % 20 == 0 { 2 } else { 1 }; // Average1_05 strategy

        let next_slot = current_slot.saturating_sub(decrement);
        if next_slot == current_slot {
            break;
        }
        current_slot = next_slot;
    }

    // Serialize to SlotHashes format: u64 len + [(u64 slot, [u8; 32] hash)]
    let num_entries = entries.len() as u64;
    let mut data = Vec::with_capacity(8 + entries.len() * (8 + 32));
    data.extend_from_slice(&num_entries.to_le_bytes());
    for (slot, hash) in &entries {
        data.extend_from_slice(&slot.to_le_bytes());
        data.extend_from_slice(hash);
    }
    data
}

#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    #[clap()]
    program_path: String,
    #[clap()]
    program_id: String,

    // Format for each string:
    // "role_name:key_placeholder:is_signer:is_writable:lamports:data_len:owner_id_or_self_or_system"
    #[clap(long = "account-spec")]
    account_specs: Vec<String>,

    #[clap(long, default_value = "")]
    instruction_data: String,
}

struct ParsedAccountSpec {
    role_name: String,
    key_placeholder: String,
    actual_pubkey: Pubkey,
    is_signer: bool,
    is_writable: bool,
    lamports: u64,
    data_len: usize,
    owner: Pubkey,
}

fn parse_account_spec(
    spec_str: &str,
    program_id: &Pubkey,
    key_map: &mut HashMap<String, Pubkey>,
    key_counter: &mut usize,
) -> Result<ParsedAccountSpec, String> {
    let parts: Vec<&str> = spec_str.split(':').collect();
    if parts.len() != 7 {
        return Err(format!(
            "Invalid account spec format. Expected 7 parts, got {}: {}",
            parts.len(), spec_str
        ));
    }

    let role_name = parts[0].to_string();
    let key_placeholder = parts[1].to_string();
    let is_signer = bool::from_str(parts[2])
        .map_err(|e| format!("Invalid is_signer bool: {} ({})", parts[2], e))?;
    let is_writable = bool::from_str(parts[3])
        .map_err(|e| format!("Invalid is_writable bool: {} ({})", parts[3], e))?;
    let lamports = u64::from_str(parts[4])
        .map_err(|e| format!("Invalid lamports u64: {} ({})", parts[4], e))?;
    let data_len = usize::from_str(parts[5])
        .map_err(|e| format!("Invalid data_len usize: {} ({})", parts[5], e))?;

    let owner_str = parts[6];
    let owner_pk = if owner_str.eq_ignore_ascii_case("self") {
        *program_id
    } else if owner_str.eq_ignore_ascii_case("system") {
        solana_system_program::id()
    } else {
        Pubkey::from_str(owner_str)
            .map_err(|e| format!("Invalid owner pubkey: {owner_str} ({e})"))?
    };

    let generated_pubkey = *key_map.entry(key_placeholder.clone()).or_insert_with(|| {
        let mut base_bytes = program_id.to_bytes();
        base_bytes[0] = base_bytes[0].wrapping_add(*key_counter as u8).wrapping_add(1);
        base_bytes[1] = base_bytes[1].wrapping_add((*key_counter >> 8) as u8);
        *key_counter += 1;
        Pubkey::new_from_array(base_bytes)
    });

    Ok(ParsedAccountSpec {
        role_name,
        key_placeholder,
        actual_pubkey: generated_pubkey,
        is_signer,
        is_writable,
        lamports,
        data_len,
        owner: owner_pk,
    })
}

fn main() {
    let args = Args::parse();

    println!(
        "Executor: SO: \"{}\", ProgramID: {}, AccountSpecs: {:?}, InstrData(hex): {}",
        args.program_path, args.program_id, args.account_specs, args.instruction_data
    );

    let so_path_obj = PathBuf::from(&args.program_path);
    if let Some(parent_dir) = so_path_obj.parent() {
        if let Some(target_dir) = parent_dir.parent() {
            if let Some(program_dir) = target_dir.parent() {
                let sbf_out_dir = program_dir.join("target").join("deploy");
                std::env::set_var("SBF_OUT_DIR", sbf_out_dir.to_str().unwrap_or("."));
                println!("Executor: Set SBF_OUT_DIR to: {}", sbf_out_dir.display());
            }
        }
    }

    let program_id_pubkey = Pubkey::from_str(&args.program_id).expect("Invalid program ID");
    let instruction_data_bytes_original =
        hex::decode(&args.instruction_data).expect("Failed to decode instruction data from hex");

    let program_crate_name = so_path_obj
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown_program")
        .to_string();
    println!("Executor: Using program crate name for Mollusk: {program_crate_name}");

    let mollusk_instance = Mollusk::new(&program_id_pubkey, &program_crate_name);

    let mut accounts_for_bench: Vec<(Pubkey, Account)> = Vec::new();
    let mut account_metas_for_instruction: Vec<AccountMeta> = Vec::new();

    let mut key_map: HashMap<String, Pubkey> = HashMap::new();
    let mut role_name_to_actual_pubkey_map: HashMap<String, Pubkey> = HashMap::new();
    let mut key_counter: usize = 0;

    if !args.account_specs.is_empty() {
        for spec_str in &args.account_specs {
            match parse_account_spec(spec_str, &program_id_pubkey, &mut key_map, &mut key_counter) {
                Ok(mut spec) => {
                    let account_to_add: Account;
                    let final_pubkey: Pubkey = spec.actual_pubkey;
                    let is_executable: bool;

                    if spec.role_name == "system_program" {
                        let (sys_prog_pk, sys_prog_acct) = keyed_account_for_system_program();
                        account_to_add = sys_prog_acct;
                        spec.is_signer = false;
                        spec.is_writable = false;
                        is_executable = account_to_add.executable;
                        role_name_to_actual_pubkey_map.insert(spec.role_name.clone(), sys_prog_pk);
                        println!(
                            "Executor: Using keyed_account_for_system_program() for role '{}'.
                             Key: {}",
                            spec.role_name, sys_prog_pk
                        );
                        account_metas_for_instruction.push(AccountMeta {
                            pubkey: sys_prog_pk,
                            is_signer: spec.is_signer,
                            is_writable: spec.is_writable,
                        });
                        accounts_for_bench.push((sys_prog_pk, account_to_add));

                        println!(
                            "Executor: Setting up account '{}({})': {}, signer: {}, writable: {},
                             lamports: {}, data_len: {}, owner: {}, executable: {}",
                            spec.role_name,
                            spec.key_placeholder,
                            sys_prog_pk,
                            spec.is_signer,
                            spec.is_writable,
                            accounts_for_bench.last().unwrap().1.lamports,
                            accounts_for_bench.last().unwrap().1.data.len(),
                            accounts_for_bench.last().unwrap().1.owner,
                            accounts_for_bench.last().unwrap().1.executable
                        );
                    } else {
                        is_executable = final_pubkey == solana_system_program::id()
                            || spec.role_name == "token_program";

                        let (actual_pubkey, account_data) = if spec.role_name == "slot_hashes" {
                            let slothashes_pubkey = Pubkey::new_from_array(SLOTHASHES_ID);
                            println!(
                                "Executor: Using proper SlotHashes sysvar account key: {}",
                                slothashes_pubkey
                            );
                            println!("Executor: Populating SlotHashes sysvar account with mock data");
                            let mock_data = generate_mock_slot_hashes_data();
                            (slothashes_pubkey, mock_data)
                        } else if final_pubkey.to_bytes() == SLOTHASHES_ID {
                            println!(
                                "Executor: Detected SlotHashes sysvar by key, populating with mock data"
                            );
                            let mock_data = generate_mock_slot_hashes_data();
                            (final_pubkey, mock_data)
                        } else {
                            (final_pubkey, vec![0u8; spec.data_len])
                        };

                        account_to_add = Account {
                            lamports: spec.lamports,
                            data: account_data.clone(),
                            owner: spec.owner,
                            executable: is_executable,
                            rent_epoch: 0,
                        };
                        account_metas_for_instruction.push(AccountMeta {
                            pubkey: actual_pubkey,
                            is_signer: spec.is_signer,
                            is_writable: spec.is_writable,
                        });
                        accounts_for_bench.push((actual_pubkey, account_to_add));
                        role_name_to_actual_pubkey_map
                            .insert(spec.role_name.clone(), actual_pubkey);

                        println!(
                            "Executor: Setting up account '{}({})': {}, signer: {}, writable: {},
                             lamports: {}, data_len: {}, owner: {}, executable: {}",
                            spec.role_name,
                            spec.key_placeholder,
                            actual_pubkey,
                            spec.is_signer,
                            spec.is_writable,
                            spec.lamports,
                            account_data.len(),
                            spec.owner,
                            is_executable
                        );
                    }
                }
                Err(e) => {
                    eprintln!("Error parsing account spec \"{spec_str}\": {e}. Skipping.");
                }
            }
        }
    }
    
    // ------------------------------------------------------------------
    // Build instruction & run benchmark via MolluskComputeUnitBencher
    // ------------------------------------------------------------------
    let instruction = Instruction {
        program_id: program_id_pubkey,
        accounts: account_metas_for_instruction,
        data: instruction_data_bytes_original.clone(),
    };

    let benchmark_id = "perilune_bench".to_string();

    let mut bencher = MolluskComputeUnitBencher::new(mollusk_instance).must_pass(true);
    bencher = bencher.bench((&benchmark_id, &instruction, &accounts_for_bench));
    bencher.execute();
} 