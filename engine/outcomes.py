"""Label logged decisions with what actually happened, read from session transcripts and project files.

Only decisions that were acted on can be labelled: when the engine stayed quiet
there is nothing to observe. So the labels measure "when we acted, was it
useful", which is what calibration needs.
"""
from __future__ import annotations

import calendar
import json
import os
import time

from . import DATA, SHARED, decide, generate

SETTLE_SECONDS = 600          # leave a decision alone until its turn has had time to finish
MAX_AGE_SECONDS = 30 * 86400
PROJECT_SETTLE_SECONDS = 7 * 86400
LOOKAHEAD = 60                # transcript entries to scan after the decision


def _entries_after(transcript, ts):
    out = []
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                stamp = o.get("timestamp")
                if not isinstance(stamp, str):
                    continue
                try:
                    t = calendar.timegm(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    continue
                if t >= ts - 2:
                    out.append(o)
                    if len(out) >= LOOKAHEAD:
                        break
    except OSError:
        return None
    return out


def _tool_uses(entries):
    for o in entries:
        content = (o.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    yield block.get("name", ""), block.get("input") or {}


def _pointer_hit(entries, names):
    for tool, inp in _tool_uses(entries):
        if tool == "Read" and any(n in str(inp.get("file_path", "")) for n in names):
            return True
        if tool == "Skill" and inp.get("skill") in names:
            return True
        if tool in ("Agent", "Task") and inp.get("subagent_type") in names:
            return True
    return False


def _model_hit(entries, model_id):
    return any((o.get("message") or {}).get("model") == model_id for o in entries)


def label():
    """Attach outcomes to unlabelled decisions. Returns the number labelled."""
    done = {r["id"] for r in decide._read_jsonl(SHARED / "logs" / "outcomes.jsonl")}
    now = time.time()
    count = 0
    for d in decide._read_jsonl(SHARED / "logs" / "decisions.jsonl"):
        if d["id"] in done or d.get("answer") is not True:
            continue
        age = now - d["ts"]
        ctx = d.get("ctx") or {}
        if d["q"] in ("pointer_useful", "model_suggestion_useful"):
            if age < SETTLE_SECONDS or age > MAX_AGE_SECONDS or not ctx.get("transcript"):
                continue
            entries = _entries_after(ctx["transcript"], d["ts"])
            if entries is None:
                continue
            hit = _pointer_hit(entries, ctx.get("names", [])) if d["q"] == "pointer_useful" else _model_hit(entries, ctx.get("suggested"))
            decide.record_outcome(d["id"], hit)
            count += 1
        elif d["q"] == "is_project" and age > PROJECT_SETTLE_SECONDS and ctx.get("root"):
            agents = generate._read(os.path.join(ctx["root"], "AGENTS.md")) or ""
            decide.record_outcome(d["id"], generate.BEGIN in agents)
            count += 1
    return count
