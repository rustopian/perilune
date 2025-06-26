#! /usr/bin/env python3

import argparse
import toml
import pathlib
import shutil
import subprocess
import sys
import os
import json
import time
import textwrap
import re
import orchestrator


from console_utils import (
    print_section,
    print_subsection,
    print_success,
    print_warning,
    print_error,
    print_result,
    print_build_info,
)
from builder import run_cargo_build
from rewriter import rewrite_sources_for_entrypoint
from entrypoint_config import ENTRYPOINT_DEPS

from helpers import (
    discover_crates,
    parse_function_path,
    format_features,
    replace_placeholders,
    get_workspace_dependencies_block,
    get_package_name_from_manifest,
)
from executor import perform_benchmark_runs
from reporter import generate_markdown_report, print_console_summary

# --- Constants ---
PERILUNE_ROOT = pathlib.Path(__file__).parent.parent.resolve()
WORKSPACE_ROOT = PERILUNE_ROOT
TEMPLATES_DIR = PERILUNE_ROOT / "scripts" / "benchmark_templates"
TARGET_DIR = PERILUNE_ROOT / "target" / "bench_gen"
BENCHED_CRATE_COPY_DIR_NAME = "benched_crate_src" # Dir name for the copied source


PINOCCHIO_PLACEHOLDER_LINE = "pinocchio = { workspace = true }"


# --- Main Logic ---

def main():
    orchestrator.run()


if __name__ == "__main__":
    main() 