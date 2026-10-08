---
description: Review the current diff for correctness and quality
argument-hint: [optional path or ref]
---

Use the code-reviewer subagent on the current changes. Scope: $ARGUMENTS

With no scope, review `git diff` and `git diff --staged`. If both are empty, say there is nothing to review and stop.
