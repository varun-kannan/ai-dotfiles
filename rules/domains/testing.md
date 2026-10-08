# Testing rules

- A bug fix starts with a test that fails for the reported reason.
- A new behavior has tests for valid input, invalid input, and at least one boundary.
- Tests go through public interfaces. Do not assert private state.
- Mock external services, clocks, and randomness. Do not mock the code under test.
- Each test name states the behavior it checks.
- Check a new test can fail: break the code once.
- Report the exact test command and its real result. If tests were not run, say so.
- No flaky tests merged. Quarantine needs a linked issue and an expiry.
