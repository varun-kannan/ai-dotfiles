#!/usr/bin/env python3
"""SessionStart hook: set up or refresh the project harness, and keep the install current.

On each session start it:
  - remembers the session's model for the prompt hook,
  - sets up the project in the working directory, or refreshes it when its stack changed,
    and hands a new or changed block to this session as context (it loads from AGENTS.md later),
  - re-runs install.sh in the background when the ai-dotfiles repo has a new clean commit,
  - once a day, labels decision outcomes and recalibrates in the background.

It prints nothing unless a block was generated or changed. Any failure exits 0 silently.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
UPDATE_CHECK_SECONDS = 3600
LEARN_SECONDS = 86400


def _due(name, seconds):
    marker = SHARED / "data" / name
    try:
        if time.time() - marker.stat().st_mtime < seconds:
            return False
    except OSError:
        pass
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(int(time.time())), encoding="utf-8")
    return True


def _detached(cmd, log_name):
    (SHARED / "logs").mkdir(parents=True, exist_ok=True)
    with open(SHARED / "logs" / log_name, "a", encoding="utf-8") as log:
        subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


def main():
    data = json.load(sys.stdin)
    if data.get("source") == "compact":
        return
    sys.path.insert(0, str(SHARED))
    from engine import doctor, generate, session

    sid = data.get("session_id")
    if data.get("model"):
        state = session.load(sid)
        state["model"] = data["model"]
        session.save(sid, state)

    if _due("last-update-check", UPDATE_CHECK_SECONDS):
        src = doctor.source_repo()
        if src is not None:
            head, clean = doctor.source_head(src)
            installed = (SHARED / "installed-commit").read_text(encoding="utf-8").strip() if (SHARED / "installed-commit").exists() else ""
            if head and clean and head != installed:
                _detached(["bash", str(src / "install.sh")], "self-update.log")
    if _due("last-learn", LEARN_SECONDS):
        _detached([sys.executable, str(SHARED / "bin" / "harness"), "learn"], "learn-runs.log")

    result = generate.auto(data.get("cwd") or os.getcwd(), "session")
    if result.get("action") in ("setup", "updated") and result.get("block"):
        verb = "generated" if result["action"] == "setup" else "updated"
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "The project harness block in AGENTS.md was just %s for this project. "
                                 "It loads from the file in later sessions. Its current content:\n\n%s" % (verb, result["block"]),
        }}))


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit):
        pass
    sys.exit(0)
