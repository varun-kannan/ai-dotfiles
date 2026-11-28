"""Round 21: path-based write-guard exemptions apply only inside installed roots."""
import unittest

from helpers import make
from test_round18_guard import Guard

ZWSP = chr(0x200B)
DIRTY = "x = \"a%sb\"\n" % ZWSP


class InstalledPathExemptions(Guard):
    def paths(self, root):
        return (root / "skills" / "ai-content-forensics" / "reference" / "forensics-x.md",
                root / ".trash-preview" / "copy.py")

    def test_project_local_lookalikes_block(self):
        project = make(self.docs / "project")
        for path in self.paths(project):
            result = self.guard({"file_path": str(path), "content": DIRTY})
            self.assertEqual(result.returncode, 2, "%s: %s" % (path, result.stderr))

    def test_installed_copies_stay_exempt(self):
        installed = make(self.tmp / "home" / ".ai-rules")
        for path in self.paths(installed):
            result = self.guard({"file_path": str(path), "content": DIRTY})
            self.assertEqual(result.returncode, 0, "%s: %s" % (path, result.stderr))

    def test_root_name_prefix_does_not_count_as_inside_root(self):
        installed = make(self.tmp / "home" / ".ai-rules")
        sibling = make(self.tmp / "home" / ".ai-rules-evil")
        for path in self.paths(sibling):
            result = self.guard({"file_path": str(path), "content": DIRTY})
            self.assertEqual(result.returncode, 2, "%s: %s" % (path, result.stderr))


if __name__ == "__main__":
    unittest.main()
