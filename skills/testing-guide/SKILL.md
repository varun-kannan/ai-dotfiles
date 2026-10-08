---
name: testing-guide
description: Test strategy and TDD workflow for any language. Use when writing tests, fixing a bug with a regression test, deciding unit vs integration vs end-to-end coverage, or repairing flaky tests.
---

# Testing Guide

## Workflow
1. Bug: write a test that fails for the reported reason. Run it. Fix. Run it again.
2. Feature: write tests for the specified behavior, including invalid input and boundaries. Confirm they fail. Implement.
3. Refactor: run the full suite before and after. Behavior tests must not change.

## Choosing the level
- Unit: pure logic, parsers, calculations. Fast, no I/O.
- Integration: a module plus a real database, filesystem, or HTTP layer. Use a real local instance when it is cheap (SQLite in memory, a Docker Postgres).
- End-to-end: one or two critical user paths. Keep the count small; they are slow and flaky.

## Test quality
- Test through the public interface. Do not assert private fields.
- One behavior per test. The name states the behavior: `rejects expired token`, not `test3`.
- Check each new test can fail: break the code once and watch it go red.
- Mock external services, clocks, and randomness. Do not mock the code under test.
- Use deterministic data. Seed random generators. Inject the clock.

## Flaky tests
- Reproduce by running the test 50 times in a loop. A flake that never reproduces is still a defect.
- Common causes: shared state between tests, real time, network calls, test order dependence, unawaited async work.
- Quarantine only with a linked issue and an expiry date. Do not delete.

## Coverage
- Use coverage to find untested branches in changed code, not as a target number.
- A line that runs without an assertion covers nothing.

## Report
State the exact test command and its result. If you did not run the tests, say so.
