"""
Metrics parsing utilities for benchmark execution results.
"""
import pathlib
import re
from typing import Dict, Any, Optional
from console_utils import print_warning, print_result


def parse_metrics_from_output(exec_result, current_run_metrics: Dict[str, Any]) -> bool:
    """Parse metrics from benchmark executor output.
    
    Returns True if metrics were successfully parsed, False otherwise.
    """
    in_metrics = False
    for line in exec_result.stdout.splitlines():
        if line.strip() == "--- Benchmark Metrics ---":
            in_metrics = True
            continue
        if line.strip() == "--- End Metrics ---":
            in_metrics = False
            break
        if in_metrics:
            if ":" in line:
                k, v = [p.strip() for p in line.split(":", 1)]
                try:
                    current_run_metrics[k] = int(v)
                except ValueError:
                    current_run_metrics[k] = v
    
    return "MedianComputeUnits" in current_run_metrics


def parse_metrics_from_markdown(perilune_root: pathlib.Path, current_run_metrics: Dict[str, Any], 
                               entrypoint_name: str) -> bool:
    """Parse metrics from Mollusk markdown output as fallback.
    
    Returns True if metrics were successfully parsed, False otherwise.
    """
    md_path = pathlib.Path(perilune_root) / "benchmark" / "benches" / "compute_units.md"
    if not md_path.is_file():
        return False
        
    base_name = current_run_metrics["id"].split("_default_run")[0].split("_accounts_")[0].split("_custom_payload")[0]
    ep_token = entrypoint_name.replace("-", "_")
    
    try:
        with md_path.open("r", encoding="utf-8") as md_f:
            for md_line in md_f:
                md_line = md_line.strip()
                if md_line.startswith("| ") and "|" in md_line[1:] and not md_line.startswith("| ---"):
                    cols = [c.strip() for c in md_line.strip("|").split("|")]
                    if len(cols) >= 2:
                        bench_name_col = cols[0]
                        if base_name in bench_name_col and ep_token in bench_name_col:
                            try:
                                cu_val = int(cols[1].replace(",", ""))
                                current_run_metrics["MedianComputeUnits"] = cu_val
                                current_run_metrics["BenchmarkName"] = bench_name_col
                                return True
                            except ValueError:
                                pass
                            break
    except Exception as md_exc:
        print_warning(f"Failed to parse {md_path}: {md_exc}")
    
    return False


def parse_metrics_from_logs(exec_result, current_run_metrics: Dict[str, Any]) -> bool:
    """Parse metrics from log output as final fallback.
    
    Returns True if metrics were successfully parsed, False otherwise.
    """
    for _stream in (exec_result.stdout, exec_result.stderr):
        match = re.search(r"consumed\s+(\d+)\s+of", _stream)
        if match:
            current_run_metrics["MedianComputeUnits"] = int(match.group(1))
            current_run_metrics["BenchmarkName"] = current_run_metrics["id"]
            return True
    return False


def extract_and_store_metrics(exec_result, current_run_metrics: Dict[str, Any], 
                            perilune_root: pathlib.Path, entrypoint_name: str) -> Optional[Dict[str, Any]]:
    """Extract metrics from executor output using multiple fallback strategies.
    
    Returns the metrics dict if successful, None otherwise.
    """
    # Try primary method: parse from structured output
    if parse_metrics_from_output(exec_result, current_run_metrics):
        print_result(
            f"Storing result for: {current_run_metrics['id']} -> {current_run_metrics['MedianComputeUnits']} CUs"
        )
        return current_run_metrics
    
    # Fallback 1: parse Mollusk markdown
    if parse_metrics_from_markdown(perilune_root, current_run_metrics, entrypoint_name):
        print_result(
            f"Storing result for: {current_run_metrics['id']} -> {current_run_metrics['MedianComputeUnits']} CUs (markdown fallback)"
        )
        return current_run_metrics
    
    # Fallback 2: scan logs for 'consumed N of'
    if parse_metrics_from_logs(exec_result, current_run_metrics):
        print_result(
            f"Storing result for: {current_run_metrics['id']} -> {current_run_metrics['MedianComputeUnits']} CUs (log fallback)"
        )
        return current_run_metrics
    
    # No metrics found
    print_warning(f"No compute unit data found for: {current_run_metrics['id']}")
    return None 