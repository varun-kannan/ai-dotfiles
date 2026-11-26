# Rules index

Layers, applied in this order. Later layers add to earlier ones and win on conflict.

1. `RULES.md`: core behavior, installed globally as CLAUDE.md, AGENTS.md, and GEMINI.md. Kept under 1,800 tokens; `detail/` holds the long sections, read only when the core names them.
2. `domains/security.md` and `domains/testing.md`: named in every project's generated block, to be read before a change they apply to.
3. `domains/<language>.md` (nodejs, python, java, kotlin): named in the generated block when the project's stack matches.
4. `detail/*.md`: long sections of the core (prose style, characters, comments, scaffolding, scope, tooling).
5. The project's `AGENTS.md` (the engine's generated block plus your own text) and `.fieldbook/bank/03-conventions.md`. Highest priority.

Nothing loads the domain or detail files automatically; the core and the generated block point to them. `bin/context-manager.py` ranks domain rules, skills, subagents and project memory for a task. The Claude Code prompt hook uses that ranking to name items a prompt points to, and `harness plan` shows it within a tier budget from `config/harness-budgets.json`.
