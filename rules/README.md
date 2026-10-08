# Rules index

Layers, applied in this order. Later layers add to earlier ones and win on conflict.

1. `RULES.md`: core behavior, installed globally as CLAUDE.md, AGENTS.md, and GEMINI.md.
2. `domains/security.md`: always loaded for code that handles input, auth, secrets, paths, or crypto.
3. `domains/testing.md`: loaded for code changes.
4. `domains/<language>.md`: loaded when the project's detected language matches (nodejs, python, java, kotlin).
5. `<project>/.harness/rules/PROJECT-RULES.md`: project-specific rules. Created by `ai-bootstrap init`. Highest priority.

The weighted loader (`bin/context-manager.py`) decides which layers fit the tier budget in `config/harness-budgets.json`.
