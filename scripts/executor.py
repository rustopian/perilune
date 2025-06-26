from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Dict, List, Any, Optional


from console_utils import (
    print_subsection,
    print_build_info,
    print_warning,
    print_error,
    print_result,
)
from account_specs import (
    get_account_count_for_benchmark,
    get_account_specs_for_benchmark,
    get_instruction_type,
)
from metrics_parser import extract_and_store_metrics

# NOTE: This is extracted wholesale from run_perilune_benchmarks.py so that the
#       main script is shorter. Only minimal tweaks were made (type hints, minor
#       refactoring) to keep behaviour identical.

__all__ = ["perform_benchmark_runs"]


def _serialize_payload(payload: Dict[str, Any], bench_id: str) -> bytes:
    """Helper that maps *instruction_payload* dicts into raw instruction bytes."""
    if not payload or not isinstance(payload, dict):
        print_warning(
            f"instruction_payload for {bench_id} is malformed. Using default byte."
        )
        return b"\xff"

    tag = payload.get("tag")
    if tag is None:
        print_warning(
            f"instruction_payload missing 'tag' for {bench_id}. Using default byte."
        )
        return b"\xff"

    data_bytes = bytearray()
    data_bytes.append(int(tag))

    # Currently supported payload variants
    if "amount" in payload:  # Transfer
        amount = payload.get("amount", 0)
        data_bytes.extend(int(amount).to_bytes(8, byteorder="little"))
    elif "lamports" in payload and "space" in payload:  # CreateAccount
        lamports = payload.get("lamports", 0)
        space = payload.get("space", 0)
        data_bytes.extend(int(lamports).to_bytes(8, byteorder="little"))
        data_bytes.extend(int(space).to_bytes(8, byteorder="little"))

    # Add more payload encodings as needed.
    return bytes(data_bytes)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def perform_benchmark_runs(
    *,
    bench_id: str,
    bench_config: Dict[str, Any],
    entrypoint_name: str,
    entrypoint_features: List[str],
    artifact_path: pathlib.Path,
    program_id: str,
    actual_benched_crate_name: str,
    build_time_seconds: Optional[float],
    program_size_bytes: Optional[int],
    perilune_root: pathlib.Path,
) -> List[Dict[str, Any]]:
    """Run all benchmark *variants* (e.g. different account counts) for the given
    compiled artifact and return a list of metric dictionaries.
    """
    results: List[Dict[str, Any]] = []

    instruction_payload = bench_config.get("instruction_payload")
    account_setups = bench_config.get("account_setups")
    runs_to_perform: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------------
    # Build the *runs_to_perform* matrix
    # ---------------------------------------------------------------------
    if instruction_payload:
        # Single custom payload run
        num_accounts = get_account_count_for_benchmark(bench_id)
        serialized = _serialize_payload(instruction_payload, bench_id)
        runs_to_perform.append(
            {
                "num_accounts": num_accounts,
                "instruction_hex": serialized.hex(),
                "run_id_suffix": "_custom_payload",
            }
        )
    elif account_setups and isinstance(account_setups, list):
        for setup in account_setups:
            count = setup.get("count")
            if isinstance(count, int) and 0 < count <= 255:
                runs_to_perform.append(
                    {
                        "num_accounts": count,
                        "instruction_hex": f"{count:02x}",
                        "run_id_suffix": f"_accounts_{count}",
                    }
                )
            else:
                print_warning(
                    f"Invalid count in account_setups for {bench_id}: {setup}. Skipping."
                )
    else:
        # Default ping-like run
        runs_to_perform.append(
            {
                "num_accounts": 0,
                "instruction_hex": "00",
                "run_id_suffix": "_default_run",
            }
        )

    # ---------------------------------------------------------------------
    # Execute each run variant
    # ---------------------------------------------------------------------
    for run_params in runs_to_perform:
        num_accounts = run_params["num_accounts"]
        instruction_hex = run_params["instruction_hex"]

        current_run_metrics: Dict[str, Any] = {
            "id": f"{bench_id}{run_params['run_id_suffix']}",
            "entrypoint": entrypoint_name,
            "features": entrypoint_features,
            "artifact": str(artifact_path),
            "program_id": program_id,
            "AccountsProcessed": num_accounts,
            "crate": actual_benched_crate_name,
            "instruction": get_instruction_type(bench_id),
            "BuildTimeSeconds": build_time_seconds,
            "ProgramSizeBytes": program_size_bytes,
        }

        print_subsection(f"=== Starting benchmark run: {current_run_metrics['id']} ===")
        print_build_info(
            f"--- Executing {entrypoint_name} benchmark for: {artifact_path} ---"
        )

        account_spec_args = get_account_specs_for_benchmark(bench_id) if instruction_payload else []

        # Use the shared executor crate (perilune/executor) to run the compiled program.
        from pathlib import Path
        workspace_manifest = (Path(__file__).parent.parent / "executor" / "Cargo.toml").resolve()

        exec_command = [
            "cargo",
            "run",
            "--bin",
            "perilune-bench-executor",
            "--manifest-path",
            str(workspace_manifest),
            "--",
            str(artifact_path),
            program_id,
            "--instruction-data",
            instruction_hex,
        ] + account_spec_args

        print(f"Executing: {' '.join(exec_command)}")
        try:
            exec_result = subprocess.run(
                exec_command,
                cwd=perilune_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            print("--- Benchmark Executor Output ---")
            print(exec_result.stdout)
            if exec_result.stderr:
                print("--- Benchmark Executor Stderr (for metrics check) ---")
                print(exec_result.stderr)
            print("--- End Executor Output ---")

            # Extract and store metrics using multiple fallback strategies
            result = extract_and_store_metrics(exec_result, current_run_metrics, perilune_root, entrypoint_name)
            if result:
                results.append(result)

        except subprocess.CalledProcessError as exc:
            print_error(f"executing benchmark for {artifact_path}:")
            print("Stdout:", exc.stdout, file=sys.stderr)
            print("Stderr:", exc.stderr, file=sys.stderr)
        except Exception as exc:
            print_error(f"An unexpected error occurred during benchmark execution: {exc}")

    return results 