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
2. Keeps the project setup current (`engine/generate.py`). A block generated or changed mid-session is passed to Claude once.
3. Finds the current model from the last assistant message in `transcript_path`, or the model recorded at session start.
4. Picks a tier with the `model_tier` question. When it differs from the current model, the `model_suggestion_useful` question decides whether to show the note. Its signals: the score gap, and penalties for a cheaper model late in a session (switching then discards the prompt cache) or for a long prompt. At most once per 5 prompts.
5. Asks the loader which rules, skills, agents and memory this prompt's own words add beyond the project baseline, minus anything named earlier in the session. The `pointer_useful` question decides whether to add that note.
6. Logs to `~/.ai-rules/logs/routing.jsonl` (no prompt text). Every decision also lands in `decisions.jsonl` for calibration.

The model note is a `systemMessage`, shown to you and not sent to the model. The task note is `additionalContext`, which is sent to the model, so it is gated and never repeats an item within a session.

## What it does not do

- It does not switch models. The documented `UserPromptSubmit` outputs are added context, a block, and a user message; none changes the model.
- It does not read token usage. A post-task cost check is manual (`router.py suggest`), because exact counts exist only after a response.
- It does not learn. Scores come from the keyword lists in `router.py`.

## Tuning

- Keyword lists: `FAST_KEYWORDS`, `STANDARD_KEYWORDS`, `FRONTIER_KEYWORDS` in `router.py`.
- Sensitivity: thresholds and weights in `config/decisions.json`. Learned weights in `~/.ai-rules/data/weights.json` override them.
- Frequency: `SUGGEST_EVERY` and `EARLY_PROMPTS` in the hook.
- Budgets per tier: `config/harness-budgets.json`.
- Per-project overrides: `.harness/config.json` with `tier`, `exclude`, and `pin`.

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

With no transcript there is no model, so only the task note can appear.

## Troubleshooting

- No notes ever appear: check `~/.claude/settings.json` has a `UserPromptSubmit` entry for `prompt-route.py`, that `~/.ai-rules/router.off` does not exist, and read `~/.ai-rules/logs/routing.jsonl` to see what the hook decided.
- Notes seem wrong: the heuristic is keyword based. Raise `MIN_CONFIDENCE` or ignore the note.
- Notes you never use: `harness learn` lowers their probability from outcomes. `harness eval` shows the hit rate per question.
