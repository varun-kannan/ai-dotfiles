---
name: database-patterns
description: Relational and document database design and query practice, covering schema normalization, indexing, transactions and isolation, N+1 avoidance, pagination, migrations, and choosing SQL vs NoSQL. Use when designing a schema, writing or reviewing queries, adding an index, or writing a migration.
---

# Database Patterns

Read the existing schema and migration history before proposing changes. Confirm the database engine and version from the config.

## Schema design
- Normalize to third normal form by default. Denormalize only for a measured read-path problem, and document the source of truth.
- Every table has a primary key. Prefer a surrogate key (`bigint` identity or UUID v7) plus natural unique constraints.
- Use `NOT NULL` unless absence is a real state. Use `CHECK` and foreign keys; do not rely on application code alone.
- Store money as integer minor units or `numeric` with explicit scale. Never `float`.
- Store timestamps as `timestamptz` (Postgres) or UTC with the zone recorded.

## Indexing
- Index foreign keys and the columns in frequent `WHERE`, `JOIN`, and `ORDER BY` clauses.
- A composite index serves its leftmost prefix. Order columns by equality first, then range.
- Verify with `EXPLAIN`. An index the planner does not use is only write cost.
- Create large indexes concurrently where the engine supports it (`CREATE INDEX CONCURRENTLY` on Postgres).

## Queries
- Parameterize every value. Never concatenate user input.
- Select the columns you need, not `SELECT *`, in hot paths.
- Avoid N+1: fetch related rows with a join or an `IN` list.
- Paginate with keyset (`WHERE id > :last ORDER BY id LIMIT n`) for large tables. Offset pagination slows as it goes deeper.

## Transactions
- Keep transactions short. Do not call external services inside one.
- Know the isolation level. Read Committed is the Postgres default; check the default for your engine.
- Retry on serialization failures and deadlocks, with a bounded count.
- For check-then-insert races, use a unique constraint and handle the conflict, instead of a read first.

## Migrations
- One change per migration file. Name it by intent.
- Review the lock each statement takes. Adding a column with a volatile default or building an index without concurrency can block writes on a large table.
- Make the migration and the application compatible in both orders during a rolling deploy (see deployment-patterns).
- Test the migration on a copy of production-sized data before running it.

## NoSQL
- Choose a document store when access is by a known key and the document is the unit of consistency. Choose SQL when you need joins, ad hoc queries, or multi-row transactions.
- Model documents around the queries you run, not around the entities you have.

## Backups
- A backup is not verified until a restore has been run and checked.
