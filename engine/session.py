"""Small per-session state shared by the Claude Code hooks (model seen, items already named).

Hooks for one session can run at the same time, so a read-modify-write goes
through update(), which holds a lock for that session. A session without an id
gets no state at all rather than sharing one file with every other session.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import time

from . import SHARED

MAX_AGE = 7 * 86400


def _path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))[:64]
    return SHARED / "state" / (safe + ".json") if safe else None


def load(session_id):
    path = _path(session_id)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(session_id, state):
    path = _path(session_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)
    cutoff = time.time() - MAX_AGE
    for old in path.parent.iterdir():
        try:
            if old.stat().st_mtime < cutoff and (old.suffix in (".json", ".tmp", ".lock") or ".json." in old.name):
                old.unlink()
        except OSError:
            pass


@contextlib.contextmanager
def update(session_id):
    """Yield the session's state dict under a lock and save it on exit."""
    path = _path(session_id)
    if path is None:
        yield {}
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path.with_suffix(".lock")), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.utime(fd)                 # flock does not touch the file; keep it out of the 7-day cleanup
        state = load(session_id)
        yield state
        save(session_id, state)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def reset(session_id, keep=("model", "model_at")):
    """Forget what was shown in a session (after /clear or compaction), keeping the model."""
    with update(session_id) as state:
        kept = {k: state[k] for k in keep if k in state}
        state.clear()
        state.update(kept)
