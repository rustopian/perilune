from __future__ import annotations

import pathlib
import toml
from typing import List

from console_utils import print_error, print_warning

# Resolve the project root based on this file's location (scripts/)
PERILUNE_ROOT = pathlib.Path(__file__).parent.parent.resolve()
WORKSPACE_ROOT = PERILUNE_ROOT

__all__ = [
    "discover_crates",
    "parse_function_path",
    "format_features",
    "replace_placeholders",
    "get_workspace_dependencies_block",
    "get_package_name_from_manifest",
]


# ---------------------------------------------------------------------------
# String / path helpers
# ---------------------------------------------------------------------------

def discover_crates(path: pathlib.Path) -> List[pathlib.Path]:
    """Return a list of crate directories that contain an *perilune_benchmarks.toml* file.

    If *path* itself points to such a crate, a single-element list is returned.
    If *path* is a directory, its immediate children are scanned for crates.
    """
    path = path.resolve()

    if (path / "perilune_benchmarks.toml").is_file():
        return [path]

    if path.is_dir():
        crates: List[pathlib.Path] = [
            subdir
            for subdir in path.iterdir()
            if subdir.is_dir() and (subdir / "perilune_benchmarks.toml").is_file()
        ]
        return sorted(crates)

    return []


def parse_function_path(full_path: str):
    """Split a Rust-style path like ``crate::mod::func`` into (crate, module, func)."""
    try:
        parts = full_path.split("::")
        if len(parts) < 2:
            raise ValueError("Function path must include crate name and function name.")
        crate_name = parts[0]
        func_name = parts[-1]
        module_path = "::".join(parts[1:-1]) if len(parts) > 2 else ""
        return crate_name, module_path, func_name
    except Exception as exc:
        print_error(f"parsing function path '{full_path}': {exc}")
        return None, None, None


# ---------------------------------------------------------------------------
# Templating helpers
# ---------------------------------------------------------------------------

def format_features(features_list):
    if not features_list:
        return ""
    return ", ".join([f'"{feat}"' for feat in features_list])


def replace_placeholders(content: str, replacements: dict[str, str]):
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, str(value))
    return content


# ---------------------------------------------------------------------------
# Workspace-level helpers
# ---------------------------------------------------------------------------

def _value_to_toml(v):
    """Convert basic Python types to inline TOML string representation."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    # Treat everything else as string for our simple needs.
    return f'"{v}"'


def _format_toml_dict(data: dict) -> str:
    """Formats a flat dict into minimal inline TOML."""
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            items_str = ", ".join([f"{k} = {_value_to_toml(v)}" for k, v in value.items()])
            lines.append(f"{key} = {{ {items_str} }}")
        else:
            lines.append(f"{key} = {_value_to_toml(value)}")
    return "\n".join(lines)


def get_workspace_dependencies_block(dep_names):
    """Extract dependency definitions from the *workspace* Cargo.toml.*"""
    root_cargo_path = WORKSPACE_ROOT / "Cargo.toml"
    try:
        manifest_text = root_cargo_path.read_text("utf-8")
        manifest = toml.loads(manifest_text)
        workspace_deps = manifest.get("workspace", {}).get("dependencies", {})

        deps_to_include = {}
        for name in dep_names:
            if name in workspace_deps:
                deps_to_include[name] = workspace_deps[name]
            else:
                print_warning(
                    f"Dependency '{name}' requested but not found in [workspace.dependencies] in {root_cargo_path}"
                )

        if not deps_to_include:
            return "[workspace.dependencies]"

        return "[workspace.dependencies]\n" + _format_toml_dict(deps_to_include)
    except FileNotFoundError:
        # Fall back to a minimal dependency block so the temporary benchmark workspace still builds.
        print_warning(f"Workspace root Cargo.toml not found at {root_cargo_path}; using fallback dependency definitions.")

        fallback_deps = {}
        for name in dep_names:
            if name == "pinocchio":
                fallback_deps[name] = {
                    "version": "0.8",
                    "git": "https://github.com/rustopian/pinocchio.git",
                    "branch": "rustopian/slot-hashes-sysvar",
                    "default-features": False,
                }
            else:
                # Generic empty stub so TOML stays valid; user can patch if needed.
                fallback_deps[name] = "*"

        return "[workspace.dependencies]\n" + _format_toml_dict(fallback_deps)
    except Exception as exc:
        print_error(f"Error reading or parsing workspace root Cargo.toml {root_cargo_path}: {exc}")
        return "[workspace.dependencies]"


def get_package_name_from_manifest(crate_dir: pathlib.Path):
    manifest_path = crate_dir / "Cargo.toml"
    try:
        manifest = toml.loads(manifest_path.read_text("utf-8"))
        package_name = manifest.get("package", {}).get("name")
        if not package_name:
            print_error(f"Could not find [package].name in {manifest_path}")
            return None
        return package_name
    except FileNotFoundError:
        print_error(f"Manifest file not found at {manifest_path}")
        return None
    except Exception as exc:
        print_error(f"reading or parsing manifest {manifest_path}: {exc}")
        return None 