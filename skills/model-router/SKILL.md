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

`analyze` prints the tier, the keyword scores, and the model. The fast tier is chosen when a prompt has fast keywords and no standard or frontier signal, or for a short mechanical edit (typo, rename, commit, push) of at most 120 characters with no code and no frontier signal, where the fast score is higher than the standard one. Frontier needs more frontier signals than standard ones. A tie goes to standard, and so does a prompt with no keyword at all, which also gets no model note. `suggest` takes the task, the model used, and real input and output token counts (whole numbers). An unknown model prints `{"error": ...}`. It prints a cheaper alternative with the saving, a stronger one with the extra cost, `OPTIMAL`, or `NO_SIGNAL` when the task has no keyword it scores. Token counts are known only after a response, so `suggest` is a check after the fact.

## The prompt hook

`install.sh` registers `prompt-route.py` as a `UserPromptSubmit` hook. On every prompt it keeps the project's setup current. For prompts of 20 characters or more that are not slash commands it also:

- finds the model in use: a `/model` switch newer than the last reply, else the last reply's model in the main conversation, else the model recorded at session start,
- scores the prompt and, when the decision engine judges it worth saying, prints a `[model-router]` note to you only, so it costs no tokens,
- names rules, skills, subagents or project memory the prompt's words point to, when the decision engine judges the note useful and the items were not named earlier in the session.

A model note appears at most once per 5 prompts. With the shipped weights a cheaper model is never suggested after the third counted prompt of a session (prompts under 20 characters and slash commands are not counted) or for a prompt over 1,500 characters, because switching then discards the prompt cache; a stronger model can be suggested at any point.

`touch ~/.ai-rules/router.off` or `AI_ROUTER_OFF=1` turns the two notes off and leaves project setup running. Each prompt adds one line to `~/.ai-rules/logs/routing.jsonl` (no prompt text).

## Limits

- The tier comes from keyword scoring and does not improve with use. Whether a note is shown does: `harness learn` recalibrates that from whether you switched. When a note is wrong, ignore it.
- A short prompt can hide a hard task, and a long one can be simple. Judge the task, not the length.
- A prompt with no keyword the router knows ("yes, go ahead", "what does this regex do") gets no model note at all, even when it carries code.
- Detail, tuning, and troubleshooting: `reference.md`.
