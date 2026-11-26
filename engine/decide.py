"""Local decision engine: typed questions in, structured answers with a probability out.

Modelled on typed decision models (state plus questions, answers limited to the
options given), with the parts those leave to the caller built in:

  - signals are computed in code by the caller, never guessed here
  - a flag's probability is corrected from logged outcomes once a probability
    range has enough of them (calibration), so it tracks how often acting was
    right, not how confident the formula looks
  - a flag just below its threshold answers None ("unsure"); callers treat it as
    "not now" and may ask again later
  - every logged answer carries the signals that drove it, for replay
  - questions marked "explore" act on a share of "unsure" cases, so outcomes also
    exist just below the threshold; without that, learning sees only cases it
    already chose to act on

Every question is a flag: is this statement true. Definitions live in
config/decisions.json. Learned weights live in ~/.ai-rules/data/weights.json and
override matching config weights only. Standard library only.
"""
from __future__ import annotations

import contextlib
import fcntl
import glob
import json
import math
import os
import random
import time
import uuid

from . import BASE, DATA, SHARED

BINS = 10
PRIOR_STRENGTH = 10      # outcomes before an observed hit rate outweighs the formula
MIN_BIN_COUNT = 30       # calibration ignores a range with fewer outcomes than this
RECENT_PER_BIN = 200     # calibration uses the newest outcomes per range, so old behavior fades
MIN_LABELS_TO_FIT = 60
MAX_WEIGHT_SHIFT = 1.5   # a refit may move a weight at most this far from its configured value
UNSURE_BAND = 0.15
LOG_LIMIT = 2_000_000
KEEP_ROTATED = 5


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, str(path))


@contextlib.contextmanager
def _flock(name):
    path = SHARED / "logs" / (".%s.lock" % name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def config():
    return _load(BASE / "config" / "decisions.json", {}).get("questions", {})


def questions():
    """Config questions with learned weights merged in. Unknown or missing keys keep config values."""
    cfg = config()
    learned = _load(DATA / "weights.json", {})
    for name, override in learned.items():
        spec = cfg.get(name)
        if not spec or spec.get("type") != "flag" or not isinstance(override, dict):
            continue
        weights = dict(spec.get("weights", {}))
        for k, v in (override.get("weights") or {}).items():
            if k in weights and isinstance(v, (int, float)):
                weights[k] = v
        bias = override.get("bias", spec.get("bias", 0.0))
        cfg[name] = dict(spec, bias=bias if isinstance(bias, (int, float)) else spec.get("bias", 0.0),
                         weights=weights)
    return cfg


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _logit(spec, signals):
    contrib = {k: w * float(signals.get(k, 0.0)) for k, w in spec.get("weights", {}).items()}
    return spec.get("bias", 0.0) + sum(contrib.values()), contrib


def _bin(p):
    return str(min(BINS - 1, max(0, int(p * BINS))))


def calibrate(question, p_raw, table=None):
    """Blend the formula's probability with the observed hit rate of its range, once the range has enough data."""
    table = _load(DATA / "calibration.json", {}) if table is None else table
    b = table.get(question, {}).get(_bin(p_raw))
    if not b or b.get("n", 0) < MIN_BIN_COUNT:
        return p_raw
    return (b["hits"] + PRIOR_STRENGTH * p_raw) / (b["n"] + PRIOR_STRENGTH)


def decide(question, signals, ctx=None, log=True, rng=random.random):
    """Answer one question. "answer" is True, False, or None (unsure)."""
    started = time.time()
    spec = questions().get(question)
    if spec is None or spec.get("type") != "flag":
        raise KeyError("unknown question: %s" % question)
    threshold = spec.get("threshold", 0.5)
    explored = False

    z, contrib = _logit(spec, signals)
    p_raw = _sigmoid(z)
    p = calibrate(question, p_raw)
    if p >= threshold:
        answer = True
    elif p >= threshold - UNSURE_BAND:
        answer = None
    else:
        answer = False
    rate = spec.get("explore", 0.0)
    if answer is None and rate and rng() < rate:
        answer, explored = True, True
    probabilities = {"true": round(p, 4), "false": round(1 - p, 4)}
    concentration = abs(2 * p - 1)
    reasons = sorted(((k, round(v, 3)) for k, v in contrib.items() if v), key=lambda kv: -abs(kv[1]))[:3]
    out = {
        "id": uuid.uuid4().hex[:12],
        "ts": int(started),
        "q": question,
        "answer": answer,
        "explored": explored,
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
        _append("decisions", dict(out, signals=signals, ctx=ctx or {}))
    return out


def _append(name, record):
    path = SHARED / "logs" / ("%s.jsonl" % name)
    with _flock(name):
        try:
            if os.path.getsize(path) > LOG_LIMIT:
                os.replace(str(path), "%s.%020d" % (path, time.time_ns()))
                rotated = sorted(glob.glob("%s.*" % path))
                for old in rotated[:-KEEP_ROTATED]:
                    os.remove(old)
        except OSError:
            pass
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def record_outcome(decision_id, hit):
    _append("outcomes", {"id": decision_id, "hit": bool(hit), "ts": int(time.time())})


def read_log(name):
    """Every record in a log and its rotated files, oldest file first. Malformed lines are skipped."""
    path = SHARED / "logs" / ("%s.jsonl" % name)
    files = sorted(glob.glob("%s.*" % path)) + [str(path)]     # rotated names sort oldest first
    rows = []
    for f in files:
        if f.endswith(".lock"):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and "id" in row:
                        rows.append(row)
        except OSError:
            pass
    return rows


def labelled():
    """Decisions joined with their first recorded outcome, oldest first, grouped by question."""
    outcomes = {}
    for r in read_log("outcomes"):
        outcomes.setdefault(r["id"], bool(r.get("hit")))
    by_q = {}
    for d in read_log("decisions"):
        if d["id"] in outcomes and isinstance(d.get("signals"), dict) and "q" in d:
            by_q.setdefault(d["q"], []).append(dict(d, hit=outcomes[d["id"]]))
    return by_q


def _log_loss(spec, rows):
    total = 0.0
    for r in rows:
        p = min(1 - 1e-6, max(1e-6, _sigmoid(_logit(spec, r["signals"])[0])))
        total -= math.log(p) if r["hit"] else math.log(1 - p)
    return total / max(1, len(rows))


def _fit(base, rows, steps=400, rate=0.3, l2=0.01):
    """Logistic regression from the configured weights, pulled toward them, bounded around them."""
    bias, weights = base.get("bias", 0.0), dict(base.get("weights", {}))
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
        bias = max(base.get("bias", 0.0) - MAX_WEIGHT_SHIFT, min(base.get("bias", 0.0) + MAX_WEIGHT_SHIFT, bias))
    return {"bias": round(bias, 4), "weights": {k: round(v, 4) for k, v in weights.items()}}


def learn():
    """Refit flag weights where a held-out check improves, then rebuild calibration.

    Only questions with "learn": true in config are fitted or calibrated. A refit
    starts from the configured weights (not the last refit), trains on the oldest
    70% of outcomes and is kept only when it lowers log loss on the newest 30% by
    more than 0.005. Calibration is rebuilt afterwards from probabilities
    recomputed with the final weights. Returns human-readable change lines.
    """
    base = config()
    data = labelled()
    changes = []
    learned = _load(DATA / "weights.json", {})
    learned = {k: v for k, v in learned.items() if k in base and base[k].get("learn")}

    for q, rows in data.items():
        spec = base.get(q)
        if not spec or spec.get("type") != "flag" or not spec.get("learn"):
            continue
        rows = [r for r in rows if all(isinstance(v, (int, float)) for v in r["signals"].values())]
        if len(rows) < MIN_LABELS_TO_FIT:
            continue
        split = int(len(rows) * 0.7)
        train, held = rows[:split], rows[split:]
        current = questions()[q]
        candidate = _fit(spec, train)
        before, after = _log_loss(current, held), _log_loss(candidate, held)
        if after < before - 0.005:
            learned[q] = candidate
            changes.append("%s: weights refit on %d outcomes, held-out log loss %.3f -> %.3f" % (q, len(train), before, after))
        else:
            changes.append("%s: refit rejected, held-out log loss %.3f -> %.3f" % (q, before, after))
    _save(DATA / "weights.json", learned)

    final = questions()
    table = {}
    for q, rows in data.items():
        spec = final.get(q, {})
        if spec.get("type") != "flag" or not spec.get("learn"):
            continue
        bins = {}
        for r in rows:
            p_raw = _sigmoid(_logit(spec, r["signals"])[0])
            bins.setdefault(_bin(p_raw), []).append(r["hit"])
        table[q] = {b: {"n": len(h[-RECENT_PER_BIN:]), "hits": sum(1 for x in h[-RECENT_PER_BIN:] if x)}
                    for b, h in bins.items()}
    _save(DATA / "calibration.json", table)
    if table:
        changes.append("calibration rebuilt for: %s" % ", ".join("%s (%d)" % (q, len(data[q])) for q in sorted(table)))

    if changes:
        path = SHARED / "logs" / "learn.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for line in changes:
                fh.write("%s %s\n" % (time.strftime("%Y-%m-%d"), line))
    return changes


def evaluate():
    """Replay report per question. Hit rate and calibration error cover labelled decisions only,
    which are acted ones plus explored ones; they say nothing about cases that were never acted on."""
    decisions = read_log("decisions")
    data = labelled()
    report = {}
    for q in sorted({d.get("q") for d in decisions if d.get("q")}):
        all_q = [d for d in decisions if d.get("q") == q]
        rows = data.get(q, [])
        ece = None
        if rows:
            bins = {}
            for r in rows:
                bins.setdefault(_bin(r.get("p", 0.0)), []).append(r)
            ece = round(sum(len(b) / len(rows) * abs(sum(x.get("p", 0.0) for x in b) / len(b)
                                                       - sum(1 for x in b if x["hit"]) / len(b))
                            for b in bins.values()), 3)
        report[q] = {
            "decisions": len(all_q),
            "acted": sum(1 for d in all_q if d.get("answer") not in (None, False)),
            "explored": sum(1 for d in all_q if d.get("explored")),
            "unsure": sum(1 for d in all_q if d.get("answer") is None or d.get("explored")),
            "labelled": len(rows),
            "hit_rate_of_labelled": round(sum(1 for r in rows if r["hit"]) / len(rows), 3) if rows else None,
            "calibration_error_of_labelled": ece,
        }
    return report
