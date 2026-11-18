# Project engine

The engine sets up every project on this machine by itself and keeps that setup current as the project changes. It records the project's decisions and its own changes, and it keeps what loads into every session under a measured token cap. Every choice it makes goes through a local decision engine whose confidence is checked against what actually happened.

Code: `engine/` (installed to `~/.ai-rules/engine/`), CLI `bin/harness`, config in `config/`.

## When it runs

Nothing needs to be run by hand. Each trigger calls `harness auto`, which returns in milliseconds when nothing changed.

| Trigger | Fires | Installed by |
|---|---|---|
| Claude Code session start | opening a session in any folder | `install.sh` (SessionStart hook) |
| Claude Code prompt | each prompt, so a manifest or `.git` created mid-session is picked up | `install.sh` (UserPromptSubmit hook) |
| `cd` in zsh | entering a folder in a terminal, for Codex, Gemini, OpenCode and anything else | `install.sh` (a marked block in `~/.zshrc`) |
| git `post-checkout`, `post-merge` | after a clone, a checkout or a pull, in repos created or cloned after install | `install.sh` (`~/.git-templates`) |

`harness init` exists only to force a setup the engine declined.

## What counts as a project

The project root is the nearest folder with `.git` or a manifest (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle(.kts)` and others). Git is not required.

Never set up:

- the home folder, and the standard folders in it (`Documents`, `Desktop`, `Downloads`...)
- container folders: a folder that holds two or more projects (`~/Documents` is a git repo holding about 20). A rule file there would load into every project below it.
- hidden and dependency folders (`node_modules`, `.venv`, `target`...)
- anything listed in `~/.ai-rules/harness-exclude` (one path or glob per line; `sb_projects` is listed)
- any project with a `.harness-skip` file

A folder without a marker is decided by the `is_project` question: three or more source files, or a `src` folder with code, while a Claude session is open there counts. An empty folder does not, until code appears.

## What it writes

| Path | Content | Owner |
|---|---|---|
| `AGENTS.md`, between `<!-- BEGIN ai-dotfiles:harness -->` markers | stack, the project's real commands, do's and don'ts for the stack, pointers to domain rules and decisions. Capped at 600 tokens. | engine, rewritten when inputs change |
| `CLAUDE.md`, `@AGENTS.md` between markers | makes Claude Code load `AGENTS.md`. Skipped when `CLAUDE.md` already points at `AGENTS.md` | engine |
| `.harness/CHANGELOG.md` | one line per automatic setup or update, with what changed | engine, append only |
| `.harness/decisions.md` | decisions recorded before git exists | you and agents |
| `.fieldbook/` | bank, one log per task, decision records, pruning | fieldbook, created once git exists |
| `.harness/config.json` (optional) | `tier`, `exclude`, `pin` for the loader | you |

Text outside the markers is never touched. When git appears, fieldbook is initialized and the entries in `.harness/decisions.md` move into `.fieldbook/bank/04-decisions.md`.

If you delete the generated block by hand, the engine treats that as a no for this project and stays out. `harness remove` deletes everything it wrote and adds `.harness-skip`; `harness init` brings it back.

The do's and don'ts come from `config/project-rules.json`: a universal set plus lines per detected tag. Edit that file to change what every project gets; projects update on their next trigger.

## Decision engine

`engine/decide.py`. Typed questions (`flag`, `choice`) are defined in `config/decisions.json`. Callers compute signals in code; the engine combines them with a logistic model, corrects the probability from observed outcomes, abstains in the unsure band, and logs the answer with the signals that drove it.

| Question | Decides | Outcome used to calibrate |
|---|---|---|
| `is_project` | whether to set up a folder with no marker | the generated block still exists a week later |
| `pointer_useful` | whether to add the "for this task" note to the prompt | Claude read a named file, used a named skill or ran a named subagent in that turn |
| `model_suggestion_useful` | whether to show a `[model-router]` note | you switched to the suggested model |
| `model_tier` | which tier a prompt fits | (not yet calibrated) |

Once a day, the session-start hook runs `harness learn` in the background: it labels decisions from transcripts, rebuilds calibration, and refits weights for questions with at least 60 outcomes. A refit is kept only when it lowers the error on held-out outcomes, and no weight moves more than 1.5 from the value in `config/decisions.json`. Rule text never changes automatically. `~/.ai-rules/logs/learn.log` records each change. `harness eval` reports volume, abstain rate, hit rate and calibration error per question.

## Token budget

`config/harness-budgets.json`:

- `session`: caps on what loads at every session start: global rules 1,800, project files 1,500, skill, agent and command descriptions 2,000.
- `project_block`: 600 for the generated block.
- `tiers`: what the loader may select per model tier.

`harness doctor` reports each against its cap and exits 1 when one is over. It also reads your Claude Code transcripts for the real median first-turn context in the project, which shows how much of it the harness accounts for. Most of it is Claude Code itself, tool and MCP schemas, and plugins.

The global rules are split: a core of about 1,700 tokens loads every session, and `rules/detail/` (prose style, characters, scope, tooling) loads only when the core points to it.

## Self-updating

- Projects: regenerate when a manifest, lockfile, `Makefile`, `.git`, fieldbook or the engine version changes.
- The install: `install.sh` records the repo path and commit. At session start, at most once an hour, the engine re-runs `install.sh` in the background when the repo has a newer commit and a clean working tree. Pulling from GitHub stays manual.
- Drift: `harness doctor` compares the installed copy with the repo.

## Switches

- `touch ~/.ai-rules/harness.off`: the engine does nothing anywhere. `AI_HARNESS_OFF=1` does the same for one shell.
- `touch ~/.ai-rules/router.off`: no model notes or task notes in Claude Code; project setup still runs.
- `.harness-skip` in a project, or a line in `~/.ai-rules/harness-exclude`: leave that project alone.

## Logs

All under `~/.ai-rules/logs/`, none containing prompt text: `decisions.jsonl` and `outcomes.jsonl` (decision engine), `routing.jsonl` (prompt hook), `learn.log`, `self-update.log`.

## Tests

```bash
python3 -m unittest discover -s tests
python3 ~/.claude/hooks/prompt-route.py --self-test
python3 ~/.ai-rules/bin/context-manager.py --self-test
```
