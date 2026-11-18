"""Local decision engine: typed questions in, structured answers with a probability out.

Modelled on typed decision models (state plus questions, answers limited to the
options given), with the parts those leave to the caller built in:

  - signals are computed in code by the caller, never guessed here
  - the probability is corrected from logged outcomes (calibration), so it
    tracks how often acting on it was right, not how concentrated the answer is
  - below the threshold the answer is "abstain", which callers treat as "do nothing"
  - every answer carries the signals that drove it and is logged for replay

Question types: "flag" (is this statement true) and "choice" (one of N options).
Definitions live in config/decisions.json. Learned weights and calibration live
in ~/.ai-rules/data/ and override the config values. Standard library only.
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid

from . import BASE, DATA, SHARED

BINS = 10
PRIOR_STRENGTH = 10      # outcomes needed before observed hit rates outweigh the raw probability
MIN_LABELS_TO_FIT = 60
MAX_WEIGHT_SHIFT = 1.5   # a refit may move a weight at most this far from its configured value
UNSURE_BAND = 0.15
LOG_LIMIT = 2_000_000


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def questions():
    cfg = _load(BASE / "config" / "decisions.json", {}).get("questions", {})
    learned = _load(DATA / "weights.json", {})
    for name, override in learned.items():
        if name in cfg and cfg[name].get("type") == "flag":
            cfg[name] = dict(cfg[name], bias=override["bias"], weights=override["weights"], learned=True)
    return cfg


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _logit(spec, signals):
    contrib = {k: w * float(signals.get(k, 0.0)) for k, w in spec.get("weights", {}).items()}
    return spec.get("bias", 0.0) + sum(contrib.values()), contrib


def calibrate(question, p_raw, table=None):
    """Blend the raw probability with the observed hit rate of its bin."""
    table = _load(DATA / "calibration.json", {}) if table is None else table
    b = table.get(question, {}).get(str(min(BINS - 1, int(p_raw * BINS))))
    if not b:
        return p_raw
    return (b["hits"] + PRIOR_STRENGTH * p_raw) / (b["n"] + PRIOR_STRENGTH)


def decide(question, signals, ctx=None, log=True):
    """Answer one question. Returns a dict; "answer" is None when the engine abstains."""
    started = time.time()
    spec = questions().get(question)
    if spec is None:
        raise KeyError("unknown question: %s" % question)
    threshold = spec.get("threshold", 0.5)

    if spec["type"] == "flag":
        z, contrib = _logit(spec, signals)
        p_raw = _sigmoid(z)
        p = calibrate(question, p_raw)
        answer = True if p >= threshold else (None if p >= threshold - UNSURE_BAND else False)
        probabilities = {"true": round(p, 4), "false": round(1 - p, 4)}
        concentration = abs(2 * p - 1)
    else:
        logits, contribs = {}, {}
        for option, ospec in spec["options"].items():
            logits[option], contribs[option] = _logit(ospec, signals)
        top = max(logits.values())
        exp = {o: math.exp(v - top) for o, v in logits.items()}
        total = sum(exp.values())
        probabilities = {o: round(v / total, 4) for o, v in exp.items()}
        best = max(probabilities, key=probabilities.get)
        p_raw = probabilities[best]
        p = calibrate(question, p_raw)
        n = len(probabilities)
        concentration = (p_raw - 1.0 / n) / (1.0 - 1.0 / n) if n > 1 else 1.0
        answer = best if p >= threshold else None
        contrib = contribs[best]

    reasons = sorted(((k, round(v, 3)) for k, v in contrib.items() if v), key=lambda kv: -abs(kv[1]))[:3]
    out = {
        "id": uuid.uuid4().hex[:12],
        "ts": int(started),
        "q": question,
        "answer": answer,
        "p": round(p, 4),
        "p_raw": round(p_raw, 4),
        "probabilities": probabilities,
        "concentration": round(concentration, 4),
        "threshold": threshold,
        "reasons": reasons,
        "backend": "local",
        "ms": round((time.time() - started) * 1000, 2),
    }
    if log:
        _append(SHARED / "logs" / "decisions.jsonl", dict(out, signals=signals, ctx=ctx or {}))
    return out


def _append(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > LOG_LIMIT:
            os.replace(path, str(path) + ".1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def record_outcome(decision_id, hit):
    _append(SHARED / "logs" / "outcomes.jsonl", {"id": decision_id, "hit": bool(hit), "ts": int(time.time())})


def _read_jsonl(path):
    rows = []
    for p in (str(path) + ".1", str(path)):
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return rows


def labelled():
    """Decisions joined with their outcomes, oldest first, grouped by question."""
    outcomes = {r["id"]: r["hit"] for r in _read_jsonl(SHARED / "logs" / "outcomes.jsonl")}
    by_q = {}
    for d in _read_jsonl(SHARED / "logs" / "decisions.jsonl"):
        if d.get("id") in outcomes:
            by_q.setdefault(d["q"], []).append(dict(d, hit=outcomes[d["id"]]))
    return by_q


def _log_loss(spec, rows):
    total = 0.0
    for r in rows:
        p = min(1 - 1e-6, max(1e-6, _sigmoid(_logit(spec, r["signals"])[0])))
        total -= math.log(p) if r["hit"] else math.log(1 - p)
    return total / max(1, len(rows))


def _fit(base, start, rows, steps=400, rate=0.3, l2=0.01):
    bias, weights = start["bias"], dict(start["weights"])
    for _ in range(steps):
        g_bias, g_w = 0.0, {k: 0.0 for k in weights}
        for r in rows:
            err = _sigmoid(bias + sum(w * float(r["signals"].get(k, 0.0)) for k, w in weights.items())) - (1.0 if r["hit"] else 0.0)
            g_bias += err
            for k in weights:
                g_w[k] += err * float(r["signals"].get(k, 0.0))
        n = len(rows)
        bias -= rate * g_bias / n
        for k in weights:
            weights[k] -= rate * (g_w[k] / n + l2 * (weights[k] - base["weights"][k]))
            weights[k] = max(base["weights"][k] - MAX_WEIGHT_SHIFT, min(base["weights"][k] + MAX_WEIGHT_SHIFT, weights[k]))
        bias = max(base["bias"] - MAX_WEIGHT_SHIFT, min(base["bias"] + MAX_WEIGHT_SHIFT, bias))
    return {"bias": round(bias, 4), "weights": {k: round(v, 4) for k, v in weights.items()}}


def learn():
    """Rebuild calibration from outcomes and refit flag weights where a held-out check improves.

    Only numeric weights and calibration change, within MAX_WEIGHT_SHIFT of the
    configured values. Returns a list of human-readable change lines.
    """
    base = _load(BASE / "config" / "decisions.json", {}).get("questions", {})
    current = questions()
    data = labelled()
    changes = []

    table = {}
    for q, rows in data.items():
        bins = {}
        for r in rows:
            b = bins.setdefault(str(min(BINS - 1, int(r["p_raw"] * BINS))), {"n": 0, "hits": 0})
            b["n"] += 1
            b["hits"] += 1 if r["hit"] else 0
        table[q] = bins
    if table:
        _save(str(DATA / "calibration.json"), table)
        changes.append("calibration rebuilt for: %s" % ", ".join("%s (%d)" % (q, len(r)) for q, r in sorted(data.items())))

    learned = _load(DATA / "weights.json", {})
    for q, rows in data.items():
        spec = base.get(q)
        if not spec or spec.get("type") != "flag" or len(rows) < MIN_LABELS_TO_FIT:
            continue
        split = int(len(rows) * 0.7)
        train, held = rows[:split], rows[split:]
        now = {"bias": current[q]["bias"], "weights": current[q]["weights"]}
        candidate = _fit(spec, now, train)
        before, after = _log_loss(now, held), _log_loss(candidate, held)
        if after < before - 0.005:
            learned[q] = candidate
            changes.append("%s: weights refit on %d outcomes, held-out log loss %.3f -> %.3f" % (q, len(train), before, after))
        else:
            changes.append("%s: refit rejected, held-out log loss %.3f -> %.3f" % (q, before, after))
    if learned:
        _save(str(DATA / "weights.json"), learned)
    if changes:
        with open(_ensure(SHARED / "logs" / "learn.log"), "a", encoding="utf-8") as fh:
            for line in changes:
                fh.write("%s %s\n" % (time.strftime("%Y-%m-%d"), line))
    return changes


def _ensure(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def evaluate():
    """Replay report per question: volume, abstain rate, hit rate of acted answers, calibration error."""
    decisions = _read_jsonl(SHARED / "logs" / "decisions.jsonl")
    data = labelled()
    report = {}
    for q in sorted({d["q"] for d in decisions}):
        all_q = [d for d in decisions if d["q"] == q]
        rows = data.get(q, [])
        ece = 0.0
        if rows:
            bins = {}
            for r in rows:
                bins.setdefault(min(BINS - 1, int(r["p"] * BINS)), []).append(r)
            ece = sum(len(b) / len(rows) * abs(sum(x["p"] for x in b) / len(b) - sum(1 for x in b if x["hit"]) / len(b))
                      for b in bins.values())
        report[q] = {
            "decisions": len(all_q),
            "acted": sum(1 for d in all_q if d["answer"] not in (None, False)),
            "abstained": sum(1 for d in all_q if d["answer"] is None),
            "labelled": len(rows),
            "hit_rate": round(sum(1 for r in rows if r["hit"]) / len(rows), 3) if rows else None,
            "calibration_error": round(ece, 3) if rows else None,
        }
    return report
