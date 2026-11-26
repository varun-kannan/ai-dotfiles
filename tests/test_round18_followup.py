"""Round 18 follow-up: an am hook kept as .local comes back when ours is removed, deleting the
first line of a file over the cap, the stale-lock turn, and an "@" added to .harness/AGENTS.md
in a settled local-mode repo."""
import os
import subprocess

from helpers import commit_all, git_init, make
from test_install import FOREIGN, Installed
from test_round18_guard import Guard
from engine import generate

ZWSP = chr(0x200B)
LQ, RQ = chr(0x201C), chr(0x201D)


class AmHookLocalComesBack(Installed):
    def put(self, path, text):
        if os.path.lexists(path):
            os.remove(path)
        path.write_text(text)
        os.chmod(path, 0o755)

    def test_kept_am_hook_is_restored_when_ours_is_removed(self):
        self.assertEqual(self.install().returncode, 0)
        repo = git_init(self.docs / "mine")
        hooks = repo / ".git" / "hooks"
        mine = {"pre-applypatch": "#!/bin/sh\n# my pre-applypatch\nexit 0\n",
                "applypatch-msg": "#!/bin/sh\n# my applypatch-msg\nexit 0\n"}
        for name, text in mine.items():
            self.put(hooks / name, text)
        self.assertEqual(self.install("--existing-repos", str(self.docs)).returncode, 0)
        for name, text in mine.items():
            self.assertEqual((hooks / (name + ".local")).read_text(), text)
        # pre-commit becomes a symlink; commit-msg and its .local become someone else's
        outside = make(self.tmp / "elsewhere", {"pre-commit": "#!/bin/sh\nexit 0\n"})
        os.remove(hooks / "pre-commit")
        os.symlink(outside / "pre-commit", hooks / "pre-commit")
        self.put(hooks / "commit-msg", FOREIGN)
        self.put(hooks / "commit-msg.local", FOREIGN)
        r = self.install("--existing-repos", str(self.docs))
        self.assertEqual(r.returncode, 1, r.stderr)
        for name, text in mine.items():
            self.assertEqual((hooks / name).read_text(), text, name)
            self.assertFalse(os.path.lexists(hooks / (name + ".local")), name)
            self.assertIn("restored %s.local in %s as %s" % (name, hooks, name), r.stdout)

    def test_symlinked_local_is_not_moved(self):
        self.assertEqual(self.install().returncode, 0)
        repo = git_init(self.docs / "linked")
        hooks = repo / ".git" / "hooks"
        target = make(self.tmp / "t", {"hook": "#!/bin/sh\nexit 0\n"}) / "hook"
        os.symlink(target, hooks / "pre-applypatch.local")
        os.remove(hooks / "pre-commit")
        os.symlink(target, hooks / "pre-commit")
        self.install("--existing-repos", str(self.docs))
        self.assertFalse(os.path.lexists(hooks / "pre-applypatch"))
        self.assertTrue(os.path.islink(hooks / "pre-applypatch.local"))


class StaleLockTurn(Installed):
    def test_stale_lock_is_cleared_and_the_turn_is_given_back(self):
        os.symlink("999999:never", self.shared / ".install.lock")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))
        self.assertFalse(os.path.lexists(self.shared / ".install.lock.turn"))

    def test_turn_left_by_a_killed_waiter_is_cleared_after_a_while(self):
        os.symlink("999999:never", self.shared / ".install.lock")
        os.symlink("1", self.shared / ".install.lock.turn")
        old = os.lstat(self.shared / ".install.lock.turn").st_mtime - 60
        os.utime(self.shared / ".install.lock.turn", (old, old), follow_symlinks=False)
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "5"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fresh_turn_held_by_another_waiter_is_respected(self):
        os.symlink("999999:never", self.shared / ".install.lock")
        os.symlink("1", self.shared / ".install.lock.turn")
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "1"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(os.readlink(self.shared / ".install.lock"), "999999:never")


class FirstLineDeletedPastTheCap(Guard):
    def test_deleting_the_opening_line_exposes_code_further_down(self):
        body = ['"""\n'] + ["line %d %s\n" % (k, ZWSP) for k in range(250)] \
            + ['"""\n', '"""\n', "x = %shi%s\n" % (LQ, RQ), '"""\n']
        f = self.write_raw(make(self.docs / "cap1") / "m.py", "".join(body))
        r = self.guard({"file_path": str(f), "old_string": '"""\nline 0 ', "new_string": "line 0 "})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_edit_below_the_first_line_is_unchanged(self):
        body = ["x = 1\n"] + ['"""\n'] + ["line %d %s\n" % (k, ZWSP) for k in range(250)] + ['"""\n']
        f = self.write_raw(make(self.docs / "cap2") / "m.py", "".join(body))
        r = self.guard({"file_path": str(f), "old_string": "x = 1", "new_string": "x = 2"})
        self.assertEqual(r.returncode, 0, r.stderr)


class LocalFastPathSeesNewReference(Installed):
    def test_reference_added_outside_the_block_drops_the_import(self):
        root = git_init(self.docs / "theirs", authors=("them@x.com",), files={"package.json": "{}"})
        commit_all(root, email="them@x.com")
        r = generate.auto(root, "git")
        self.assertEqual((r["action"], r.get("mode")), ("setup", "local"), r)
        self.assertEqual(generate.auto(root, "session")["action"], "current")
        local = root / "CLAUDE.local.md"
        self.assertIn("@.harness/AGENTS.md", local.read_text(encoding="utf-8"))
        agents = root / ".harness" / "AGENTS.md"
        with open(str(agents), "a", encoding="utf-8") as fh:
            fh.write("@notes/secret.md\n")
        generate.auto(root, "session")
        self.assertFalse(local.exists() and "@.harness/AGENTS.md" in local.read_text(encoding="utf-8"))
        # and the repo settles again rather than running setup on every trigger
        self.assertEqual(generate.auto(root, "session")["action"], "current")
