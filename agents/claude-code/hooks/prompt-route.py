#!/usr/bin/env python3
"""UserPromptSubmit hook: model-fit suggestion and a short harness plan pointer.

Reads the hook JSON on stdin and prints at most one JSON object:
  systemMessage                          shown to the user only, costs no tokens
  hookSpecificOutput.additionalContext   added to the model's context, a few lines

It never blocks a prompt. Any failure exits 0 with no output, because a hook that
breaks prompts gets deleted.

The hook input has no model field, so the current model is read from the last
assistant message in the transcript. On the first prompt of a session there is
none, and no model suggestion is made.

Turn it off with AI_ROUTER_OFF=1 or by creating ~/.ai-rules/router.off.

Usage:
    prompt-route.py --self-test
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
MIN_PROMPT_CHARS = 20   # shorter prompts are continuations ("yes", "push it")
MAX_DOWNGRADE_CHARS = 1500  # a long prompt carries real context; do not suggest a cheaper model
SUGGEST_EVERY = 5       # prompts between repeats of a model suggestion
MIN_CONFIDENCE = 2      # score gap between the chosen tier and the runner-up
TRANSCRIPT_TAIL = 400_000
RANK = {"fast": 0, "standard": 1, "frontier": 2}
LOG_LIMIT = 1_000_000
STATE_MAX_AGE = 7 * 86400


def load_module(path, name):
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_model(transcript_path):
    """Model id of the most recent assistant message, or None."""
    if not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TRANSCRIPT_TAIL))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        try:
            msg = json.loads(line).get("message") or {}
        except ValueError:
            continue
        model = msg.get("model")
        if msg.get("role") == "assistant" and isinstance(model, str) and not model.startswith("<"):
            return model
    return None


def tier_for_model(model, router):
    if not model:
        return None
    for tier, info in router.MODELS.items():
        if info["id"] == model:
            return tier
    low = model.lower()
    if "haiku" in low:
        return "fast"
    if "sonnet" in low:
        return "standard"
    if "opus" in low or "fable" in low or "mythos" in low:
        return "frontier"
    return None


def decide(prompt, current, router):
    """Return a user-facing suggestion, or None when the model fits."""
    rec, analysis = router.analyze_complexity(prompt)
    scores = analysis["scores"]
    confidence = scores[rec] - max(v for k, v in scores.items() if k != rec)
    if confidence < MIN_CONFIDENCE or rec == current:
        return None, rec, confidence
    cur, new = router.MODELS[current], router.MODELS[rec]
    if RANK[rec] < RANK[current]:
        if len(prompt) > MAX_DOWNGRADE_CHARS:
            return None, rec, confidence
        ratio = max(1, round(cur["output_cost"] / new["output_cost"]))
        text = ("[model-router] This reads as a %s task and you are on %s. %s would handle it at about "
                "1/%d of the per-token price. Switch with: /model %s"
                % (rec, cur["name"], new["name"], ratio, new["id"]))
    else:
        text = ("[model-router] This reads as a %s task and you are on %s, which may struggle with it. "
                "Consider: /model %s" % (rec, cur["name"], new["id"]))
    return text, rec, confidence


def pointer(prompt, cwd, tier, cm):
    """Short factual pointer to the files the loader picked, or (None, None)."""
    plan = cm.plan(prompt, cwd, tier_flag=tier)
    if not plan["project_tags"]:
        return None, None
    names = lambda cat: [i["name"] for i in plan["selected"][cat]]
    rules = names("rules")
    skills = [n for n in names("skills") if n != "model-router"][:4]
    agents = names("agents")[:3]
    memory = names("memory")[:3]
    key = "|".join([tier] + rules + skills + agents + memory)
    parts = ["Harness plan for this task (budget tier %s, about %d of %d tokens if all are read):"
             % (tier, plan["used"]["total"], plan["budget"]["total"])]
    if rules:
        parts.append("Domain rules to apply, in ~/.ai-rules/rules/domains/: %s." % ", ".join(rules))
    if skills:
        parts.append("Skills likely relevant: %s." % ", ".join(skills))
    if agents:
        parts.append("Subagents that fit: %s." % ", ".join(agents))
    if memory:
        parts.append("Project memory worth reading, in .fieldbook/bank/: %s." % ", ".join(memory))
    return " ".join(parts), key


def load_state(session):
    path = SHARED / "state" / (session + ".json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(session, state):
    directory = SHARED / "state"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (session + ".json")).write_text(json.dumps(state), encoding="utf-8")
    cutoff = time.time() - STATE_MAX_AGE
    for old in directory.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def log_decision(record):
    directory = SHARED / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "routing.jsonl"
    try:
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.replace(directory / "routing.jsonl.1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def run(data):
    prompt = (data.get("prompt") or "").strip()
    if len(prompt) < MIN_PROMPT_CHARS or prompt.startswith("/"):
        return None
    router = load_module(SHARED / "skills" / "model-router" / "router.py", "model_router")
    if router is None:
        return None
    cwd = data.get("cwd") or os.getcwd()
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or ""))[:64] or "nosession"
    state = load_state(session)
    state["n"] = state.get("n", 0) + 1

    model = last_model(data.get("transcript_path"))
    current = tier_for_model(model, router)
    message, rec, confidence = (None, None, 0)
    if current:
        message, rec, confidence = decide(prompt, current, router)
        if message and state["n"] - state.get("last_suggest", -SUGGEST_EVERY) < SUGGEST_EVERY:
            message = None
        if message:
            state["last_suggest"] = state["n"]

    context = None
    cm = load_module(SHARED / "bin" / "context-manager.py", "context_manager")
    if cm is not None:
        try:
            text, key = pointer(prompt, cwd, current or rec or "standard", cm)
        except (Exception, SystemExit):
            text, key = None, None
        if text and key != state.get("pointer_key"):
            context = text
            state["pointer_key"] = key

    save_state(session, state)
    log_decision({"ts": int(time.time()), "session": session, "project": os.path.basename(cwd),
                  "model": model, "current_tier": current, "recommended_tier": rec,
                  "confidence": confidence, "suggested": bool(message),
                  "pointer": bool(context), "prompt_chars": len(prompt)})

    out = {}
    if message:
        out["systemMessage"] = message
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": context}
    return out or None


def self_test():
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    router = load_module(SHARED / "skills" / "model-router" / "router.py", "model_router")
    if router is None:
        print("FAIL router not found under", SHARED)
        return 1

    check("tier by exact id", tier_for_model("claude-opus-5-5", router) == "frontier")
    check("tier by family name", tier_for_model("claude-haiku-4-5-20251001", router) == "fast")
    check("unknown model has no tier", tier_for_model("gpt-x", router) is None)

    text, rec, _ = decide("format this json list and sort the keys then validate it", "frontier", router)
    check("simple task on frontier suggests a cheaper model", text and "/model claude-haiku-5-5" in text and "1/40" in text)
    text, rec, _ = decide("design the architecture and evaluate and compare strategy options for the research platform", "fast", router)
    check("hard task on fast suggests a stronger model", text and "may struggle" in text)
    text, _, _ = decide("write a function to parse the config", "standard", router)
    check("matching tier gives no suggestion", text is None)
    text, _, _ = decide("hello there how are you today my friend", "frontier", router)
    check("no signal gives no suggestion", text is None)

    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp) / "t.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-sonnet-5-5"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "<synthetic>"}}),
            "not json",
        ]
        tpath.write_text("\n".join(lines), encoding="utf-8")
        check("last model skips synthetic and bad lines", last_model(str(tpath)) == "claude-sonnet-5-5")
        check("missing transcript gives None", last_model(str(Path(tmp) / "nope")) is None)

    for label in failures:
        print("FAIL", label)
    if not failures:
        print("ok")
    return 1 if failures else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    try:
        if os.environ.get("AI_ROUTER_OFF") == "1" or (SHARED / "router.off").exists():
            return 0
        result = run(json.load(sys.stdin))
        if result:
            print(json.dumps(result))
    except (Exception, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
