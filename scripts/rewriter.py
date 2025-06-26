from __future__ import annotations

import pathlib
import re
import toml
from console_utils import print_success, print_warning
from entrypoint_config import NORMALIZE_TO_BREAKOUT, DENORMALIZE_FROM_BREAKOUT, BENCHED_CRATE_DEPS, IDENTIFIER_MAPPINGS
from typing import List
from abc import ABC, abstractmethod
from import_processor import strip_imports_and_generate_clean_imports

__all__ = [
    "rewrite_sources_for_entrypoint",
]


# Common regex patterns used throughout the rewriter
COMMON_PATTERNS = {
    # Allocator and panic handler patterns
    'NO_ALLOCATOR_CALL': re.compile(r"^\s*no_allocator!\(\);\s*\n?", re.MULTILINE),
    'NOSTD_PANIC_CALL': re.compile(r"^\s*nostd_panic_handler!\(\);\s*\n?", re.MULTILINE),
    'NO_ALLOCATOR_IMPORT': re.compile(r"^\s*use\s+[^;]*\bno_allocator\b[^;]*;\s*\n?", re.MULTILINE),
    'NOSTD_PANIC_IMPORT': re.compile(r"^\s*use\s+[^;]*\bnostd_panic_handler\b[^;]*;\s*\n?", re.MULTILINE),
    
    # AccountMeta patterns
    'ACCOUNT_META_WRITABLE_SIGNER': re.compile(r"AccountMeta::writable_signer\(\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\s*\)"),
    'ACCOUNT_META_NEW': re.compile(r"AccountMeta::new\(\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\s*,\s*true\s*\)"),
    
    # Key handling patterns
    'KEY_DEREFERENCE': re.compile(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\b"),
    'KEY_INTO_CONVERSION': re.compile(r"\(\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\)\.into\(\)"),
    'KEY_DEREF_WITH_CALL': re.compile(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)"),
    
    # CPI patterns
    'CPI_ACCOUNT_FROM': re.compile(r"CpiAccount::from\(\s*&?(\w+)\s*\)"),
    
    # Module patterns
    'PUB_MOD_BENCHES': re.compile(r"pub mod (\w+_benches)\s*{", re.MULTILINE),
    'PUB_MOD_START': re.compile(r"^pub\s+mod\s+\w+\s*{\s*$"),
    'CLOSING_BRACE': re.compile(r"^\s*}\s*$"),
    
    # System instruction patterns
    'INSTRUCTION_CREATE_ACCOUNT': re.compile(r'\binstruction::create_account\b'),
    'INSTRUCTION_TRANSFER': re.compile(r'\binstruction::transfer\b'),
    'PROGRAM_ID': re.compile(r'\bprogram::ID\b'),
    
    # Pinocchio patterns
    'PINOCCHIO_MSG': re.compile(r'\bpinocchio::msg!'),
    'PINOCCHIO_SOL_LOG': re.compile(r'\bpinocchio::log::sol_log\b'),
    'PINOCCHIO_PUBKEY': re.compile(r'\bpinocchio::pubkey::Pubkey\b'),
    'PINOCCHIO_ACCOUNT_INFO': re.compile(r'\bpinocchio::account_info::AccountInfo\b'),
    'PINOCCHIO_PROGRAM_ERROR': re.compile(r'\bpinocchio::program_error::ProgramError\b'),
    'PINOCCHIO_PROGRAM_RESULT': re.compile(r'\bpinocchio::ProgramResult\b'),
}

# Replacement strings for common patterns
REPLACEMENTS = {
    'solana-program': {
        'instruction_create_account': 'solana_system_interface::instruction::create_account',
        'instruction_transfer': 'solana_system_interface::instruction::transfer',  
        'program_id': 'solana_system_interface::program::ID',
        'account_meta_new': r"AccountMeta::new((*\1.key()).into(), true)",
    },
    'solana-program-mono': {
        'instruction_create_account': 'solana_program::system_instruction::create_account',
        'instruction_transfer': 'solana_program::system_instruction::transfer',
        'program_id': 'solana_program::system_program::ID',  
        'account_meta_new': r"AccountMeta::new((*\1.key()).into(), true)",
    },
    'pinocchio': {
        'instruction_create_account': 'pinocchio::sysvars::system_instruction::create_account',
        'program_id': 'pinocchio::sysvars::SYSTEM_PROGRAM_ID',
        'cpi_account_replacement': r"\1.into()",
    },
    'solana-nostd-entrypoint': {
        'instruction_create_account': 'create_account_instruction',
        'program_id': 'system_program_id',
        'account_meta_new': r"AccountMeta::new(Pubkey::new_from_array(\1.key().to_bytes()), true)",
        'key_to_pubkey': r"Pubkey::new_from_array(\1.key().to_bytes())",
    },
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_pinocchio_handlers(crate_root: pathlib.Path):
    """Make sure the copied benched crate is *no_std* and wired up for Pinocchio."""
    lib_rs = crate_root / "src" / "lib.rs"
    if not lib_rs.is_file():
        return

    try:
        content = lib_rs.read_text("utf-8")
        needs_write = False

        # 1. Guarantee #![no_std]
        if "#![no_std]" not in content:
            content = "#![no_std]\n" + content
            needs_write = True

        # 2. Ensure macro invocations exist (using fully-qualified path so no `use` needed)
        lines = content.splitlines()
        has_no_allocator = any("no_allocator!();" in line for line in lines)
        has_panic_handler = any("nostd_panic_handler!();" in line for line in lines)
        
        macros_to_insert: List[str] = []
        if not has_no_allocator:
            macros_to_insert.append("pinocchio::no_allocator!();")
        if not has_panic_handler:
            macros_to_insert.append("pinocchio::nostd_panic_handler!();")

        if macros_to_insert:
            # Determine insertion index: first non-attribute line (items start) but **after** last inner attribute
            insert_index = 0
            for idx, ln in enumerate(lines):
                if ln.lstrip().startswith('#!['):
                    insert_index = idx + 1
                else:
                    break
            # Insert macros in original order
            for m in reversed(macros_to_insert):
                lines.insert(insert_index, m)
            content = "\n".join(lines)
            needs_write = True

        if needs_write or macros_to_insert:
            lib_rs.write_text(content, encoding="utf-8")
            print_success("Updated src/lib.rs for pinocchio handlers and no_std")
    except Exception as exc:
        print_warning(f"Failed to patch {lib_rs}: {exc}")


def _ensure_nostd_entrypoint_alias(crate_root: pathlib.Path):
    lib_rs = crate_root / "src" / "lib.rs"
    if not lib_rs.is_file():
        return
    try:
        content = lib_rs.read_text("utf-8")
        
        # Only add alias to NoStdAccountInfo that doesn't already have an alias
        # Pattern: NoStdAccountInfo (but not NoStdAccountInfo as something)
        if "NoStdAccountInfo as AccountInfo" not in content:
            # Use a more precise regex that only matches in import statements
            content = re.sub(
                r'(use\s+[^;]*\b)NoStdAccountInfo(?!\s+as\s+\w+)',  # NoStdAccountInfo in use statements only
                r'\1NoStdAccountInfo as AccountInfo',
                content
            )
            lib_rs.write_text(content, encoding="utf-8")
            print_success("Added alias `as AccountInfo` for NoStdAccountInfo")
    except Exception as exc:
        print_warning(f"Failed to patch alias in {lib_rs}: {exc}")


def _ensure_manifest_deps_for_entrypoint(entrypoint_name: str, crate_root: pathlib.Path):
    deps_to_add = BENCHED_CRATE_DEPS.get(entrypoint_name)
    if not deps_to_add:
        return

    manifest_path = crate_root / "Cargo.toml"
    if not manifest_path.is_file():
        return

    try:
        manifest_data = toml.load(manifest_path)
    except Exception as exc:
        print_warning(f"Failed to parse manifest {manifest_path}: {exc}")
        return

    deps_table = manifest_data.setdefault("dependencies", {})
    changed = False

    ALL_KNOWN_SDK_DEPS = [
        "pinocchio",
        "solana-program",
        "solana-account-info",
        "solana-entrypoint",
        "solana-program-error",
        "solana-pubkey",
        "solana-msg",
        "solana-nostd-entrypoint",
    ]

    for key in list(deps_table.keys()):
        if key in ALL_KNOWN_SDK_DEPS:
            deps_table.pop(key)
            changed = True

    for dep_name, dep_info in deps_to_add.items():
        if dep_name not in deps_table:
            deps_table[dep_name] = dep_info
            changed = True

    if changed:
        try:
            manifest_path.write_text(toml.dumps(manifest_data), encoding="utf-8")
            print_success(
                f"Patched dependencies in benched crate manifest for {entrypoint_name}"
            )
        except Exception as exc:
            print_warning(f"Failed to update manifest {manifest_path}: {exc}")


# Import processing functions moved to import_processor.py


def _replace_qualified_usage_patterns(content: str, entrypoint_name: str) -> str:
    """Replace qualified usage patterns like instruction::create_account and program::ID in the code."""
    import re
    
    if entrypoint_name in ("pinocchio", "pinocchio-std"):
        # For pinocchio, replace qualified usage patterns
        content = re.sub(r'\binstruction::create_account\b', 'pinocchio::sysvars::system_instruction::create_account', content)
        content = re.sub(r'\bprogram::ID\b', 'pinocchio::sysvars::SYSTEM_PROGRAM_ID', content)
        
        # Fix remaining pinocchio qualified patterns that weren't handled in import stripping
        # Split content into lines and only apply replacements to non-import lines
        lines = content.splitlines()
        modified_lines = []
        
        for line in lines:
            if line.strip().startswith('use '):
                # Don't modify import lines
                modified_lines.append(line)
            else:
                # Apply replacements to non-import lines
                line = re.sub(r'\bpinocchio::msg!', 'msg!', line)
                line = re.sub(r'\bpinocchio::log::sol_log\b', 'sol_log', line)
                line = re.sub(r'\bpinocchio::pubkey::Pubkey\b', 'Pubkey', line)
                line = re.sub(r'\bpinocchio::account_info::AccountInfo\b', 'AccountInfo', line)
                line = re.sub(r'\bpinocchio::program_error::ProgramError\b', 'ProgramError', line)
                line = re.sub(r'\bpinocchio::ProgramResult\b', 'ProgramResult', line)
                modified_lines.append(line)
        
        content = '\n'.join(modified_lines)
    
    elif entrypoint_name == "solana-program":
        # Replace instruction::create_account with full path
        content = re.sub(r'\binstruction::create_account\b', 'solana_system_interface::instruction::create_account', content)
        # Replace instruction::transfer with full path
        content = re.sub(r'\binstruction::transfer\b', 'solana_system_interface::instruction::transfer', content)
        # Replace program::ID with full path
        content = re.sub(r'\bprogram::ID\b', 'solana_system_interface::program::ID', content)
    
    elif entrypoint_name == "solana-program-mono":
        # Replace instruction::create_account with full path
        content = re.sub(r'\binstruction::create_account\b', 'solana_program::system_instruction::create_account', content)
        # Replace instruction::transfer with full path
        content = re.sub(r'\binstruction::transfer\b', 'solana_program::system_instruction::transfer', content)
        # Replace program::ID with full path
        content = re.sub(r'\bprogram::ID\b', 'solana_program::system_program::ID', content)
    
    elif entrypoint_name == "solana-nostd-entrypoint":
        # For nostd, avoid system functions that require unavailable crates
        # Replace with basic invoke pattern since we can't use system_instruction 
        content = re.sub(r'\binstruction::create_account\b', 'create_account_instruction', content)
        # Use a hardcoded system program ID since solana_program isn't available
        content = re.sub(r'\bprogram::ID\b', 'system_program_id', content)
    
    return content


# Function moved to import_processor.py


def _replace_imports_with_target_imports(content: str, entrypoint_name: str) -> str:
    """DEPRECATED: Use strip_imports_and_generate_clean_imports instead."""
    return strip_imports_and_generate_clean_imports(content, entrypoint_name)


def _transform_grouped_solana_program_imports(content: str) -> str:
    """DEPRECATED: Use _replace_solana_imports_with_clean_imports instead."""
    return content


def _apply_import_rewrite_patterns(content: str, patterns: dict) -> str:
    """Apply a set of regex patterns to rewrite imports in content."""
    modified_content = content
    for pattern, replacement in patterns.items():
        modified_content = re.sub(pattern, replacement, modified_content)
    return modified_content


def _should_skip_normalization_for_mono(content: str) -> bool:
    """Check if we should skip normalization for solana-program-mono target.
    
    Skip if the source already uses correct solana_program grouped imports
    to avoid breaking them.
    """
    return ("use solana_program::{" in content and 
            any(pattern in content for pattern in ["pubkey::", "account_info::", "entrypoint::"]))


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_DOUBLE_PREFIX_RE = re.compile(
    r"\b(\w+)::(solana_(?:pubkey|account_info))::"
)


def _collapse_double_prefixes(content: str) -> str:
    """Turn `foo::solana_pubkey::` -> `solana_pubkey::`."""
    return _DOUBLE_PREFIX_RE.sub(r"\2::", content)


# ---------------------------------------------------------------------------
# Generic post-processing helpers (entrypoint-agnostic)
# ---------------------------------------------------------------------------

def _strip_duplicate_bench_modules(src: str) -> str:
    """Remove duplicate *_benches modules that can appear after cfg stripping."""
    import re
    pattern = re.compile(r"pub mod (\w+_benches)\s*{", re.MULTILINE)
    matches = list(pattern.finditer(src))
    if not matches:
        return src

    to_remove: list[tuple[int, int]] = []
    seen: set[str] = set()
    for m in matches:
        name = m.group(1)
        if name in seen:
            # Check if the duplicate has a cfg attribute directly above it; if so, keep both copies.
            # We look back a few lines to see if there's a cfg attribute.
            line_start = src.rfind('\n', 0, m.start()) + 1
            prev_segment = src[max(0, line_start - 120): line_start]  # up to ~4 lines back
            if re.search(r"#\s*\[\s*cfg", prev_segment):
                # Distinct feature-gated copy; keep it.
                continue

            # Otherwise treat as redundant and remove
            brace_lvl = 1
            idx = m.end()
            while idx < len(src):
                if src[idx] == '{':
                    brace_lvl += 1
                elif src[idx] == '}':
                    brace_lvl -= 1
                    if brace_lvl == 0:
                        idx += 1  # include closing brace
                        break
                idx += 1
            to_remove.append((m.start(), idx))
        else:
            seen.add(name)
    # remove from back to front so indices stay valid
    for start, end in sorted(to_remove, key=lambda t: -t[0]):
        src = src[:start] + src[end:]
    return src


def _deduplicate_use_lines(content: str) -> str:
    """Remove duplicate `use XXX;` lines that cause E0252 re-imports."""
    seen: set[str] = set()
    out_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("use ") and stripped.endswith(";"):
            if stripped in seen:
                continue
            seen.add(stripped)
        out_lines.append(line)
    return "\n".join(out_lines)


def _ensure_use_super_in_modules(content: str) -> str:
    """Insert `use super::*;` at the start of every module block if absent.

    This allows inner modules to see top-level imports/consts without knowing
    their names. We detect a line that opens a `pub mod … {` (any visibility)
    and inject one indent level deeper.
    """
    lines = content.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        stripped = line.lstrip()
        if stripped.startswith("pub mod ") and stripped.rstrip().endswith("{"):
            # determine indent (spaces/tabs before 'pub')
            indent = line[: len(line) - len(stripped)] + "    "
            # look ahead for first non-blank line inside module
            j = i + 1
            has_super = False
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and "use super::*;" in lines[j]:
                has_super = True
            if not has_super:
                out.append(f"{indent}use super::*;")
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Bracing helpers
# ---------------------------------------------------------------------------

def _close_unclosed_top_modules(content: str) -> str:
    """Ensure each top-level `pub mod XYZ {{` declaration has a matching closing brace.

    We only track braces that appear at column 0 (i.e. no leading whitespace)
    so that braces within function bodies, impl blocks, etc. do **not** affect
    our module-level balance accounting.
    """

    out_lines: list[str] = []
    depth = 0  # number of currently open top-level modules

    mod_start_re = re.compile(r"^pub\s+mod\s+\w+\s*{\s*$")
    closing_brace_re = re.compile(r"^\s*}\s*$")

    for line in content.splitlines():
        stripped = line.lstrip()

        # If a new module starts while one is already open, close the previous
        # one first.
        if mod_start_re.match(stripped) and depth == 1:
            out_lines.append("}")
            depth -= 1

        out_lines.append(line)

        # Update depth counters *after* writing the current line so that the
        # opening brace we just saw isn't immediately cancelled out.
        if mod_start_re.match(stripped):
            depth += 1
        elif closing_brace_re.match(stripped) and depth > 0:
            depth -= 1

    # Close any unbalanced modules at EOF.
    while depth > 0:
        out_lines.append("}")
        depth -= 1

    return "\n".join(out_lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rewrite_sources_for_entrypoint(entrypoint_name: str, crate_root: pathlib.Path):
    """Rewrite imported paths in the copied benched crate by detecting all Solana types
    and mapping them to the appropriate target entrypoint format.
    """
    print_success(f"Rewriting source imports for entrypoint: {entrypoint_name}")
    files_modified = 0
    
    processor = ContentProcessor(entrypoint_name)

    for rust_file in crate_root.rglob("*.rs"):
        try:
            original_content = rust_file.read_text("utf-8")
            modified_content = processor.process_file_content(original_content)

            if modified_content != original_content:
                rust_file.write_text(modified_content, "utf-8")
                files_modified += 1
                print_success(f"  Modified: {rust_file.relative_to(crate_root)}")
        except Exception as exc:
            print_warning(f"Failed to rewrite {rust_file}: {exc}")

    if files_modified == 0:
        print_warning(
            f"No source files needed import rewriting for '{entrypoint_name}' entrypoint."
        )

    # Post-processing tweaks
    if entrypoint_name == "pinocchio":
        _ensure_pinocchio_handlers(crate_root)
        # Inject a dummy no_std feature so cfg(feature="no_std") sections compile
        manifest_path = crate_root / "Cargo.toml"
        try:
            manifest_data = toml.load(manifest_path)
            feats = manifest_data.setdefault("features", {})
            if "no_std" not in feats:
                feats["no_std"] = []
                manifest_path.write_text(toml.dumps(manifest_data), "utf-8")
        except Exception:
            pass
    elif entrypoint_name == "solana-nostd-entrypoint":
        _ensure_nostd_entrypoint_alias(crate_root)

    _ensure_manifest_deps_for_entrypoint(entrypoint_name, crate_root)

class EntrypointRewriter(ABC):
    """Base class for entrypoint-specific rewriting strategies."""
    
    def __init__(self, entrypoint_name: str):
        self.entrypoint_name = entrypoint_name
    
    @abstractmethod
    def should_skip_normalization(self, content: str) -> bool:
        """Check if normalization should be skipped for this entrypoint."""
        return False
    
    @abstractmethod
    def apply_specific_fixes(self, content: str) -> str:
        """Apply entrypoint-specific fixes to the content."""
        return content
    
    def get_preferred_module_name(self) -> str:
        """Get the preferred module name for this entrypoint."""
        if self.entrypoint_name in ("pinocchio", "solana-nostd-entrypoint"):
            return "nostd_benches"
        return "std_benches"
    
    def get_benches_alias(self) -> str:
        """Get the benchmark module alias for this entrypoint."""
        alias_map = {
            "pinocchio": "pinocchio_benches",
            "pinocchio-std": "pinocchio_std_benches", 
            "solana-program": "solana_benches",
            "solana-program-mono": "solana_program_mono_benches",
            "solana-nostd-entrypoint": "nostd_entrypoint_benches",
        }
        return alias_map.get(self.entrypoint_name, "solana_benches")

class PinocchioRewriter(EntrypointRewriter):
    def should_skip_normalization(self, content: str) -> bool:
        return False
    
    def apply_specific_fixes(self, content: str) -> str:
        # Remove macro calls and imports for non-lib.rs files
        lines = content.splitlines()
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if (stripped == "no_allocator!();" or 
                stripped == "nostd_panic_handler!();" or
                stripped == "use pinocchio::{no_allocator, nostd_panic_handler};"):
                continue
            filtered_lines.append(line)
        content = '\n'.join(filtered_lines)
        
        # Fix pinocchio-specific issues
        # Replace PINOCCHIO_SYSTEM_PROGRAM_ID with the actual system program ID
        system_program_id = "Pubkey::from([0u8; 32])"  # System program ID is all zeros
        content = content.replace("PINOCCHIO_SYSTEM_PROGRAM_ID", system_program_id)
        
        # For pinocchio, CPI calls use AccountInfo references directly, not Account type
        # Replace the entire CPI pattern with the correct pinocchio pattern
        content = re.sub(
            r"let\s+(\w+)\s*=\s*CpiAccount::from\(\s*(\w+)\s*\);\s*\n\s*let\s+(\w+)\s*=\s*CpiAccount::from\(\s*(\w+)\s*\);\s*\n\s*let\s+accounts_for_invoke:\s*\[CpiAccount;\s*2\]\s*=\s*\[\s*\1,\s*\3\s*\];",
            r"let accounts_for_invoke: [&AccountInfo; 2] = [\2, \4];",
            content,
            flags=re.MULTILINE
        )
        # Clean up any remaining CpiAccount references
        content = re.sub(r"CpiAccount", "AccountInfo", content)
        
        # Replace unsafe invoke_signed_unchecked with regular invoke_signed
        # Use more specific pattern to avoid accidentally removing other closing braces
        content = re.sub(r"unsafe\s*\{\s*invoke_signed_unchecked\(([^}]+)\);\s*\}", r"invoke_signed(\1);", content)
        
        return content

class SolanaNoStdRewriter(EntrypointRewriter):
    def should_skip_normalization(self, content: str) -> bool:
        return False
    
    def apply_specific_fixes(self, content: str) -> str:
        # Fix nostd-specific issues
        content = re.sub(r"&?\s*PINOCCHIO_SYSTEM_PROGRAM_ID", "Pubkey::default()", content)
        content = content.replace("invoke_signed_unchecked", "invoke_signed")
        
        # Fix undefined references in std section
        content = content.replace("next_account_info", "solana_account_info::next_account_info")
        content = content.replace("system_program_id", "solana_program::system_program::ID")
        content = content.replace("create_account_instruction", "solana_program::system_instruction::create_account")
        
        # Normalize key usage patterns
        content = re.sub(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\b", r"*\1.key()", content)
        content = re.sub(
            r"\(\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\)\.into\(\)",
            r"Pubkey::new_from_array(\1.key().to_bytes())",
            content,
        )
        content = re.sub(
            r"\*\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)",
            r"Pubkey::new_from_array(\1.key().to_bytes())",
            content,
        )
        
        # Update AccountMeta helpers
        content = re.sub(
            r"AccountMeta::writable_signer\(\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\s*\)",
            r"AccountMeta::new(Pubkey::new_from_array(\1.key().to_bytes()), true)",
            content,
        )
        
        # Fix Instruction constructor - nostd needs Vec, not array references
        content = re.sub(
            r"accounts: &account_metas,",
            r"accounts: account_metas.to_vec(),",
            content
        )
        content = re.sub(
            r"data: &system_instruction_data,",
            r"data: system_instruction_data.to_vec(),",
            content
        )
        
        # Remove CpiAccount usage and unsafe blocks
        content = re.sub(r"CpiAccount", "NoStdAccountInfo", content)
        # Use specific pattern for unsafe invoke_signed blocks only
        content = re.sub(r"unsafe\s*\{\s*invoke_signed\(([^}]+)\);\s*\}", r"invoke_signed(\1);", content)
        
        # Fix invoke_signed call for nostd - use AccountInfo slice
        content = re.sub(
            r"let\s+(\w+)\s*=\s*NoStdAccountInfo::from\(\s*(\w+)\s*\);\s*\n\s*let\s+(\w+)\s*=\s*NoStdAccountInfo::from\(\s*(\w+)\s*\);\s*\n\s*let\s+accounts_for_invoke:\s*\[NoStdAccountInfo;\s*2\]\s*=\s*\[\s*\1,\s*\3\s*\];",
            r"let accounts_for_invoke = [*\2, *\4];",
            content,
            flags=re.MULTILINE
        )
        
        # Fix invoke_signed call to use slice  
        content = re.sub(
            r"invoke_signed\(&ix, &accounts_for_invoke, &\[\]\)",
            r"invoke_signed(&ix, &accounts_for_invoke, &[])",
            content
        )
        
        return content

class SolanaProgramRewriter(EntrypointRewriter):
    def should_skip_normalization(self, content: str) -> bool:
        return False
    
    def apply_specific_fixes(self, content: str) -> str:
        # Fix AccountMeta for solana entrypoints
        content = re.sub(r"AccountMeta::writable_signer\(\s*([A-Za-z_][A-Za-z0-9_]*)\.key\(\)\s*\)", 
                        r"AccountMeta::new((*\1.key()).into(), true)", content)
        
        # Strip Pinocchio-only allocator / panic macros
        content = re.sub(r"^\s*no_allocator!\(\);\s*\n?", "", content, flags=re.MULTILINE)
        content = re.sub(r"^\s*nostd_panic_handler!\(\);\s*\n?", "", content, flags=re.MULTILINE)
        content = re.sub(r"^\s*use\s+[^;]*\bno_allocator\b[^;]*;\s*\n?", "", content, flags=re.MULTILINE)
        content = re.sub(r"^\s*use\s+[^;]*\bnostd_panic_handler\b[^;]*;\s*\n?", "", content, flags=re.MULTILINE)
        return content

class SolanaProgramMonoRewriter(SolanaProgramRewriter):
    def should_skip_normalization(self, content: str) -> bool:
        # Don't skip normalization for mono - always apply full rewrite
        return False
    
    def apply_specific_fixes(self, content: str) -> str:
        content = super().apply_specific_fixes(content)
        # Always apply mono-specific fixes
        content = self._apply_mono_manual_fixes(content)
        return content
    
    def _apply_mono_manual_fixes(self, content: str) -> str:
        # For mono, apply minimal fixes within the std module only
        # Replace system interface calls with proper solana_program equivalents
        content = re.sub(r"instruction::create_account", "solana_program::system_instruction::create_account", content)
        content = re.sub(r"program::ID", "solana_program::system_program::ID", content)
        
        # Remove pinocchio-specific references in no_std section
        content = content.replace("PINOCCHIO_SYSTEM_PROGRAM_ID", "solana_program::system_program::ID")
        content = content.replace("invoke_signed_unchecked", "solana_program::program::invoke_signed")
        
        # Remove unsafe blocks - use more specific pattern
        content = re.sub(r"unsafe\s*\{\s*invoke_signed\(([^}]+)\);\s*\}", r"invoke_signed(\1);", content)
        
        return content

def _get_entrypoint_rewriter(entrypoint_name: str) -> EntrypointRewriter:
    """Factory function to get the appropriate rewriter for an entrypoint."""
    rewriters = {
        "pinocchio": PinocchioRewriter,
        "pinocchio-std": SolanaProgramRewriter,  # Similar to solana-program
        "solana-program": SolanaProgramRewriter,
        "solana-program-mono": SolanaProgramMonoRewriter,
        "solana-nostd-entrypoint": SolanaNoStdRewriter,
    }
    rewriter_class = rewriters.get(entrypoint_name, SolanaProgramRewriter)
    return rewriter_class(entrypoint_name) 

class ContentProcessor:
    """Handles the common content processing pipeline for all entrypoints."""
    
    def __init__(self, entrypoint_name: str):
        self.entrypoint_name = entrypoint_name
        self.rewriter = _get_entrypoint_rewriter(entrypoint_name)
    
    def process_file_content(self, content: str) -> str:
        """Main processing pipeline for file content."""
        # Step 1: Check if normalization should be skipped
        if self.rewriter.should_skip_normalization(content):
            content = self._handle_skip_normalization(content)
        else:
            # Step 2: Replace imports with clean, target-specific imports
            content = strip_imports_and_generate_clean_imports(content, self.entrypoint_name)
        
        # Step 3: Apply common post-processing
        content = self._apply_common_postprocessing(content)
        
        # Step 4: Apply entrypoint-specific fixes
        content = self.rewriter.apply_specific_fixes(content)
        
        # Step 5: Apply benchmark module alias
        content = self._add_benchmark_alias(content)
        
        # Step 6: Apply qualified usage pattern replacements
        content = _replace_qualified_usage_patterns(content, self.entrypoint_name)
        
        # Step 7: Final cleanup
        content = self._apply_final_cleanup(content)
        
        return content
    
    def _handle_skip_normalization(self, content: str) -> str:
        """Handle content when normalization is skipped (mono-specific logic)."""
        if self.entrypoint_name != "solana-program-mono":
            return content
            
        # Apply patterns only within module blocks for mono target
        lines = content.split('\n')
        in_std_module = False
        brace_count = 0
        
        for i, line in enumerate(lines):
            if '#[cfg(all(feature = "std"))]' in line:
                in_std_module = True
            elif in_std_module and 'pub mod ' in line and ' {' in line:
                brace_count = 1
            elif in_std_module and brace_count > 0:
                brace_count += line.count('{') - line.count('}')
                lines[i] = self._apply_mono_transformations(line)
                if brace_count == 0:
                    in_std_module = False
        
        content = '\n'.join(lines)
        
        # Remove no_std-gated modules
        content = re.sub(
            r"#\[cfg\(all\(feature = \"no_std\"\)\)\]\s*pub mod \w+_benches\s*\{[^}]*\}\s*",
            "",
            content,
            flags=re.MULTILINE | re.DOTALL,
        )
        return content
    
    def _apply_mono_transformations(self, line: str) -> str:
        """Apply mono-specific transformations to a line."""
        transformations = [
            ('solana_account_info::', 'solana_program::account_info::'),
            ('solana_program_error::ProgramResult', 'solana_program::entrypoint::ProgramResult'),
            ('solana_program_error::', 'solana_program::program_error::'),
            ('solana_cpi::invoke', 'solana_program::program::invoke'),
            ('solana_pubkey::', 'solana_program::pubkey::'),
        ]
        
        for old, new in transformations:
            line = line.replace(old, new)
        return line
    
    def _apply_common_postprocessing(self, content: str) -> str:
        """Apply common post-processing steps."""
        content = _strip_duplicate_bench_modules(content)
        content = _ensure_use_super_in_modules(content)
        return content
    
    def _add_benchmark_alias(self, content: str) -> str:
        """Add benchmark module alias if not present."""
        benches_alias = self.rewriter.get_benches_alias()
        
        if benches_alias not in content:
            preferred_module_name = self._find_preferred_module(content)
            if preferred_module_name:
                alias_line = f"\npub use {preferred_module_name} as {benches_alias};\n"
                if alias_line.strip() not in content:
                    content = content.rstrip() + alias_line
        return content
    
    def _find_preferred_module(self, content: str) -> str:
        """Find the preferred benchmark module name."""
        preferred = self.rewriter.get_preferred_module_name()
        
        # Look for preferred module first
        m_pref = re.search(rf"pub mod ({preferred})\s*\{{", content)
        if m_pref:
            return m_pref.group(1)
        
        # Fallback to first benches module
        m_generic = re.search(r"pub mod (\w+_benches)\s*\{", content)
        if m_generic:
            return m_generic.group(1)
        
        return None
    
    def _apply_final_cleanup(self, content: str) -> str:
        """Apply final cleanup steps."""
        # Remove NoStdAccountInfo as CpiAccount alias import
        content = re.sub(r",\s*NoStdAccountInfo\s+as\s+CpiAccount", "", content)
        
        # Apply entrypoint-specific cleanup patterns
        if self.entrypoint_name in ("solana-program", "solana-program-mono", "pinocchio-std"):
            content = self._remove_allocator_macros(content)
        
        return content
    
    def _remove_allocator_macros(self, content: str) -> str:
        """Remove allocator and panic handler macros."""
        content = COMMON_PATTERNS['NO_ALLOCATOR_CALL'].sub("", content)
        content = COMMON_PATTERNS['NOSTD_PANIC_CALL'].sub("", content)
        content = COMMON_PATTERNS['NO_ALLOCATOR_IMPORT'].sub("", content)
        content = COMMON_PATTERNS['NOSTD_PANIC_IMPORT'].sub("", content)
        return content 