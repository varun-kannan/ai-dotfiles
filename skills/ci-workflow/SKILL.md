---
name: ci-workflow
description: Continuous integration design for GitHub Actions, covering reproducible installs, job structure, caching, required checks, secrets scope, least-privilege tokens, and pinning actions. Use when creating or editing CI workflows or diagnosing a failing pipeline.
---

# CI Workflow

## Structure
- One workflow per concern: `ci.yml` for build and test on every push and pull request; `release.yml` for tagged builds.
- Keep the required checks small and fast. Put slow suites in a separate job that runs on schedule or on label.
- Fail the workflow on the first broken step. Do not use `continue-on-error` to hide failures.

## Reproducible installs
- Install from the lockfile: `npm ci`, `pip install -r requirements.lock` or `uv sync --frozen`, `mvn -B verify`, `cargo test --locked`.
- Pin the runtime version (`actions/setup-node` with `node-version-file`).

## Caching
- Use the setup action's built-in cache. Key on the lockfile hash.
- A cache is an optimization. A build must succeed with an empty cache.

## Permissions and secrets
- Set `permissions:` at the top of each workflow to the minimum. `contents: read` is the usual default.
- Pass secrets only to the steps that need them, never as job-wide env on untrusted triggers.
- Pull requests from forks get no secrets. Do not use `pull_request_target` to run untrusted code.

## Pinning
- Pin third-party actions to a full commit SHA for anything that touches secrets or deploys. Keep a comment with the version.
- Confirm an action exists and its tag resolves before pinning.

## Debugging a failure
1. Read the first error, not the last. Later steps often fail as a consequence.
2. Compare with the last green run on the same branch or main.
3. Reproduce locally with the same runtime version and a clean install.
4. Check for time-dependent tests and unpinned tool versions.

## Checklist
- Triggers scoped. Permissions minimal. Lockfile install. Caches keyed. Actions pinned for secret-touching jobs. Concurrency group set to cancel superseded runs on branches.
