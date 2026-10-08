# Java rules

- Check the release level in the build file before using newer language features.
- Records for immutable data. Defensive copies of collections in constructors.
- Never return null for a collection; return an empty one.
- Catch specific exceptions. Preserve the cause when wrapping.
- Use try-with-resources for every `AutoCloseable`.
- Shut down executors you create. Do not create a thread per request.
- Use `java.time`. Do not add `java.util.Date` to new code.
- Confirm a new dependency's coordinates and version on Maven Central before adding.
