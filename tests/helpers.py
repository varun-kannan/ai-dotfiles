"""Shared test scaffolding: an isolated HOME and shared folder per test, and real git repos."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for var in list(os.environ):
    if var.startswith("GIT_") or var in ("AI_HARNESS_OFF", "AI_ROUTER_OFF", "FIELDBOOK_CMD"):
        os.environ.pop(var)
_BOOT = tempfile.mkdtemp(prefix="engine-boot-")
os.environ["HOME"] = _BOOT
os.environ["AI_RULES_HOME"] = os.path.join(_BOOT, ".ai-rules")
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402
from engine import generate  # noqa: E402

ME = "me@example.com"
FAKE_FIELDBOOK = """#!/bin/sh
mkdir -p .fieldbook/bank .fieldbook/logs/hot
echo "version: 1" > .fieldbook/config.yml
printf '# Decisions\\n' > .fieldbook/bank/04-decisions.md
"""


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["LC_ALL"] = "C"
    return env


def git(path, *args, check=True):
    return subprocess.run(["git", "-C", str(path)] + list(args), capture_output=True, text=True,
                          env=git_env(), check=check)


def git_init(path, authors=(ME,), files=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=git_env())
    for i, email in enumerate(authors):
        (path / ("commit-%d.txt" % i)).write_text(str(i), encoding="utf-8")
        git(path, "add", "-A")
        git(path, "-c", "user.name=x", "-c", "user.email=" + email, "commit", "-q", "-m", "c%d" % i)
    for name, text in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    return path


def trusted_repo(path, authors=(ME,), files=None):
    """A git repo on the trust list, as after `harness trust`."""
    git_init(path, authors=authors, files=files)
    generate.trust(path)
    return path


def born_here(path, files=None):
    """A folder made on this machine: the engine sees it empty first, then with its first files."""
    path.mkdir(parents=True)
    generate.auto(path, "cd")
    make(path, files or {"package.json": "{}"})
    return generate.auto(path, "session")


def commit_all(path, email=ME, message="c"):
    git(path, "add", "-A")
    git(path, "-c", "user.name=x", "-c", "user.email=" + email, "commit", "-q", "-m", message)


def commit_paths(path, paths, email=ME, message="c"):
    git(path, "add", "--", *paths)
    git(path, "-c", "user.name=x", "-c", "user.email=" + email, "commit", "-q", "-m", message)


def make(path, files=None):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    return path


class Sandbox(unittest.TestCase):
    """A fresh HOME, shared folder and git identity for every test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="engine-test-")).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.shared = self.home / ".ai-rules"
        self.shared.mkdir()
        self.docs = self.home / "Documents"
        self.docs.mkdir()
        self._env = dict(os.environ)
        os.environ["HOME"] = str(self.home)
        os.environ["AI_RULES_HOME"] = str(self.shared)
        (self.home / ".gitconfig").write_text("[user]\n\temail = %s\n\tname = me\n" % ME, encoding="utf-8")
        engine.configure(self.shared)
        generate.FIELDBOOK_OVERRIDE = None

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        generate.FIELDBOOK_OVERRIDE = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_binary(self, name, body):
        p = self.tmp / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        return str(p)

    def link_shared(self):
        """Make the sandbox shared folder look like an install: engine, tools and config from the repo."""
        for name in ("engine", "skills", "bin", "config", "rules"):
            target = self.shared / name
            if not target.exists():
                os.symlink(ROOT / name, target)

    def status(self, path):
        return git(path, "status", "--porcelain").stdout

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
