"""Round 17: am hooks and foreign partners, the install lock, harness exit output, duplicate settings keys."""
import os
import subprocess
import sys

from helpers import ME, ROOT, commit_all, git, git_env, git_init, make
from test_install import FOREIGN, Installed

FAILING = "#!/bin/sh\n# someone else's hook that always fails\nexit 1\n"


def start_time(pid):
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             env=dict(os.environ, LC_ALL="C")).stdout
    except OSError:
        return ""
    return out.replace(" ", "").strip()


class AmHooks(Installed):
    def patch_repo(self, name):
        repo = git_init(self.docs / name)
        (repo / "b.txt").write_text("b\n")
        commit_all(repo, message="add b")
        patch = git(repo, "format-patch", "-1", "--stdout").stdout
        git(repo, "reset", "-q", "--hard", "HEAD~1")
        return repo, patch

    def am(self, repo, patch):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.name=x", "-c", "user.email=" + ME, "am", "-q"],
                              input=patch, capture_output=True, text=True, env=git_env())

    def put(self, path, text):
        if os.path.lexists(path):
            os.remove(path)
        path.write_text(text)
        os.chmod(path, 0o755)

    def test_am_hooks_never_run_a_foreign_partner(self):
        self.assertEqual(self.install().returncode, 0)
        repo, patch = self.patch_repo("foreign")
        hooks = repo / ".git" / "hooks"
        self.put(hooks / "pre-commit", FAILING)
        self.put(hooks / "commit-msg", FAILING)
        r = self.am(repo, patch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / "b.txt").exists())

    def test_am_hooks_never_run_a_symlinked_partner(self):
        self.assertEqual(self.install().returncode, 0)
        repo, patch = self.patch_repo("linked")
        hooks = repo / ".git" / "hooks"
        outside = make(self.tmp / "elsewhere")
        for name in ("pre-commit", "commit-msg"):
            target = outside / name
            # Our header, failing: the header alone must not make a symlink trusted.
            target.write_text("#!/bin/bash\n# ai-dotfiles-hook: a link to somewhere else\nexit 1\n")
            os.chmod(target, 0o755)
            os.remove(hooks / name)
            os.symlink(target, hooks / name)
        r = self.am(repo, patch)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_am_hooks_are_not_installed_beside_a_partner_left_alone(self):
        self.assertEqual(self.install().returncode, 0)
        repo, patch = self.patch_repo("partly")
        hooks = repo / ".git" / "hooks"
        for name in ("pre-commit", "commit-msg"):
            self.put(hooks / name, FAILING)
            self.put(hooks / (name + ".local"), FOREIGN)
        r = self.install("--existing-repos", str(self.docs))
        self.assertEqual(r.returncode, 1)
        self.assertIn("partly hooked %s" % repo, r.stderr)
        self.assertFalse(os.path.lexists(hooks / "pre-applypatch"))
        self.assertFalse(os.path.lexists(hooks / "applypatch-msg"))
        self.assertIn("pre-applypatch in %s: it hands off to pre-commit, which was left alone" % hooks, r.stdout)
        self.assertEqual((hooks / "pre-commit").read_text(), FAILING)
        r = self.am(repo, patch)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_template_am_hooks_follow_their_partner(self):
        hooks = make(self.home / ".git-templates" / "hooks")
        self.put(hooks / "commit-msg", FOREIGN)
        self.put(hooks / "commit-msg.local", FOREIGN)
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.lexists(hooks / "applypatch-msg"))
        self.assertTrue((hooks / "pre-applypatch").exists(), "pre-commit was installed, so its am hook is too")
        self.assertIn("left alone commit-msg", r.stderr)
        self.assertNotIn("applypatch-msg (see above)", r.stderr)


class Lock(Installed):
    def running(self, *cmd):
        p = subprocess.Popen(list(cmd))
        self.addCleanup(lambda: (p.kill(), p.wait()))
        return p

    def test_lock_with_the_owners_start_time_is_respected(self):
        fake = make(self.tmp / "running") / "install.sh"
        fake.write_text("#!/bin/bash\nsleep 30\n")
        other = self.running("/bin/bash", str(fake))
        started = start_time(other.pid)
        if not started:
            self.skipTest("ps process start times are unavailable in this sandbox")
        token = "%d:%s" % (other.pid, started)
        os.symlink(token, self.shared / ".install.lock")
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "2"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("another install (pid %d) is still running" % other.pid, r.stderr)
        self.assertEqual(os.readlink(self.shared / ".install.lock"), token)

    def test_reused_pid_with_install_sh_in_its_command_line_does_not_block(self):
        if not start_time(os.getpid()):
            self.skipTest("ps command lines are unavailable in this sandbox")
        fake = make(self.tmp / "editor") / "vim"
        fake.write_text("#!/bin/sh\nsleep 30\n")
        os.chmod(fake, 0o755)
        other = self.running(str(fake), "install.sh")
        os.symlink(str(other.pid), self.shared / ".install.lock")
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "2"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_stale_lock_is_cleared_without_leftovers(self):
        os.symlink("999999:Thu Jan 1 00:00:00 1970", self.shared / ".install.lock")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p for p in os.listdir(self.shared) if p.startswith(".install.lock")], [])

    def test_installs_racing_over_a_stale_lock_all_finish(self):
        os.symlink("999999", self.shared / ".install.lock")
        e = git_env()
        procs = [subprocess.Popen(["/bin/bash", str(ROOT / "install.sh")], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=e) for _ in range(3)]
        for p in procs:
            out, err = p.communicate(timeout=300)
            self.assertEqual(p.returncode, 0, err)
        self.assertEqual([p for p in os.listdir(self.shared) if p.startswith(".install.lock")], [])


class HarnessAndSettings(Installed):
    def test_no_project_here_goes_to_stderr_when_it_is_an_error(self):
        lone = make(self.tmp / "lone")
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "harness"), "init", str(lone)], capture_output=True,
                           text=True, env=dict(os.environ), cwd=str(self.home), timeout=60)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn("no project here", r.stderr)
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "harness"), "status", str(lone)], capture_output=True,
                           text=True, env=dict(os.environ), cwd=str(self.home), timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("no project here", r.stdout)

    def test_settings_with_a_repeated_key_are_left_alone(self):
        target = self.home / ".claude" / "settings.json"
        for text in ('{"model": "opus", "model": "haiku"}',
                     '{"permissions": {"allow": ["A"], "allow": ["B"]}}'):
            target.write_text(text)
            r = self.install()
            self.assertEqual(r.returncode, 1, text)
            self.assertEqual(target.read_text(), text)
            self.assertIn("appears more than once", r.stderr)
            self.assertIn("Left untouched", r.stderr)
