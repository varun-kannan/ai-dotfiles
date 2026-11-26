"""Round 18: a CLAUDE.local.md that came with the folder, a worktree whose common folder is an
ordinary folder, and a tracked AGENTS.md in another letter case on untrust."""
import os
import tempfile
import unittest

from helpers import Sandbox, commit_all, commit_paths, git, git_init, make
from engine import generate, project


def _case_insensitive():
    d = tempfile.mkdtemp(prefix="engine-case-")
    try:
        open(os.path.join(d, "probe"), "w").close()
        return os.path.exists(os.path.join(d, "PROBE"))
    finally:
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
        os.rmdir(d)


def _exclude(root):
    p = root / ".git" / "info" / "exclude"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


class ShippedClaudeLocal(Sandbox):
    def arrived(self):
        """A folder unpacked from an archive: someone else's .git plus their untracked CLAUDE.local.md."""
        root = git_init(self.docs / "unpacked", authors=("them@x.com",), files={"package.json": "{}"})
        commit_all(root, email="them@x.com")
        make(root, {"CLAUDE.local.md": "their notes\n"})
        return root

    def test_claude_local_that_came_with_the_folder_is_left_alone(self):
        root = self.arrived()
        self.assertEqual(self.status(root), "?? CLAUDE.local.md\n")
        r = generate.auto(root, "git")
        self.assertEqual((r["action"], r.get("mode")), ("setup", "local"), r)
        self.assertEqual((root / "CLAUDE.local.md").read_text(encoding="utf-8"), "their notes\n")
        self.assertNotIn("CLAUDE.local.md", _exclude(root))
        self.assertIn(".harness/", _exclude(root))
        self.assertEqual(self.status(root), "?? CLAUDE.local.md\n")
        self.assertTrue(any("CLAUDE.local.md came with this folder" in n for n in r["notes"]), r)
        log = (root / ".harness" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("CLAUDE.local.md came with this folder", log)
        # and keeps leaving it alone on later runs
        make(root, {"other.txt": "x"})
        commit_paths(root, ["other.txt"])
        generate.auto(root, "git")
        self.assertEqual((root / "CLAUDE.local.md").read_text(encoding="utf-8"), "their notes\n")
        self.assertEqual(self.status(root), "?? CLAUDE.local.md\n")

    def test_engine_takes_over_once_the_shipped_file_is_deleted(self):
        root = self.arrived()
        generate.auto(root, "git")
        os.remove(root / "CLAUDE.local.md")
        make(root, {"other.txt": "x"})
        commit_all(root)
        generate.auto(root, "git")
        self.assertIn("@.harness/AGENTS.md", (root / "CLAUDE.local.md").read_text(encoding="utf-8"))
        self.assertEqual(self.status(root), "")

    def test_engine_written_and_user_edited_claude_local_behave_as_before(self):
        root = git_init(self.docs / "clone", authors=("them@x.com",), files={"package.json": "{}"})
        commit_all(root, email="them@x.com")
        r = generate.auto(root, "git")
        self.assertEqual((r["action"], r.get("mode")), ("setup", "local"), r)
        local = root / "CLAUDE.local.md"
        local.write_text("my own line\n" + local.read_text(encoding="utf-8"), encoding="utf-8")
        make(root, {"other.txt": "x"})
        commit_all(root)
        r = generate.auto(root, "git")
        text = local.read_text(encoding="utf-8")
        self.assertIn("my own line", text)
        self.assertIn("@.harness/AGENTS.md", text)
        self.assertIn("CLAUDE.local.md", _exclude(root))
        self.assertEqual(self.status(root), "")
        self.assertFalse(any("came with this folder" in n for n in r["notes"]), r)


class WorktreeCommonDir(Sandbox):
    def test_common_dir_that_is_an_ordinary_folder_is_refused(self):
        downloads = make(self.home / "Downloads", {"photo.txt": "x", "worktrees/x/commondir": "../..\n"})
        root = make(downloads / "proj", {"package.json": "{}"})
        (downloads / "worktrees" / "x" / "gitdir").write_text(str(root / ".git") + "\n", encoding="utf-8")
        (root / ".git").write_text("gitdir: ../worktrees/x\n", encoding="utf-8")
        self.assertIsNone(project.git_layout(root))

    def test_bare_like_common_dir_that_is_an_ancestor_is_refused(self):
        downloads = make(self.home / "Downloads", {"HEAD": "ref: refs/heads/main\n", "objects/.keep": "",
                                                   "refs/.keep": "", "worktrees/x/commondir": "../..\n"})
        root = make(downloads / "proj", {"package.json": "{}"})
        (downloads / "worktrees" / "x" / "gitdir").write_text(str(root / ".git") + "\n", encoding="utf-8")
        (root / ".git").write_text("gitdir: ../worktrees/x\n", encoding="utf-8")
        self.assertIsNone(project.git_layout(root))

    def test_real_worktree_and_bare_repo_worktree_still_qualify(self):
        repo = git_init(self.docs / "repo")
        wt = self.docs / "wt"
        git(repo, "worktree", "add", "-q", str(wt))
        layout = project.git_layout(wt)
        self.assertIsNotNone(layout)
        self.assertEqual(layout[1].name, ".git")
        bare = self.docs / "bare.git"
        git(self.docs, "clone", "-q", "--bare", str(repo), str(bare))
        wt2 = self.docs / "wt2"
        git(bare, "worktree", "add", "-q", str(wt2))
        layout = project.git_layout(wt2)
        self.assertIsNotNone(layout)
        self.assertTrue(os.path.samefile(layout[1], bare))


class RetireCaseVariant(Sandbox):
    def test_tracked_lower_case_agents_md_is_left_on_untrust(self):
        if not _case_insensitive():
            self.skipTest("the temp file system is case-sensitive")
        root = git_init(self.docs / "mine", files={"package.json": "{}", "agents.md": "# team notes\n"})
        commit_all(root)
        generate.trust(root)
        r = generate.setup(root, "manual")
        self.assertEqual(r.get("mode"), "full", r)
        self.assertIn(generate.BEGIN, (root / "agents.md").read_text(encoding="utf-8"))
        commit_paths(root, ["agents.md", "CLAUDE.md"])     # the team now has the block committed in agents.md
        generate.untrust(root)
        r = generate.setup(root, "manual", force=True)
        self.assertEqual(r.get("mode"), "local", r)
        self.assertIn(generate.BEGIN, (root / "agents.md").read_text(encoding="utf-8"))
        self.assertNotIn("agents.md", git(root, "status", "--porcelain").stdout.lower())


if __name__ == "__main__":
    unittest.main()
