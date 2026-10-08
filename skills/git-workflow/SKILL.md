---
name: git-workflow
description: Git branching, commit message, rebase, and pull request practices. Use when creating branches, writing commits or PR descriptions, resolving conflicts, or undoing a mistake safely. Commit messages describe the change, never the tool.
---

# Git Workflow

## Commits
- Subject: imperative mood, under 72 characters, states the change. `Reject expired refresh tokens` not `Fixed stuff` or `Updated auth`.
- Body: why the change was needed, and anything a reviewer must know. Wrap at 72.
- One logical change per commit. Separate refactors from behavior changes.
- No tooling attribution: no `Co-Authored-By` trailers for AI tools, no "Generated with" footers, no AI session links. The repo's `commit-msg` hook strips these; do not rely on it as the only check.

## Branches
- Branch from the default branch. Name by intent: `fix/expired-token`, `feat/export-csv`.
- Keep branches short-lived. Rebase onto the default branch before review.

## Before committing
- Review the staged diff: `git diff --staged`. Look for secrets, debug prints, and unrelated files.
- Run the project's test command. Report what ran.

## Safe history editing
- Rewriting history is fine on your own unpushed branch. Never force-push a shared branch.
- Use `git push --force-with-lease`, never plain `--force`.
- To undo a pushed commit, `git revert`. To undo local work, check `git reflog` first; it lists the old tip.
- Never run `git reset --hard` or `git clean -fd` without first listing what they will delete (`git status`, `git clean -nd`).

## Conflicts
- Read both sides. Keep both intents when they are compatible. Ask when they are not.
- After resolving, run the tests before `git add`.

## Pull request description
- Title: the change in one line.
- Body: what changed, why, how it was tested (the exact command and result), and what a reviewer should check first.
- Keep the PR small enough to review in one sitting; split it otherwise.
