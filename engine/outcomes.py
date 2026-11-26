"""Label logged decisions with what actually happened, read from Claude Code transcripts.

Two questions are labelled:
  pointer_useful           hit when, in the turn that answered the prompt, Claude read a
                           named rule or memory file, used a named skill, or ran a named
                           subagent (exact names, not substrings)
  model_suggestion_useful  hit when the next turn ran on the suggested model (main
                           conversation only, not subagents)

A decision is labelled only once its window is complete; until then it is left for a
later run, and a decision whose window never completes is never labelled. Labels are
first-wins and written under a lock, so concurrent runs cannot double-label.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import time

from . import decide

SETTLE_SECONDS = 600            # a turn with no later prompt counts as finished after this
MAX_AGE_SECONDS = 30 * 86400
MAX_TRANSCRIPT_BYTES = 50_000_000
LABELLED = ("pointer_useful", "model_suggestion_useful")


_STAMP = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:?\d\d)?$")


def _ts(value):
    """Epoch seconds for an ISO timestamp; no zone means UTC."""
    m = _STAMP.match(value) if isinstance(value, str) else None
    if not m:
        return None
    try:
        base = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    frac = float("0." + m.group(2)) if m.group(2) else 0.0
    zone = m.group(3)
    offset = 0
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        digits = zone[1:].replace(":", "")
        offset = sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return base + frac - offset


def _entries(path):
    try:
        if os.path.getsize(path) > MAX_TRANSCRIPT_BYTES:
            return None
        out = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict) and isinstance(o.get("message"), dict):
                    t = _ts(o.get("timestamp"))
                    if t is not None:
                        out.append((t, o))
        return out
    except OSError:
        return None


COMMAND_MARKERS = ("<local-command-", "<command-name>", "<command-message>", "<bash-input>", "<bash-stdout>",
                   "<bash-stderr>", "<system-reminder>")


def _is_prompt(o):
    """A message the person typed: not a tool result, a command echo, injected text, or a subagent."""
    m = o["message"]
    if m.get("role") != "user" or o.get("isSidechain") or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    c = m.get("content")
    if isinstance(c, str):
        return bool(c.strip()) and not c.lstrip().startswith(COMMAND_MARKERS)
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return False
        texts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
        return any(isinstance(t, str) and t.strip() and not t.lstrip().startswith(COMMAND_MARKERS) for t in texts)
    return False


def _is_reply(o):
    m = o["message"]
    return m.get("role") == "assistant" and not o.get("isSidechain") and isinstance(m.get("model"), str) \
        and not m["model"].startswith("<")


def _turns(entries, ts):
    """(entries of the turn answering the prompt at ts, entries of the next turn, window complete)."""
    prompts = [i for i, (t, o) in enumerate(entries) if _is_prompt(o)]
    # The hook's clock and the transcript's differ by a little, so take the prompt nearest to ts
    # among those not clearly before it. Two prompts sent seconds apart are then told apart.
    near = [i for i in prompts if entries[i][0] >= ts - 5]
    start = min(near, key=lambda i: abs(entries[i][0] - ts)) if near else None
    if start is None:
        return None, None, False
    later = [i for i in prompts if i > start]
    end = later[0] if later else len(entries)
    turn = [o for _, o in entries[start + 1:end]]
    nxt_end = later[1] if len(later) > 1 else len(entries)
    nxt = [o for _, o in entries[end + 1:nxt_end]] if later else []
    complete = bool(later) or (entries and time.time() - entries[-1][0] > SETTLE_SECONDS)
    return turn, nxt, complete


def _uses(turn):
    for o in turn:
        content = o["message"].get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    yield block.get("name", ""), block.get("input") if isinstance(block.get("input"), dict) else {}


def pointer_hit(turn, names):
    rules = {"/rules/domains/%s.md" % n for n in names.get("rules", [])}
    memory = {"/.fieldbook/bank/%s" % n for n in names.get("memory", [])}
    skills, agents = set(names.get("skills", [])), set(names.get("agents", []))
    for tool, inp in _uses(turn):
        if tool == "Read":
            path = str(inp.get("file_path", ""))
            if any(path.endswith(s) for s in rules | memory):
                return True
        elif tool == "Skill":
            skill = str(inp.get("skill", ""))
            if skill in skills or skill.split(":")[-1] in skills:
                return True
        elif tool in ("Agent", "Task") and inp.get("subagent_type") in agents:
            return True
    return False


def model_hit(nxt, model_id):
    """None when the next turn has no reply yet, else whether it ran on model_id."""
    reply = next((o for o in nxt if _is_reply(o)), None)
    return None if reply is None else reply["message"]["model"] == model_id


def label():
    """Attach outcomes to unlabelled decisions. Returns the number labelled."""
    with decide._flock("label"):
        done = {r["id"] for r in decide.read_log("outcomes")}
        cache = {}
        count = 0
        now = time.time()
        for d in decide.read_log("decisions"):
            if d["id"] in done or d.get("answer") is not True or d.get("q") not in LABELLED:
                continue
            ctx = d.get("ctx") if isinstance(d.get("ctx"), dict) else {}
            path = ctx.get("transcript")
            if not isinstance(path, str) or now - d.get("ts", 0) > MAX_AGE_SECONDS:
                continue
            if path not in cache:
                cache[path] = _entries(path)
            entries = cache[path]
            if not entries:
                continue
            turn, nxt, complete = _turns(entries, d.get("ts", 0))
            if turn is None:
                continue
            if d["q"] == "pointer_useful":
                if not complete or not any(_is_reply(o) for o in turn):
                    continue
                hit = pointer_hit(turn, ctx.get("names") if isinstance(ctx.get("names"), dict) else {})
            else:
                hit = model_hit(nxt, ctx.get("suggested"))
                if hit is None:
                    continue
            decide.record_outcome(d["id"], hit)
            done.add(d["id"])
            count += 1
        return count
