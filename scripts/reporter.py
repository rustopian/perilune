from __future__ import annotations

import pathlib
import textwrap
from typing import List, Dict, Any

from console_utils import print_section, print_success

__all__ = ["generate_markdown_report", "print_console_summary"]


def _human_size(num_bytes: int | float | None) -> str:
    if num_bytes is None or not isinstance(num_bytes, (int, float)):
        return "N/A"
    return f"{num_bytes} ({num_bytes/1024:.1f} KB)"


def generate_markdown_report(results: List[Dict[str, Any]], md_path: pathlib.Path) -> None:
    """Write the benchmark *results* to a markdown table at *md_path*."""
    if not results:
        return

    headers = [
        "ID",
        "Entrypoint",
        "Features",
        "AccountsProcessed",
        "BuildTimeSeconds",
        "ProgramSizeBytes",
        "BenchmarkName",
        "MedianComputeUnits",
        "TotalComputeUnits",
        "InstructionsExecuted",
        "Program ID",
        "Artifact",
    ]

    md_path.write_text("", encoding="utf-8")  # ensure dir exists later if needed
    md_path.parent.mkdir(parents=True, exist_ok=True)

    with md_path.open("w", encoding="utf-8") as md_file:
        md_file.write("# Perilune Benchmark Results\n\n")
        md_file.write("| " + " | ".join(headers) + " |\n")
        md_file.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for row in results:
            features = row.get("features", [])
            if isinstance(features, list):
                features = ", ".join(features) if features else "none"

            program_size_display = _human_size(row.get("ProgramSizeBytes"))

            display_map = {
                "ID": row.get("id", "N/A"),
                "Entrypoint": row.get("entrypoint", "N/A"),
                "Features": features,
                "AccountsProcessed": row.get("AccountsProcessed", "N/A"),
                "BuildTimeSeconds": row.get("BuildTimeSeconds", "N/A"),
                "ProgramSizeBytes": program_size_display,
                "BenchmarkName": row.get("BenchmarkName", "N/A"),
                "MedianComputeUnits": row.get("MedianComputeUnits", "N/A"),
                "TotalComputeUnits": row.get("TotalComputeUnits", "N/A"),
                "InstructionsExecuted": row.get("InstructionsExecuted", "N/A"),
                "Program ID": row.get("program_id", "N/A"),
                "Artifact": row.get("artifact", "N/A"),
            }

            pid = display_map["Program ID"]
            if isinstance(pid, str) and len(pid) > 8:
                display_map["Program ID"] = f"{pid[:4]}...{pid[-4:]}"

            row_markdown = "| " + " | ".join(str(display_map[h]) for h in headers) + " |"
            md_file.write(row_markdown + "\n")

    print_success(f"Report generated: {md_path}")


def print_console_summary(results: List[Dict[str, Any]]) -> None:
    """Pretty-print a condensed summary of *results* to the console."""
    if not results:
        print("\nNo benchmark results to report.")
        return

    print_section("\n=== Benchmark Summary ===")
    headers = ["crate", "instruction", "entrypoint", "build_time", "program_size", "CUs"]
    col_widths = [12, 12, 20, 12, 14, 8]

    def _wrap(cell: str, width: int):
        if not cell or cell == "N/A":
            return [cell]
        return textwrap.wrap(str(cell), width=width) or [str(cell)]

    def _print_row(cells: List[str]):
        wrapped = [_wrap(c, w) for c, w in zip(cells, col_widths)]
        max_lines = max(len(x) for x in wrapped)
        for idx in range(max_lines):
            parts = [(
                wrapped[i][idx] if idx < len(wrapped[i]) else ""
            ).ljust(col_widths[i]) for i in range(len(col_widths))]
            print("| " + " | ".join(parts) + " |")

    _print_row(headers)
    print("| " + " | ".join("-" * w for w in col_widths) + " |")

    for row in results:
        build_time = row.get("BuildTimeSeconds", "N/A")
        if isinstance(build_time, (int, float)):
            build_time = f"{build_time:.2f}s"
        program_size = row.get("ProgramSizeBytes", "N/A")
        if isinstance(program_size, (int, float)):
            program_size = f"{program_size/1024:.1f}KB"

        cells = [
            row.get("crate", "N/A"),
            (
                f"{row.get('instruction', 'N/A')} (N={row['AccountsProcessed']})"
                if row.get("AccountsProcessed") not in (None, 1)
                else row.get("instruction", "N/A")
            ),
            row.get("entrypoint", "N/A"),
            str(build_time),
            str(program_size),
            str(row.get("MedianComputeUnits", "N/A")),
        ]
        _print_row(cells) 