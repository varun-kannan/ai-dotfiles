---
name: kotlin-patterns
description: Idiomatic Kotlin covering null safety, data classes, sealed hierarchies, scope functions, collections, coroutines and structured concurrency, Flow, and Gradle Kotlin DSL hygiene. Use when writing or reviewing Kotlin code or Gradle build files.
---

# Kotlin Patterns

Check the Kotlin version in `build.gradle.kts` or the version catalog before using newer APIs.

## Null safety
- Keep types non-null by default. Use `?` only where null is a real value.
- Prefer `?.`, `?:`, and `let` over `!!`. `!!` needs a comment naming why it cannot be null.
- Use `requireNotNull(x) { "message" }` at boundaries instead of `!!`.

## Data and types
- Use `data class` for value holders. Use `copy()` for changes; do not mutate with `var` fields.
- Model closed variants with `sealed interface` and exhaustive `when`.
- Use `value class` for typed IDs to avoid mixing them up.

## Collections
- Prefer read-only interfaces (`List`, `Map`) in signatures. Use `mutableListOf` only locally.
- Use `asSequence()` for long chains over large collections; plain lists for small ones.

## Scope functions
- `let` for nullable transforms, `apply` for configuring an object, `also` for side effects, `run` for computing a value from an object. Do not nest them.

## Coroutines
- Use `coroutineScope` or `supervisorScope` to tie child work to the caller. Do not launch into `GlobalScope`.
- Never swallow `CancellationException`. If you catch `Exception`, rethrow it: `catch (e: CancellationException) { throw e }`.
- Blocking calls (JDBC, file I/O) go on `Dispatchers.IO`, not `Default`.
- Use `withTimeout` or `withTimeoutOrNull` for external calls.

## Flow
- Expose `Flow` or `StateFlow` from repositories. Collect in a lifecycle-aware scope.
- Use `flowOn` to change the dispatcher upstream of a collector. Do not wrap `collect` in `withContext` to do the same.

## Errors
- Use `Result` for expected failures at boundaries. Use exceptions for programming errors.
- Do not use `runCatching` around suspend calls without checking cancellation.

## Gradle (Kotlin DSL)
- Use the version catalog (`libs.versions.toml`) if the project has one.
- Run `./gradlew check`. Report the result.
- Confirm a library coordinate on Maven Central before adding it.
