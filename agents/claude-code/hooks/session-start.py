#!/usr/bin/env python3
"""SessionStart hook: set up or refresh the project, and keep the install current.

On each session start it:
  - remembers the session's model for the prompt hook, and after /clear or
    compaction forgets which items the session was already told about,
  - sets up the project in the working directory, or refreshes it when its stack
    changed, and hands a new or changed block to this session as context,
  - at most hourly, re-runs install.sh in the background when the ai-dotfiles repo
    moved forward on the installed branch with a clean tree (never for another
    branch, an older commit, or an install made from uncommitted changes),
  - at most daily, labels decision outcomes and recalibrates in the background.

~/.ai-rules/harness.off stops all of it. It prints nothing unless a block was
generated or changed, and any failure exits 0 silently.
"""
import os
import sys

# Run isolated (python3 -I): no PYTHONPATH, no user site, and not the current folder on the
# module path, which may be a repository with a file named like a standard module. A start
# without -I (from a #! line or a hook command) restarts once with it.
if not sys.flags.isolated and __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
import json
import re
import subprocess
import time
from pathlib import Path

SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
UPDATE_CHECK_SECONDS = 3600
LEARN_SECONDS = 86400
LOG_LIMIT = 1_000_000


def _due(name, seconds):
    """True for exactly one caller per interval, even when sessions start together."""
    folder = SHARED / "data"
    folder.mkdir(parents=True, exist_ok=True)
    bucket = int(time.time()) // seconds
    claim = folder / ("%s.%d" % (name, bucket))
    try:
        os.close(os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    for old in folder.glob(name + ".*"):
        if old != claim:
            try:
                old.unlink()
            except OSError:
                pass
    return True


def _install_running():
    """True when another install holds the lock and its process is alive.

    The lock is a symlink whose target is the installer's pid. An older installer used a
    folder holding a pid file.
    """
    lock = SHARED / ".install.lock"
    try:
        pid = int(os.readlink(lock)) if lock.is_symlink() else int((lock / "pid").read_text().strip())
        os.kill(pid, 0)
        ps = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
        return bool(re.search(r"(^|[ /])install\.sh( |$)", ps.stdout.strip()))    # a reused pid is not an install
    except (OSError, ValueError, subprocess.SubprocessError):
        return False         # no lock, or one left by a killed install; install.sh clears it


def _detached(cmd, log_name):
    path = SHARED / "logs" / log_name
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.stat().st_size > LOG_LIMIT:
            path.replace(path.with_name(log_name + ".1"))
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as log:
        subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, cwd="/")


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        return
    sys.path.insert(0, str(SHARED))
    import engine
    from engine import doctor, generate, session
    if engine.harness_off():
        return

    sid = data.get("session_id")
    if data.get("source") in ("clear", "compact"):
        session.reset(sid)
    if isinstance(data.get("model"), str):
        with session.update(sid) as state:
            state["model"] = data["model"]
            state["model_at"] = int(time.time())
    if data.get("source") == "compact":
        return

    try:
        if _due("update-check", UPDATE_CHECK_SECONDS):
            src = doctor.source_repo()
            if src is not None and doctor.update_allowed(src) and not _install_running():
                _detached(["/bin/bash", str(src / "install.sh")], "self-update.log")
        if _due("learn", LEARN_SECONDS):
            _detached([sys.executable, str(SHARED / "bin" / "harness"), "learn"], "learn-runs.log")
    except Exception:
        pass

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    result = generate.auto(cwd, "session")
    if result.get("action") in ("setup", "updated") and result.get("block"):
        where = ".harness/AGENTS.md (imported by CLAUDE.local.md)" if result.get("mode") == "local" else "AGENTS.md"
        verb = "generated" if result["action"] == "setup" else "updated"
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "The project harness block in %s was just %s for this project. "
                                 "It loads from the file in later sessions. Its current content:\n\n%s" % (where, verb, result["block"]),
        }}))


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit):
        pass
    sys.exit(0)
