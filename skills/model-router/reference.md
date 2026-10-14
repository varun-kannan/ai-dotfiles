# Model router reference

## Pieces

| File | Role |
|---|---|
| `skills/model-router/router.py` | scoring and cost comparison. `analyze_complexity(task)` and `suggest_rerun(...)` |
| `agents/claude-code/hooks/prompt-route.py` | the `UserPromptSubmit` hook. Installed to `~/.claude/hooks/` |
| `bin/context-manager.py` | picks rules, skills, agents, and memory within the tier budget. The hook calls it |
| `config/harness-budgets.json` | token budget per tier |

## What the hook does on a prompt

1. Skips when disabled, when the prompt is under 20 characters, or when it starts with `/`.
2. Finds the current model: last assistant message in `transcript_path`. No assistant message yet means no model suggestion.
3. Scores the prompt with `analyze_complexity`. The confidence is the top score minus the runner-up. Below 2, no suggestion.
4. A suggestion needs a different tier than the current model, and is throttled to once per 5 prompts. A cheaper-model suggestion is dropped for prompts over 1,500 characters.
5. Runs the loader for the current directory with the current model's tier. If the directory is a recognized project and the selection changed since the last prompt in this session, it adds one short paragraph of context. The paragraph names files; it does not paste them.
6. Appends one line to `~/.ai-rules/logs/routing.jsonl`: time, session, project folder name, model, tiers, confidence, whether a suggestion or paragraph was shown, and the prompt length.

The note is a `systemMessage`, shown to the user and not sent to the model. The context paragraph is `additionalContext`, which is sent to the model, so it is kept to a few lines and only repeated when the selection changes.

## What it does not do

- It does not switch models. The documented `UserPromptSubmit` outputs are added context, a block, and a user message; none changes the model.
- It does not read token usage. A post-task cost check is manual (`router.py suggest`), because exact counts exist only after a response.
- It does not learn. Scores come from the keyword lists in `router.py`.

## Tuning

- Keyword lists: `FAST_KEYWORDS`, `STANDARD_KEYWORDS`, `FRONTIER_KEYWORDS` in `router.py`.
- Sensitivity: `MIN_CONFIDENCE` in the hook. Raise it for fewer notes.
- Frequency: `SUGGEST_EVERY` in the hook.
- Budgets per tier: `config/harness-budgets.json`.
- Per-project overrides: `.fieldbook/harness.json` with `tier`, `exclude`, and `pin`.

After editing, run `./install.sh` so the copies in `~/.claude`, `~/.ai-rules`, and the other tools update. New Claude Code sessions pick up hook changes.

## Checks

```bash
python3 ~/.claude/hooks/prompt-route.py --self-test
python3 ~/.ai-rules/bin/context-manager.py --self-test
```

Feed the hook a prompt by hand:

```bash
echo '{"prompt":"format this json list and sort the keys then validate it","cwd":"'"$PWD"'","session_id":"manual"}' | python3 ~/.claude/hooks/prompt-route.py
```

With no transcript there is no model, so only the context paragraph can appear.

## Troubleshooting

- No notes ever appear: check `~/.claude/settings.json` has a `UserPromptSubmit` entry for `prompt-route.py`, that `~/.ai-rules/router.off` does not exist, and read `~/.ai-rules/logs/routing.jsonl` to see what the hook decided.
- Notes seem wrong: the heuristic is keyword based. Raise `MIN_CONFIDENCE` or ignore the note.
- Too many context paragraphs: the selection changes with the prompt. Pin or exclude items in `.fieldbook/harness.json`.
