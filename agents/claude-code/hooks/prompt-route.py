#!/usr/bin/env python3
"""UserPromptSubmit hook: keep the project harness current, and make two gated suggestions.

Reads the hook JSON on stdin and prints at most one JSON object:
  systemMessage                          a model-fit note, shown to the user only (no tokens)
  hookSpecificOutput.additionalContext   added to the model's context, kept to a few lines

Every "should I say anything" choice goes through the decision engine
(~/.ai-rules/engine/decide.py), which logs it so outcomes can be measured later.
The hook never blocks a prompt. Any failure exits 0 with no output.

Turn it off with AI_ROUTER_OFF=1 or by creating ~/.ai-rules/router.off.

Usage:
    prompt-route.py --self-test
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
MIN_PROMPT_CHARS = 20     # shorter prompts are continuations ("yes", "push it")
LONG_PROMPT_CHARS = 1500  # a long prompt carries real context; do not suggest a cheaper model
EARLY_PROMPTS = 3         # after this, switching to a cheaper model discards a warm prompt cache
SUGGEST_EVERY = 5         # prompts between repeats of a model suggestion
TRANSCRIPT_TAIL = 400_000
RANK = {"fast": 0, "standard": 1, "frontier": 2}
LOG_LIMIT = 1_000_000


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


def model_note(prompt, current, n_prompt, router, decide, ctx):
    """Return (message or None, suggested model id or None)."""
    _, analysis = router.analyze_complexity(prompt)
    scores = analysis["scores"]
    rec = decide.decide("model_tier", scores, log=False)["answer"]
    if rec is None or rec == current:
        return None, None
    ordered = sorted(scores.values(), reverse=True)
    down = RANK[rec] < RANK[current]
    new = router.MODELS[rec]
    d = decide.decide("model_suggestion_useful", {
        "gap": min(ordered[0] - ordered[1], 4) / 4.0,
        "down_late": int(down and n_prompt > EARLY_PROMPTS),
        "down_long": int(down and len(prompt) > LONG_PROMPT_CHARS),
    }, ctx=dict(ctx, suggested=new["id"]))
    if d["answer"] is not True:
        return None, None
    cur = router.MODELS[current]
    if down:
        ratio = max(1, round(cur["output_cost"] / new["output_cost"]))
        text = ("[model-router] This reads as a %s task and you are on %s. %s would handle it at about "
                "1/%d of the per-token price. Switch with: /model %s" % (rec, cur["name"], new["name"], ratio, new["id"]))
    else:
        text = ("[model-router] This reads as a %s task and you are on %s, which may struggle with it. "
                "Consider: /model %s" % (rec, cur["name"], new["id"]))
    return text, new["id"]


def task_specific(prompt, cwd, tier, cm):
    """Items the loader picks because of this prompt's own words, by category."""
    with_task = cm.plan(prompt, cwd, tier_flag=tier)
    if not with_task["project_tags"]:
        return {}
    baseline = cm.plan("", cwd, tier_flag=tier)
    base = {i["name"] for items in baseline["selected"].values() for i in items}
    return {cat: [i["name"] for i in items if i["name"] not in base and i["name"] != "model-router"]
            for cat, items in with_task["selected"].items()}


def pointer_text(picked):
    parts = ["For this task:"]
    if picked.get("rules"):
        parts.append("domain rules in ~/.ai-rules/rules/domains/: %s." % ", ".join(picked["rules"]))
    if picked.get("skills"):
        parts.append("Skills that fit: %s." % ", ".join(picked["skills"]))
    if picked.get("agents"):
        parts.append("Subagents that fit: %s." % ", ".join(picked["agents"]))
    if picked.get("memory"):
        parts.append("Project memory worth reading, in .fieldbook/bank/: %s." % ", ".join(picked["memory"]))
    return " ".join(parts)


def log_line(record):
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
    sys.path.insert(0, str(SHARED))
    from engine import decide, generate, session
    router = load_module(SHARED / "skills" / "model-router" / "router.py", "model_router")
    cm = load_module(SHARED / "bin" / "context-manager.py", "context_manager")
    if router is None:
        return None

    cwd = data.get("cwd") or os.getcwd()
    sid = data.get("session_id")
    transcript = data.get("transcript_path")
    state = session.load(sid)
    state["n"] = state.get("n", 0) + 1
    ctx = {"session": sid, "transcript": transcript}
    context = []

    # A manifest or .git may have appeared since the session started.
    result = generate.auto(cwd, "prompt")
    if result.get("action") in ("setup", "updated") and result.get("block"):
        context.append("The project harness block in AGENTS.md was just %s. Its current content:\n\n%s"
                       % ("generated" if result["action"] == "setup" else "updated", result["block"]))
    has_block = result.get("action") in ("setup", "updated", "current") and "root" in result

    model = last_model(transcript) or state.get("model")
    current = tier_for_model(model, router)
    message = None
    if current and state["n"] - state.get("last_suggest", -SUGGEST_EVERY) >= SUGGEST_EVERY:
        message, _ = model_note(prompt, current, state["n"], router, decide, ctx)
        if message:
            state["last_suggest"] = state["n"]

    pointed = False
    if cm is not None and not context:
        try:
            picked = task_specific(prompt, cwd, current or "standard", cm)
        except (Exception, SystemExit):
            picked = {}
        shown = set(state.get("shown", []))
        fresh = {cat: [n for n in names if n not in shown] for cat, names in picked.items()}
        fresh = {cat: names for cat, names in fresh.items() if names}
        count = sum(len(v) for v in fresh.values())
        if count:
            names = [("domains/%s.md" % n) if cat == "rules" else n for cat, ns in fresh.items() for n in ns]
            d = decide.decide("pointer_useful", {
                "new_specific": min(count, 3) / 3.0,
                "first_prompt": int(state["n"] == 1),
                "has_block": int(has_block),
                "short_prompt": int(len(prompt) < 60),
            }, ctx=dict(ctx, names=names))
            if d["answer"] is True:
                context.append(pointer_text(fresh))
                state["shown"] = sorted(shown | {n for ns in fresh.values() for n in ns})
                pointed = True

    session.save(sid, state)
    log_line({"ts": int(time.time()), "project": os.path.basename(cwd), "model": model,
              "suggested": bool(message), "pointer": pointed, "harness": result.get("action"),
              "prompt_chars": len(prompt)})

    out = {}
    if message:
        out["systemMessage"] = message
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(context)}
    return out or None


def self_test():
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    sys.path.insert(0, str(SHARED))
    try:
        import engine
        from engine import decide
    except ImportError:
        print("FAIL engine not found under", SHARED)
        return 1
    router = load_module(SHARED / "skills" / "model-router" / "router.py", "model_router")
    if router is None:
        print("FAIL router not found under", SHARED)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        # Decisions made by the test must not land in the real logs.
        decide.SHARED, decide.DATA = Path(tmp), Path(tmp) / "data"
        check("tier by exact id", tier_for_model("claude-opus-5-5", router) == "frontier")
        check("tier by family name", tier_for_model("claude-haiku-4-5-20251001", router) == "fast")
        check("unknown model has no tier", tier_for_model("gpt-x", router) is None)

        simple = "format this json list and sort the keys then validate it"
        hard = "design the architecture and evaluate and compare strategy options for the research platform"
        text, model = model_note(simple, "frontier", 1, router, decide, {})
        check("simple task on frontier suggests a cheaper model", bool(text) and model == "claude-haiku-5-5")
        text, _ = model_note(simple, "frontier", 9, router, decide, {})
        check("no cheaper-model note late in a session", text is None)
        text, _ = model_note(hard, "fast", 9, router, decide, {})
        check("hard task on fast suggests a stronger model at any point", bool(text) and "may struggle" in text)
        text, _ = model_note("write a function to parse the config", "standard", 1, router, decide, {})
        check("matching tier gives no note", text is None)
        text, _ = model_note("hello there how are you today my friend", "frontier", 1, router, decide, {})
        check("no signal gives no note", text is None)

        tpath = Path(tmp) / "t.jsonl"
        tpath.write_text("\n".join([
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-sonnet-5-5"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "<synthetic>"}}),
            "not json",
        ]), encoding="utf-8")
        check("last model skips synthetic and bad lines", last_model(str(tpath)) == "claude-sonnet-5-5")
        check("missing transcript gives None", last_model(str(Path(tmp) / "nope")) is None)
        check("pointer text names each category", "Skills that fit: testing-guide." in pointer_text({"skills": ["testing-guide"]}))

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
