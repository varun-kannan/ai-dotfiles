# Agent specialization

Seven subagents are defined in `agents/definitions/`. Claude Code installs them to `~/.claude/agents/`. Each has a narrow job, a tool list, and a model.

| Agent | Model | Tools | Job |
|---|---|---|---|
| planner | opus | Read, Grep, Glob | Breaks a non-trivial change into verifiable steps. Does not edit. |
| code-reviewer | sonnet | Read, Grep, Glob, Bash | Reviews a diff for correctness, duplication, error handling, and test gaps. |
| security-reviewer | opus | Read, Grep, Glob, Bash | Audits changed code for injection, XSS, path traversal, auth, crypto, and secrets. |
| tester | sonnet | Read, Grep, Glob, Bash, Edit, Write | Writes failing tests first, then makes them pass. |
| architect | opus | Read, Grep, Glob, Write | Compares design options and writes ADRs. Does not implement. |
| performance-optimizer | sonnet | Read, Grep, Glob, Bash, Edit | Measures a baseline, changes one thing, re-measures. |
| documentation-guide | sonnet | Read, Grep, Glob, Write, Edit | Updates docs and checks every claim against the code. |

Model choice and token ranges per agent are in `config/routing-config.json`. The agent frontmatter sets the model Claude Code uses.

Agents are not specialized by language. Language rules and skills are chosen by the loader from the project's detected tags.
