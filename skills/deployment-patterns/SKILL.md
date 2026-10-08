---
name: deployment-patterns
description: Release and deployment strategies covering rolling, blue-green, and canary releases, health checks, database migration ordering, feature flags, and rollback procedure. Use when planning a deploy, writing a release runbook, or deciding how to roll back a bad release.
---

# Deployment Patterns

## Before deploying
- The artifact is built once and promoted through environments. Do not rebuild for production.
- The version being deployed is recorded (git SHA in the image tag or a version endpoint).
- Migrations are reviewed separately from code changes.

## Strategies
- Rolling: replace instances in batches. Simple. Old and new versions run together, so the API must tolerate both.
- Blue-green: run the new version alongside the old, switch traffic. Fast rollback by switching back. Costs double capacity during the switch.
- Canary: send a small share of traffic to the new version, watch error rate and latency, then increase. Needs metrics you trust.

Choose the simplest one that meets the risk. A stateless service with good health checks often needs only rolling.

## Migrations and compatibility
- Expand, then migrate, then contract. Add the new column (nullable), deploy code that writes both, backfill, switch reads, then drop the old column in a later release.
- Never deploy code that needs a column before the migration has run.
- Make each migration safe to run twice or at least safe to stop halfway.

## Health checks
- Liveness: the process is running. Readiness: it can serve traffic (dependencies reachable). Do not put dependency checks in liveness, or a database outage restarts every pod.
- The deploy waits for readiness and aborts on timeout.

## Feature flags
- Ship code dark, then enable. Each flag has an owner and a removal date.
- Flags must default to the safe behavior when the flag service is down.

## Rollback
- Write the rollback command before the deploy. Test it on staging.
- Roll back code first. Roll back a migration only if it is reversible and tested; otherwise roll forward with a fix.
- After rollback, record what failed and why in the incident note.

## Runbook template
Pre-checks, deploy command, verification (named metric and threshold), rollback command, owner, and escalation contact.
