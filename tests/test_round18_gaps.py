"""Round 18 gaps: behaviours a mutation review found nothing guarding. The write guard on a CR-only
file over the scanner cap and on a multi-edit past its shared diff budget, the install lock, the
dependency check's tests folder, the commit-msg session links and the context scorer's hit count."""
import importlib.util
import json
import os
import subprocess
import sys

from helpers import ROOT, Sandbox, git, git_env, git_init, make
from test_install import Installed
from test_round17_install import start_time

GUARD = ROOT / "agents" / "claude-code" / "hooks" / "pre-write-guard.sh"
ZWSP = chr(0x200B)


class Guard(Sandbox):
    def guard(self, tool_input):
        home = make(self.tmp / "home")
        env = dict(os.environ, HOME=str(home), AI_RULES_HOME=str(home / ".ai-rules"),
                   CONTENT_HYGIENE_BIN=str(ROOT / "bin" / "content-hygiene"))
        return subprocess.run(["/bin/bash", str(GUARD)], input=json.dumps({"tool_input": tool_input}),
                              capture_output=True, text=True, env=env, timeout=60)

    def write_raw(self, path, text):
        with open(str(path), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path


class CrOnlyOverTheCap(Guard):
    def fixture(self):
        # A shell file with lone CRs is one line to the scanner, so every finding is on line 1. It
        # holds exactly the 200 findings the scanner lists (199 and the CR inside the line), so one
        # more, at the very end, is cut by the cap and only a rescan can see it.
        body = "echo a" + (ZWSP + "a") * 199 + "\ry=2"
        return self.write_raw(make(self.docs / "crcap") / "c.sh", body)

    def test_finding_added_past_the_cap_is_found_by_a_rescan_from_line_one(self):
        f = self.fixture()
        r = self.guard({"file_path": str(f), "old_string": "y=2", "new_string": "y=2%s" % ZWSP})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(":1:", r.stderr)

    def test_edit_adding_nothing_in_the_same_file_passes(self):
        f = self.fixture()
        r = self.guard({"file_path": str(f), "old_string": "y=2", "new_string": "y=3"})
        self.assertEqual(r.returncode, 0, r.stderr)


class SharedDiffBudget(Guard):
    def block(self, tag, finding_in_middle):
        lines = ["%s%d = %d\n" % (tag, k, k) for k in range(400)]
        if finding_in_middle:
            lines[200] = "%s200 = \"a%sb\"\n" % (tag, ZWSP)
        return "".join(lines)

    def edit_of(self, text):
        # Only the first and last lines change; the middle is kept, finding included.
        lines = text.split("\n")
        lines[0] += "0"
        lines[-2] += "0"
        return {"old_string": text, "new_string": "\n".join(lines)}

    def test_second_large_edit_past_the_shared_budget_keeps_only_its_start_and_end(self):
        # Each edit alone is 160000 line pairs of the 300000 shared by the whole call, so the second
        # is not diffed and every line between its start and end counts as changed: the finding that
        # was already there is charged to it. This is the documented, cautious side of the budget.
        a, b = self.block("a", False), self.block("b", True)
        f = self.write_raw(make(self.docs / "budget") / "b.py", a + b)
        r = self.guard({"file_path": str(f), "edits": [self.edit_of(a), self.edit_of(b)]})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("b.py:601:", r.stderr)

    def test_the_same_large_edit_on_its_own_is_diffed_and_the_old_finding_is_not_charged(self):
        a, b = self.block("a", False), self.block("b", True)
        f = self.write_raw(make(self.docs / "alone") / "b.py", a + b)
        r = self.guard({"file_path": str(f), "edits": [self.edit_of(b)]})
        self.assertEqual(r.returncode, 0, r.stderr)


class InstallLock(Installed):
    def running(self, *cmd):
        p = subprocess.Popen(list(cmd))
        self.addCleanup(lambda: (p.kill(), p.wait()))
        return p

    def sleeper(self):
        fake = make(self.tmp / "running") / "install.sh"
        fake.write_text("#!/bin/bash\nsleep 30\n")
        other = self.running("/bin/bash", str(fake))
        started = start_time(other.pid)
        if not started:
            self.skipTest("ps process start times are unavailable in this sandbox")
        return other, started

    def test_lock_of_a_live_pid_with_another_start_time_is_cleared(self):
        other, _ = self.sleeper()
        os.symlink("%d:Thu Jan 1 00:00:00 1970".replace(" ", "") % other.pid, self.shared / ".install.lock")
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "3"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))
        self.assertIsNone(other.poll(), "the process that only shares the pid is left running")

    def test_lock_replaced_by_a_live_owner_after_it_was_read_is_not_removed(self):
        # The installer reads the lock, finds its owner gone, and goes to clear it. A stand-in
        # readlink makes the owner it reads the dead one while the lock is swapped for a live one
        # at that moment; the clear must look again and leave the new lock alone.
        other, started = self.sleeper()
        live = "%d:%s" % (other.pid, started)
        lock = self.shared / ".install.lock"
        os.symlink("999999:Thu Jan 1 00:00:00 1970".replace(" ", ""), lock)
        real = "/usr/bin/readlink"
        if not os.path.exists(real):
            self.skipTest("no /usr/bin/readlink to stand in front of")
        bindir = make(self.tmp / "shim")
        flag = self.tmp / "swapped"
        shim = bindir / "readlink"
        shim.write_text("""#!/bin/sh
for last; do :; done
if [ "$last" = "%(lock)s" ] && [ ! -e "%(flag)s" ]; then
  stale="$(%(real)s "$last")"
  : > "%(flag)s"
  rm -f "$last"
  ln -s "%(live)s" "$last"
  echo "$stale"
  exit 0
fi
exec %(real)s "$@"
""" % {"lock": lock, "flag": flag, "real": real, "live": live})
        os.chmod(shim, 0o755)
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "2", "PATH": "%s:%s" % (bindir, os.environ["PATH"])})
        self.assertTrue(flag.exists(), "the stand-in readlink ran")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(os.readlink(lock), live)


class OlderCode(Sandbox):
    def test_check_deps_takes_a_module_in_the_tests_folder_as_the_projects_own(self):
        proj = make(self.docs / "tdeps", {"pyproject.toml": '[project]\nname = "x"\n',
                                          "app/main.py": "import shared_fixtures\nimport not_anywhere_at_all\n",
                                          "tests/shared_fixtures.py": "X = 1\n"})
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "check-deps"), "--", str(proj / "app" / "main.py")],
                           capture_output=True, text=True, timeout=30)
        self.assertIn("not_anywhere_at_all", r.stdout)
        self.assertNotIn("shared_fixtures", r.stdout)

    def test_commit_msg_removes_session_link_lines_in_a_real_commit(self):
        repo = git_init(self.docs / "msgrepo")
        hooks = repo / ".git" / "hooks"
        os.symlink(ROOT / "hooks" / "git" / "commit-msg", hooks / "commit-msg")
        (repo / "f.txt").write_text("f\n")
        git(repo, "add", "-A")
        message = ("Fix the retry loop\n\nBody line.\n"
                   "https://claude.ai/code/session_01ABC\n"
                   "  http://claude.ai/code/session_02DEF\n"
                   "See https://claude.ai/code/session_03GHI for background\n")
        r = git(repo, "-c", "user.name=x", "-c", "user.email=me@example.com", "commit", "-q", "-m", message, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = git(repo, "log", "-1", "--format=%B").stdout
        self.assertNotIn("session_01ABC", body)
        self.assertNotIn("session_02DEF", body)
        self.assertIn("Body line.", body)
        self.assertIn("See https://claude.ai/code/session_03GHI for background", body, "a sentence that cites a link stays")

    def test_context_score_rises_with_the_number_of_matching_tags_up_to_a_cap(self):
        spec = importlib.util.spec_from_file_location("cm_gaps", ROOT / "bin" / "context-manager.py")
        cm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cm)
        entry = {"tags": ["alpha", "beta", "gamma"], "weight": 0.4}
        words = lambda *w: {cm.stem(x) for x in w}
        self.assertEqual(cm.score(entry, words("zeta"), {}), 0.0)
        one = cm.score(entry, words("alpha"), {})
        two = cm.score(entry, words("alpha", "beta"), {})
        three = cm.score(entry, words("alpha", "beta", "gamma"), {})
        self.assertEqual((one, two, three), (0.3, 0.4, 0.4))
        bonus = {"priority_bonus": {"high": 0.25}}
        self.assertEqual(cm.score(dict(entry, priority="high"), words("alpha"), bonus), 0.55)
