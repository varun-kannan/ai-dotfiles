# rules-and-skills

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
agents/
  claude-code/              agent.env, setup.sh, hooks/
  codex/                    agent.env
  gemini-cli/               agent.env
  opencode/                 agent.env
skills/
  ai-content-forensics/     SKILL.md + reference/
bin/
  content-hygiene           scanner: invisible chars, placeholders, scaffolding, prose tells
  check-deps                imports not declared in the project manifest
hooks/git/
  pre-commit                blocks hygiene violations in staged files
  commit-msg                strips AI attribution trailers
install.sh
INSTALL.md                  detail: layers, verification, limitations
```

## Adding an agent

Create `agents/<name>/agent.env`:

```bash
DETECT="$HOME/.mytool"               # skipped when this path does not exist
RULES_FILE="$HOME/.mytool/AGENTS.md" # where the tool reads global instructions
RULES_TITLE="AGENTS.md"
SKILLS_DIR=""                        # set only if the tool loads SKILL.md folders
```

Anything more than rules and skills (hooks, settings) goes in an executable
`agents/<name>/setup.sh`, which the installer runs with `AGENT_DIR` set. See
`agents/claude-code/setup.sh`.

Check the tool's documentation for the real global instructions path before
adding it. A rules file in a location the tool never reads does nothing.

## Adding a skill

Put a folder with a `SKILL.md` under `skills/`. The installer copies every skill
into each agent that has a `SKILLS_DIR`. Reference material goes in the skill's
own folder, and `SKILL.md` should tell the agent which file to read for which
question.

## What is enforced, and what is only asked

| Layer | Covers | Strength |
|---|---|---|
| Rules files | Every configured agent | Instruction; usually followed |
| Claude Code write hooks | Files Claude Code writes | Blocks the write |
| git `pre-commit` | Anything committed, from any tool | Blocks the commit |
| git `commit-msg` | Commit messages | Removes attribution |

Chat replies are covered by instructions alone. Tested against fresh sessions,
the model follows the verification, honesty and attribution rules, and slips on
prose style (em dashes, negation-reversal framing) and template placeholders in
drafts. The hooks catch those once they reach a file or a commit.

Run the scanner's own tests with `bin/content-hygiene --self-test`.

## Credits

Sections 1 to 4 of `rules/RULES.md` (Think Before Coding, Simplicity First,
Surgical Changes, Goal-Driven Execution) are adapted from
andrej-karpathy-skills. The attribution, verification, security, hygiene and
forensics material, the scanners and the hooks were built on top of that.
