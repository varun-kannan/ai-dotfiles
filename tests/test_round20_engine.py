"""Round 20: harness remove and harness init against tracked files in another letter case or a
committed .harness-skip, and one ls-files listing per run."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, Sandbox, commit_all, git, git_init, make
from engine import generate, gitsafe


def _case_insensitive():
    d = tempfile.mkdtemp(prefix="engine-case-")
    try:
        open(os.path.join(d, "probe"), "w").close()
        return os.path.exists(os.path.join(d, "PROBE"))
    finally:
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
        os.rmdir(d)


class Cloned(Sandbox):
    def clone_with(self, files):
        """A clone of someone else's repository that commits files: local mode, never trusted."""
        upstream = git_init(self.tmp / "upstream", authors=("them@x.com",), files=dict({"package.json": "{}"}, **files))
        commit_all(upstream, email="them@x.com")
        clone = self.docs / "clone"
        git(self.tmp, "clone", "-q", str(upstream), str(clone))
        self.assertEqual(self.status(clone), "")
        return clone


class RemoveFoldsCase(Cloned):
    def setUp(self):
        super().setUp()
        if not _case_insensitive():
            self.skipTest("this file system does not fold letter case")

    def assert_left(self, rel, text):
        clone = self.clone_with({rel: text})
        generate.remove(clone)
        self.assertEqual(self.status(clone), "")
        self.assertEqual((clone / rel).read_text(encoding="utf-8"), text)

    def test_tracked_changelog_in_upper_case_is_kept(self):
        self.assert_left(".HARNESS/CHANGELOG.md", "# their changelog\n")

    def test_tracked_claude_local_in_mixed_case_keeps_its_block(self):
        self.assert_left("claude.LOCAL.md", "their notes\n\n%s\n@.harness/AGENTS.md\n%s\n"
                         % (generate.IMPORT_BEGIN, generate.IMPORT_END))

    def test_tracked_agents_md_in_upper_case_folder_is_kept(self):
        self.assert_left(".HARNESS/AGENTS.md", "%s\nblock\n%s\n" % (generate.BEGIN, generate.END))

    def test_tracked_skip_file_in_mixed_case_is_not_overwritten(self):
        clone = self.clone_with({".Harness-Skip": "theirs\n"})
        done = generate.remove(clone)
        self.assertEqual(self.status(clone), "")
        self.assertEqual((clone / ".Harness-Skip").read_text(encoding="utf-8"), "theirs\n")
        self.assertTrue(any("engine's state" in line for line in done), done)
        self.assertEqual(generate.auto(clone, "session")["action"], "skip")


class InitKeepsCommittedSkip(Cloned):
    def harness(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "bin" / "harness")] + list(args), capture_output=True,
                              text=True, env=dict(os.environ), cwd=str(self.home), timeout=60)

    def test_init_overrides_a_committed_skip_file_without_deleting_it(self):
        clone = self.clone_with({".harness-skip": "team opt-out\n"})
        self.assertEqual(generate.auto(clone, "session")["action"], "skip")
        r = self.harness("init", str(clone))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tracked by git", r.stdout)
        self.assertEqual(self.status(clone), "")
        self.assertEqual((clone / ".harness-skip").read_text(encoding="utf-8"), "team opt-out\n")
        self.assertTrue((clone / ".harness" / "AGENTS.md").exists())
        make(clone, {"index.js": "x\n"})                 # a new stamp, so the hook runs setup again
        self.assertIn(generate.auto(clone, "session")["action"], ("updated", "current"))
        generate.remove(clone)                          # remove takes the override back
        self.assertEqual(self.status(clone), "?? index.js\n")
        self.assertEqual(generate.auto(clone, "session")["action"], "skip")

    def test_init_still_deletes_your_own_skip_file(self):
        root = git_init(self.docs / "mine", files={"package.json": "{}"})
        commit_all(root)
        generate.trust(root)
        make(root, {".harness-skip": "x\n"})
        r = self.harness("init", str(root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(root / ".harness-skip"))


class OneListingPerRun(Cloned):
    def counting(self):
        calls = []
        real = gitsafe.scan

        def scan(root, args, match, timeout=gitsafe.TIMEOUT):
            if args[:1] == ["ls-files"]:
                calls.append(str(root))
            return real(root, args, match, timeout)
        return calls, mock.patch.object(gitsafe, "scan", scan)

    def test_setup_that_stops_lists_tracked_files_once(self):
        clone = self.clone_with({})
        self.assertEqual(generate.auto(clone, "session").get("mode"), "local")
        agents = clone / ".harness" / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace(generate.END, ""), encoding="utf-8")
        calls, patch = self.counting()
        with patch:
            r = generate.setup(clone, "prompt", force=True)
        self.assertEqual(r["action"], "damaged", r)
        self.assertEqual(len(calls), 1, calls)

    def test_remove_lists_tracked_files_once(self):
        clone = self.clone_with({})
        generate.auto(clone, "session")
        calls, patch = self.counting()
        with patch:
            generate.remove(clone)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(self.status(clone), "")

    def test_one_listing_answers_each_name(self):
        clone = self.clone_with({".harness/CHANGELOG.md": "x\n", "docs/CLAUDE.md": "y\n"})
        got = generate._scan_tracked(clone, [".harness", ".harness/CHANGELOG.md", ".harness/AGENTS.md",
                                             "CLAUDE.md", "docs"])
        self.assertEqual(got, {".harness": True, ".harness/CHANGELOG.md": True, ".harness/AGENTS.md": False,
                               "CLAUDE.md": False, "docs": True})


if __name__ == "__main__":
    unittest.main()
