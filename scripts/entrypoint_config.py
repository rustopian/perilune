# Configuration data for different Solana entrypoint formats.

# Two-step rewrite approach using solana-program breakout as canonical intermediate
NORMALIZE_TO_BREAKOUT = {
    # Convert FROM any format TO solana-program breakout crates
    
    # From pinocchio
    r"\bpinocchio::account_info::":     "solana_account_info::",
    r"\bpinocchio::pubkey::":           "solana_pubkey::",
    r"\bpinocchio::program_error::":    "solana_program_error::",
    r"\bpinocchio::log::":              "solana_msg::",
    r"\bpinocchio::":                   "solana_entrypoint::",
    
    # From monolithic solana_program - be specific, no catch-all
    r"\bsolana_program::account_info::": "solana_account_info::",
    r"\bsolana_program::pubkey::":       "solana_pubkey::",
    r"\bsolana_program::program_error::": "solana_program_error::",
    r"\bsolana_program::entrypoint::":   "solana_entrypoint::",
    r"\bsolana_program::entrypoint_deprecated::": "solana_entrypoint::",
    r"\bsolana_program::msg::":          "solana_msg::",
    r"\bsolana_program::instruction::":  "solana_instruction::",
    # For program::invoke and system functions, they should go to appropriate crates
    r"\bsolana_program::program::":      "solana_entrypoint::",  # invoke functions
    
    # Handle newer crates that don't exist in breakout world
    r"\bsolana_cpi::":                   "solana_entrypoint::",  # CPI functions -> entrypoint
    r"\bsolana_system_interface::instruction": "solana_system_instruction",  # system instruction functions
    r"\bsolana_system_interface::program": "solana_system_program",  # system program constants
}

DENORMALIZE_FROM_BREAKOUT = {
    # Convert FROM solana-program breakout TO target format
    
    "pinocchio": {
        r"\bsolana_account_info::":      "pinocchio::account_info::",
        r"\bsolana_pubkey::":            "pinocchio::pubkey::",
        r"\bsolana_program_error::":     "pinocchio::program_error::",
        r"\bsolana_entrypoint::":        "pinocchio::",
        r"\bsolana_msg::":               "pinocchio::log::",
        r"\bsolana_instruction::":       "pinocchio::instruction::",
    },
    
    "solana-program": {
        # Target is already breakout format - no transformation needed
    },
    
    "solana-program-mono": {
        r"\bsolana_account_info::":      "solana_program::account_info::",
        r"\bsolana_pubkey::":            "solana_program::pubkey::",
        r"\bsolana_program_error::":     "solana_program::program_error::",
        r"\bsolana_entrypoint::":        "solana_program::entrypoint::",
        r"\bsolana_msg::":               "solana_program::msg::",
        r"\bsolana_instruction::":       "solana_program::instruction::",
    },
    
    "solana-nostd-entrypoint": {
        # For nostd, we keep most breakout crates but change AccountInfo
        r"\bsolana_account_info::AccountInfo": "solana_nostd_entrypoint::NoStdAccountInfo",
        r"\bsolana_entrypoint::ProgramResult": "solana_program_error::ProgramResult",
        # solana_pubkey, solana_program_error, solana_msg stay as-is
    },

    "pinocchio-std": {
        # Same mappings as "pinocchio" but without log path changes; identical rewrite suffices
        r"\bsolana_account_info::":      "pinocchio::account_info::",
        r"\bsolana_pubkey::":            "pinocchio::pubkey::",
        r"\bsolana_program_error::":     "pinocchio::program_error::",
        r"\bsolana_entrypoint::":        "pinocchio::",
        r"\bsolana_msg::":               "pinocchio::log::",
        r"\bsolana_instruction::":       "pinocchio::instruction::",
    },
}

ENTRYPOINT_DEPS = {
    "pinocchio": """pinocchio = { workspace = true, default-features = false }""",

    "solana-program": """solana-account-info = { version = "^2.2", default-features = false }
solana-entrypoint = { package = "solana-program-entrypoint", version = "^2.2", default-features = false }
solana-program-error = { version = "^2.2", default-features = false }
solana-pubkey = { version = "^2.2", default-features = false }
solana-msg = { version = "^2.2", default-features = false }""",

    "solana-program-mono": """solana-program = { version = "^2.2", default-features = false }""",

    "solana-nostd-entrypoint": """solana-nostd-entrypoint = { version = "0.6", default-features = false }
solana-program-error = { version = "^2.2", default-features = false }
solana-pubkey = { version = "^2.2", default-features = false }""",

    "pinocchio-std": """pinocchio = { workspace = true, default-features = false, features = ["std"] }""",
}

BENCHED_CRATE_DEPS = {
    "pinocchio": {
        "pinocchio": {
            "workspace": True,
            "default-features": False
        }
    },
    "solana-program": {
        "solana-account-info": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-entrypoint": {
            "package": "solana-program-entrypoint",
            "version": "^2.2",
            "default-features": False,
        },
        "solana-program-error": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-pubkey": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-msg": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-instruction": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-cpi": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-system-interface": {
            "version": "^1.0",
            "default-features": False,
            "features": ["bincode"],
        },
        "spl-associated-token-account": {
            "git": "https://github.com/solana-program/associated-token-account.git",
            "default-features": False,
            "features": ["no-entrypoint"],
        },
        "spl-token": {
            "version": "^8.0",
            "default-features": False,
            "features": ["no-entrypoint"],
        },
    },
    "solana-program-mono": {
        "solana-program": {
            "version": "^2.2",
            "default-features": False,
        },
        "spl-associated-token-account": {
            "git": "https://github.com/solana-program/associated-token-account.git",
            "default-features": False,
            "features": ["no-entrypoint"],
        },
        "spl-token": {
            "version": "^8.0",
            "default-features": False,
        },
    },
    "solana-nostd-entrypoint": {
        "solana-nostd-entrypoint": {
            "version": "0.6",
            "default-features": False,
        },
        "solana-program-error": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-pubkey": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-msg": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-instruction": {
            "version": "^2.2",
            "default-features": False,
        },
        "solana-cpi": {
            "version": "^2.2",
            "default-features": False,
        },
    },
    "pinocchio-std": {
        "pinocchio": {
            "version": "0.8",
            "git": "https://github.com/rustopian/pinocchio.git",
            "branch": "rustopian/slot-hashes-sysvar",
            "default-features": False,
            "features": ["std"],
        },
        "solana-program": {
            "version": "^2.2",
            "default-features": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Common identifier patterns to reduce duplication
# ---------------------------------------------------------------------------

# Base common identifiers used across multiple entrypoints
_COMMON_IDENTIFIERS = {
    "AccountMeta": "{base}::instruction::AccountMeta",
    "Instruction": "{base}::instruction::Instruction", 
    "Account": "{base}::account_info::AccountInfo",
    "Pubkey": "{base}::pubkey::Pubkey",
    "ProgramError": "{base}::program_error::ProgramError",
}

# SPL token identifiers (same across most entrypoints)
_SPL_IDENTIFIERS = {
    "create_associated_token_account": "spl_associated_token_account::instruction::create_associated_token_account",
    "create_associated_token_account_idempotent": "spl_associated_token_account::instruction::create_associated_token_account_idempotent",
    "recover_nested": "spl_associated_token_account::instruction::recover_nested",
    "get_associated_token_address": "spl_associated_token_account::get_associated_token_address",
    "spl_token_program_id": "spl_token::ID",
}

def _build_identifier_mapping(base_path: str, overrides: dict = None) -> dict:
    """Build identifier mapping for an entrypoint with common patterns."""
    mapping = {}
    
    # Apply common identifiers with base path substitution
    for identifier, pattern in _COMMON_IDENTIFIERS.items():
        mapping[identifier] = pattern.format(base=base_path)
    
    # Add SPL identifiers (same for most entrypoints)
    if base_path in ("solana_program", "solana-program", "solana-program-mono"):
        mapping.update(_SPL_IDENTIFIERS)
    
    # Apply any entrypoint-specific overrides
    if overrides:
        mapping.update(overrides)
    
    return mapping

# ---------------------------------------------------------------------------
# Identifier rewrite mappings used by scripts.rewriter
# ---------------------------------------------------------------------------
IDENTIFIER_MAPPINGS = {
    "pinocchio": _build_identifier_mapping("pinocchio", {
        "ProgramResult": "pinocchio::ProgramResult",
        "AccountInfo": "pinocchio::account_info::AccountInfo", 
        "Account": "pinocchio::instruction::Account",  # Override the common template
        "invoke": "pinocchio::cpi::invoke",
        "invoke_signed": "pinocchio::cpi::invoke_signed",
        "sol_log": "pinocchio::log::sol_log",
        "msg": "pinocchio::msg",
        "CpiAccount": "pinocchio::instruction::Account",
        "no_allocator": "pinocchio::no_allocator",
        "nostd_panic_handler": "pinocchio::nostd_panic_handler",
        "invoke_signed_unchecked": "pinocchio::cpi::invoke_signed",
        "SlotHashes": "pinocchio::sysvars::slot_hashes::SlotHashes",
    }),

    "solana-program": {
        # For solana-program breakout, we need individual crate mappings
        "Pubkey": "solana_pubkey::Pubkey",
        "ProgramError": "solana_program_error::ProgramError",
        "ProgramResult": "solana_entrypoint::ProgramResult",
        "AccountInfo": "solana_account_info::AccountInfo",
        "AccountMeta": "solana_instruction::AccountMeta", 
        "Instruction": "solana_instruction::Instruction",
        "Account": "solana_account_info::AccountInfo",
        "invoke": "solana_cpi::invoke",
        "invoke_signed": "solana_cpi::invoke_signed",
        "sol_log": "solana_msg::sol_log",
        "msg": "solana_msg::msg",
        "next_account_info": "solana_account_info::next_account_info",
        "CpiAccount": "solana_account_info::AccountInfo",
        "instruction": "solana_system_interface::instruction",
        "program": "solana_system_interface::program",
        # SPL ATA functions - map to actual import paths
        "ata_program_id": "spl_associated_token_account::program::id",
        "ata_process_instruction": "spl_associated_token_account::processor::process_instruction",
        **_SPL_IDENTIFIERS,
    },

    "solana-program-mono": _build_identifier_mapping("solana_program", {
        "ProgramResult": "solana_program::entrypoint::ProgramResult",
        "AccountInfo": "solana_program::account_info::AccountInfo",
        "invoke": "solana_program::program::invoke", 
        "invoke_signed": "solana_program::program::invoke_signed",
        "sol_log": "solana_program::log::sol_log",
        "msg": "solana_program::msg",
        "next_account_info": "solana_program::account_info::next_account_info",
        "CpiAccount": "solana_program::account_info::AccountInfo",
        "instruction": "solana_program::system_instruction",
        "program": "solana_program::system_program",
        # SPL ATA functions - map to actual import paths  
        "ata_program_id": "spl_associated_token_account::program::id",
        "ata_process_instruction": "spl_associated_token_account::processor::process_instruction",
        **_SPL_IDENTIFIERS,
    }),

    "solana-nostd-entrypoint": {
        # For solana-nostd-entrypoint, we need individual crate mappings
        "Pubkey": "solana_pubkey::Pubkey",
        "SystemPubkey": "solana_nostd_entrypoint::solana_program::pubkey::Pubkey",
        "ProgramError": "solana_program_error::ProgramError",
        "ProgramResult": "solana_program_error::ProgramResult",
        "AccountInfo": "solana_nostd_entrypoint::NoStdAccountInfo",
        "AccountMeta": "solana_instruction::AccountMeta",
        "Instruction": "solana_instruction::Instruction", 
        "InstructionC": "solana_nostd_entrypoint::InstructionC",
        "syscalls": "solana_cpi::syscalls",
        "invoke": "solana_cpi::invoke",
        "invoke_signed": "solana_cpi::invoke_signed",
        "sol_log": "solana_msg::sol_log",
        "msg": "solana_msg::sol_log",
        "CpiAccount": "solana_nostd_entrypoint::NoStdAccountInfo",
        "Account": "solana_nostd_entrypoint::NoStdAccountInfo",
        "invoke_signed_unchecked": "solana_cpi::invoke_signed",
    },

    "pinocchio-std": {
        "Pubkey": "pinocchio::pubkey::Pubkey",
        "ProgramError": "pinocchio::program_error::ProgramError",
        "ProgramResult": "pinocchio::ProgramResult",
        "AccountInfo": "pinocchio::account_info::AccountInfo",
        "AccountMeta": "pinocchio::instruction::AccountMeta", 
        "Instruction": "pinocchio::instruction::Instruction",
        "Account": "pinocchio::instruction::Account",
        "invoke": "pinocchio::cpi::invoke",
        "invoke_signed": "pinocchio::cpi::invoke_signed",
        "sol_log": "pinocchio::log::sol_log",
        "msg": "pinocchio::msg",
        "next_account_info": "solana_program::account_info::next_account_info",
        "CpiAccount": "pinocchio::instruction::Account",
        "invoke_signed_unchecked": "pinocchio::cpi::invoke_signed",
        "SlotHashes": "pinocchio::sysvars::slot_hashes::SlotHashes",
        # Use solana-program for system instructions since pinocchio doesn't have high-level APIs
        "create_account": "solana_program::system_instruction::create_account",
        "ID": "solana_program::system_program::ID",
        **_SPL_IDENTIFIERS,
    }
} 