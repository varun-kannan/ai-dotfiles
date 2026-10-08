# Command reference

Slash commands are installed to `~/.claude/commands/` for Claude Code. Each one hands the request to a subagent.

| Command | Subagent | Use |
|---|---|---|
| `/plan <task>` | planner | Plan before coding. No edits. |
| `/review [scope]` | code-reviewer | Review the current diff or a given path. |
| `/test <target>` | tester | Write or repair tests for a behavior or bug. |
| `/security [scope]` | security-reviewer | Audit the current changes or a path. |
| `/architecture <question>` | architect | Compare design options and record a decision. |
| `/optimize <target>` | performance-optimizer | Measure and fix a slow path. |
| `/docs <target>` | documentation-guide | Update docs to match the code. |

Each command's source is in `commands/`. Other vendors do not get these commands.
