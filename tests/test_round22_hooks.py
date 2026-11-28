"""Round 22: git am hooks hand off only to the correctly typed partner hook."""
import os
import shutil
import subprocess

from helpers import ME, ROOT, Sandbox, commit_all, git, git_env, git_init


class TypedAmPartners(Sandbox):
    def patch_repo(self, name, text="clean\n"):
        repo = git_init(self.docs / name)
        (repo / "patch.txt").write_text(text, encoding="utf-8")
        commit_all(repo, message="add patch")
        patch = git(repo, "format-patch", "-1", "--stdout").stdout
        git(repo, "reset", "-q", "--hard", "HEAD~1")
        return repo, patch

    def put_hook(self, hooks, source, destination):
        shutil.copyfile(ROOT / "hooks" / "git" / source, hooks / destination)
        os.chmod(hooks / destination, 0o755)

    def am(self, repo, patch, **extra_env):
        env = git_env()
        env.update(extra_env)
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=x", "-c", "user.email=" + ME, "am", "-q"],
            input=patch, capture_output=True, text=True, env=env,
        )

    def test_commit_msg_copied_as_pre_commit_is_not_run(self):
        repo, patch = self.patch_repo("wrong-pre-commit")
        hooks = repo / ".git" / "hooks"
        self.put_hook(hooks, "pre-applypatch", "pre-applypatch")
        self.put_hook(hooks, "commit-msg", "pre-commit")
        result = self.am(repo, patch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((repo / "patch.txt").exists())

    def test_real_pre_commit_blocks_zero_width_space(self):
        repo, patch = self.patch_repo("typed-pre-commit", "bad" + chr(0x200B) + "text\n")
        hooks = repo / ".git" / "hooks"
        self.put_hook(hooks, "pre-applypatch", "pre-applypatch")
        self.put_hook(hooks, "pre-commit", "pre-commit")
        result = self.am(repo, patch, AI_RULES_HOME=str(ROOT), AI_HYGIENE_STRICT="1")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ZERO WIDTH SPACE", result.stderr)

    def test_applypatch_msg_does_not_run_pre_commit_as_commit_msg(self):
        repo, patch = self.patch_repo("wrong-commit-msg")
        hooks = repo / ".git" / "hooks"
        self.put_hook(hooks, "applypatch-msg", "applypatch-msg")
        self.put_hook(hooks, "pre-commit", "commit-msg")
        missing = self.tmp / "missing-rules"
        result = self.am(repo, patch, AI_RULES_HOME=str(missing), AI_HYGIENE_STRICT="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((repo / "patch.txt").exists())
