#!/usr/bin/env python3
"""
Model router: analyze task complexity and suggest optimal Claude model.
"""
import sys
import json
import re
from collections import Counter

# Model tiers with pricing and thresholds
MODELS = {
    "fast": {
        "name": "Claude Haiku 4.5",
        "id": "claude-haiku-4-5-20251001",
        "input_cost": 0.80,  # per 1M tokens
        "output_cost": 4.0,
        "token_budget": 2000,
        "speed": "fastest",
        "latency_ms": 300,
    },
    "standard": {
        "name": "Claude Sonnet 5",
        "id": "claude-sonnet-5-20241022",
        "input_cost": 3.0,
        "output_cost": 15.0,
        "token_budget": 15000,
        "speed": "fast",
        "latency_ms": 600,
    },
    "frontier": {
        "name": "Claude Opus 5",
        "id": "claude-opus-5-20240729",
        "input_cost": 15.0,
        "output_cost": 75.0,
        "token_budget": 200000,
        "speed": "slower but most capable",
        "latency_ms": 1000,
    },
}

FAST_KEYWORDS = [
    "format",
    "summarize",
    "classify",
    "extract",
    "split",
    "parse",
    "list",
    "sort",
    "filter",
    "convert",
    "validate",
    "check",
]

STANDARD_KEYWORDS = [
    "fix",
    "refactor",
    "write",
    "explain",
    "implement",
    "review",
    "test",
    "debug",
    "optimize",
    "improve",
    "rewrite",
]

FRONTIER_KEYWORDS = [
    "design",
    "architect",
    "strategy",
    "analyze",
    "research",
    "plan",
    "evaluate",
    "assess",
    "compare",
    "novel",
    "complex",
]


def analyze_complexity(task: str) -> tuple[str, dict]:
    """
    Analyze task complexity and return model tier + reasoning.
    Returns: (tier: str, analysis: dict)
    """
    task_lower = task.lower()
    words = re.findall(r"\b\w+\b", task_lower)

    # Count keyword matches
    fast_score = sum(1 for w in words if w in FAST_KEYWORDS)
    standard_score = sum(1 for w in words if w in STANDARD_KEYWORDS)
    frontier_score = sum(1 for w in words if w in FRONTIER_KEYWORDS)

    # Heuristics
    task_length = len(task)
    word_count = len(words)
    has_code = "```" in task or bool(re.search(r"function|class|def|const", task_lower))
    has_multipart = task.count("and") + task.count("also") + task.count("plus")

    # Score adjustments
    if has_code:
        standard_score += 2
    if has_multipart > 2:
        frontier_score += 1
    if task_length > 500:
        standard_score += 1
    if task_length > 1000:
        frontier_score += 1

    # Determine tier
    scores = {
        "fast": fast_score,
        "standard": standard_score,
        "frontier": frontier_score,
    }
    tier = max(scores, key=scores.get)

    # If no signals, default to standard
    if sum(scores.values()) == 0:
        tier = "standard"

    analysis = {
        "tier": tier,
        "scores": scores,
        "signals": {
            "task_length": task_length,
            "word_count": word_count,
            "has_code": has_code,
            "multipart_indicators": has_multipart,
        },
        "model": MODELS[tier],
    }

    return tier, analysis


def suggest_rerun(
    task: str, current_model: str, input_tokens: int, output_tokens: int
) -> dict:
    """
    Analyze if the model was appropriate, suggest alternatives.
    """
    tier, analysis = analyze_complexity(task)
    recommended_tier = tier
    current_tier = None

    # Map model ID to tier
    for t, m in MODELS.items():
        if m["id"] in current_model or m["name"].lower() in current_model.lower():
            current_tier = t
            break

    if not current_tier:
        return {"error": "Could not identify current model", "task": task}

    total_tokens = input_tokens + output_tokens
    current_cost = (
        MODELS[current_tier]["input_cost"] * input_tokens / 1_000_000
        + MODELS[current_tier]["output_cost"] * output_tokens / 1_000_000
    )

    # Analyze efficiency
    result = {
        "task": task[:100],
        "current_model": MODELS[current_tier]["name"],
        "current_tier": current_tier,
        "recommended_tier": recommended_tier,
        "tokens_used": {"input": input_tokens, "output": output_tokens, "total": total_tokens},
        "cost_usd": round(current_cost, 4),
        "suggestions": [],
    }

    # Generate suggestions
    if current_tier == "frontier" and recommended_tier in ["fast", "standard"]:
        alt_tier = recommended_tier
        alt_model = MODELS[alt_tier]
        alt_cost = (
            alt_model["input_cost"] * input_tokens / 1_000_000
            + alt_model["output_cost"] * output_tokens / 1_000_000
        )
        savings_pct = round((1 - alt_cost / current_cost) * 100)
        result["suggestions"].append(
            {
                "action": "OVERPROVIDED",
                "reason": f"Task is {recommended_tier}, but using Opus (frontier)",
                "alternative": alt_model["name"],
                "estimated_cost": round(alt_cost, 4),
                "savings_usd": round(current_cost - alt_cost, 4),
                "savings_pct": savings_pct,
                "latency_ms": alt_model["latency_ms"],
                "command": f"/model {alt_model['id']}",
            }
        )
    elif current_tier == "standard" and recommended_tier == "fast":
        alt_model = MODELS["fast"]
        alt_cost = (
            alt_model["input_cost"] * input_tokens / 1_000_000
            + alt_model["output_cost"] * output_tokens / 1_000_000
        )
        savings_pct = round((1 - alt_cost / current_cost) * 100)
        result["suggestions"].append(
            {
                "action": "OVERPROVIDED",
                "reason": f"Task is {recommended_tier}, but using Sonnet",
                "alternative": alt_model["name"],
                "estimated_cost": round(alt_cost, 4),
                "savings_usd": round(current_cost - alt_cost, 4),
                "savings_pct": savings_pct,
                "latency_ms": alt_model["latency_ms"],
                "command": f"/model {alt_model['id']}",
            }
        )
    elif current_tier == "fast" and recommended_tier in ["standard", "frontier"]:
        result["suggestions"].append(
            {
                "action": "UNDERPOWERED",
                "reason": f"Task is {recommended_tier}, but using Haiku",
                "note": "Haiku may struggle with complex tasks. Consider re-running with Sonnet or Opus.",
                "alternative": MODELS[recommended_tier]["name"],
                "command": f"/model {MODELS[recommended_tier]['id']}",
            }
        )
    elif current_tier == recommended_tier:
        result["verdict"] = "OPTIMAL"
        result["note"] = f"Model tier {current_tier} is well-matched for this task."

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: router.py [analyze|suggest] [task] [optional: current_model input_tokens output_tokens]")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "analyze":
        if len(sys.argv) < 3:
            print("Error: provide a task")
            sys.exit(1)
        task = " ".join(sys.argv[2:])
        tier, analysis = analyze_complexity(task)
        print(json.dumps({"tier": tier, **analysis}, indent=2))

    elif mode == "suggest":
        if len(sys.argv) < 6:
            print(
                "Error: provide task, current_model, input_tokens, output_tokens"
            )
            sys.exit(1)
        task = sys.argv[2]
        current_model = sys.argv[3]
        input_tokens = int(sys.argv[4])
        output_tokens = int(sys.argv[5])
        result = suggest_rerun(task, current_model, input_tokens, output_tokens)
        print(json.dumps(result, indent=2))
