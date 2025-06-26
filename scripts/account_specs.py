"""
Account specification configurations for benchmark execution.
"""
from typing import Dict, List

# Account count mappings for different benchmark types
BENCHMARK_ACCOUNT_COUNTS = {
    "create_account": 3,
    "transfer": 3,
    "log": 0,
    "slot_hashes": 1,
    "create_ata": 6,
    "recover_nested_ata": 7,
}

# Account specification templates
ACCOUNT_SPECS = {
    "create_account": [
        "funder:funder_key:true:true:10000000000:0:system",
        "new_account:new_account_key:true:true:0:0:system",
        "system_program:system_key:false:false:0:0:system",
    ],
    "transfer": [
        "source:source_key:true:true:20000000000:0:system",
        "destination:dest_key:false:true:0:0:system",
        "system_program:system_key:false:false:0:0:system",
    ],
    "slot_hashes": [
        "slot_hashes:SysvarS1otHashes111111111111111111111111111:false:false:1:20488:Sysvar1111111111111111111111111111111111111",
    ],
    "create_ata": [
        "funder:funder_key:true:true:10000000000:0:system",
        "ata:ata_key:false:true:0:0:system",
        "wallet:wallet_key:false:false:0:0:system",
        "mint:mint_key:false:false:0:0:system",
        "system_program:system_key:false:false:0:0:system",
        "token_program:TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA:false:false:0:0:self",
    ],
    "recover_nested_ata": [
        "nested_ata:nested_ata_key:false:true:0:0:system",
        "nested_mint:nested_mint_key:false:false:0:0:system",
        "destination_ata:dest_ata_key:false:true:0:0:system",
        "owner_ata:owner_ata_key:false:false:0:0:system",
        "owner_mint:owner_mint_key:false:false:0:0:system",
        "wallet:wallet_key:true:false:5000000000:0:system",
        "token_program:TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA:false:false:0:0:self",
    ],
}

def get_account_count_for_benchmark(bench_id: str) -> int:
    """Get the number of accounts needed for a benchmark."""
    for bench_type, count in BENCHMARK_ACCOUNT_COUNTS.items():
        if bench_type in bench_id:
            return count
    return 1  # Default

def get_account_specs_for_benchmark(bench_id: str) -> List[str]:
    """Get account specifications for a benchmark."""
    for bench_type, specs in ACCOUNT_SPECS.items():
        if bench_type in bench_id:
            # Convert to --account-spec format
            result = []
            for spec in specs:
                result.extend(["--account-spec", spec])
            return result
    return []  # Default: no custom specs

def get_instruction_type(bench_id: str) -> str:
    """Determine the instruction type from benchmark ID."""
    instruction_types = ["create_account", "transfer", "ping", "log"]
    for inst_type in instruction_types:
        if inst_type in bench_id:
            return inst_type
    return bench_id  # Fallback to bench_id itself 