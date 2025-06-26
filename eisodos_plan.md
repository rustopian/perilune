# Eisodos Olympia: Pluggable Benchmarking Framework Plan

## 1. Goal

To create **Eisodos Olympia** (Greek: είσοδος - "entry point", combined with Olympia, home of the ancient games, signifying peak performance testing), a framework for accurately benchmarking the compute unit (CU) cost of specific Rust code snippets within different Solana runtime environments (`solana-program` standard library, `solana-program` no-std, Pinocchio) without incurring Cross-Program Invocation (CPI) overhead. The framework should be "pluggable," allowing users to easily add their own code snippets for benchmarking against various data sets and configurations.
 
// ... rest of file content ... 