# Cascade: base rules, then the project

The base layer is machine-wide and lives in `~/.ai-rules/`. A project adds its own layer on top. Where they conflict, the project wins. Where a project has nothing, the base applies.

## Layers

| Layer | Where | Set by |
|---|---|---|
| Base rules | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md`; source copy `~/.ai-rules/RULES.md` | `install.sh` |
| Domain rules | `~/.ai-rules/rules/domains/*.md` | `install.sh`; selected per task by the loader |
| Project rules and memory | `AGENTS.md` (generated block plus your own text), `.fieldbook/bank/` | the engine, automatically; fieldbook once git exists |
| Project overrides | `.harness/config.json` (`tier`, `exclude`, `pin`) | you, optional |

## How each tool reaches the base

- Claude Code loads the global `CLAUDE.md` and the project `CLAUDE.md` together. The project file written by fieldbook points at `AGENTS.md`.
- OpenCode: per the OpenCode docs as recorded in `agents/opencode/agent.env`, a project `AGENTS.md` takes priority and the global file is not loaded in that project. Because of this, the engine's block in the project `AGENTS.md` names `~/.ai-rules/RULES.md`.
- Other tools: not verified here. The `AGENTS.md` block is the common path, so any tool that reads `AGENTS.md` is told where the base rules are.

The block sits between `<!-- BEGIN ai-dotfiles:base -->` and `<!-- END ai-dotfiles:base -->`. Fieldbook's `sync` only rewrites its own blocks, so ours is left alone.

## Enforced and asked

- Asked: the base rules and the generated block. Tools follow them as instructions.
- Added by the prompt hook (Claude Code only), when the decision engine judges it useful: a short note naming rules, skills or memory that fit this task and were not named earlier in the session.
- Enforced: the write hooks and the git hooks, which act on files and commits whatever the tool.

## Calibration

The base rules load in every session in every tool. They are kept to a core of about 1,700 tokens; the long sections live in `~/.ai-rules/rules/detail/` and load only when the core points to them. `harness doctor` checks the core, the project files and the descriptions against `config/harness-budgets.json`.
