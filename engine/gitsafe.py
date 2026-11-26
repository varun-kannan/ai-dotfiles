"""Run git inside folders that may be hostile.

A folder that arrived as a zip, tarball or synced copy can carry its own
.git/config. Some settings make plain read commands run programs: for example
log.showSignature with gpg.program makes `git log` execute an attacker binary.
Every git call the engine makes goes through run(), which overrides those
settings, ignores the repo's hooks, forbids lazy fetches, runs with a fixed
locale, starts outside the repo, and uses an absolute git binary so a `git`
planted in the repo cannot be picked from PATH.

This does not make every git command safe. Commands that hash working-tree files
(status, diff, add) can run a filter driver named in the repo's config, and no
override covers that, so the engine only uses commands that read objects and
refs: config --get, rev-parse, log, ls-files.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading

HARDEN = [
    "-c", "log.showSignature=false",
    "-c", "gpg.program=/usr/bin/false",
    "-c", "gpg.openpgp.program=/usr/bin/false",
    "-c", "gpg.x509.program=/usr/bin/false",
    "-c", "gpg.ssh.program=/usr/bin/false",
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.sshCommand=/usr/bin/false",
    "-c", "protocol.allow=never",
    "-c", "diff.external=",
    "-c", "core.pager=cat",
]
TIMEOUT = 3
_GIT = None


def git_binary():
    """Absolute git, found only through absolute PATH entries."""
    global _GIT
    if _GIT is None:
        safe_path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if os.path.isabs(p))
        _GIT = shutil.which("git", path=safe_path or "/usr/bin:/bin") or ""
    return _GIT or None


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    # No lazy fetch: a partial clone could otherwise run a transport helper to fetch a missing object.
    env.update(LC_ALL="C", LANG="C", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    return env


def child_env(path):
    """Environment for a program that runs git itself: the same overrides, passed as config
    variables so every git it starts gets them, and a fixed PATH."""
    env = _env()
    pairs = [(HARDEN[i + 1].split("=", 1)) for i in range(0, len(HARDEN), 2) if "hooksPath" not in HARDEN[i + 1]]
    env["GIT_CONFIG_COUNT"] = str(len(pairs))
    for n, (key, value) in enumerate(pairs):
        env["GIT_CONFIG_KEY_%d" % n] = key
        env["GIT_CONFIG_VALUE_%d" % n] = value
    env["PATH"] = path
    return env


def run(root, *args, harden=True, timeout=TIMEOUT):
    """CompletedProcess for `git -C root args`, or None when git is missing or too slow."""
    git = git_binary()
    if not git:
        return None
    cmd = [git] + (HARDEN if harden else []) + ["-C", str(root)] + list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env(),
                              cwd="/", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None



def scan(root, args, match, timeout=TIMEOUT):
    """Feed each NUL-terminated record that `git -C root args` prints, as bytes, to match until
    it returns True. True on a match, False when git exits cleanly without one, None when git is
    missing, fails or is too slow. Records are read as they arrive and not kept, so a listing of
    a very large repository costs time but not memory."""
    git = git_binary()
    if not git:
        return None
    cmd = [git] + HARDEN + ["-C", str(root)] + list(args)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_env(),
                                cwd="/", stdin=subprocess.DEVNULL)
    except OSError:
        return None
    late = []
    timer = threading.Timer(timeout, lambda: (late.append(True), proc.kill()))
    timer.start()
    found, rest = False, b""
    try:
        while not found:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            records = (rest + chunk).split(b"\0")
            rest = records.pop()
            found = any(match(r) for r in records)
    finally:
        timer.cancel()
        if found:
            proc.kill()
        proc.stdout.close()
        code = proc.wait()
    if found:
        return True
    return None if late or code != 0 or rest else False
