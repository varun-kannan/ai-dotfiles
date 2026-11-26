"""Round 20 installer: a user's hook that passes our script extra arguments is kept, the
core.hooksPath note is printed when init.templateDir points elsewhere, a symlinked
~/.git-templates is named as the link, and replacing a shared-folder link that was not ours
is reported."""
import json
import os

from test_install import Installed


class UserHookWithArguments(Installed):
    def test_hook_that_passes_our_script_extra_arguments_is_kept(self):
        mine = "$HOME/.claude/hooks/pre-write-guard.sh --x"
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Write", "hooks": [{"type": "command", "command": mine}]}]}}))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        commands = [h["command"] for g in self.settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn(mine, commands)
        self.assertEqual(len(commands), 2, commands)
        self.assertEqual(self.install().returncode, 0)
        commands = [h["command"] for g in self.settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(len(commands), 2, commands)


class GitTemplates(Installed):
    def test_hooks_path_note_is_printed_when_template_dir_points_elsewhere(self):
        with open(self.home / ".gitconfig", "a") as f:
            f.write("[init]\n\ttemplateDir = %s\n[core]\n\thooksPath = %s\n"
                    % (self.tmp / "elsewhere", self.tmp / "managed-hooks"))
        r = self.install()
        self.assertIn("init.templateDir is already", r.stdout)
        self.assertIn("core.hooksPath or GIT_TEMPLATE_DIR is set", r.stdout)

    def test_symlinked_templates_folder_is_named_as_the_link(self):
        target = self.tmp / "dotfiles-templates"
        (target / "hooks").mkdir(parents=True)
        os.symlink(target, self.home / ".git-templates")
        r = self.install()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("%s is a symlink" % (self.home / ".git-templates"), r.stderr)
        self.assertNotIn("hooks is a symlink", r.stderr)
        self.assertEqual(os.listdir(target / "hooks"), [])


class SharedLinkNotOurs(Installed):
    def test_replacing_a_link_into_your_dotfiles_is_reported(self):
        mine = self.tmp / "dotfiles-bin"
        mine.mkdir()
        (mine / "tool").write_text("#!/bin/sh\n")
        os.symlink(mine, self.shared / "bin")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(self.shared / "bin"), "current/bin")
        self.assertIn("was a link to %s" % mine, r.stdout)
        self.assertTrue((mine / "tool").exists())
        r = self.install()
        self.assertNotIn("was a link to", r.stdout)
