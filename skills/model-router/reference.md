# Model Router — Setup & Implementation Guide

## Quick Start

### 1. Check complexity of your current task (before running it)

In any Claude Code session:
```
What model should I use for: "Refactor this function to reduce complexity"
```

The model-router skill analyzes it and suggests the tier. Output:

```
ANALYSIS:
Detected complexity: STANDARD (Sonnet 5)
Reasoning:
  - Keywords: "refactor" (standard work)
  - Code present: yes (+2 standard score)
  - Single-part task

Recommendation: Use Sonnet 5 (claude-sonnet-5-20241022)
Current model: Opus 5 (overproviding)
Potential savings: 80% tokens, $0.05 vs $0.25, 2x faster
```

### 2. Auto-routing with a hook (optional, advanced)

To automatically switch models before each task, add this hook to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^Claude response starts",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/model-router-pre-hook.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

The hook:
- Receives your task from stdin
- Calls `router.py analyze`
- Switches the model if needed
- Outputs a note: "Routing to Sonnet 5 for this task"

**Note:** Claude Code's hook system has limitations. For now, **manual invocation is more reliable**:

```
# Before a task, ask:
/model-router analyze "your task here"

# After a response, ask:
Check if this used the right model
```

### 3. Post-task analysis (after any response)

After Claude completes a response, you can ask:
```
Analyze the tokens used: was this the right model?
```

Output (example):
```
RESPONSE ANALYSIS:
Task: "Format a JSON file"
Tokens used: 1,200 input, 180 output (total: 1,380)
Model used: Opus 5
Complexity detected: FAST (should be Haiku)

VERDICT: OVERPROVIDED
  - Task is classification/formatting (Haiku level)
  - Opus cost: $0.018
  - Haiku cost: $0.001
  - Savings: $0.017 (94%)

Recommendation: Re-run with Haiku 4.5
  /model claude-haiku-4-5-20251001
```

## Model Selection Workflow

```
┌─ Task arrives
│
├─→ Ask: "What model for this?"
│   (or invoke /model-router analyze "task")
│
├─→ Router suggests tier
│   (fast / standard / frontier)
│
├─→ Manually: /model <suggested-model-id>
│   (or hook auto-switches)
│
├─→ Task runs
│
└─→ After response, ask:
    "Check if this used the right model"
    (suggests re-run if better option exists)
```

## Token Savings Examples

| Task | Current | Best | Savings |
|---|---|---|---|
| "Format JSON" | Opus: 1.4K tokens, $0.018 | Haiku: 140 tokens, $0.001 | 90% |
| "Write function" | Opus: 8K tokens, $0.12 | Sonnet: 8K tokens, $0.03 | 75% |
| "Design system" | Sonnet: 15K tokens, $0.045 | Opus: 15K tokens, $0.225 | (stay Opus) |

## When to use each model

### Haiku 4.5 (fast, cheapest)
- ✅ Formatting, parsing, validation
- ✅ Classifying text or data
- ✅ Simple extraction
- ❌ Complex logic, design, strategy
- Token limit: ~2,000 before slowdown

### Sonnet 5 (balanced)
- ✅ Most coding tasks, refactoring, testing
- ✅ Debugging and explaining code
- ✅ Moderate multi-step reasoning
- ❌ Deep system design, novel problems
- Token limit: ~15,000 optimal range

### Opus 5 (frontier, most capable)
- ✅ Complex architecture and design
- ✅ Novel problems, research
- ✅ Deep reasoning across many domains
- ✅ Large codebases, detailed analysis
- ❌ Overkill for simple tasks
- Token limit: 200,000 (highest)

## Advanced: Custom Complexity Rules

Edit `router.py` to customize keyword scoring:

```python
# Add your own keywords
FRONTIER_KEYWORDS = [
    "design", "architect", "strategy",
    "YOUR_KEYWORD_HERE",  # custom signal
]

# Or modify token budgets per domain
MODELS["frontier"]["token_budget"] = 100000  # for your use case
```

Then re-run `./install.sh` to deploy the updated skill.

## Troubleshooting

**Q: The router suggests a model but I disagree**

A: You're right to override it. The router uses heuristics, not ML. If your task is simpler or more complex than the keywords suggest, manually set the model:
```bash
/model claude-opus-5-20240729  # lock to Opus
```

**Q: How do I know token counts before running?**

A: You can't — only Claude knows after running. That's why post-task analysis is useful. After the first run, you'll know if you need a re-run on a cheaper model.

**Q: Can I disable the router?**

A: Yes. The skill is optional. Just don't invoke it, and Claude Code uses whatever model you've set globally (default: Opus).

**Q: What if I always want Opus?**

A: Set it globally:
```bash
/model claude-opus-5-20240729
```
The router will note you're overproviding, but it won't force a switch.

## Integration with ai-dotfiles

The model-router skill is part of your ai-dotfiles repo. It's installed to:
- `~/.claude/skills/model-router/` (Claude Code)
- `~/.codex/skills/model-router/` (Codex, if installed)

To update it:
```bash
cd ~/Documents/ai-dotfiles
# Edit skills/model-router/router.py or SKILL.md
./install.sh
```

Changes take effect immediately in new sessions.
