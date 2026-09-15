# Install
<!-- hygiene:ignore-file - contains verification fixtures that quote the scanned patterns -->

Universal rules, enforcement tooling and skills for every AI agent on this
machine.

```bash
./install.sh
./install.sh --existing-repos ~/Documents
```

Idempotent. Edit anything here and re-run. The installer detects which agents are
present and only configures those.

---

## Architecture

One source of truth, four delivery layers, each covering a failure of the one
above it.

```
rules/RULES.md  (source of truth)
    |
    +-- ~/.ai-rules/RULES.md          canonical copy + shared tooling
    +-- ~/.claude/CLAUDE.md           Claude Code reads this
    +-- ~/.codex/AGENTS.md            Codex reads this
    +-- rules/paste-into-chat-ui.txt  for app UIs with no config file
```

| Layer | Mechanism | Scope | Reliability |
|---|---|---|---|
| 1 | Rules files | Per agent | Instruction. Usually followed, not guaranteed |
| 2 | `settings.json` flags | Claude Code | Unreliable, see below |
| 3 | Claude Code hooks | Claude Code | Deterministic within a session |
| 4 | **Git hooks** | **Every tool** | **Deterministic at the git layer** |

Layer 4 is the one that makes this universal. Claude Code, Codex, Cursor, a paste
out of a chat window, a tool installed next year, or a human typing: all of it
reaches git eventually, and all of it passes through the same gate.

**On layer 2.** `includeCoAuthoredBy: false` is set because it is harmless if it
works, but it has been reported as inconsistently honoured, and a
`Claude-Session:` trailer has been reported as driven server-side.
`attribution: {commit, pr}` is *not* set, because that key is unverified.

---

## What gets installed where

**Shared** (`~/.ai-rules/`)

| File | Role |
|---|---|
| `bin/content-hygiene` | Scanner: characters, placeholders, scaffolding |
| `bin/check-deps` | Imports not declared in the project manifest |
| `RULES.md` | Canonical copy of the rules |

**Claude Code** (`~/.claude/`)

| File | Role |
|---|---|
| `CLAUDE.md` | Rules, generated from `rules/RULES.md`, loaded every session |
| `hooks/pre-write-guard.sh` | PreToolUse: blocks defective writes |
| `hooks/post-write-audit.sh` | PostToolUse: reports unresolved imports |
| `skills/ai-content-forensics/` | On-demand provenance reference |
| `settings.json` | Hooks, `Read(~/.claude/skills/**)` so skills can open their reference files headless; merged, not overwritten |

**Codex** (`~/.codex/`)

| File | Role |
|---|---|
| `AGENTS.md` | Rules, generated from `rules/RULES.md` |
| `skills/ai-content-forensics/` | Same skill; Codex uses the same format |

An existing non-empty `AGENTS.md` is backed up to `AGENTS.md.bak` first.

**Git** (`~/.git-templates/hooks/`)

| File | Role |
|---|---|
| `commit-msg` | Strips AI attribution trailers |
| `pre-commit` | Blocks hygiene violations in staged files |

**Other agents.** Every folder under `agents/` is one agent. Gemini CLI
(`~/.gemini/GEMINI.md`) and OpenCode (`~/.config/opencode/AGENTS.md`) are defined
but skipped until installed; install either, re-run `./install.sh`, and it is
covered. Cursor and Windsurf keep global rules in their app settings rather than
a file, so they have no agent folder: paste `rules/paste-into-chat-ui.txt` there,
or rely on a project-level `AGENTS.md`. See `README.md` for adding an agent.

---

## Verify

```bash
~/.ai-rules/bin/content-hygiene --self-test      # expect 26/26 passed
```

Claude Code: `/memory` lists `~/.claude/CLAUDE.md`, `/skills` lists
`ai-content-forensics`. Restart the app first so the new `settings.json` loads.

Codex: `head ~/.codex/AGENTS.md` shows the rules.

Write hook:

```bash
printf '{"tool_name":"Write","tool_input":{"file_path":"/tmp/t.py","content":"# TODO: implement logic\n"}}' \
  | ~/.claude/hooks/pre-write-guard.sh
```

Expect the findings and exit code 2.

Git layer, the important one:

```bash
cd /tmp && rm -rf ht && mkdir ht && cd ht && git init -q
git config user.email t@example.com && git config user.name Test
printf 'const m = \xe2\x80\x9chi\xe2\x80\x9d;\n' > app.js && git add app.js
git commit -m "test"
```

Expect the commit to be blocked with a curly-quote finding.

---

## App UIs with no config file

ChatGPT.app and Claude.app take rules through their own settings, not a file.
Paste everything below the marker line in `rules/paste-into-chat-ui.txt`
(1,319 characters, within ChatGPT's 1,500 limit) into:

- **ChatGPT** - Settings, Personalization, Custom instructions
- **Claude** - Settings, Profile, personal preferences

This is instruction only. There is no enforcement layer inside a chat app; what
you paste out of one still meets the git hooks.

---

## Hook behaviour

**`pre-write-guard.sh`** blocks `Write`, `Edit` and `NotebookEdit` on:

- invisible Unicode (zero-width, directional marks, soft hyphen, narrow NBSP)
- non-breaking space, curly quotes, em or en dashes, ellipsis **in source code**
  (warnings only in `.md` and `.txt`)
- unfilled placeholders, or code elided with a "rest of the implementation" comment
- generation scaffolding (model self-reference, leaked tool tags or citations)

**`pre-commit`** applies the same hard checks to staged files and blocks the
commit. Bypass with `AI_HYGIENE_SKIP=1 git commit` or `--no-verify`.

**`post-write-audit.sh`** and the pre-commit dependency pass never block. They
report imports absent from `package.json`, `requirements*.txt` or
`pyproject.toml`. False positives are expected for monorepo aliases and
transitive imports.

**Opting out.** A file that must legitimately contain scanned characters carries
`hygiene:ignore-file` in its first 30 lines. Six files here use it. The forensics
references are also exempt by path.

---

## Limitations

- **`--no-verify` bypasses it.** A guardrail, not a security control.
- **Server-side commits skip it.** Cloud agents never touch a local hook.
- **PR bodies are not covered.** Commit messages only. CI backstop:

```yaml
- name: Block AI attribution
  run: |
    if git log origin/main..HEAD --format=%B | grep -qiE \
      'Co-Authored-By:.*(Claude|Anthropic|Copilot)|Claude-Session:|Generated with \[Claude'; then
      echo "::error::AI attribution found in commit messages"; exit 1
    fi
```

- **History is not rewritten.** Existing commits keep their trailers.
- **New repos only, unless you bulk-apply.** `init.templateDir` covers repos you
  init or clone from now on; `--existing-repos` covers the rest.

---

## What this does not do

It does not affect the statistical text watermark, which has no opt-out. That is
also not what these layers target: the watermark lives in free word choices, so
code carries almost none of it, and models released before 2 August 2026 carry
none at all. What is controllable is attribution metadata and output quality.

A Unicode-stripping tool does not remove a watermark. It removes copy-paste
artifacts, which are a different thing.

---

## Maintenance

- Keep `rules/RULES.md` short. It is in context on every turn in every agent.
- When a rule is violated, rewrite that rule rather than adding another.
- Re-run `./install.sh` after any edit, and after installing a new agent.
- Re-verify volatile claims. Watermark coverage is per model version and goes
  stale on its own.
