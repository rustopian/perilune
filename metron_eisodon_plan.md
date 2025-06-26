# Metron Eisodon: Pluggable Benchmarking Framework Plan

## 1. Goal

To create **Metron Eisodon** (Greek: Μέτρον Εἰσόδων - "Measure of the Entry Points"), a framework for accurately benchmarking the compute unit (CU) cost of specific Rust code snippets within different Solana runtime environments (`solana-program` standard library, `solana-program` no-std, Pinocchio) without incurring Cross-Program Invocation (CPI) overhead. The framework should be \"pluggable,\" allowing users to easily add their own code snippets for benchmarking against various data sets and configurations.

## 2. Core Architecture: Trait-Based with Compile-Time Features

This architecture uses a central trait definition, separate crates for user implementations and runner programs, and leverages Cargo features for compile-time selection of the correct code paths.

**Key Components:**

1.  **`eisodos-core` (New Crate):** A small library crate defining the core `EisodosBenchTarget` trait.
2.  **`eisodos-user-benchmarks` (New Crate):** A workspace library crate where users add modules implementing the `EisodosBenchTarget` trait for their code snippets. Implementations for different environments are conditionally compiled using features.
3.  **`eisodos/programs/` (Modified Directory):** Contains the generic *runner* programs (e.g., `sdk-runner`, `pinocchio-runner`, `nostd-runner`). Each runner depends on `eisodos-user-benchmarks` with a specific feature enabled (`sdk`, `pinocchio`, or `nostd`) and dispatches calls to the appropriate trait implementation based on instruction data.
4.  **`eisodos/benchmark/` (Existing Crate):** The main benchmark suite crate.
    *   Depends on `mollusk-svm-bencher`, `eisodos-user-benchmarks` (for type info/IDs if needed), and shared setup utilities.
    *   `benches/*.rs`: Files define specific benchmark scenarios, configure accounts/data, select the appropriate runner SBF, and specify which user benchmark target to execute via instruction data.
    *   `src/setup/`: Contains reusable utilities (e.g., `generate_mock_slot_hashes_data`, account creation helpers).

## 3. Implementation Steps

**Step 3.1: Create `eisodos-core` Crate**

*   Create a new library crate: `cargo new eisodos-core --lib` (or manually add to workspace).
*   Add necessary minimal dependencies (e.g., `solana-program-error`, maybe `solana-pubkey` if using a common pubkey type).
*   Define the core trait:
    ```rust
    // eisodos-core/src/lib.rs
    use solana_program_error::{ProgramError, ProgramResult};
    // Use a common Pubkey type if possible, maybe from solana-pubkey directly
    use solana_pubkey::Pubkey; 

    /// Trait for code snippets benchmarkable by Metron Eisodon.
    /// Generic over the AccountInfo type provided by the specific runtime environment.
    pub trait EisodosBenchTarget<AccInfo> {
        /// Optional setup called once before the benchmark loop for this target.
        /// `bench_data`: Opaque data slice passed from benchmark setup for initialization.
        fn setup(
            program_id: &Pubkey,
            accounts: &[AccInfo],
            bench_data: &[u8]
        ) -> Result<Self, ProgramError> where Self: Sized;

        /// The core logic to be benchmarked. Called repeatedly.
        fn run(&mut self, accounts: &[AccInfo]) -> ProgramResult;
    }
    ```

**Step 3.2: Create `eisodos-user-benchmarks` Crate**

*   Create a new library crate: `cargo new eisodos-user-benchmarks --lib`.
*   Add it as a member to the root `eisodos/Cargo.toml` workspace definition.
*   In `eisodos-user-benchmarks/Cargo.toml`:
    *   Add `eisodos-core = { path = "../eisodos-core" }`.
    *   Define features: `features = ["sdk", "pinocchio", "nostd"]`.
    *   Add optional dependencies gated by these features:
        ```toml
        solana-program = { version = "1.18", optional = true }
        pinocchio = { version = "0.8", git = "https://github.com/rustopian/pinocchio.git", branch = "rustopian/slot-hashes-sysvar", optional = true }
        solana-nostd-entrypoint = { version = "0.6", optional = true }
        # Add other conditional dependencies needed by user benchmarks
        ```
    *   Define feature activations:
        ```toml
        [features]
        default = []
        sdk = ["dep:solana-program"]
        pinocchio = ["dep:pinocchio"]
        nostd = ["dep:solana-nostd-entrypoint"]
        ```
*   In `eisodos-user-benchmarks/src/lib.rs`:
    *   Declare public modules for each user benchmark: `pub mod slot_hashes_example;`
*   In `eisodos-user-benchmarks/src/slot_hashes_example.rs` (example):
    *   Implement `EisodosBenchTarget` for different `AccountInfo` types under `#[cfg(feature = "...")]`.
    ```rust
    use eisodos_core::EisodosBenchTarget;
    use solana_program_error::{ProgramError, ProgramResult};
    use solana_pubkey::Pubkey;

    #[cfg(feature = "sdk")]
    mod sdk {
        use super::*;
        use solana_program::account_info::AccountInfo;
        use solana_program::sysvar::slot_hashes::SlotHashes; // SDK type

        #[derive(Default)]
        pub struct SlotHashesBenchSdk;
        impl EisodosBenchTarget<AccountInfo<'_>> for SlotHashesBenchSdk {
            fn setup(/*...*/) -> Result<Self, ProgramError> { Ok(Self) }
            fn run(&mut self, accounts: &[AccountInfo]) -> ProgramResult {
                let sysvar_account = &accounts[0]; // Assume index 0
                let _slot_hashes = SlotHashes::from_account_info(sysvar_account)?;
                // Perform SDK-specific operation
                Ok(())
            }
        }
    }
    #[cfg(feature = "sdk")] pub use sdk::*;

    #[cfg(feature = "pinocchio")]
    mod pinocchio_impl {
        use super::*;
        use pinocchio::account_info::AccountInfo;
        use pinocchio::sysvars::slot_hashes::SlotHashes; // Pinocchio type

        #[derive(Default)]
        pub struct SlotHashesBenchPinocchio;
        impl EisodosBenchTarget<AccountInfo<'_>> for SlotHashesBenchPinocchio {
            fn setup(/*...*/) -> Result<Self, ProgramError> { Ok(Self) }
            fn run(&mut self, accounts: &[AccountInfo]) -> ProgramResult {
                 let sysvar_account = &accounts[0]; // Assume index 0
                let _slot_hashes = SlotHashes::from_account_info(sysvar_account)?;
                 // Perform Pinocchio-specific operation
                Ok(())
            }
        }
    }
     #[cfg(feature = "pinocchio")] pub use pinocchio_impl::*;
     // ... add nostd implementation ...
    ```

**Step 3.3: Refactor Runner Programs (`eisodos/programs/`)**

*   Rename existing programs (e.g., `eisodos-pinocchio` -> `eisodos-pinocchio-runner`).
*   For each runner (e.g., `eisodos-pinocchio-runner`):
    *   Update `Cargo.toml`:
        *   Remove dependencies specific to old benchmark logic.
        *   Add `eisodos-core = { path = "../../eisodos-core" }`.
        *   Add `eisodos-user-benchmarks = { path = "../../eisodos-user-benchmarks", default-features = false, features = ["pinocchio"] }` (Enable *only* the feature relevant to this runner).
        *   Keep the primary SDK dependency (`pinocchio`).
    *   Update `src/lib.rs`, `src/entrypoint.rs` as needed (standard program setup).
    *   Update `src/processor.rs`:
        *   Remove old `process_*` functions.
        *   Import necessary types from `eisodos_user_benchmarks::*`.
        *   Implement the main `process_instruction`:
            *   Deserialize a `target_id` (e.g., a `u8` or `u16`) from `instruction_data`.
            *   Deserialize any `bench_data` needed for `setup` from the rest of `instruction_data`.
            *   Use a `match` statement on `target_id` to call a generic `run_bench` function with the correct user benchmark type.
        *   Implement `run_bench<T: EisodosBenchTarget<AccountInfoType>>`:
            *   Call `T::setup(...)`.
            *   Call `target.run(...)`.
*   *(Repeat for `sdk-runner` and `nostd-runner`, adjusting dependencies and feature flags)*.

**Step 3.4: Refactor Benchmark Crate (`eisodos/benchmark/`)**

*   Update `Cargo.toml`:
    *   Remove `dev-dependencies` on the old program crates (`eisodos-pinocchio`, etc.).
    *   Add `dev-dependency` on `eisodos-user-benchmarks = { path = "../eisodos-user-benchmarks" }` (no specific features needed here, maybe just for type definitions or target IDs).
    *   Ensure setup utilities dependencies are present (`solana-account`, `solana-instruction`, etc.).
*   Update `src/setup/mod.rs`: Keep/refine data generation utilities like `generate_mock_slot_hashes_data`. The `DecrementStrategy` enum might move to `eisodos-core` if needed by `setup`.
*   Refactor `src/setup/runner.rs`: The `run` function is likely removed or significantly simplified. The core benchmarking logic moves to the individual `benches/*.rs` files.
*   Update/Create `benches/*.rs` files (e.g., `benches/slot_hashes.rs`):
    *   For each benchmark target (e.g., SlotHashes):
        *   Define benchmark functions for each environment (e.g., `bench_pinocchio_slot_hashes`, `bench_sdk_slot_hashes`).
        *   Inside each function:
            *   Instantiate `MolluskComputeUnitBencher`, pointing it to the correct runner SBF (e.g., `../target/deploy/eisodos-pinocchio-runner.so`).
            *   Define the `target_id` corresponding to the implementation (e.g., `0` for `SlotHashesBenchPinocchio`).
            *   Loop through data variations (e.g., `DecrementStrategy`).
            *   Generate necessary accounts using setup utilities (including the sysvar account *and* the runner program account).
            *   Generate `instruction_data` containing the `target_id` and any `bench_data` needed by the target's `setup` function.
            *   Generate a descriptive benchmark ID string (e.g., `format!("pinocchio: SlotHashesGetEntry ({})", strategy_name)`).
            *   Store the `(id, instruction, accounts)` tuple in a `benchmark_data` vector.
        *   After generating all variations for that environment:
            *   Iterate through `benchmark_data` and call `bencher.bench((id.as_str(), instruction, accounts))`.
            *   Call `bencher.execute()`.

## 4. User Workflow for Adding New Benchmarks

1.  **Define Logic:** Create a new module (e.g., `my_new_test.rs`) in `eisodos-user-benchmarks/src/`.
2.  **Implement Trait:** Inside the module, create a struct (e.g., `MyNewTestSdk`) and implement `EisodosBenchTarget<RelevantAccountInfo>` for each desired environment (`sdk`, `pinocchio`, `nostd`), using `#[cfg(feature = "...")]`.
3.  **Register Module:** Add `pub mod my_new_test;` to `eisodos-user-benchmarks/src/lib.rs`.
4.  **Assign ID:** Choose a unique ID (e.g., `u8`).
5.  **Update Runners:** Add a `match` arm for the new ID in the relevant runner program processors (`eisodos/programs/*/src/processor.rs`), calling `run_bench::<my_new_test::MyNewTestSdk>(...)`.
6.  **Add Benchmark:** Create or modify a file in `eisodos/benchmark/benches/`. Configure the accounts, instruction data (including the `target_id`), and call `bencher.bench()` with appropriate labels for each environment and data variation.
7.  **Build & Run:** Build the necessary runner programs (`cargo build-sbf --manifest-path eisodos/programs/.../Cargo.toml`) and run the benchmarks (`cargo bench --manifest-path eisodos/benchmark/Cargo.toml`).

## 5. Future Enhancements

*   **Proc Macro for Dispatch:** Create a procedural macro to automatically scan `eisodos-user-benchmarks` and generate the `match target_id` dispatch logic in the runner programs, reducing boilerplate.
*   **More Sophisticated Data Generation:** Enhance the setup utilities for generating more complex account states or instruction data patterns.
*   **Typed Bench Data:** Define a trait or enum for `bench_data` in `eisodos-core` instead of using `&[u8]` to provide more type safety for benchmark setup parameters.

This plan leverages Rust's type system and features for a relatively clean separation, prioritizes accuracy by avoiding CPIs, and provides a structured (though initially slightly manual) way for users to plug in their code. 