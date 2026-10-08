---
name: rust-patterns
description: Rust ownership, borrowing, error handling with Result, iterator and lifetime idioms, and concurrency basics for libraries and binaries. Use when writing or reviewing Rust code or Cargo configuration.
---

# Rust Patterns

Check `rust-version` in `Cargo.toml` and the toolchain file before using newer language features.

## Ownership and borrowing
- Take `&str` and `&[T]` in function parameters; return owned `String` and `Vec<T>`.
- Clone to satisfy the borrow checker only after checking the borrow is not needed. Note the clone if it is on a hot path.
- Do not store references in structs unless the lifetime is obvious. Owned fields first.

## Errors
- Return `Result<T, E>` for recoverable failures. Use `?` to propagate.
- Libraries: define an error enum (`thiserror` if the crate already depends on it).
- Binaries at the top level: `anyhow::Result` if already in use; otherwise a plain `Box<dyn Error>`.
- Do not `unwrap()` or `expect()` on input from outside the program. `expect` messages must state the invariant.

```rust
let port: u16 = value.parse().map_err(|e| ConfigError::BadPort { value: value.to_owned(), source: e })?;
```

## Iterators
- Chain iterator adapters instead of index loops. `collect::<Result<Vec<_>, _>>()` stops at the first error.
- `iter()` yields references, `into_iter()` consumes, `iter_mut()` yields mutable references.

## Option
- Use `ok_or` / `ok_or_else` to turn `Option` into `Result`.
- Use `if let` or `match` for two-branch cases; `map` and `and_then` for chains.

## Concurrency
- `Arc<Mutex<T>>` for shared mutable state. Keep the lock scope small and never hold it across an `.await`.
- Prefer message passing (`mpsc`, `tokio::sync::mpsc`) when the state has one owner.
- In async code, use the runtime's async mutex if a lock must cross an await point.

## Unsafe
- Avoid `unsafe`. When it is required, add a `// SAFETY:` comment that states the invariant the caller must uphold, and keep the block minimal.

## Tooling
- Run `cargo clippy --all-targets` and `cargo test`. Report what passed.
- `cargo fmt --check` in CI. Do not reformat unrelated files.

## Dependencies
- Confirm a crate exists and is maintained with `cargo search <name>` and the crate's repository before adding it.
