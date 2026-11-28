"""Round 21 installer: settings merges keep integer and float spellings."""
import json
import shutil

from test_install import Installed


class SettingsMerge(Installed):
    def test_number_spellings_survive_a_merge(self):
        path = self.home / ".claude" / "settings.json"
        path.write_text(
            '{"negative_zero": -0, "ten": 10, "big": 12345678901234567890, "ratio": 1.10}\n'
        )
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = path.read_text()
        hook_dir = self.home / ".claude" / "hooks"
        command = lambda script: str(hook_dir / script)
        python_command = lambda script: "%s %s" % (shutil.which("python3"), hook_dir / script)
        self.assertEqual(json.loads(text), {
            "negative_zero": 0,
            "ten": 10,
            "big": 12345678901234567890,
            "ratio": 1.1,
            "includeCoAuthoredBy": False,
            "permissions": {"allow": ["Read(~/.claude/skills/**)"]},
            "hooks": {
                "PreToolUse": [{"hooks": [{"type": "command", "command": command("pre-write-guard.sh"),
                                              "timeout": 15}], "matcher": "Write|Edit|NotebookEdit"}],
                "PostToolUse": [{"hooks": [{"type": "command", "command": command("post-write-audit.sh"),
                                               "timeout": 20}], "matcher": "Write|Edit"}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": python_command("prompt-route.py"),
                                                    "timeout": 10}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": python_command("session-start.py"),
                                                "timeout": 30}]}],
            },
        })
        for spelling in ('"negative_zero": -0', '"ten": 10',
                         '"big": 12345678901234567890', '"ratio": 1.10'):
            self.assertEqual(text.count(spelling), 1, spelling)
