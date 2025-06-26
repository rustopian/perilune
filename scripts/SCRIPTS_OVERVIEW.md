# Perilune Scripts Overview

This document provides a comprehensive overview of the Python scripts in the `/perilune/scripts` folder, which collectively form the **Perilune** benchmarking system for Solana programs across different entrypoint implementations.

## System Purpose

The Perilune system is designed to benchmark Solana programs compiled with different entrypoint frameworks (Pinocchio, Solana Program breakout crates, monolithic Solana Program, etc.) to measure and compare their compute unit (CU) efficiency, build times, and binary sizes. It automates the process of:

1. **Source code transformation** - Converting programs between different Solana SDK formats
2. **Dependency management** - Injecting appropriate dependencies for each entrypoint
3. **Program compilation** - Building programs with different entrypoint configurations
4. **Benchmark execution** - Running performance tests using Mollusk SVM
5. **Results analysis** - Parsing metrics and generating comparison reports

## Script Breakdown

### Core Orchestration

#### `orchestrator.py` (769 lines)
**Domain**: Main workflow coordination and full program benchmarking

The central orchestrator that coordinates the entire benchmarking pipeline. Key responsibilities:
- **CLI argument parsing** - Handles user input for crate paths and entrypoint selection
- **Crate discovery** - Finds benchmark-enabled crates (containing `perilune_benchmarks.toml`)
- **Full program benchmarking** - Clones external git repositories, applies entrypoint transformations, and builds complete programs
- **Example-crate benchmarking** – Builds and benches *local* example crates in addition to full-program runs
- **Feature injection & manifest patching** – Auto-adds or strips `no_std`, `std`, `host`, etc. features for the target entrypoint and rewrites `Cargo.toml`
- **Mollusk SVM integration** - Creates and executes Criterion-based benchmarks using Mollusk SVM for full program testing
- **Entrypoint compatibility detection** - Analyzes existing programs to determine if source rewriting is needed
- **Workspace management** - Creates isolated build environments for each benchmark configuration
- **Results aggregation** - Collects all benchmark results for final reporting

**Key functions**:
- `_clone_and_build_program()` - Handles external program compilation with specific entrypoints
- `_create_mollusk_benchmark()` - Sets up Criterion benchmarks for full program testing
- `_process_full_program_benchmark()` - Orchestrates complete program benchmark workflows
- `_build_runner_workspace()` – Generates a temp workspace to build & run **example-crate** benches (copying/re-writing the crate, wiring templates)
- `generate_markdown_report()/print_console_summary()` – Called at the end of `run()` to emit human- and machine-readable results
- `run()` - Main entry point that coordinates the entire pipeline

#### `run_perilune_benchmarks.py` (59 lines)
**Domain**: Thin entry-point wrapper

Besides delegating to `orchestrator.run()`, this script re-exports several constants (`TARGET_DIR`, `TEMPLATES_DIR`, etc.) that other tools may import when it is the process root, preserving legacy behaviour.

### Source Code Transformation

#### `rewriter.py` (753 lines)
**Domain**: Rust source code transformation and entrypoint adaptation

The most complex script responsible for transforming Rust source code to work with different Solana entrypoint frameworks. Uses a two-phase approach:

**Phase 1 - Normalization**: Converts any source format to a canonical "breakout crates" intermediate representation
**Phase 2 - Denormalization**: Transforms from the intermediate format to the target entrypoint format

Key capabilities:
- **Import rewriting** - Transforms `use` statements between different SDK formats (e.g., `solana_program::pubkey::Pubkey` ↔ `pinocchio::pubkey::Pubkey`)
- **Identifier mapping** - Maps function calls and type references across entrypoint APIs
- **No-std adaptation** - Ensures Pinocchio programs use `#![no_std]` with appropriate allocator/panic handlers
- **AccountInfo aliasing** - Handles type compatibility issues between different account info implementations
- **CPI pattern rewriting** - Transforms cross-program invocation patterns for different frameworks
- **Module structure cleanup & fix-ups**
  - Deduplicates `use` lines, injects `use super::*;` into nested modules, and auto-closes unbalanced braces
  - Provides helper class hierarchy: `EntrypointRewriter` subclasses + `ContentProcessor` orchestrate per-entrypoint rewrites
  - Entry-point specific utilities (`_ensure_pinocchio_handlers`, `_ensure_nostd_entrypoint_alias`) patch `lib.rs` and imports after rewrites

**Entrypoint-specific transformations**:
- **Pinocchio**: Strips allocator macros, ensures no-std compatibility, maps to Pinocchio APIs
- **Solana Program breakout**: Maps to individual fine-grained Solana crates
- **Solana Program mono**: Maps to monolithic `solana-program` crate
- **Solana nostd-entrypoint**: Handles the experimental no-std entrypoint with special AccountInfo handling

#### `import_processor.py` (342 lines)
**Domain**: Rust import statement analysis and generation

Specialized module for processing Rust `use` statements with sophisticated parsing capabilities:

- **Top-level grouped import parsing** – Correctly handles constructs such as `use {Foo, bar::Baz}` via `_process_top_level_grouped_import()`
- **Identifier scanning** - Detects implicitly used identifiers that need imports (e.g., `msg!`, `invoke`)
- **Clean import generation** - Creates minimal, properly formatted import statements for target entrypoints
- **Grouped import handling** - Manages both top-level and nested grouped imports
- **Alias preservation** - Maintains proper `as` aliases when transforming between entrypoints
  - Special‐case alias insertion for `solana-nostd-entrypoint` (e.g. `NoStdAccountInfo as AccountInfo`).

**Key functions**:
- `extract_all_imported_identifiers()` - Comprehensive import parsing with nested group support
- `generate_target_imports()` - Creates clean imports for specific entrypoint frameworks
- `strip_imports_and_generate_clean_imports()` - Main transformation pipeline

### Configuration and Mappings

#### `entrypoint_config.py` (324 lines)
**Domain**: Entrypoint configuration and transformation mappings

Central configuration defining how to transform code between different Solana entrypoint frameworks:

**Transformation patterns**:
- `NORMALIZE_TO_BREAKOUT` - Regex patterns to convert any format to breakout crates
- `DENORMALIZE_FROM_BREAKOUT` - Patterns to convert from breakout to target formats
- `IDENTIFIER_MAPPINGS` - Function and type mappings for each entrypoint

**Dependency specifications**:
- `ENTRYPOINT_DEPS` - Dependency strings for Cargo.toml generation
- `BENCHED_CRATE_DEPS` - Complete dependency configurations for each entrypoint

**Supported entrypoints**:
- `pinocchio` - Zero-dependency Solana SDK with no-std focus
- `solana-program` - Modern breakout crates approach
- `solana-program-mono` - Legacy monolithic SDK
- `solana-nostd-entrypoint` - Experimental no-std implementation
- `pinocchio-std` - Pinocchio with standard library features enabled

Additional details:
- Exports helper constants like `_COMMON_IDENTIFIERS`, `_SPL_IDENTIFIERS` and builder `_build_identifier_mapping()` which auto-generate large portions of `IDENTIFIER_MAPPINGS`.
- Includes a dedicated mapping/dependency section for the pseudo-entrypoint **`pinocchio-std`**.

### Build and Execution

#### `builder.py` (143 lines)
**Domain**: Solana program compilation

Handles the compilation of Solana programs using `cargo-build-sbf`:

- **Build orchestration** - Executes `cargo-build-sbf` with proper environment setup
- **Artifact verification** - Confirms `.so` files and keypairs are generated correctly
- **Program ID extraction** - Uses `solana-keygen` to extract program IDs from keypairs
- **Build metrics** - Measures compilation time and binary size
- **Error handling** - Provides detailed diagnostics for build failures
- Sets `RUSTFLAGS='--cfg getrandom_backend="custom"'` so the `getrandom` crate compiles for SBF.

**Return values**: `(artifact_path, program_id, build_time_seconds, program_size_bytes)` – four items (size previously unmentioned).

**Key outputs**:
- Program artifact path (`.so` file)
- Program ID (extracted from keypair)
- Build time in seconds
- Program size in bytes

#### `executor.py` (197 lines)
**Domain**: Benchmark execution and instruction processing

Manages the execution of compiled programs through the Perilune benchmark executor:

- **Instruction payload serialization** - Converts benchmark configurations into raw instruction bytes
- **Account setup matrix** - Handles different account count configurations for scaling tests
- **Executor invocation** - Runs the `perilune-bench-executor` binary with proper arguments
- **Multiple run variants** - Supports custom payloads, account count variations, and default ping tests
- **Results aggregation** - Collects execution results for each benchmark variant
- **Classifies each run's **instruction type** (e.g. transfer, create_account) for summary tables.

**Supported instruction types**:
- Transfer operations with amount encoding
- Create account operations with lamports/space encoding
- Ping operations for basic functionality testing
- Custom payload configurations

### Results Processing

#### `metrics_parser.py` (113 lines)
**Domain**: Performance metrics extraction and parsing

Extracts compute unit and performance metrics from benchmark execution with multiple fallback strategies:

Parsing order:
1. Structured executor output (`--- Benchmark Metrics ---` block)
2. Mollusk *Markdown* file fallback (`compute_units.md`)
3. Regex scan of logs for `consumed N of` pattern

Fields like *TotalComputeUnits* and *InstructionsExecuted* are only propagated if supplied by the executor; the parser does not derive them itself.

**Metrics extracted**:
- Median compute units consumed
- Total compute units
- Instructions executed
- Benchmark names and identifiers

**Resilience features**:
- Multiple parsing strategies to handle different output formats
- Graceful degradation when primary methods fail
- Detailed warning messages for debugging

#### `reporter.py` (124 lines)
**Domain**: Results formatting and report generation

Generates comprehensive reports from benchmark results:

**Markdown reporting**:
- Tabular format with all benchmark metrics
- Program ID truncation for readability
- Build time and program size formatting
- Feature list formatting

**Console summary**:
- Condensed table format for quick review
- Text wrapping for long entries
- Human-readable size formatting (KB conversion)
- Account count annotations

Condensed table uses dynamic column-width wrapping and truncates long Program IDs (`abcd…wxyz`). Utility `_human_size()` converts bytes → "KB".

**Report columns**:
- Benchmark ID and entrypoint
- Account processing counts
- Build metrics (time, size)
- Performance metrics (compute units)
- Program identification

### Utility and Support

#### `helpers.py` (140 lines)
**Domain**: Common utility functions and workspace operations

Provides shared functionality used across the system:

**Crate discovery**:
- Recursive search for `perilune_benchmarks.toml` files
- Path resolution and validation

**String processing**:
- Rust function path parsing (`crate::module::function`)
- Feature list formatting for Cargo.toml
- Template placeholder replacement

**Workspace operations**:
- Dependency extraction from workspace Cargo.toml
- Package name resolution from manifests
- TOML formatting utilities

Exports constants `PERILUNE_ROOT`, `WORKSPACE_ROOT` and helper `_format_toml_dict()` used to pretty-print inline TOML tables.

#### `console_utils.py` (66 lines)
**Domain**: Console output formatting and user feedback

Provides consistent, colored console output for user feedback:

**Color-coded messaging**:
- Section headers (bright cyan, bold)
- Success messages (green)
- Warnings (yellow to stderr)
- Errors (red to stderr)
- Build information (blue)
- Results (bright green, bold)

**Features**:
- ANSI color code management
- Proper stream routing (stdout/stderr)
- Consistent formatting across all scripts

#### `account_specs.py` (74 lines)
**Domain**: Account configuration for benchmark execution

Defines account specifications for different types of Solana operations:

**Account templates**:
- System operations (create account, transfer)
- Token operations (ATA creation, recovery)
- Sysvar access (slot hashes)

**Configuration mappings**:
- Account count requirements per benchmark type
- Account specification strings for executor
- Instruction type classification

**Account specification format**:
```
name:pubkey:is_signer:is_writable:lamports:data_len:owner
```

Adds templates for:
- **slot_hashes** sysvar benchmark
- **log** instruction benchmark (zero-account ping-style)

## Data Flow

1. **Discovery**: `helpers.py` finds benchmark-enabled crates
2. **Configuration**: `entrypoint_config.py` provides transformation rules
3. **Transformation**: `rewriter.py` and `import_processor.py`