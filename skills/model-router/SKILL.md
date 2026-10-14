---
name: model-router
description: Recommend a Claude model tier (Haiku, Sonnet, Opus) for a task and explain the [model-router] suggestions the prompt hook shows. Use when asked which model to use, whether a model is too big or too small for a task, or what a routing note means.
---

# Model Router

A keyword heuristic that maps a task to a tier. It suggests and does not switch the model. Change the model with `/model <id>`.

## Tiers

| Tier | Model | ID | Input / output per 1M tokens | Fits |
|---|---|---|---|---|
| fast | Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 | formatting, parsing, classification, extraction, simple Q&A |
| standard | Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 | everyday coding, debugging, refactoring, review, tests |
| frontier | Opus 5.5 | `claude-opus-5-5` | $4 / $20 | architecture, research, multi-step analysis, novel problems |

Prices are the Anthropic API rates cached 2026-10-06. Haiku 5.5 costs more for prompts over 100K tokens. These are API rates; subscription plans differ.

## Running it by hand

```bash
python3 ~/.ai-rules/skills/model-router/router.py analyze "refactor the payment retry logic"
python3 ~/.ai-rules/skills/model-router/router.py suggest "format this json" claude-opus-5-5 1400 180
```

`analyze` prints the tier, the keyword scores, and the model. `suggest` takes the task, the model used, and real input and output token counts, and prints a cheaper or stronger alternative with the cost difference. Token counts are known only after a response, so `suggest` is a check after the fact.

## The prompt hook

`install.sh` registers `prompt-route.py` as a `UserPromptSubmit` hook. On each prompt it:

- reads the current model from the last assistant message in the session transcript (the hook input has no model field),
- scores the prompt and prints a `[model-router]` note to the user only, so it costs no tokens, when the model looks much too big or too small,
- adds a few lines naming the domain rules, skills, and project memory the context loader picked, when the session is in a recognized project.

It stays quiet when the gap between tiers is small, for prompts under 20 characters, for slash commands, for the first prompt of a session (no model known yet), and it repeats a suggestion at most once per 5 prompts. It never suggests a cheaper model for prompts over 1,500 characters.

Turn it off with `touch ~/.ai-rules/router.off`, or `AI_ROUTER_OFF=1` in the environment. Each decision is logged to `~/.ai-rules/logs/routing.jsonl` (no prompt text).

## Limits

- Keyword scoring, not a learned model. It does not improve with use. When it is wrong, ignore it.
- A short prompt can hide a hard task, and a long one can be simple. Judge the task, not the length.
- Detail, tuning, and troubleshooting: `reference.md`.
