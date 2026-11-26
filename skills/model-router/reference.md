# Model router reference

## Pieces

| File | Role |
|---|---|
| `skills/model-router/router.py` | scoring and cost comparison. `analyze_complexity(task)` and `suggest_rerun(...)` |
| `agents/claude-code/hooks/prompt-route.py` | the `UserPromptSubmit` hook. Installed to `~/.claude/hooks/` |
| `bin/context-manager.py` | ranks rules, skills, subagents and memory against a task. The hook calls `task_matches` |
| `engine/decide.py`, `config/decisions.json` | decide whether each note is shown, and log the decision |

## What the hook does on a prompt

1. Stops when `~/.ai-rules/harness.off` exists or `AI_HARNESS_OFF=1` is set.
2. Keeps the project setup current (`engine/generate.py`), for every prompt. A block generated or changed mid-session is passed to Claude once.
3. Stops here when the notes are off (`router.off`), the prompt is under 20 characters, it starts with `/`, or the hook input has no session id (without one nothing can be remembered as already shown).
4. Finds the model in use (see `SKILL.md`). Subagent replies are ignored.
5. Takes the tier from `router.py`. When the prompt has a keyword the router scores and the tier differs from the current model's, the `model_suggestion_useful` question decides whether to show the note. Its signals: the score gap, and penalties for a cheaper model after the third counted prompt (prompts under 20 characters and slash commands are not counted) or for a prompt over 1,500 characters. At most once per 5 prompts. The note names the model actually in use, and gives a price ratio only when that model's price is known.
6. Asks the loader which rules, skills, subagents and memory files the prompt's own words point to (always-on items excluded), minus anything named earlier in the session. The `pointer_useful` question decides whether to add the note. With the shipped weights three new items always get it; two get it except on a prompt under 60 characters that is not the first, which is unsure; one is unsure on a first prompt of 60 characters or more and gets no note otherwise. Unsure answers are acted on 20% of the time.
7. Prints its output, then appends one line to `~/.ai-rules/logs/routing.jsonl` (no prompt text). The two decisions are logged to `decisions.jsonl` with their signals.

The model note is a `systemMessage`, shown to you and not sent to the model. The task note is `additionalContext`, which is sent to the model, so it is gated and never repeats an item within a session. After `/clear` or a compaction the session forgets what it named.

## What it does not do

- It does not switch models. The documented `UserPromptSubmit` outputs are added context, a block, and a user message; none changes the model.
- It does not read token usage. A post-task cost check is manual (`router.py suggest`), because exact counts exist only after a response.
- The tier pick does not learn: it comes from the keyword lists in `router.py`. Whether a note is shown is recalibrated by `harness learn`.

## Tuning

- Keyword lists: `FAST_KEYWORDS`, `STANDARD_KEYWORDS`, `FRONTIER_KEYWORDS` in `router.py`.
- Sensitivity: thresholds and weights in `config/decisions.json`. Learned weights in `~/.ai-rules/data/weights.json` override them.
- Frequency: `SUGGEST_EVERY`, `EARLY_PROMPTS` and `LONG_PROMPT_CHARS` in the hook.
- Budgets per tier, used by `harness plan`: `config/harness-budgets.json`.
- Per-project overrides: `.harness/config.json` with `tier`, `exclude`, and `pin`.

After editing, run `./install.sh` so the copies in `~/.claude`, `~/.ai-rules`, and the other tools update. New Claude Code sessions pick up hook changes.

## Checks

```bash
python3 ~/.claude/hooks/prompt-route.py --self-test
python3 ~/.ai-rules/bin/context-manager.py --self-test
```

Feed the hook a prompt by hand. It runs project setup for the folder you name, so point it at a scratch folder unless you want that:

```bash
mkdir -p /tmp/hook-try && echo '{"prompt":"format this json list and sort the keys then validate it","cwd":"/tmp/hook-try","session_id":"manual"}' | python3 ~/.claude/hooks/prompt-route.py
```

`/tmp` is outside the home folder, so nothing is set up there. With no transcript and no recorded model, no model note can appear.

## Troubleshooting

- No notes ever appear: check `~/.claude/settings.json` has a `UserPromptSubmit` entry for `prompt-route.py`, that `~/.ai-rules/router.off` does not exist, and read `~/.ai-rules/logs/routing.jsonl` to see what the hook decided.
- Notes seem wrong: the tier is keyword based. Raise `threshold` for `model_suggestion_useful` in `config/decisions.json`, or ignore the note.
- Notes you never use: `harness learn` lowers their probability from outcomes. `harness eval` shows the hit rate per question.
