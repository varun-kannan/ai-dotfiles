"""Round 19 installer: only the named tools are taken from bin/, a settings.json in a folder that
cannot be written is refused cleanly, a merge keeps the user's text and numbers as written, and
the stale-turn clear in the install lock never removes a live turn."""
import os
import shutil
import subprocess
import sys
import unittest

from helpers import ROOT, git_env
from test_install import Installed


class StrayFileInBin(Installed):
    def test_stray_file_is_not_installed_and_does_not_break_the_check(self):
        src = self.tmp / "src"
        shutil.copytree(ROOT, src, symlinks=True, ignore=shutil.ignore_patterns(".git", "tests", "__pycache__"))
        for stray in ("content-hygiene.rej.orig", "harness~"):
            (src / "bin" / stray).write_text("#!/bin/sh\nexit 0\n")
        r = subprocess.run(["/bin/bash", str(src / "install.sh")], capture_output=True, text=True,
                           env=git_env(), timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(self.shared / "bin")),
                         ["check-deps", "content-hygiene", "context-manager.py", "harness"])


class SettingsMerge(Installed):
    @unittest.skipIf(os.geteuid() == 0, "root can write a read-only folder")
    def test_writable_file_in_read_only_folder_is_refused_without_a_traceback(self):
        dot = self.tmp / "dotfiles"
        dot.mkdir()
        real = dot / "settings.json"
        real.write_text('{"model": "opus"}\n')
        os.symlink(real, self.home / ".claude" / "settings.json")
        os.chmod(dot, 0o555)
        try:
            r = self.install()
        finally:
            os.chmod(dot, 0o755)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("Left untouched", r.stderr)
        self.assertEqual(real.read_text(), '{"model": "opus"}\n')
        self.assertEqual(os.listdir(dot), ["settings.json"])

    def test_non_ascii_text_and_number_spelling_survive_a_merge(self):
        path = self.home / ".claude" / "settings.json"
        path.write_text('{"name": "café", "ratio": 1.10, "big": 1e5, "count": 3}\n', encoding="utf-8")
        self.assertEqual(self.install().returncode, 0)
        text = path.read_text(encoding="utf-8")
        for kept in ('"café"', '"ratio": 1.10,', '"big": 1e5,', '"count": 3,'):
            self.assertIn(kept, text)
        self.assertEqual(self.settings()["name"], "café")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), text)


def lock_clear_script():
    """The stale-lock step of take_lock, as install.sh hands it to python."""
    text = (ROOT / "install.sh").read_text()
    start = text.index("import os, shutil, sys, time\nlock, raw, turn")
    return text[start:text.index("' \"$LOCK\" \"$raw\" \"$LOCK.turn\"", start)]


# Runs the step with os.lstat patched: right after the first look at the old turn, other waiters
# clear it and take a fresh one, which is the race the step must survive.
RACE = r"""
import os, sys
turn = sys.argv[3]
real_lstat, looked = os.lstat, []
def lstat(p, *a, **k):
    st = real_lstat(p, *a, **k)
    if p == turn and not looked:
        looked.append(1)
        os.remove(turn)
        os.symlink("fresh", turn)
    return st
os.lstat = lstat
try:
    exec(compile(open(sys.argv[4]).read(), "lock", "exec"), {"__name__": "__main__"})
except SystemExit:
    pass
"""


class StaleTurnRace(Installed):
    def test_fresh_turn_taken_during_the_stale_clear_is_kept(self):
        script = self.tmp / "lock.py"
        script.write_text(lock_clear_script())
        turn = self.shared / ".install.lock.turn"
        os.symlink("1", turn)
        old = os.lstat(turn).st_mtime - 60
        os.utime(turn, (old, old), follow_symlinks=False)
        lock = self.shared / ".install.lock"
        os.symlink("999999:never", lock)
        subprocess.run([sys.executable, "-I", "-c", RACE, str(lock), "999999:never", str(turn), str(script)],
                       check=True, timeout=30)
        self.assertTrue(os.path.islink(turn))
        self.assertEqual(os.readlink(turn), "fresh")
        self.assertEqual([p for p in os.listdir(self.shared) if p.endswith(".stale")], [])

    def test_old_turn_is_still_cleared(self):
        script = self.tmp / "lock.py"
        script.write_text(lock_clear_script())
        turn = self.shared / ".install.lock.turn"
        os.symlink("1", turn)
        old = os.lstat(turn).st_mtime - 60
        os.utime(turn, (old, old), follow_symlinks=False)
        subprocess.run([sys.executable, "-I", script.as_posix(), str(self.shared / ".install.lock"), "x", str(turn)],
                       timeout=30)
        self.assertFalse(os.path.lexists(turn))


if __name__ == "__main__":
    unittest.main()
