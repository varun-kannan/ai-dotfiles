"""Small per-session state shared by the Claude Code hooks (model seen, items already named)."""
from __future__ import annotations

import json
import re
import time

from . import SHARED

MAX_AGE = 7 * 86400


def _path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))[:64] or "nosession"
    return SHARED / "state" / (safe + ".json")


def load(session_id):
    try:
        return json.loads(_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(session_id, state):
    path = _path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    cutoff = time.time() - MAX_AGE
    for old in path.parent.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
