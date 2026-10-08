# Kotlin rules

- Keep types non-null unless null is a real value. No `!!` without a comment naming why it cannot be null.
- Model closed variants with `sealed` and exhaustive `when`.
- Never swallow `CancellationException`. Rethrow it when catching broad exceptions.
- Blocking I/O runs on `Dispatchers.IO`.
- Do not launch work into `GlobalScope`. Use a scope the caller owns.
- Expose read-only collections and `Flow` from public APIs.
- Confirm a new library coordinate on Maven Central before adding.
