"""
Import processing module for the Solana program rewriter.

This module handles all aspects of parsing, extracting, and rewriting import statements
for different Solana entrypoint formats.
"""

import re
from console_utils import print_warning
from entrypoint_config import IDENTIFIER_MAPPINGS


def extract_all_imported_identifiers(content: str) -> set:
    """Extract all imported identifiers from use statements."""
    identifiers = set()
    
    # Find all use statements
    use_pattern = r'use\s+[^;]+;'
    use_statements = re.findall(use_pattern, content, re.MULTILINE | re.DOTALL)
    
    for stmt in use_statements:
        # Remove 'use' and ';', clean up whitespace
        cleaned = re.sub(r'use\s+|;', '', stmt).strip()
        cleaned = ' '.join(cleaned.split())  # Normalize whitespace
        # Strip any surrounding braces on the entire cleaned statement to simplify parsing
        cleaned = cleaned.strip('{}')
        
        # Check if this is a top-level grouped import: use { ... }
        if cleaned.startswith('{') and cleaned.endswith('}'):
            identifiers.update(_process_top_level_grouped_import(cleaned))
        else:
            identifiers.update(_process_regular_import(cleaned))
    
    return identifiers


def _process_top_level_grouped_import(cleaned: str) -> set:
    """Process top-level grouped imports like: use { item1, item2::subitem, item3::{a, b} }"""
    identifiers = set()
    inner_content = cleaned[1:-1]  # Remove outer braces
    
    # Split by comma, but be careful about nested braces
    items = []
    current_item = ""
    brace_depth = 0
    
    for char in inner_content + ',':  # Add comma to ensure last item is processed
        if char == '{':
            brace_depth += 1
            current_item += char
        elif char == '}':
            brace_depth -= 1
            current_item += char
        elif char == ',' and brace_depth == 0:
            if current_item.strip():
                items.append(current_item.strip())
            current_item = ""
        else:
            current_item += char
    
    # Process each item in the top-level group
    for item in items:
        identifiers.update(_process_import_item(item))
    
    return identifiers


def _process_regular_import(cleaned: str) -> set:
    """Process regular imports (not top-level grouped)."""
    identifiers = set()
    
    # Handle grouped imports: extract from {...}
    grouped_match = re.search(r'\{([^}]*)\}', cleaned)
    if grouped_match:
        grouped_content = grouped_match.group(1)
        # Split by comma and extract identifiers
        for item in grouped_content.split(','):
            identifiers.update(_process_import_item(item.strip()))
    else:
        # Handle individual imports like "use solana_program::pubkey::Pubkey;"
        identifiers.update(_process_import_item(cleaned))
    
    return identifiers


def _process_import_item(item: str) -> set:
    """Process a single import item and extract identifiers."""
    identifiers = set()
    item = item.strip()
    
    # Clean up any brace artifacts
    if item.startswith('{'):
        item = item[1:].lstrip()
    if item.endswith('}'):
        item = item[:-1].rstrip()
    if item.endswith(','):
        item = item[:-1].rstrip()
    if not item:
        return identifiers
    
    # Check if this item has its own grouped imports: item::{a, b}
    if '{' in item and '}' in item:
        # This is like: solana_account_info::{AccountInfo, next_account_info}
        grouped_part = item[item.find('{')+1:item.find('}')]
        for subitem in grouped_part.split(','):
            subitem = subitem.strip()
            if ' as ' in subitem:
                alias = subitem.split(' as ')[1].strip()
                identifiers.add(alias)
            else:
                identifiers.add(subitem)
    else:
        # This is a simple import like: solana_cpi::invoke or Pubkey
        if '::' in item:
            final_part = item.split('::')[-1]
            if ' as ' in final_part:
                alias = final_part.split(' as ')[1].strip()
                identifiers.add(alias)
            else:
                identifiers.add(final_part.strip())
        else:
            identifiers.add(item.strip())
    
    return identifiers


def generate_target_imports(found_identifiers: set, entrypoint_name: str) -> str:
    """Generate clean import statements for the target entrypoint."""
    rewrite_mapping = IDENTIFIER_MAPPINGS.get(entrypoint_name, {})
    
    # Find which identifiers need to be imported for this target
    target_imports = {}
    unknown_identifiers = []
    
    for identifier in found_identifiers:
        # Skip obviously malformed identifiers that still contain braces or commas
        if any(ch in identifier for ch in '{} ,'):
            continue
        # Skip identifiers that are not relevant for std entrypoints
        if entrypoint_name == "solana-program" and identifier == "invoke_signed_unchecked":
            continue
        if identifier in rewrite_mapping:
            target_path = rewrite_mapping[identifier]
            target_imports[identifier] = target_path
        elif identifier == "black_box":
            target_imports[identifier] = "core::hint::black_box"
        else:
            # Only warn about identifiers that look like Solana types
            if any(solana_hint in identifier.lower() for solana_hint in 
                   ['program', 'account', 'pubkey', 'invoke', 'instruction', 'error', 'result']):
                unknown_identifiers.append(identifier)
    
    if unknown_identifiers:
        print_warning(f"Unknown Solana identifiers for {entrypoint_name}: {', '.join(unknown_identifiers)}")
    
    if not target_imports:
        return ""
    
    return _format_import_statements(target_imports, entrypoint_name)


def _format_import_statements(target_imports: dict, entrypoint_name: str) -> str:
    """Format target imports into clean import statements."""
    # Group imports by crate
    crate_imports = {}
    for identifier, full_path in target_imports.items():
        if '::' in full_path:
            path_parts = full_path.split('::')
            if len(path_parts) >= 2:
                crate = '::'.join(path_parts[:-1])
                type_name = path_parts[-1]
            else:
                # Fallback for single part paths
                crate = full_path
                type_name = identifier
        else:
            # This shouldn't happen with our mappings, but just in case
            crate = full_path
            type_name = identifier
            
        if crate not in crate_imports:
            crate_imports[crate] = []
        
        # Special handling for solana-nostd-entrypoint double alias issue
        if entrypoint_name == "solana-nostd-entrypoint" and crate == "solana_nostd_entrypoint" and type_name == "NoStdAccountInfo":
            if identifier == "AccountInfo":
                # Just import as AccountInfo (the alias will be added by _ensure_nostd_entrypoint_alias)
                crate_imports[crate].append("NoStdAccountInfo")
            elif identifier == "CpiAccount":
                # Import as CpiAccount directly
                crate_imports[crate].append("NoStdAccountInfo as CpiAccount")
            else:
                crate_imports[crate].append(type_name)
        else:
            # Handle aliases: if identifier != type_name, we need an alias
            if identifier != type_name:
                crate_imports[crate].append(f"{type_name} as {identifier}")
            else:
                crate_imports[crate].append(type_name)
    
    # Generate import statements
    import_lines = []
    for crate, types in sorted(crate_imports.items()):
        # Skip empty or invalid crate names
        if not crate or crate.isspace():
            continue
            
        unique_types = sorted(set(types))  # Remove duplicates and sort
        # Filter out invalid imports like Pubkey::default()
        valid_types = [t for t in unique_types if '::' not in t or ' as ' in t]
        if not valid_types:
            continue
        if len(valid_types) == 1:
            import_lines.append(f"use {crate}::{valid_types[0]};")
        else:
            types_str = ', '.join(valid_types)
            import_lines.append(f"use {crate}::{{{types_str}}};")
    
    return '\n'.join(import_lines)


def strip_imports_and_generate_clean_imports(content: str, entrypoint_name: str) -> str:
    """Remove all `use …;` statements and regenerate clean imports for the target entrypoint."""
    lines = content.splitlines()
    kept_lines: list[str] = []
    removed_use_lines: list[str] = []

    i = 0
    while i < len(lines):
        attr_buffer: list[str] = []

        # Collect preceding attributes (#[cfg …]) so we can drop them together
        while i < len(lines) and lines[i].lstrip().startswith('#['):
            attr_buffer.append(lines[i])
            i += 1

        if i >= len(lines):
            kept_lines.extend(attr_buffer)
            break

        line = lines[i]
        stripped = line.lstrip()

        if stripped.startswith('use '):
            # Keep the special crate::processor import, drop everything else
            if stripped.startswith('use crate::processor'):
                kept_lines.extend(attr_buffer)
                kept_lines.append(line)
                i += 1
            else:
                # Drop attr_buffer + the entire use-block up to and including the semicolon
                current_use_lines: list[str] = attr_buffer + [line]
                while ';' not in lines[i]:
                    i += 1
                    if i < len(lines):
                        current_use_lines.append(lines[i])
                removed_use_lines.extend(current_use_lines)
                i += 1  # move past the semicolon line (lines[i] already contains semicolon)
        else:
            # Not an import – keep what we buffered and this line
            kept_lines.extend(attr_buffer)
            kept_lines.append(line)
            i += 1

    content_without_imports = '\n'.join(kept_lines)
    had_original_imports = len(removed_use_lines) > 0

    # Extract identifiers and scan for usage
    found_identifiers = extract_all_imported_identifiers('\n'.join(removed_use_lines))
    found_identifiers.update(_scan_for_implicit_identifiers(content_without_imports, entrypoint_name))

    new_imports = ""
    if had_original_imports and found_identifiers:
        new_imports = generate_target_imports(found_identifiers, entrypoint_name)

    return _insert_imports_into_content(content_without_imports, new_imports)


def _scan_for_implicit_identifiers(content: str, entrypoint_name: str) -> set:
    """Scan content for identifiers that might be used without explicit imports."""
    found_identifiers = set()
    
    # Add identifiers that might be used without explicit imports
    if "msg!" in content:
        found_identifiers.add("msg")
    if "sol_log" in content:
        found_identifiers.add("sol_log")

    # Common Solana identifiers
    common_keywords = [
        "Pubkey", "SystemPubkey", "AccountInfo", "ProgramResult", "ProgramError", 
        "Instruction", "InstructionC", "AccountMeta", "next_account_info", "invoke", "invoke_signed",
        "syscalls",
    ]
    for keyword in common_keywords:
        if re.search(rf"\b{keyword}\b", content):
            found_identifiers.add(keyword)

    # SPL Associated Token Account identifiers
    spl_ata_keywords = [
        "create_associated_token_account", "create_associated_token_account_idempotent", 
        "recover_nested", "get_associated_token_address", "spl_token_program_id",
    ]
    for keyword in spl_ata_keywords:
        if re.search(rf"\b{keyword}\b", content):
            found_identifiers.add(keyword)

    # Entrypoint-specific processing
    if entrypoint_name in ("pinocchio", "pinocchio-std"):
        found_identifiers.update(["Pubkey", "AccountInfo", "ProgramResult", "ProgramError"])
        found_identifiers.discard("no_allocator")
        found_identifiers.discard("nostd_panic_handler")
        
        # Add identifiers that will be created by transformations
        if "CpiAccount" in content:
            found_identifiers.add("Account")  # CpiAccount gets transformed to Account
        if "invoke_signed_unchecked" in content:
            found_identifiers.add("invoke_signed")  # invoke_signed_unchecked gets transformed to invoke_signed
    
    # Add identifiers for nostd entrypoint transformations
    if entrypoint_name == "solana-nostd-entrypoint":
        if "invoke_signed_unchecked" in content:
            found_identifiers.add("invoke_signed")  # invoke_signed_unchecked gets transformed to invoke_signed

    # Detect SlotHashes usages which often appear without an explicit import after rewrites.
    if re.search(r"\bSlotHashes\b", content):
        found_identifiers.add("SlotHashes")

    return found_identifiers


def _insert_imports_into_content(content: str, new_imports: str) -> str:
    """Insert new imports into content after initial attributes."""
    # insert import block after initial #![…] attrs
    final_lines = content.splitlines()
    insert_idx = 0
    for idx, ln in enumerate(final_lines):
        if ln.strip().startswith('#!['):
            insert_idx = idx + 1
        elif ln.strip() and not ln.strip().startswith('//'):
            break

    if new_imports:
        final_lines.insert(insert_idx, "")
        final_lines.insert(insert_idx + 1, new_imports)
        final_lines.insert(insert_idx + 2, "")

    # Handle special processor import case - only if there's actually a processor module
    content_str = '\n'.join(final_lines)
    if 'pub mod instruction' in content and ('pub mod processor' in content or 'mod processor' in content):
        content_str = re.sub(
            r'(pub\s+mod\s+instruction\s*{\s*)(?![^}]*use\s+crate::processor;)',
            r'\1use crate::processor;\n',
            content_str,
            count=1,
            flags=re.DOTALL,
        )

    return content_str 