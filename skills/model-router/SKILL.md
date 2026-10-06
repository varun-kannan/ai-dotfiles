---
name: model-router
description: Analyze task complexity and auto-route to optimal Claude model (Haiku/Sonnet/Opus) with post-task suggestions for token efficiency and cost savings.
---

# Model Router: Smart Model Selection

Route tasks to the right Claude model based on complexity, then suggest cheaper alternatives if you overspent tokens.

## How it works

### 1. Pre-task routing (automatic via hook)

When you send a request, the router:
- Scans your task for complexity signals
- Recommends: **fast** (Haiku), **standard** (Sonnet), **frontier** (Opus)
- Switches the model automatically
- Runs your task

### 2. Post-task suggestion (manual check)

After a response, you can ask:
> "Check if this used the right model"

The router analyzes:
- **Token count** — did we overspend?
- **Task complexity** — was the model overkill or underpowered?
- **Suggestions** — re-run with Model X to save Y% tokens, Z seconds faster

## Complexity scoring

### Fast (Haiku 4.5) — $0.80 / 1M input tokens
- Classification, simple Q&A, templates, formatting
- Keywords: "format", "summarize", "classify", "extract", "split", "parse", "list"
- Token budget: under 2,000 tokens expected
- Good for: one-shot tasks, API calls, filtering

### Standard (Sonnet 5) — $3 / 1M input tokens
- Normal coding, debugging, rewriting, moderate reasoning
- Keywords: "fix", "refactor", "write", "explain", "implement", "review", "test"
- Token budget: 2,000–15,000 tokens expected
- Good for: most everyday work, multi-step tasks

### Frontier (Opus 5) — $15 / 1M input tokens
- Complex multi-step reasoning, architecture, strategy, deep analysis
- Keywords: "design", "architect", "strategy", "analyze", "research", "optimize"
- Token budget: 15,000+ tokens expected
- Good for: system design, code reviews at scale, novel problems

## Usage

### Check model recommendation for your current task
```
/model-router analyze
```
Output:
```
Task: "Write a function to validate email addresses"
Complexity: STANDARD (Sonnet 5)
Reasoning: Implementation + testing, moderate logic

Current model: Opus 5
Recommendation: Switch to Sonnet 5
Estimated savings: 67% fewer tokens, 3x cheaper, slightly faster
```

### After a response, check if you overspent
```
/model-router check-response
```
Output:
```
Tokens used: 1,847 input, 523 output
Model used: Opus 5
Analysis: OVERPROVIDED
  This task could run on Haiku 4.5 (90% token savings)
  Re-run with Haiku for: format-only work, simple list

Actual task: "Format this JSON"
Complexity detected: FAST

Recommendation: Re-run with /model claude-haiku-4-5
Estimated: 185 tokens total, $0.0001, instant
```

### View current model tier and pricing
```
/model-router status
```

## Integration with hooks

**Automatic pre-task routing** (enabled by default after setup):
- Every message is scanned before execution
- Model is auto-switched if a better fit is detected
- You see the suggested model in the response header
- Can disable with `/model-router hook disable`

**Post-task analysis** (manual, triggered by you):
- Ask "Check if this used the right model" after a response
- Router suggests re-run with savings estimate
- You decide whether to re-run

## Disabling auto-routing

If you want to keep a specific model, disable the hook:
```bash
# Disable for this session only
/model-router hook disable

# Re-enable
/model-router hook enable

# Check hook status
/model-router hook status
```

Or set a default model:
```bash
/model claude-opus-5  # locks to Opus, router suggests but doesn't switch
```

## Pricing comparison (as of Oct 2026)

| Model | Input | Output | Best for |
|---|---|---|---|
| Haiku 4.5 | $0.80/1M | $4/1M | Fast, cheap, classification |
| Sonnet 5 | $3/1M | $15/1M | Balanced, general work |
| Opus 5 | $15/1M | $75/1M | Complex reasoning, strategy |

**Example savings:** A 5,000-token task costs $0.15 on Opus but only $0.015 on Haiku — 90% less.

## Token counting

Estimates use Claude's official token counters. Actual usage shown after each response. The router learns from your patterns and improves recommendations over time.
