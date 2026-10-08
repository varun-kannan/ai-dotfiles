---
name: code-review-guide
description: Checklist-driven code review for a pull request or diff, covering correctness, design, security, tests, naming, and readability, with severity and the reviewer's verdict. Use when asked to review code or prepare a change for review.
---

# Code Review Guide

Review the change, not the author. Read the description first, then the diff, then the files around it.

## Pass 1: does it do what it says?
- Does the code match the stated goal? Flag behavior the description does not mention.
- Are edge cases handled: empty input, null, zero, maximum size, concurrent calls, timeouts?
- Are error paths reachable and correct?

## Pass 2: design
- Is the change in the right module? Does it add a dependency between modules that should not know each other?
- Is there a simpler version that meets the same requirement? Name it.
- Does it add speculative options, abstractions for one caller, or flags nobody sets?

## Pass 3: safety
- Input validated at the boundary. Output escaped for its context.
- Authorization checked on the server for each object.
- No secrets, no sensitive data in logs.
- New dependencies are real, maintained, and needed.

## Pass 4: tests
- New behavior has a test that would fail without the change.
- Bugs have a regression test.
- Tests assert behavior, not implementation details.

## Pass 5: readability
- Names say what the thing is. Avoid `data`, `tmp`, `handle` where a real noun exists.
- Comments explain why. Delete comments that restate the code.
- Match the neighboring files' style. Do not reformat unrelated lines.

## Writing the comments
- Prefix: `blocker` (must fix), `major` (should fix), `minor` (optional), `question` (need an answer).
- Give the location, the problem, and a concrete suggestion. "Consider refactoring" is not a comment.
- Praise specific good decisions, briefly, when they are non-obvious.

## Verdict
Approve, approve with minor changes, request changes, or block. State it on the first line.
