---
name: performance-optimization
description: Measure-first performance work for any stack. Use when a request, job, test, or page is slow, memory grows, CPU is high, or a change must not regress speed. Covers profiling, query analysis, caching, and bundle size.
---

# Performance Optimization

## Rule
Measure, change one thing, measure again. A change without a before and after number is not an optimization.

## Baseline
1. Pick the workload: the endpoint, the input size, the command.
2. Record the number: wall time (p50 and p95 for services), peak memory, query count, bundle bytes.
3. Save the command so the measurement can be repeated.

## Finding the cost
- CPU: a sampling profiler. Python `cProfile` or `py-spy`; Node `--cpu-prof`; Java async-profiler or JFR; Rust `cargo flamegraph`; browser DevTools Performance tab.
- Memory: heap snapshots, or count live objects before and after the operation.
- Database: `EXPLAIN` (or `EXPLAIN ANALYZE`) on the slow query. Look for sequential scans on large tables and row estimates far from actual.
- Network: count round trips. Ten sequential calls where one batch call works is the usual cause.

## Common causes and fixes
- N+1 queries: load related rows in one query or a batch (`IN (...)`, DataLoader, `select_related` or `prefetch_related` in Django, eager fetch in JPA with care).
- Missing index: add it for the filter and sort columns the query uses. Confirm with `EXPLAIN` that it is used.
- Work inside a loop that does not depend on the loop variable: hoist it.
- Quadratic membership checks on lists: use a set or map.
- Unbounded caches: give them a size limit and a TTL.
- Synchronous I/O on a request path: move it to a queue or make it concurrent with a bounded pool.
- Large bundles: code-split routes, drop unused dependencies, import the function instead of the package.

## Caching
- Cache the expensive, stable result, not the raw data. Define the invalidation rule before adding the cache.
- Include the version or tenant in the key so one user never reads another's data.

## Report
Before, after, the command, the input size, and any trade-off (memory for speed, staleness for latency). Do not claim a speedup you did not measure.
