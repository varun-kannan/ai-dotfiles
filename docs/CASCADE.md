# Cascade: base rules, then the project

The base layer is machine-wide and lives in `~/.ai-rules/`. A project adds its own layer on top. Where they conflict, the project wins. Where a project has nothing, the base applies.

## Layers

| Layer | Where | Set by |
|---|---|---|
| Base rules | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md`; source copy `~/.ai-rules/RULES.md` | `install.sh` |
| Domain rules | `~/.ai-rules/rules/domains/*.md` | `install.sh`; selected per task by the loader |
| Project rules and memory | `AGENTS.md`, `.fieldbook/bank/` (conventions, decisions, gotchas) | `fieldbook`, via `ai-bootstrap init` |
| Project overrides | `.fieldbook/harness.json` (`tier`, `exclude`, `pin`) | `ai-bootstrap init`, then by hand |

## How each tool reaches the base

- Claude Code loads the global `CLAUDE.md` and the project `CLAUDE.md` together. The project file written by fieldbook points at `AGENTS.md`.
- OpenCode: per the OpenCode docs as recorded in `agents/opencode/agent.env`, a project `AGENTS.md` takes priority and the global file is not loaded in that project. Because of this, `ai-bootstrap init` adds a block to the project `AGENTS.md` that names `~/.ai-rules/RULES.md`.
- Other tools: not verified here. The `AGENTS.md` block is the common path, so any tool that reads `AGENTS.md` is told where the base rules are.

The block sits between `<!-- BEGIN ai-dotfiles:base -->` and `<!-- END ai-dotfiles:base -->`. Fieldbook's `sync` only rewrites its own blocks, so ours is left alone.

## Enforced and asked

- Asked: the base rules and the pointer block. Tools follow them as instructions.
- Added by the prompt hook (Claude Code only): the paragraph naming the domain rules, skills, and memory the loader picked for the task. It is a pointer, so it costs a few lines and is repeated only when the selection changes.
- Enforced: the write hooks and the git hooks, which act on files and commits whatever the tool.

## Calibration

The loader fills a token budget per tier (`config/harness-budgets.json`). The base `RULES.md` is loaded by each tool on every session and is not counted in those budgets. At about 16 KB it is larger than the fast tier's whole budget. If that matters, shorten the base file or raise the budgets.
