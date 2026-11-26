#!/usr/bin/env python3
"""UserPromptSubmit hook: keep the project set up, then make two gated suggestions.

On every prompt, short ones and slash commands included, it first keeps the
project's generated setup current. Then, for prompts of 20 characters or more
that are not slash commands, it may add:
  systemMessage                          a model-fit note, shown to you only (no tokens)
  hookSpecificOutput.additionalContext   a short note naming rules, skills, subagents or
                                         memory this prompt points to, not named before
                                         in the session
Both suggestions go through the decision engine (~/.ai-rules/engine/decide.py).

It prints at most one JSON object and never blocks a prompt. A failure in one
part never stops the others. AI_ROUTER_OFF=1 or ~/.ai-rules/router.off turns off
the suggestions; ~/.ai-rules/harness.off turns off everything.

Usage:
    prompt-route.py --self-test
"""
import os
import sys

# Run isolated (python3 -I): no PYTHONPATH, no user site, and not the current folder on the
# module path, which may be a repository with a file named like a standard module. A start
# without -I (from a #! line or a hook command) restarts once with it.
if not sys.flags.isolated and __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
import importlib.util
import json
import re
import tempfile
import time
from pathlib import Path

SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
MIN_PROMPT_CHARS = 20     # shorter prompts are continuations ("yes", "push it")
LONG_PROMPT_CHARS = 1500  # a long prompt carries real context; do not suggest a cheaper model
EARLY_PROMPTS = 3         # after this, switching to a cheaper model discards a warm prompt cache
SUGGEST_EVERY = 5         # prompts between model suggestions
TAIL_CHUNK = 256_000
TAIL_MAX = 4_000_000
RANK = {"fast": 0, "standard": 1, "frontier": 2}
LOG_LIMIT = 1_000_000
KEEP_ROTATED = 5
MODEL_SET = re.compile(r"<local-command-stdout>\s*Set model to\s+`?([\w.\-\[\]]+)`?")


def load_module(path, name):
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tail_lines(path):
    """Lines from the end of a file, newest first, reading backward in chunks."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            carry = b""
            read = 0
            while pos > 0 and read < TAIL_MAX:
                step = min(TAIL_CHUNK, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step) + carry
                read += step
                parts = chunk.split(b"\n")
                carry = parts[0]
                for line in reversed(parts[1:]):
                    if line.strip():
                        yield line
            if carry.strip() and pos == 0:
                yield carry
    except OSError:
        return


def last_model(transcript_path):
    """The model in use: a /model switch newer than the last reply, else the last reply's model."""
    if not transcript_path:
        return None
    for raw in _tail_lines(transcript_path):
        try:
            entry = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            m = MODEL_SET.search(msg["content"])
            if m:
                return m.group(1)
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


def model_note(prompt, model, current, n_prompt, router, decide, ctx):
    """Return (message or None, suggested model id or None)."""
    rec, analysis = router.analyze_complexity(prompt)
    scores = analysis["scores"]
    if rec == current or not analysis.get("keywords"):
        return None, None             # same tier, or no word in the prompt that the router scores
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
    known = {m["id"]: m for m in router.MODELS.values()}
    if down:
        price = ""
        if model in known:
            ratio = max(1, round(known[model]["output_cost"] / new["output_cost"]))
            price = " at about 1/%d of the per-token price" % ratio
        text = ("[model-router] This reads as a %s task and you are on %s. %s would handle it%s. Switch with: /model %s"
                % (rec, model, new["name"], price, new["id"]))
    else:
        text = ("[model-router] This reads as a %s task and you are on %s, which may struggle with it. "
                "Consider: /model %s" % (rec, model, new["id"]))
    return text, new["id"]


def pointer_text(fresh):
    parts = ["For this task:"]
    if fresh.get("rules"):
        parts.append("domain rules %s, in ~/.ai-rules/rules/domains/." % ", ".join(n + ".md" for n in fresh["rules"]))
    if fresh.get("skills"):
        parts.append("Skills that fit: %s." % ", ".join(fresh["skills"]))
    if fresh.get("agents"):
        parts.append("Subagents that fit: %s." % ", ".join(fresh["agents"]))
    if fresh.get("memory"):
        parts.append("Project memory worth reading, in .fieldbook/bank/: %s." % ", ".join(fresh["memory"]))
    return " ".join(parts)


def log_line(record):
    directory = SHARED / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "routing.jsonl"
    try:
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.replace(directory / ("routing.jsonl.%020d" % time.time_ns()))
            for old in sorted(directory.glob("routing.jsonl.*"))[:-KEEP_ROTATED]:
                old.unlink()
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _setup(engine_generate, cwd):
    try:
        return engine_generate.auto(cwd, "prompt")
    except Exception:
        return {"action": "error"}


def run(data):
    if not isinstance(data, dict):
        return None, {}
    sys.path.insert(0, str(SHARED))
    import engine
    from engine import decide, generate, session
    if engine.harness_off():
        return None, {}
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    prompt = data.get("prompt") if isinstance(data.get("prompt"), str) else ""
    prompt = prompt.strip()
    context, message, pointed = [], None, False

    result = _setup(generate, cwd)
    if result.get("action") in ("setup", "updated") and result.get("block"):
        where = ".harness/AGENTS.md" if result.get("mode") == "local" else "AGENTS.md"
        context.append("The project harness block in %s was just %s. Its current content:\n\n%s"
                       % (where, "generated" if result["action"] == "setup" else "updated", result["block"]))

    notes_off = os.environ.get("AI_ROUTER_OFF") == "1" or (SHARED / "router.off").exists()
    record = {"ts": int(time.time()), "harness": result.get("action"), "prompt_chars": len(prompt)}
    if notes_off or len(prompt) < MIN_PROMPT_CHARS or prompt.startswith("/"):
        return _output(message, context), record

    sid = data.get("session_id")
    if not isinstance(sid, str) or not sid:
        return _output(message, context), record      # nothing to remember what was shown: say nothing
    transcript = data.get("transcript_path") if isinstance(data.get("transcript_path"), str) else None
    root = Path(result["root"]) if result.get("root") else None
    record["project"] = root.name if root else os.path.basename(cwd)
    ctx = {"session": sid, "transcript": transcript}
    try:
        router = load_module(SHARED / "skills" / "model-router" / "router.py", "model_router")
    except Exception:
        router = None
    try:
        cm = load_module(SHARED / "bin" / "context-manager.py", "context_manager")
    except (Exception, SystemExit):
        cm = None

    with session.update(sid) as state:
        state["n"] = state.get("n", 0) + 1
        model = last_model(transcript) or state.get("model")
        record["model"] = model
        current = tier_for_model(model, router) if router else None
        if router and current and state["n"] - state.get("last_suggest", -SUGGEST_EVERY) >= SUGGEST_EVERY:
            try:
                message, _ = model_note(prompt, model, current, state["n"], router, decide, ctx)
            except Exception:
                message = None
            if message:
                state["last_suggest"] = state["n"]

        if cm is not None and not context and root is not None:
            try:
                picked = cm.task_matches(prompt, root, use_config=result.get("action") in ("current", "setup", "updated"))
            except (Exception, SystemExit):
                picked = {}
            # .fieldbook/bank/ in a repo nobody trusted, or in a folder that arrived with its files
            # (an unpacked download), is whatever came with it: not memory.
            if picked.get("memory"):
                if generate._repo(root) is not None:
                    ours = generate.is_trusted(root)
                else:
                    ours = bool(generate._load_state(root).get("seen_empty"))
                if not ours:
                    picked.pop("memory")
            shown = set(state.get("shown", []))
            fresh = {c: [n for n in names if n not in shown] for c, names in picked.items()}
            fresh = {c: v for c, v in fresh.items() if v}
            count = sum(len(v) for v in fresh.values())
            if count:
                d = decide.decide("pointer_useful", {
                    "new_specific": min(count, 3) / 3.0,
                    "first_prompt": int(state["n"] == 1),
                    "short_prompt": int(len(prompt) < 60),
                }, ctx=dict(ctx, names=fresh))
                if d["answer"] is True:
                    context.append(pointer_text(fresh))
                    state["shown"] = sorted(shown | {n for v in fresh.values() for n in v})
                    pointed = True
    record.update(suggested=bool(message), pointer=pointed)
    return _output(message, context), record


def _output(message, context):
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
        engine.configure(tmp)            # decisions made here must not land in the real logs
        check("tier by exact id", tier_for_model("claude-opus-5-5", router) == "frontier")
        check("tier by family name", tier_for_model("claude-haiku-4-5-20251001", router) == "fast")
        check("unknown model has no tier", tier_for_model("gpt-x", router) is None)
        simple = "format this json list and sort the keys then validate it"
        hard = "design the architecture and evaluate and compare strategy options for the research platform"
        text, model = model_note(simple, "claude-opus-5-5", "frontier", 1, router, decide, {})
        check("simple task on frontier suggests a cheaper model", bool(text) and model == "claude-haiku-5-5")
        text, _ = model_note(simple, "claude-opus-5-5", "frontier", 9, router, decide, {})
        check("no cheaper-model note late in a session", text is None)
        text, _ = model_note(hard, "claude-haiku-5-5", "fast", 9, router, decide, {})
        check("hard task on fast suggests a stronger model at any point", bool(text) and "may struggle" in text)
        text, _ = model_note(simple, "claude-opus-4-1", "frontier", 1, router, decide, {})
        check("note names the model actually in use", bool(text) and "claude-opus-4-1" in text)

        tpath = Path(tmp) / "t.jsonl"
        tpath.write_text("\n".join([
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-sonnet-5-5"}}),
            json.dumps({"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "model": "claude-haiku-5-5"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "<synthetic>"}}),
            "123", "not json",
        ]), encoding="utf-8")
        check("last model skips sidechain, synthetic and bad lines", last_model(str(tpath)) == "claude-sonnet-5-5")
        with open(tpath, "a") as fh:
            fh.write("\n" + json.dumps({"type": "user", "message": {"role": "user",
                                        "content": "<local-command-stdout>Set model to `claude-opus-5-5`</local-command-stdout>"}}))
        check("a /model switch newer than the last reply wins", last_model(str(tpath)) == "claude-opus-5-5")
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
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    try:
        output, record = run(data)
    except (Exception, SystemExit):
        return 0
    if output:
        print(json.dumps(output))
        sys.stdout.flush()
    try:
        if record:
            log_line(record)
    except (Exception, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
