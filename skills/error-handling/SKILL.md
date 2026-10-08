---
name: error-handling
description: Error handling patterns across languages, including when to catch, how to wrap and propagate errors with their cause, retry with backoff, timeouts, and user-facing vs internal messages. Use when adding error paths, fixing swallowed exceptions, or designing retries.
---

# Error Handling

## Principles
- Handle an error where you can do something useful. Otherwise propagate it.
- Never swallow. An empty `catch`, `except: pass`, or `_ = err` needs a comment naming why the failure is safe to ignore.
- Keep the cause. Wrap with context, do not replace: `failed to load config: <cause>`.
- Separate the message for the user from the detail for the log. Users get "could not save"; logs get the query, input ID, and stack.
- Fail closed on security checks. A failed auth lookup denies access.

## Retries
- Retry only idempotent operations, or ones with an idempotency key.
- Retry only transient failures: timeouts, 429, 502, 503, 504, connection reset. Never retry 400, 401, 403, 404, or 422.
- Exponential backoff with full jitter, capped attempts (3 to 5), and an overall deadline.

```text
delay = random(0, min(cap, base * 2^attempt))
```

## Timeouts
- Every outbound call has a timeout. A call with no timeout is a defect.
- Set the timeout from the caller's deadline, not a fixed large number.

## Language notes
- Python: catch specific exceptions. Use `raise NewError(...) from exc` to keep the chain.
- JavaScript and TypeScript: `await` every promise in a try block. Unhandled rejections crash Node 15+. Narrow `unknown` in catch before reading `.message`.
- Java and Kotlin: do not catch `Throwable` or `Exception` broadly except at a top-level boundary. Kotlin coroutines: never swallow `CancellationException`; rethrow it.
- Rust: return `Result`. Use `?` to propagate. Use `thiserror` for library errors and `anyhow` only at application edges, if those crates are already in the project.
- Go: wrap with `fmt.Errorf("...: %w", err)` and check with `errors.Is`.

## Checklist for a new error path
- Is the failure visible to the caller or logged once at the boundary, not both?
- Is there a test that triggers the failure?
- Is partial work rolled back or made idempotent?
