---
name: java-patterns
description: Modern Java (17 and later) idioms covering records, sealed types, Optional, streams, exceptions, resource handling, immutability, null safety, and build hygiene for Maven or Gradle projects. Use when writing or reviewing Java code.
---

# Java Patterns

Check the release level in `pom.xml` (`maven.compiler.release`) or `build.gradle` (`toolchain`) before using newer features. Records need 16+, sealed types 17+, pattern matching for `switch` 21+.

## Data
- Use `record` for immutable data carriers. Validate in the compact constructor.

```java
public record Port(int value) {
    public Port {
        if (value < 1 || value > 65535) throw new IllegalArgumentException("port " + value);
    }
}
```

- Use `List.copyOf` and `Map.copyOf` to defensively copy collections in constructors.

## Null handling
- Do not return `null` from methods that return collections. Return an empty collection.
- `Optional` for return values only. Not for fields or parameters.
- Avoid `Optional.get()` without `isPresent()`. Use `orElseThrow()` with a message.

## Sealed hierarchies
- Model closed sets of variants with `sealed` interfaces and `record` implementations. Use exhaustive `switch` expressions with pattern matching (Java 21+).

## Streams
- Use streams for transformations, loops for side effects. A `forEach` that mutates outside state is a loop; write it as one.
- Do not use parallel streams without measuring. They share the common pool.

## Exceptions
- Catch specific exceptions. Do not catch `Exception` or `Throwable` except at the top-level boundary.
- Use try-with-resources for anything `AutoCloseable`.
- Do not use exceptions for normal control flow.
- Preserve the cause: `throw new ServiceException("load failed", e)`.

## Concurrency
- Use `ExecutorService` from a managed pool; shut it down. Do not create threads per request.
- `CompletableFuture`: always supply an executor for blocking work, and handle exceptions with `exceptionally` or `handle`.
- Prefer immutable objects shared between threads over locks.

## Strings and formatting
- Use `String.formatted` or text blocks (15+) for multi-line text. Use `StringBuilder` in loops.
- Use `java.time` for dates. Never `java.util.Date` in new code.

## Build and dependencies
- Maven: run `mvn -q verify`; Gradle: `./gradlew check`. Report the result.
- Before adding a dependency, confirm the coordinates on Maven Central and check the version exists.
- Keep the Spring Boot or framework BOM as the single source of versions when the project uses one.
