"""Round 26 installer regression tests for filename-specific hook ownership."""
import os

from helpers import ROOT
from test_install import FOREIGN, Installed


class HookOwnership(Installed):
    def hooks(self):
        return self.home / ".git-templates" / "hooks"

    @staticmethod
    def write_hook(path, marker):
        path.write_text("#!/bin/sh\n# %s\nexit 0\n" % marker, encoding="utf-8")
        path.chmod(0o755)

    def test_mismatched_typed_am_hook_survives_when_partner_is_left_alone(self):
        self.assertEqual(self.install().returncode, 0)
        hooks = self.hooks()
        mismatched = "#!/bin/sh\n# ai-dotfiles hook: commit-msg\nexit 7\n"
        (hooks / "pre-applypatch").write_text(mismatched, encoding="utf-8")
        os.chmod(hooks / "pre-applypatch", 0o755)
        (hooks / "pre-commit").write_text(FOREIGN, encoding="utf-8")
        (hooks / "pre-commit.local").write_text(FOREIGN + "# local\n", encoding="utf-8")

        result = self.install()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("pre-commit, which was left alone", result.stdout)
        survivors = [p.read_text(encoding="utf-8") for p in
                     (hooks / "pre-applypatch", hooks / "pre-applypatch.local") if p.exists()]
        self.assertIn(mismatched, survivors)
        self.assertEqual((hooks / "pre-commit").read_text(encoding="utf-8"), FOREIGN)

    def test_correctly_marked_hook_is_replaced(self):
        self.assertEqual(self.install().returncode, 0)
        hook = self.hooks() / "post-merge"
        self.write_hook(hook, "ai-dotfiles hook: post-merge")

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(hook.read_bytes(), (ROOT / "hooks" / "git" / "post-merge").read_bytes())

    def test_legacy_header_hook_is_replaced(self):
        self.assertEqual(self.install().returncode, 0)
        hook = self.hooks() / "post-checkout"
        self.write_hook(hook, "ai-dotfiles-hook: legacy")

        result = self.install()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(hook.read_bytes(), (ROOT / "hooks" / "git" / "post-checkout").read_bytes())
