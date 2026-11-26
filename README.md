# ai-dotfiles

One set of rules, skills and enforcement hooks for every AI coding agent on a
machine. Write the rules once, and each installed agent gets them in the file it
actually reads. A git layer blocks bad output from any tool, including ones
with no config at all.

Clone the repository, then from its root:

```bash
./install.sh
./install.sh --existing-repos ~/code    # optional: hook repos you already have
```

The installer is idempotent. Edit anything, run it again.

## Layout

```
rules/
  RULES.md                  the single source of truth
  paste-into-chat-ui.txt    condensed rules for ChatGPT / Claude app settings
  domains/                  per-domain rules: security, testing, nodejs, python, java, kotlin
  detail/                   long sections of RULES.md, loaded only when the core points to them
agents/
  app-setup.sh              shared by the chat apps below
  definitions/              seven subagents, installed to ~/.claude/agents
  claude-code/              agent.env, setup.sh, hooks/
  codex/                    agent.env
  gemini-cli/               agent.env (installed even before Gemini CLI is)
  opencode/                 agent.env (installed even before OpenCode is)
  cursor/                   agent.env, setup.sh (prints the paste step)
  hermes/                   agent.env (skills only)
  devin/                    agent.env, setup.sh (repo AGENTS.md, written by the engine)
  chatgpt-app/              agent.env, setup.sh (prints the paste step; keeps a local copy)
  claude-app/               agent.env, setup.sh (prints the paste step)
commands/                   seven slash commands, installed to ~/.claude/commands
skills/                     22 skills, one folder each with SKILL.md
config/                     token budgets, relevance, decisions, project rules (JSON)
engine/                     project engine: detection, safe file and git access, decisions, generation, doctor
shell/                      zsh cd trigger
tests/                      engine, hook, CLI and installer tests
bin/                        only these four are installed
  content-hygiene           scanner: hidden text, invisible chars, placeholders, scaffolding, prose tells
  check-deps                imports not declared in the project manifest
  context-manager.py        picks which agents, skills and rules fit a task and tier budget
  harness                   project engine CLI: status, doctor, trust, untrust, init, remove, plan, eval, learn
hooks/git/
  pre-commit                blocks hygiene violations in the staged content
  commit-msg                strips AI attribution trailers
  pre-applypatch,
  applypatch-msg            hand git am patches to our pre-commit and commit-msg, when those are ours
  post-checkout, post-merge keep a project's setup current after clone, checkout and pull
install.sh
INSTALL.md                  detail: layers, verification, limitations
docs/                       engine, cascade, skill placement, agent roles, command reference, engine plan
```

## Harness layer

Subagents and slash commands work in Claude Code. Each subagent has one job, a
tool list and a model; each slash command hands the request to one of them.

| Command | Subagent |
|---|---|
| `/plan` | planner |
| `/review` | code-reviewer |
| `/test` | tester |
| `/security` | security-reviewer |
| `/architecture` | architect |
| `/optimize` | performance-optimizer |
| `/docs` | documentation-guide |

Every project is set up automatically: open a Claude Code session in it, `cd` into it,
or clone it. The engine writes a capped block with the stack, the project's own commands
and do's and don'ts, logs its changes to `.harness/CHANGELOG.md`, and regenerates when
the project changes. In a folder without git the block goes into `AGENTS.md`. A git repo
gets the same only once you run `harness trust` in it, or when the engine set the folder
up before it had git; fieldbook memory is then added if the fieldbook binary is
installed. In every other git repo nothing tracked is touched: the block goes into
`.harness/AGENTS.md`, loaded through `CLAUDE.local.md`, both hidden from git. The engine
does not guess whose a repo is, because commit authors can be forged. Home, container
folders, `~/.ai-rules/harness-exclude` and `.harness-skip` are left alone. `harness
status`, `harness doctor` and `harness remove` are for looking and overriding. Details:
`docs/ENGINE.md`.

In Claude Code the prompt hook can show a `[model-router]` note when the model looks much
too big or too small, and can name rules, skills or memory a prompt points to. Both are
gated by the decision engine, which logs each choice and recalibrates from what happened
next. It suggests only; it does not switch models. `touch ~/.ai-rules/router.off` turns
the notes off and leaves project setup running.

See `docs/` for the placement policy, agent roles, command reference and the base/project cascade.

## Adding an agent

Create `agents/<name>/agent.env`:

```bash
DETECT="$HOME/.mytool"               # skipped when this path is missing; "" installs always
RULES_FILE="$HOME/.mytool/AGENTS.md" # where the tool reads global instructions
RULES_TITLE="AGENTS.md"
SKILLS_DIR=""                        # set only if the tool loads SKILL.md folders
```

Anything more than rules and skills (hooks, settings) goes in
`agents/<name>/setup.sh`, which the installer runs with `AGENT_DIR` set. See
`agents/claude-code/setup.sh`.

For a tool whose instructions live in account settings rather than a file, leave
`RULES_FILE` empty, set `APP_NAME` and `APP_SETTINGS`, and point `setup.sh` at
`agents/app-setup.sh`, as `claude-app/` does. The installer then prints what to
paste and where.

Check the tool's documentation for the real global instructions path before
adding it. A rules file in a location the tool never reads does nothing.

## Adding a skill

Put a folder with a `SKILL.md` under `skills/`. The frontmatter `name` must equal
the folder name. The installer copies every skill into each agent that has a
`SKILLS_DIR`. Reference material goes in the skill's own folder, and `SKILL.md`
should tell the agent which file to read for which question.

To make the loader select a skill, add it to `config/skill-metadata.json` and
`config/harness-relevance.json`. Without the second entry it is never chosen.
`docs/SKILL-PLACEMENT-POLICY.md` has the full steps.

## What is enforced, and what is only asked

| Layer | Covers | Strength |
|---|---|---|
| Rules files | Every configured agent | Instruction; usually followed |
| Claude Code write hooks | Files Claude Code writes with its Write, Edit and NotebookEdit tools (not through the Bash tool) | Blocks the write |
| git `pre-commit` | New commits and `git am` patches, from any tool | Blocks the commit |
| git `commit-msg` | Commit messages | Removes attribution |

Chat replies are covered by instructions alone. Tested against fresh sessions,
the model follows the verification, honesty and attribution rules, and slips on
prose style (em dashes, negation-reversal framing) and template placeholders in
drafts. The hooks block unfilled template slots and curly quotes used as code; other
typographic characters are a warning.
Prose style in Markdown is reported only when you run the scanner yourself
(`bin/content-hygiene FILE`); the hooks do not block or show it.

Run the scanner's own tests with `bin/content-hygiene --self-test`, the loader's with
`python3 bin/context-manager.py --self-test`, and the engine's with
`python3 -m unittest discover -s tests`.

## Credits

Sections 1 to 4 of `rules/RULES.md` (Think before coding, Simplicity,
Surgical changes, Goal-driven execution) are adapted from
andrej-karpathy-skills. The attribution, verification, security, hygiene and
forensics material, the scanners and the hooks were built on top of that.
