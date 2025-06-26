from __future__ import annotations

import os
import subprocess
import sys
import time
import toml
import pathlib
from typing import Tuple, Optional

from console_utils import (
    print_build_info,
    print_error,
    print_success,
    print_warning,
)

__all__ = [
    "run_cargo_build",
]


# NOTE: This is nearly a verbatim extraction of the logic that used to live in
#       run_perilune_benchmarks.py. Minor clean-ups/additional typing were added
#       but the core behaviour is unchanged so that the refactor remains
#       risk-free.

def run_cargo_build(temp_project_dir: pathlib.Path) -> Tuple[
    Optional[pathlib.Path], Optional[str], Optional[float], Optional[int]
]:
    """Build the given temporary benchmark project with *cargo-build-sbf*.

    Returns a 4-tuple of:
        1. The path to the generated *.so* artifact (or *None* on failure).
        2. The program id extracted from the keypair (or *None*).
        3. The wall-clock build time in **seconds** (or *None*).
        4. The size of the resulting BPF program in **bytes** (or *None*).
    """
    print_build_info(
        f"--- Building benchmark project using cargo-build-sbf in: {temp_project_dir} ---"
    )

    package_name: Optional[str] = None
    program_id: Optional[str] = None
    artifact_path: Optional[pathlib.Path] = None
    build_time_seconds: Optional[float] = None
    program_size_bytes: Optional[int] = None

    manifest_path = temp_project_dir / "Cargo.toml"
    try:
        manifest = toml.loads(manifest_path.read_text("utf-8"))
        package_name = manifest.get("package", {}).get("name")
    except Exception as exc:  # pragma: no cover – just paranoia
        print_warning(f"Could not determine package name from {manifest_path}: {exc}")

    if not package_name:
        print_error("Cannot determine package name for build artifact.")
        return None, None, None, None

    canonical_filename_stem = package_name.replace("-", "_")
    expected_so_filename = f"{canonical_filename_stem}.so"
    expected_keypair_filename = f"{canonical_filename_stem}-keypair.json"
    deploy_dir = temp_project_dir / "target" / "deploy"
    expected_so_path = deploy_dir / expected_so_filename
    expected_keypair_path = deploy_dir / expected_keypair_filename

    try:
        build_command = ["cargo-build-sbf"]
        print(f"Running build command: {' '.join(build_command)} in {temp_project_dir}")

        # Measure build time
        build_start_time = time.time()
        subprocess.run(
            build_command,
            cwd=temp_project_dir,
            env=dict(os.environ, RUSTFLAGS='--cfg getrandom_backend="custom"'),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        build_time_seconds = round(time.time() - build_start_time, 2)
        print_success(f"Build command finished in {build_time_seconds}s.")

        # --- Verify the build outputs -------------------------------------------------
        print(f"Checking for expected artifact at: {expected_so_path}")
        if expected_so_path.is_file():
            print_success(f"  Artifact found: {expected_so_path}")
            artifact_path = expected_so_path
            try:
                program_size_bytes = expected_so_path.stat().st_size
                print_success(
                    f"  Program size: {program_size_bytes} bytes ({program_size_bytes/1024:.1f} KB)"
                )
            except Exception as size_err:  # pragma: no cover – filesystem oddities
                print_warning(f"Could not determine program size: {size_err}")
        else:
            print_error(f"  Artifact NOT found: {expected_so_path}")
            return None, None, None, None

        # --- Extract the Program ID ---------------------------------------------------
        print(f"Checking for keypair file at: {expected_keypair_path}")
        if expected_keypair_path.is_file():
            print(f"  Keypair file found: {expected_keypair_path}")
            try:
                keygen_command = ["solana-keygen", "pubkey", str(expected_keypair_path)]
                print(f"  Running: {' '.join(keygen_command)}")
                keygen_result = subprocess.run(
                    keygen_command,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                program_id = keygen_result.stdout.strip()
                if program_id:
                    print_success(f"  Extracted Program ID via solana-keygen: {program_id}")
                else:
                    print_error("  solana-keygen command returned empty output.")
            except subprocess.CalledProcessError as exc:
                print_error(f"running solana-keygen for {expected_keypair_path}:")
                print(f"Stderr: {exc.stderr}", file=sys.stderr)
            except FileNotFoundError:
                print_error("'solana-keygen' command not found. Is the Solana toolchain installed and in PATH?")
            except Exception as exc:  # pragma: no cover
                print_error(f"extracting Program ID via solana-keygen for {expected_keypair_path}: {exc}")
        else:
            print_error(
                f"  Keypair file NOT found: {expected_keypair_path}. Cannot determine Program ID."
            )

    except subprocess.CalledProcessError as exc:
        print_error(f"building benchmark project in {temp_project_dir}:")
        print(exc.stderr, file=sys.stderr)
        return None, None, None, None
    except FileNotFoundError:
        print_error("'cargo-build-sbf' command not found. Is the Solana toolchain installed and in PATH?")
        return None, None, None, None
    except Exception as exc:  # pragma: no cover – belt & braces
        print_error(f"An unexpected error occurred during build: {exc}")
        return None, None, None, None

    return artifact_path, program_id, build_time_seconds, program_size_bytes 