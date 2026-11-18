# Rules index

Layers, applied in this order. Later layers add to earlier ones and win on conflict.

1. `RULES.md`: core behavior, installed globally as CLAUDE.md, AGENTS.md, and GEMINI.md. Kept to about 1,700 tokens; `detail/` holds the long sections, loaded only when the core names them.
2. `domains/security.md`: always loaded for code that handles input, auth, secrets, paths, or crypto.
3. `domains/testing.md`: loaded for code changes.
4. `domains/<language>.md`: loaded when the project's detected language matches (nodejs, python, java, kotlin).
5. The project's `AGENTS.md` (the engine's generated block plus your own text) and `.fieldbook/bank/03-conventions.md`. Highest priority.

The weighted loader (`bin/context-manager.py`) decides which layers fit the tier budget in `config/harness-budgets.json`.
