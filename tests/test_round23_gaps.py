"""Round 23 regression tests for hook partners, install locks, and empty folders."""
import importlib.util
import os
import shutil
import subprocess
from unittest import mock

from helpers import ME, ROOT, Sandbox, commit_all, git, git_env, git_init
from engine import project


_spec = importlib.util.spec_from_file_location(
    "session_start_round23_under_test", ROOT / "agents" / "claude-code" / "hooks" / "session-start.py"
)
session_start = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(session_start)


class TypedAmPartnerMatrix(Sandbox):
    def patch_repo(self, name):
        repo = git_init(self.docs / name)
        (repo / "patch.txt").write_text("patched\n", encoding="utf-8")
        commit_all(repo, message="add patch")
        patch = git(repo, "format-patch", "-1", "--stdout").stdout
        git(repo, "reset", "-q", "--hard", "HEAD~1")
        return repo, patch

    @staticmethod
    def put_hook(hooks, source, destination):
        shutil.copyfile(ROOT / "hooks" / "git" / source, hooks / destination)
        os.chmod(hooks / destination, 0o755)

    def put_partner(self, hooks, name, marker, regular, executable):
        target = hooks / (name + (".target" if not regular else ""))
        target.write_text(
            "#!/bin/sh\n# ai-dotfiles hook: %s\n: > \"$ROUND23_MARKER\"\n" % marker,
            encoding="utf-8",
        )
        target.chmod(0o755 if executable else 0o644)
        partner = hooks / name
        if not regular:
            partner.symlink_to(target.name)

    def am(self, repo, patch, marker):
        env = git_env()
        env["ROUND23_MARKER"] = str(marker)
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=x", "-c", "user.email=" + ME, "am", "-q"],
            input=patch,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_only_regular_executable_partners_with_exact_markers_run(self):
        hook_cases = (
            ("pre-applypatch", "pre-commit"),
            ("applypatch-msg", "commit-msg"),
        )
        type_cases = (
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        )
        for hook, partner in hook_cases:
            for regular, executable in type_cases:
                with self.subTest(hook=hook, regular=regular, executable=executable):
                    suffix = "%s-%s-%s" % (hook, "file" if regular else "link", "x" if executable else "no-x")
                    repo, patch = self.patch_repo(suffix)
                    hooks = repo / ".git" / "hooks"
                    self.put_hook(hooks, hook, hook)
                    marker = self.tmp / (suffix + ".ran")
                    self.put_partner(hooks, partner, partner, regular, executable)
                    result = self.am(repo, patch, marker)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(marker.exists(), regular and executable)


class InstallLockWithoutStartTime(Sandbox):
    def setUp(self):
        super().setUp()
        session_start.SHARED = self.shared

    def test_live_pid_with_empty_start_time_is_not_running(self):
        os.symlink("%d:" % os.getpid(), self.shared / ".install.lock")
        with mock.patch.object(session_start.subprocess, "run") as ps:
            self.assertFalse(session_start._install_running())
        ps.assert_not_called()


class FinderFileEmptiness(Sandbox):
    def test_only_regular_finder_file_counts_as_empty(self):
        root = self.docs / "regular"
        root.mkdir()
        (root / ".DS_Store").write_text("finder\n", encoding="utf-8")
        self.assertTrue(project.is_empty(root))

    def test_symlink_named_like_finder_file_is_not_empty(self):
        root = self.docs / "symlink"
        root.mkdir()
        target = self.tmp / "finder-data"
        target.write_text("finder\n", encoding="utf-8")
        (root / ".DS_Store").symlink_to(target)
        self.assertFalse(project.is_empty(root))

    def test_directory_named_like_finder_file_is_not_empty(self):
        root = self.docs / "directory"
        (root / ".DS_Store").mkdir(parents=True)
        self.assertFalse(project.is_empty(root))
