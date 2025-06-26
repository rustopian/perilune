from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import toml
import subprocess
import tempfile
from typing import List, Tuple, Dict, Any, Optional

from builder import run_cargo_build
from console_utils import (
    print_section,
    print_subsection,
    print_success,
    print_warning,
    print_error,
)
from entrypoint_config import ENTRYPOINT_DEPS
from executor import perform_benchmark_runs
from helpers import (
    discover_crates,
    parse_function_path,
    format_features,
    replace_placeholders,
    get_workspace_dependencies_block,
    get_package_name_from_manifest,
)
from reporter import generate_markdown_report, print_console_summary
from rewriter import rewrite_sources_for_entrypoint

# Re-export for caller convenience
__all__ = ["run"]

PERILUNE_ROOT = pathlib.Path(__file__).parent.parent.resolve()
TEMPLATES_DIR = PERILUNE_ROOT / "scripts" / "benchmark_templates"
TARGET_DIR = PERILUNE_ROOT / "target" / "bench_gen"
BENCHED_CRATE_COPY_DIR_NAME = "benched_crate_src"

# ---------------------------------------------------------------------------
# CLI / entry helpers
# ---------------------------------------------------------------------------

def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate and build Perilune benchmarks.")
    p.add_argument("--crate", required=True, type=pathlib.Path, nargs="+", help="Crate(s) or dirs to search.")
    p.add_argument(
        "--entrypoints",
        type=str,
        default="pinocchio",
        help="Comma-separated list of entrypoint implementations to benchmark.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Full program benchmark helpers
# ---------------------------------------------------------------------------

def _detect_program_entrypoint_style(program_dir: pathlib.Path) -> str:
    """Detect what entrypoint style a program is currently using by examining its dependencies.
    
    Returns one of: 'solana-program-mono', 'pinocchio', 'solana-program-breakout', 'unknown'
    """
    manifest_path = program_dir / "Cargo.toml"
    if not manifest_path.exists():
        return "unknown"
    
    try:
        manifest = toml.loads(manifest_path.read_text("utf-8"))
        deps = manifest.get("dependencies", {})
        
        # Check for pinocchio
        if "pinocchio" in deps:
            return "pinocchio"
        
        # Check for monolithic solana-program
        if "solana-program" in deps:
            return "solana-program-mono"
        
        # Check for breakout crates (if using multiple specific solana crates)
        breakout_crates = {"solana-pubkey", "solana-instruction", "solana-account-info", "solana-program-error"}
        if any(crate in deps for crate in breakout_crates):
            return "solana-program-breakout"
        
        return "unknown"
        
    except Exception:
        return "unknown"


def _should_rewrite_program_for_entrypoint(program_dir: pathlib.Path, target_entrypoint: str) -> bool:
    """Determine if a program needs rewriting to match the target entrypoint.
    
    Returns True if rewriting is needed, False if source is already compatible.
    """
    current_style = _detect_program_entrypoint_style(program_dir)
    
    # Define compatibility matrix
    compatibility_map = {
        "solana-program-mono": {
            "solana-program-mono": False,  # Already compatible
            "pinocchio": True,             # Need to rewrite
            "solana-program": True,        # Need to rewrite to breakout crates
            "solana-nostd-entrypoint": True,
        },
        "pinocchio": {
            "pinocchio": False,            # Already compatible
            "pinocchio-std": False,        # pinocchio works for both std and no-std
            "solana-program-mono": True,   # Need to rewrite
            "solana-program": True,
            "solana-nostd-entrypoint": True,
        },
        "solana-program-breakout": {
            "solana-program": False,       # Already compatible
            "solana-program-mono": True,   # Need to rewrite to monolithic
            "pinocchio": True,             # Need to rewrite
            "solana-nostd-entrypoint": True,
        },
    }
    
    # Default to rewriting if we're unsure
    if current_style == "unknown":
        return True
    
    current_map = compatibility_map.get(current_style, {})
    return current_map.get(target_entrypoint, True)  # Default to True (rewrite) if unsure


def _clone_and_build_program(program_source: Dict[str, Any], entrypoint_name: str, target_dir: pathlib.Path) -> Tuple[Optional[pathlib.Path], Optional[str]]:
    """Clone and build an external program from git source with a specific entrypoint.
    
    Returns (artifact_path, program_id) or (None, None) on failure.
    """
    git_url = program_source.get("git")
    program_path = program_source.get("path", "")
    
    if not git_url:
        print_error("Missing 'git' URL in program_source")
        return None, None
    
    print(f"Cloning program from {git_url} for entrypoint {entrypoint_name}")
    
    # Create temp directory for cloning
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        clone_path = temp_path / "program_source"
        
        try:
            # Clone the repository
            subprocess.run(
                ["git", "clone", git_url, str(clone_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            
            # Copy the entire repository to preserve internal dependencies
            repo_build_dir = target_dir / f"repo_build_{entrypoint_name}"
            shutil.rmtree(repo_build_dir, ignore_errors=True)
            shutil.copytree(clone_path, repo_build_dir)
            
            # Navigate to the program subdirectory if specified
            if program_path:
                build_dir = repo_build_dir / program_path
                if not build_dir.exists():
                    print_error(f"Program path {program_path} not found in repository")
                    return None, None
            else:
                build_dir = repo_build_dir
            
            # Sanitize the root workspace Cargo.toml if it exists
            root_manifest_path = repo_build_dir / "Cargo.toml"
            if root_manifest_path.is_file():
                try:
                    root_manifest = toml.loads(root_manifest_path.read_text("utf-8"))
                    if "workspace" in root_manifest:
                        # Make the root workspace only include the program we're building
                        if program_path:
                            root_manifest["workspace"] = {"members": [program_path]}
                        else:
                            # If no specific program path, make it an empty workspace
                            root_manifest["workspace"] = {}
                        root_manifest_path.write_text(toml.dumps(root_manifest), "utf-8")
                        print(f"Sanitized root workspace for {entrypoint_name} build")
                except Exception as exc:
                    print_warning(f"Failed to sanitise root workspace {root_manifest_path}: {exc}")
            
            # Sanitize the program's Cargo.toml (remove workspace references)
            manifest_path = build_dir / "Cargo.toml"
            if manifest_path.is_file():
                try:
                    manifest = toml.loads(manifest_path.read_text("utf-8"))
                    changed = False
                    
                    # Make this package its own workspace to avoid conflicts
                    if "workspace" in manifest:
                        # Replace with empty workspace declaration
                        manifest["workspace"] = {}
                        changed = True
                    else:
                        # Add empty workspace declaration 
                        manifest["workspace"] = {}
                        changed = True
                    
                    # Ensure proper lib crate-type
                    lib_table = manifest.setdefault("lib", {})
                    crate_types = lib_table.get("crate-type")
                    if crate_types is None:
                        lib_table["crate-type"] = ["cdylib", "lib"]
                        changed = True
                    elif isinstance(crate_types, str):
                        lib_table["crate-type"] = [crate_types, "cdylib", "lib"]
                        changed = True
                    elif isinstance(crate_types, list):
                        for t in ("cdylib", "lib"):
                            if t not in crate_types:
                                crate_types.append(t)
                                changed = True
                    
                    if changed:
                        manifest_path.write_text(toml.dumps(manifest), "utf-8")
                        print(f"Sanitized manifest for {entrypoint_name} build")
                        
                except Exception as exc:
                    print_warning(f"Failed to sanitise manifest {manifest_path}: {exc}")
            
            # Remove Cargo.lock to avoid workspace conflicts
            cargo_lock_path = build_dir / "Cargo.lock"
            if cargo_lock_path.exists():
                cargo_lock_path.unlink()
                print(f"Removed Cargo.lock to avoid workspace conflicts")
            
            # Apply entrypoint rewrites only if the source program doesn't already match the target
            if _should_rewrite_program_for_entrypoint(build_dir, entrypoint_name):
                print(f"Applying {entrypoint_name} entrypoint rewrites to program source")
                rewrite_sources_for_entrypoint(entrypoint_name, build_dir)
            else:
                print(f"Source program already compatible with {entrypoint_name}, skipping rewrites")
            
            # Patch dependencies for the entrypoint (like we do for example crates)
            from entrypoint_config import BENCHED_CRATE_DEPS
            if entrypoint_name in BENCHED_CRATE_DEPS:
                try:
                    manifest = toml.loads(manifest_path.read_text("utf-8"))
                    deps = manifest.setdefault("dependencies", {})
                    
                    # Add entrypoint-specific dependencies (but skip SPL packages to avoid conflicts)
                    skip_deps = {"spl-associated-token-account", "spl-token"}
                    for dep_name, dep_config in BENCHED_CRATE_DEPS[entrypoint_name].items():
                        if dep_name not in deps and dep_name not in skip_deps:
                            deps[dep_name] = dep_config
                            print(f"Added dependency {dep_name} for {entrypoint_name}")
                    
                    manifest_path.write_text(toml.dumps(manifest), "utf-8")
                    print(f"Patched dependencies for {entrypoint_name} entrypoint")
                    
                except Exception as exc:
                    print_warning(f"Failed to patch dependencies for {entrypoint_name}: {exc}")
            
            # Build the program
            print(f"Building program with {entrypoint_name} entrypoint in {build_dir}")
            artifact, program_id, build_time, prog_size = run_cargo_build(build_dir)
            
            return artifact, program_id
            
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to clone repository: {e.stderr}")
            return None, None
        except Exception as e:
            print_error(f"Failed to build program: {e}")
            return None, None


def _create_mollusk_benchmark(
    bench_id: str,
    crate_dir: pathlib.Path,
    test_functions: List[Dict[str, str]],
    features: List[str],
    program_artifact: pathlib.Path,
    program_id: str,
    target_dir: pathlib.Path,
) -> pathlib.Path:
    """Create a traditional Rust benchmark that uses Mollusk SVM to test against the compiled program.
    
    Returns the path to the created benchmark project.
    """
    benchmark_dir = target_dir / f"{bench_id}_mollusk_benchmark"
    benchmark_src_dir = benchmark_dir / "src"
    
    shutil.rmtree(benchmark_dir, ignore_errors=True)
    benchmark_dir.mkdir(parents=True)
    benchmark_src_dir.mkdir()
    
    # Create Cargo.toml for the benchmark
    cargo_toml_content = f"""[package]
name = "{bench_id}_benchmark"
version = "0.1.0"
edition = "2021"

[workspace]

[[bench]]
name = "mollusk_bench"
harness = false

[dependencies]
mollusk-svm = "0.1.5"
mollusk-svm-bencher = "0.1.5"
solana-account = "2.2"
solana-instruction = "2.2"
solana-pubkey = "2.2"
solana-system-interface = "1.0"
criterion = "0.5"

[dev-dependencies]
{crate_dir.name} = {{ path = "{crate_dir.absolute()}", features = {features} }}
"""
    
    (benchmark_dir / "Cargo.toml").write_text(cargo_toml_content)
    
    # Create the benchmark runner
    benches_dir = benchmark_dir / "benches"
    benches_dir.mkdir()
    
    bench_content = f"""use criterion::{{criterion_group, criterion_main, Criterion}};
use mollusk_svm::Mollusk;
use {crate_dir.name.replace('-', '_')}::std_benches::*;

fn benchmark_ata_functions(c: &mut Criterion) {{
    // Load the compiled ATA program
    let program_path = r"{program_artifact.absolute()}";
    let program_id = "{program_id}";
    
    c.bench_function("ata_create", |b| {{
        b.iter(|| {{
            // Run the benchmark function
            run_create_ata_bench().expect("ATA create benchmark failed");
        }})
    }});
    
    c.bench_function("ata_create_idempotent", |b| {{
        b.iter(|| {{
            run_create_ata_idempotent_bench().expect("ATA create idempotent benchmark failed");
        }})
    }});
    
    c.bench_function("ata_recover_nested", |b| {{
        b.iter(|| {{
            run_recover_nested_ata_bench().expect("ATA recover nested benchmark failed");
        }})
    }});
}}

criterion_group!(benches, benchmark_ata_functions);
criterion_main!(benches);
"""
    
    (benches_dir / "mollusk_bench.rs").write_text(bench_content)
    
    # Create a simple lib.rs
    (benchmark_src_dir / "lib.rs").write_text("// Benchmark runner for full program tests")
    
    return benchmark_dir


def _process_full_program_benchmark(
    bench_cfg: Dict[str, Any],
    crate_dir: pathlib.Path, 
    crate_name: str,
    requested_entrypoints: set,
    all_results: List[Dict[str, Any]],
    built_artifacts: List[pathlib.Path],
) -> None:
    """Process a full program benchmark configuration."""
    bench_id = bench_cfg.get("id")
    program_source = bench_cfg.get("program_source")
    test_functions = bench_cfg.get("test_functions", [])
    entrypoints = bench_cfg.get("entrypoints", [])
    feats_cfg = bench_cfg.get("features", [])
    
    print_subsection(f"--> Full Program Benchmark: {bench_id}")
    
    if not program_source:
        print_error(f"Missing 'program_source' in full program benchmark {bench_id}")
        return
        
    if not test_functions:
        print_error(f"Missing 'test_functions' in full program benchmark {bench_id}")
        return
    
    target_dir = TARGET_DIR / bench_id
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each entrypoint that was requested
    for ep_cfg in entrypoints:
        # Only run benchmarks that exactly match the requested entrypoints
        if ep_cfg in requested_entrypoints:
            ep_runtime = ep_cfg
        else:
            continue
            
        print_subsection(f"--> Building {bench_id} with {ep_runtime} entrypoint")
        
        # Clone and build the external program with this entrypoint
        program_artifact, program_id = _clone_and_build_program(program_source, ep_runtime, target_dir)
        if not program_artifact or not program_id:
            print_error(f"Failed to build program for benchmark {bench_id} with entrypoint {ep_runtime}")
            continue
            
        print_success(f"Built program artifact: {program_artifact}")
        built_artifacts.append(program_artifact)
        
        # Get features for the test crate (always std for Mollusk tests)
        test_crate_feats = ["std"]
        
        # Create and run Mollusk SVM benchmark for this entrypoint
        try:
            benchmark_project = _create_mollusk_benchmark(
                f"{bench_id}_{ep_runtime}", crate_dir, test_functions, test_crate_feats, 
                program_artifact, program_id, target_dir
            )
            
            print(f"Created benchmark project at: {benchmark_project}")
            
            # Run the benchmark using cargo bench
            print(f"Running Mollusk SVM benchmarks for {ep_runtime} compiled program...")
            result = subprocess.run(
                ["cargo", "bench"], 
                cwd=benchmark_project,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                print_success(f"Mollusk SVM benchmarks completed successfully for {ep_runtime}")
                
                # Create a result entry
                benchmark_result = {
                    "benchmark_id": f"{bench_id}_{ep_runtime}",
                    "type": "full_program",
                    "program_artifact": str(program_artifact),
                    "program_id": program_id,
                    "program_entrypoint": ep_runtime,  # How the program was compiled
                    "test_functions": [tf.get("name") for tf in test_functions],
                    "status": "success",
                    "output": result.stdout,
                }
                all_results.append(benchmark_result)
                
            else:
                print_error(f"Mollusk SVM benchmarks failed for {ep_runtime}: {result.stderr}")
                
        except Exception as e:
            print_error(f"Failed to create/run benchmark for {bench_id} with {ep_runtime}: {e}")


# ---------------------------------------------------------------------------
# Crate / benchmark processing helpers
# ---------------------------------------------------------------------------

def _copy_and_prepare_benched_crate(crate_dir: pathlib.Path, entrypoint_name: str, dest_dir: pathlib.Path) -> None:
    """Copy *crate_dir* into *dest_dir* and apply import rewrites etc."""
    print(f"Copying benchmarked crate from {crate_dir} to {dest_dir}")
    shutil.copytree(
        crate_dir, dest_dir, ignore=shutil.ignore_patterns("target"), dirs_exist_ok=True
    )

    manifest_path = dest_dir / "Cargo.toml"
    if manifest_path.is_file():
        try:
            manifest = toml.loads(manifest_path.read_text("utf-8"))
            changed = False
            if "workspace" in manifest:
                manifest.pop("workspace", None)
                changed = True
            lib_table = manifest.setdefault("lib", {})
            crate_types = lib_table.get("crate-type")
            if crate_types is None:
                lib_table["crate-type"] = ["cdylib", "lib"]
                changed = True
            elif isinstance(crate_types, str):
                lib_table["crate-type"] = [crate_types, "cdylib", "lib"]
                changed = True
            elif isinstance(crate_types, list):
                for t in ("cdylib", "lib"):
                    if t not in crate_types:
                        crate_types.append(t)
                        changed = True
            if changed:
                manifest_path.write_text(toml.dumps(manifest), "utf-8")
        except Exception as exc:
            print_warning(f"Failed to sanitise manifest {manifest_path}: {exc}")

    # Rewrite imports + ensure deps
    rewrite_sources_for_entrypoint(entrypoint_name, dest_dir)

    # Ensure crates expose the appropriate features for each entrypoint
    try:
        manifest_data = toml.load(manifest_path)
        feats = manifest_data.setdefault("features", {})
        
        if entrypoint_name in ["pinocchio", "solana-nostd-entrypoint"] and "no_std" not in feats:
            feats["no_std"] = []
        elif entrypoint_name == "pinocchio-std":
            if "std" not in feats:
                feats["std"] = []
            if "host" not in feats:
                feats["host"] = []
        elif entrypoint_name in ["solana-program", "solana-program-mono"] and "std" not in feats:
            feats["std"] = []
        elif entrypoint_name == "solana-nostd-entrypoint" and "no_std" not in feats:
            feats["no_std"] = []
        manifest_path.write_text(toml.dumps(manifest_data), "utf-8")
    except Exception:
        pass


def _build_runner_workspace(
    bench_id: str,
    crate_name: str,
    entrypoint_name: str,
    entrypoint_features: List[str],
    complete_ws_dep_block: str,
    bench_module: str,
    bench_func: str,
    rust_import_crate_name: str,
) -> pathlib.Path:
    """Create a temporary workspace for a single benchmark/entrypoint combo and return its path."""
    temp_dir_name = f"{bench_id}_{entrypoint_name}_{'_'.join(entrypoint_features) if entrypoint_features else 'nofeatures'}"
    temp_project_dir = TARGET_DIR / temp_dir_name
    temp_src_dir = temp_project_dir / "src"
    benched_crate_dest_path = temp_project_dir / BENCHED_CRATE_COPY_DIR_NAME

    shutil.rmtree(temp_project_dir, ignore_errors=True)
    temp_project_dir.mkdir(parents=True)

    # 1. Copy benched crate & apply rewrites (actual copy handled by caller)

    # 2. Generate runner Cargo.toml and lib.rs from templates
    cargo_tmpl = {
        "pinocchio": "template.pinocchio.cargo.toml",
        "solana-program": "template.solana_program.cargo.toml",
        "solana-program-mono": "template.solana_program_mono.cargo.toml",
        "solana-nostd-entrypoint": "template.solana_nostd_entrypoint.cargo.toml",
        "pinocchio-std": "template.pinocchio.cargo.toml",
    }[entrypoint_name]
    main_tmpl = cargo_tmpl.replace("cargo.toml", "lib.rs")

    cargo_template_path = TEMPLATES_DIR / cargo_tmpl
    main_template_path = TEMPLATES_DIR / main_tmpl

    replacements = {
        "%%BENCH_ID%%": temp_dir_name,
        "%%BENCHED_CRATE_COPY_DIR_NAME%%": BENCHED_CRATE_COPY_DIR_NAME,
        "%%WORKSPACE_DEPENDENCIES_BLOCK%%": complete_ws_dep_block,
        "%%CRATE_NAME%%": crate_name,
        "%%CRATE_FEATURES%%": format_features(entrypoint_features),
        "%%ENTRYPOINT_SDK_DEPENDENCY_LINE%%": ENTRYPOINT_DEPS[entrypoint_name],
        "%%RUST_IMPORT_CRATE_NAME%%": rust_import_crate_name,
        "%%BENCHMARK_FUNCTION_MODULE%%": bench_module,
        "%%BENCHMARK_FUNCTION_NAME%%": bench_func,
    }

    cargo_content = replace_placeholders(cargo_template_path.read_text(), replacements)
    (temp_project_dir / "Cargo.toml").write_text(cargo_content)
    temp_src_dir.mkdir()
    main_content = replace_placeholders(main_template_path.read_text(), replacements)
    (temp_src_dir / "lib.rs").write_text(main_content)

    # stub env_logger crate
    noop_dir = temp_project_dir / "noop_env_logger" / "src"
    noop_dir.mkdir(parents=True, exist_ok=True)
    (noop_dir.parent / "Cargo.toml").write_text(
        """[package]
name = "env_logger"
version = "0.10.2"
edition = "2021"
[lib]
crate-type = ["rlib"]
[dependencies]
log = { version = "0.4", default-features = false }
"""
    )
    (noop_dir / "lib.rs").write_text("#![no_std]\npub use log::*;\n")

    return temp_project_dir, benched_crate_dest_path


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def run() -> None:
    args = _parse_cli()
    requested_entrypoints = {ep.strip().lower() for ep in args.entrypoints.split(",") if ep.strip()}
    if not requested_entrypoints:
        requested_entrypoints = {"pinocchio"}

    print(f"Requested entrypoints: {', '.join(sorted(requested_entrypoints))}\n")

    crates_to_process: List[pathlib.Path] = []
    for p in args.crate:
        crates_to_process.extend(discover_crates(p))

    if not crates_to_process:
        print_error("No valid crates found to process")
        sys.exit(1)

    print_section("Crates to process:")
    for c in crates_to_process:
        print(f" - {c}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    all_results: List[Dict[str, Any]] = []
    built_artifacts: List[pathlib.Path] = []

    for crate_dir in crates_to_process:
        print_section(f"\n=== Processing crate: {crate_dir} ===")
        crate_name = get_package_name_from_manifest(crate_dir) or crate_dir.name

        config_path = crate_dir / "perilune_benchmarks.toml"
        try:
            config = toml.loads(config_path.read_text("utf-8"))
        except Exception as exc:
            print_error(f"Failed to parse {config_path}: {exc}")
            continue

        for bench_cfg in config.get("benchmark", []):
            bench_id = bench_cfg.get("id")
            bench_type = bench_cfg.get("type", "example_crate")  # Default to example crate
            entrypoints = bench_cfg.get("entrypoints", [])
            feats_cfg = bench_cfg.get("features", [])
            
            if not bench_id:
                print_warning(f"Skipping benchmark config without id: {bench_cfg}")
                continue
                
            # Handle full program benchmarks differently
            if bench_type == "full_program":
                _process_full_program_benchmark(
                    bench_cfg, crate_dir, crate_name, requested_entrypoints, 
                    all_results, built_artifacts
                )
                continue
                
            # Handle example crate benchmarks (existing logic)
            func_path = bench_cfg.get("function")
            if not func_path:
                print_warning(f"Skipping example crate benchmark without function: {bench_cfg}")
                continue
            crate_mod, bench_mod, bench_fn = parse_function_path(func_path)

            for ep_cfg in entrypoints:
                # Only run benchmarks that exactly match the requested entrypoints
                if ep_cfg in requested_entrypoints:
                    ep_runtime = ep_cfg
                else:
                    continue

                print_subsection(f"--> Benchmark {bench_id} | entrypoint {ep_runtime}")

                # Generate workspace dependency block specific to this entrypoint
                ws_dep_block = get_workspace_dependencies_block(["pinocchio"])
                
                if ep_runtime == "pinocchio-std":
                    # strip any existing pinocchio line
                    ws_dep_block = "\n".join([
                        ln for ln in ws_dep_block.splitlines() if not ln.strip().startswith("pinocchio =")
                    ]) or "[workspace.dependencies]"
                    ws_dep_block += """
pinocchio = { version = "0.8", git = "https://github.com/rustopian/pinocchio.git", branch = "rustopian/slot-hashes-sysvar", default-features = false, features = [\"std\"] }"""
                elif ep_runtime == "pinocchio":
                    # strip any existing pinocchio line
                    ws_dep_block = "\n".join([
                        ln for ln in ws_dep_block.splitlines() if not ln.strip().startswith("pinocchio =")
                    ]) or "[workspace.dependencies]"
                    ws_dep_block += """
pinocchio = { version = "0.8", git = "https://github.com/rustopian/pinocchio.git", branch = "rustopian/slot-hashes-sysvar", default-features = false }"""

                ep_feats = next((fc.get("features", []) for fc in feats_cfg if fc.get("entrypoint") == ep_cfg), [])

                # Drop features not declared in the benched crate's manifest to avoid build failures
                try:
                    manifest_feats = list(
                        toml.loads((crate_dir / "Cargo.toml").read_text("utf-8")).get("features", {}).keys()
                    )
                except Exception:
                    manifest_feats = []

                valid_ep_feats = [f for f in ep_feats if f in manifest_feats]
                if ep_feats and not valid_ep_feats:
                    print_warning(
                        f"Requested features {ep_feats} for {ep_runtime} not present in crate; omitting."
                    )
                ep_feats = valid_ep_feats

                # Clean feature list & auto-add
                if ep_runtime == "pinocchio":
                    if "std" in ep_feats:
                        ep_feats.remove("std")
                    if "no_std" not in ep_feats:
                        ep_feats.append("no_std")
                elif ep_runtime == "pinocchio-std":
                    # Switch from no_std to full std/host environment
                    ep_feats = [f for f in ep_feats if f not in ("no_std", "host")]
                    if "host" not in ep_feats:
                        ep_feats.append("host")  # enables std + disables no_std cfgs
                    if "std" not in ep_feats:
                        ep_feats.append("std")
                elif ep_runtime in ["solana-program", "solana-program-mono"] and "std" not in ep_feats:
                    ep_feats.append("std")
                elif ep_runtime == "solana-nostd-entrypoint":
                    ep_feats = [f for f in ep_feats if f != "std"]
                    if "no_std" not in ep_feats:
                        ep_feats.append("no_std")

                # 1. Prepare temp workspace
                temp_project_dir, benched_copy_path = _build_runner_workspace(
                    bench_id,
                    crate_name,
                    ep_runtime,
                    ep_feats,
                    ws_dep_block,
                    bench_mod,
                    bench_fn,
                    crate_mod,
                )

                # 2. Copy & rewrite benched crate
                _copy_and_prepare_benched_crate(crate_dir, ep_runtime, benched_copy_path)

                # 3. Build
                artifact, program_id, build_secs, prog_size = run_cargo_build(temp_project_dir)
                if not (artifact and program_id):
                    continue
                print_success(f"Built {artifact}")
                built_artifacts.append(artifact)

                # 4. Execute benchmarks via helper
                results = perform_benchmark_runs(
                    bench_id=bench_id,
                    bench_config=bench_cfg,
                    entrypoint_name=ep_runtime,
                    entrypoint_features=ep_feats,
                    artifact_path=artifact,
                    program_id=program_id,
                    actual_benched_crate_name=crate_name,
                    build_time_seconds=build_secs,
                    program_size_bytes=prog_size,
                    perilune_root=PERILUNE_ROOT,
                )
                all_results.extend(results)

    # -------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------
    if all_results:
        generate_markdown_report(all_results, PERILUNE_ROOT / "benchmark_results.md")
        print_console_summary(all_results)
    else:
        print("\nNo benchmark results to report.")

    print_section("\n=== Summary ===")
    if built_artifacts:
        for art in built_artifacts:
            print_success(f"Built artifact: {art}")
    else:
        print("No artifacts were built successfully.") 