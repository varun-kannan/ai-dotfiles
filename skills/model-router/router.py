#!/usr/bin/env python3
"""
Model router: analyze task complexity and suggest optimal Claude model.
"""
import os
import sys

# Run isolated (python3 -I): no PYTHONPATH, no user site, and not the current folder on the
# module path, which may be a repository with a file named like a standard module. A start
# without -I (from a #! line or a hook command) restarts once with it.
if not sys.flags.isolated and __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
import json
import re
from collections import Counter

# Model tiers with pricing and thresholds
MODELS = {
    "fast": {
        "name": "Claude Haiku 5.5",
        "id": "claude-haiku-5-5",
        "input_cost": 0.10,  # per 1M tokens, prompts up to 100K (0.50/2.50 beyond)
        "output_cost": 0.50,
        "token_budget": 2000,
        "speed": "fastest",
        "latency_ms": 300,
    },
    "standard": {
        "name": "Claude Sonnet 5.5",
        "id": "claude-sonnet-5-5",
        "input_cost": 2.0,
        "output_cost": 10.0,
        "token_budget": 15000,
        "speed": "fast",
        "latency_ms": 600,
    },
    "frontier": {
        "name": "Claude Opus 5.5",
        "id": "claude-opus-5-5",
        "input_cost": 4.0,
        "output_cost": 20.0,
        "token_budget": 200000,
        "speed": "slower but most capable",
        "latency_ms": 1000,
    },
}

RANK = {"fast": 0, "standard": 1, "frontier": 2}

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

# Small mechanical edits. Each counts double for the fast tier, and they are the one case
# where the fast tier can win over a standard keyword ("fix the typo").
TRIVIAL_KEYWORDS = [
    "typo",
    "spelling",
    "rename",
    "commit",
    "push",
    "whitespace",
    "indent",
    "capitalize",
]
TRIVIAL_MAX_CHARS = 120

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
    "update",
    "upgrade",
    "add",
    "change",
    "migrate",
    "remove",
]

# Words that widen a task from one place to many.
SCOPE_KEYWORDS = ["across", "codebase", "everywhere", "every", "all", "entire", "whole"]

FRONTIER_KEYWORDS = [
    "design",
    "redesign",
    "architect",
    "architecture",
    "strategy",
    "analyze",
    "research",
    "plan",
    "evaluate",
    "assess",
    "compare",
    "novel",
    "complex",
    "investigate",
    "propose",
    "intermittent",
    "corruption",
    "race",
    "deadlock",
    "concurrency",
    "security",
    "vulnerability",
    "vulnerabilities",
]
FRONTIER_PHRASES = ["root cause", "trade-off", "tradeoff", "trade off"]


def analyze_complexity(task: str) -> tuple[str, dict]:
    """
    Analyze task complexity and return model tier + reasoning.
    Returns: (tier: str, analysis: dict)
    """
    task_lower = task.lower()
    words = re.findall(r"\b\w+\b", task_lower)

    # Count keyword matches
    trivial = sum(1 for w in words if w in TRIVIAL_KEYWORDS)
    fast_score = sum(1 for w in words if w in FAST_KEYWORDS) + 2 * trivial
    standard_score = sum(1 for w in words if w in STANDARD_KEYWORDS) + sum(1 for w in words if w in SCOPE_KEYWORDS)
    frontier_score = sum(1 for w in words if w in FRONTIER_KEYWORDS) + sum(1 for p in FRONTIER_PHRASES if p in task_lower)

    keywords = fast_score + standard_score + frontier_score     # before the length and code adjustments

    # Heuristics
    task_length = len(task)
    word_count = len(words)
    has_code = "```" in task or bool(re.search(r"\b(function|class|def|const|import|return)\b\s*[\w({]", task))
    has_multipart = sum(1 for w in words if w in ("and", "also", "plus"))

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
    # A short mechanical edit goes to the fast tier even beside a standard keyword
    # ("fix the typo"), as long as nothing points higher.
    small_edit = trivial and not frontier_score and not has_code and task_length <= TRIVIAL_MAX_CHARS \
        and fast_score > standard_score
    if small_edit:
        tier = "fast"
    elif frontier_score > standard_score:
        tier = "frontier"
    elif standard_score or frontier_score:
        tier = "standard"            # a tie goes to standard
    elif fast_score:
        tier = "fast"                # the cheap tier needs a clear field: no other signal at all
    else:
        tier = "standard"            # no signal

    analysis = {
        "tier": tier,
        "scores": scores,
        "keywords": keywords,
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

    # Map model ID to tier, by exact id first, then by family name
    low = current_model.lower()
    for t, m in MODELS.items():
        if m["id"] == current_model or m["name"].lower() in low:
            current_tier = t
            break
    if current_tier is None:
        current_tier = ("fast" if "haiku" in low else "standard" if "sonnet" in low
                        else "frontier" if any(f in low for f in ("opus", "fable", "mythos")) else None)

    if not current_tier:
        return {"error": "Could not identify current model", "task": task}

    total_tokens = input_tokens + output_tokens
    current_cost = (
        MODELS[current_tier]["input_cost"] * input_tokens / 1_000_000
        + MODELS[current_tier]["output_cost"] * output_tokens / 1_000_000
    )

    if not analysis["keywords"]:
        return {"task": task[:100], "current_tier": current_tier, "verdict": "NO_SIGNAL",
                "note": "The task has no keywords the router scores; no suggestion."}

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
        savings_pct = round((1 - alt_cost / current_cost) * 100) if current_cost else 0
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
        savings_pct = round((1 - alt_cost / current_cost) * 100) if current_cost else 0
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
    elif RANK[current_tier] < RANK[recommended_tier]:
        alt_model = MODELS[recommended_tier]
        alt_cost = (
            alt_model["input_cost"] * input_tokens / 1_000_000
            + alt_model["output_cost"] * output_tokens / 1_000_000
        )
        result["suggestions"].append(
            {
                "action": "UNDERPOWERED",
                "reason": f"Task is {recommended_tier}, but using {MODELS[current_tier]['name']}",
                "note": "A weaker model may need retries on this kind of task, which can cost more than one run on the stronger model.",
                "alternative": alt_model["name"],
                "estimated_cost": round(alt_cost, 4),
                "extra_cost_usd": round(alt_cost - current_cost, 4),
                "command": f"/model {alt_model['id']}",
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
        try:
            input_tokens = int(sys.argv[4])
            output_tokens = int(sys.argv[5])
        except ValueError:
            print("Error: input_tokens and output_tokens must be whole numbers", file=sys.stderr)
            sys.exit(2)
        result = suggest_rerun(task, current_model, input_tokens, output_tokens)
        print(json.dumps(result, indent=2))
