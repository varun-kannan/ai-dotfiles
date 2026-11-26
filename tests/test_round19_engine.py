"""Round 19: a tracked path git's icase pathspec misses (a long s pulled into .harness), and a
worktree common folder that is named .git but is not a git folder."""
import os
import tempfile
import unittest
from unittest import mock

from helpers import Sandbox, commit_all, git, git_init, make
from engine import generate, gitsafe, project

LONG_S = ".harne\u017fs"


def _folds_long_s():
    """True when the temp file system treats "s" and U+017F as one letter (APFS does)."""
    d = tempfile.mkdtemp(prefix="engine-case-")
    try:
        open(os.path.join(d, "probe"), "w").close()
        return os.path.exists(os.path.join(d, "PROBE")) and os.path.exists(os.path.join(d, "probe".replace("s", "\u017f")))
    finally:
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
        os.rmdir(d)


class LongSPulledIn(Sandbox):
    def setUp(self):
        super().setUp()
        if not _folds_long_s():
            self.skipTest("this file system does not fold U+017F")

    def cloned_then_pulled(self, rel, text):
        """A clone set up in local mode, then pulls that ignore .harne* and commit rel under .harne<long s>s/."""
        upstream = git_init(self.tmp / "upstream", authors=("them@x.com",), files={"package.json": "{}"})
        commit_all(upstream, email="them@x.com")
        clone = self.docs / "clone"
        git(self.tmp, "clone", "-q", str(upstream), str(clone))
        r = generate.auto(clone, "git")
        self.assertEqual((r["action"], r.get("mode")), ("setup", "local"), r)
        self.assertIn("@.harness/AGENTS.md", (clone / "CLAUDE.local.md").read_text(encoding="utf-8"))
        make(upstream, {".gitignore": ".harne*/\n"})
        commit_all(upstream, email="them@x.com")
        git(clone, "pull", "-q", "--ff-only")          # the ignore rule first, so git may overwrite the engine's file
        generate.auto(clone, "git")
        make(upstream, {LONG_S + "/" + rel: text})
        git(upstream, "add", "-f", "--", LONG_S + "/" + rel)
        commit_all(upstream, email="them@x.com")
        git(clone, "pull", "-q", "--ff-only")
        return clone

    def test_long_s_agents_md_is_seen_as_tracked(self):
        text = generate.LOCAL_HEADER + "project text without an at sign\n\n" + generate.BEGIN + "\nblock\n" \
            + generate.END + "\n"
        clone = self.cloned_then_pulled("AGENTS.md", text)
        self.assertEqual((clone / ".harness" / "AGENTS.md").read_text(encoding="utf-8"), text)
        r = generate.auto(clone, "git")
        self.assertEqual(r["action"], "skipped", r)
        local = clone / "CLAUDE.local.md"            # the engine wrote it, so it goes once its import is out
        self.assertFalse(local.exists() and "@.harness/AGENTS.md" in local.read_text(encoding="utf-8"))
        self.assertEqual((clone / ".harness" / "AGENTS.md").read_text(encoding="utf-8"), text)
        self.assertEqual(git(clone, "status", "--porcelain").stdout, "")

    def test_long_s_config_is_not_used(self):
        clone = self.cloned_then_pulled("config.json", '{"exclude": ["testing-guide"]}\n')
        r = generate.auto(clone, "git")
        self.assertEqual(r["action"], "skipped", r)     # prompt-route then reads no project config
        self.assertTrue(any("tracked by git" in n for n in r["notes"]), r["notes"])


class TrackedFolding(Sandbox):
    def test_folded_names_count_on_any_file_system(self):
        root = git_init(self.docs / "r", files={"package.json": "{}", "src/x.txt": "x"})
        commit_all(root)
        self.assertFalse(generate._tracked_any(root, ".harness"))
        records = [b"src/x.txt", (LONG_S + "/AGENTS.md").encode("utf-8"), b"Claude.Local.md"]
        with mock.patch.object(gitsafe, "scan", side_effect=lambda r, a, match: any(match(p) for p in records)):
            self.assertTrue(generate._tracked_any(root, ".harness"))
            self.assertTrue(generate._tracked_any(root, ".harness/AGENTS.md"))
            self.assertFalse(generate._tracked_any(root, ".harness/config.json"))
            self.assertTrue(generate._tracked_any(root, "CLAUDE.local.md"))
            self.assertFalse(generate._tracked_any(root, "AGENTS.md"))

    def test_subfolder_project_sees_only_its_own_paths(self):
        repo = git_init(self.docs / "mono", files={".harness/AGENTS.md": "x", "app/package.json": "{}"})
        commit_all(repo)
        self.assertTrue(generate._tracked_any(repo, ".harness"))
        self.assertFalse(generate._tracked_any(repo / "app", ".harness"))
        make(repo, {"app/.harness/README": "x"})
        commit_all(repo)
        self.assertTrue(generate._tracked_any(repo / "app", ".harness"))

    def test_git_that_cannot_answer_counts_as_tracked(self):
        root = git_init(self.docs / "r", files={"package.json": "{}"})
        commit_all(root)
        with mock.patch.object(gitsafe, "scan", side_effect=lambda *a, **k: None):
            self.assertTrue(generate._tracked_any(root, ".harness"))
        self.assertIsNone(gitsafe.scan(self.tmp / "missing", ["ls-files", "-z"], lambda p: False))


class FakeDotGitCommonDir(Sandbox):
    def test_folder_named_git_without_a_store_is_refused(self):
        dl = make(self.home / "Downloads" / "unpacked", {"store/.git/worktrees/w/commondir": "../..\n"})
        app = make(dl / "app", {"package.json": "{}"})
        (dl / "store" / ".git" / "worktrees" / "w" / "gitdir").write_text(str(app / ".git") + "\n", encoding="utf-8")
        (app / ".git").write_text("gitdir: %s\n" % (dl / "store" / ".git" / "worktrees" / "w"), encoding="utf-8")
        self.assertIsNone(project.git_layout(app))
        generate.auto(app, "git")
        self.assertFalse(os.path.lexists(dl / "store" / ".git" / "info" / "exclude"))

    def test_real_worktree_still_qualifies(self):
        repo = git_init(self.docs / "repo")
        wt = self.docs / "wt"
        git(repo, "worktree", "add", "-q", str(wt))
        self.assertIsNotNone(project.git_layout(wt))


if __name__ == "__main__":
    unittest.main()
