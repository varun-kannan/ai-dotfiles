# Skill placement policy

## Where skills live
- Canonical source: `skills/<name>/SKILL.md` in this repo. Edit skills here only.
- Shared copy: `~/.ai-rules/skills/`, written by `install.sh`. Used by the loader.
- Per-tool copies: `install.sh` copies each skill into every vendor folder listed in `agents/*/agent.env` (`SKILLS_DIR`). Copies are replaced on every run, so edits made in a tool folder are lost.
- Project-level skills are not loaded by the harness. Project customization goes in `.harness/rules/PROJECT-RULES.md` and `.harness/project-config.json`.

## Adding a skill
1. Create `skills/<name>/SKILL.md` with frontmatter `name:` equal to the folder name and a `description:` that says when to use it.
2. Add an entry to `config/skill-metadata.json` (tier, cost, relevance).
3. Add an entry to `config/harness-relevance.json` (tags, weight, priority). Without this the loader never selects the skill.
4. Run `./install.sh`, then `python3 bin/context-manager.py --self-test`.

## Vendor notes
- Claude Code: `~/.claude/skills/`.
- Codex: `~/.codex/skills/`.
- Gemini CLI: `~/.gemini/skills/`.
- Hermes: `~/.hermes/skills/`.
- OpenCode: reads `~/.claude/skills/`, so it gets no separate copy.
- Cursor: no skill folder. Its project rules are `.cursor/rules/*.mdc`, which the harness does not generate yet.
- Devin: no local skill folder. Its repo instructions are `AGENTS.md`.
