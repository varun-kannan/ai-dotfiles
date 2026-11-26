"""install.sh, the git hooks, doctor and the harness CLI, run for real against a sandbox home."""
import codecs
import json
import os
import shutil
import subprocess
import sys
import time

from helpers import ME, ROOT, Sandbox, commit_all, git, git_env, git_init, make

OLD_HOOK = "#!/usr/bin/env bash\n# strip-ai-attribution - git commit-msg hook\nexit 0\n"
FOREIGN = "#!/bin/sh\n# someone else's hook\nexit 0\n"
ZERO_WIDTH_SPACE = chr(0x200B)


class Installed(Sandbox):
    def setUp(self):
        super().setUp()
        make(self.home / ".claude")
        (self.home / ".zshrc").write_text("# mine\nexport FOO=1\n")

    def install(self, *args, env=None):
        e = git_env()
        e.update(env or {})
        return subprocess.run(["/bin/bash", str(ROOT / "install.sh")] + list(args), capture_output=True, text=True, env=e, timeout=180)

    def harness(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(self.shared / "bin" / "harness")] + list(args), capture_output=True,
                              text=True, env=dict(os.environ), cwd=str(cwd or self.home), timeout=60)

    def settings(self):
        return json.loads((self.home / ".claude" / "settings.json").read_text())


class Install(Installed):
    def test_fresh_install_then_rerun_is_idempotent(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.shared / "current").is_symlink())
        for name in ("bin", "engine", "rules", "config", "skills", "shell", "RULES.md"):
            self.assertTrue((self.shared / name).is_symlink(), name)
        self.assertTrue((self.shared / "bin" / "harness").exists())
        self.assertFalse((self.shared / ".install.lock").exists())
        self.assertEqual([p for p in (self.shared / "releases").iterdir() if p.name.startswith(".stage")], [])
        self.assertEqual((self.shared / "source").read_text().strip(), str(ROOT))
        first = self.settings()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.settings(), first)
        for event in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart"):
            self.assertEqual(len(first["hooks"][event]), 1, event)
        self.assertNotIn("matcher", first["hooks"]["UserPromptSubmit"][0])
        self.assertTrue(first["hooks"]["SessionStart"][0]["hooks"][0]["command"].split()[0].startswith("/"))
        zshrc = (self.home / ".zshrc").read_text()
        self.assertEqual(zshrc.count("BEGIN ai-dotfiles:harness"), 1)
        self.assertTrue(zshrc.startswith("# mine\nexport FOO=1\n"))
        self.assertIn(str(ROOT), (self.shared / "harness-exclude").read_text())
        self.assertEqual(git(self.home, "config", "--global", "--get", "init.templateDir").stdout.strip(),
                         str(self.home / ".git-templates"))
        self.assertEqual(sorted(os.listdir(self.home / ".git-templates" / "hooks")),
                         ["applypatch-msg", "commit-msg", "post-checkout", "post-merge", "pre-applypatch", "pre-commit"])

    def test_releases_are_pruned_to_three(self):
        for _ in range(5):
            self.assertEqual(self.install().returncode, 0)
        self.assertEqual(len([p for p in (self.shared / "releases").iterdir() if not p.name.startswith(".")]), 3)
        self.assertTrue((self.shared / "current" / "engine" / "decide.py").exists())

    def test_user_settings_and_similar_hooks_survive(self):
        mine = {"model": "opus", "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(.env)"]},
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "/me/my/session-start.py"}]}],
                          "Stop": [{"hooks": [{"type": "command", "command": "/me/stop.sh"}]}]}}
        self.write_json(self.home / ".claude" / "settings.json", mine)
        self.assertEqual(self.install().returncode, 0)
        cfg = self.settings()
        self.assertEqual(cfg["model"], "opus")
        self.assertIn("Bash(ls:*)", cfg["permissions"]["allow"])
        self.assertEqual(cfg["permissions"]["deny"], ["Read(.env)"])
        commands = [h["command"] for g in cfg["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertIn("/me/my/session-start.py", commands)
        self.assertEqual(len(commands), 2)
        self.assertEqual(cfg["hooks"]["Stop"], mine["hooks"]["Stop"])

    def test_broken_settings_file_is_left_alone(self):
        broken = '{"permissions":{"allow":["X"]},"model":"opus",}'
        (self.home / ".claude" / "settings.json").write_text(broken)
        r = self.install()
        self.assertEqual(r.returncode, 1, "hooks that are not registered are a failed install, said plainly")
        self.assertEqual((self.home / ".claude" / "settings.json").read_text(), broken)
        self.assertIn("not valid JSON", r.stderr)
        self.assertIn("NOT registered", r.stderr)
        self.assertIn("not fully installed: claude-code", r.stderr)
        self.assertFalse(any(".bak" in p.name for p in (self.home / ".claude").iterdir()), "nothing was changed, so nothing is copied")
        self.assertTrue((self.home / ".git-templates" / "hooks" / "pre-commit").exists(), "the rest was installed")

    def test_settings_parts_with_an_unexpected_shape_are_never_dropped(self):
        cases = ({"hooks": ["mine"]}, {"permissions": "all"}, {"permissions": {"allow": "Bash"}},
                 {"hooks": {"SessionStart": {"hooks": [{"type": "command", "command": "~/mine.sh"}]}}}, ["a", "list"])
        for content in cases:
            text = json.dumps(content)
            (self.home / ".claude" / "settings.json").write_text(text)
            r = self.install()
            self.assertEqual(r.returncode, 1, text)
            self.assertEqual((self.home / ".claude" / "settings.json").read_text(), text)
            self.assertIn("Left untouched", r.stderr)

    def test_settings_with_a_byte_order_mark_or_read_only_or_dangling_link(self):
        target = self.home / ".claude" / "settings.json"
        target.write_bytes(codecs.BOM_UTF8 + json.dumps({"model": "opus"}).encode())
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.settings()["model"], "opus")
        self.assertIn("SessionStart", self.settings()["hooks"])
        before = target.read_text()
        os.chmod(target, 0o444)
        try:
            r = self.install()
            self.assertEqual(r.returncode, 1)
            self.assertEqual(target.read_text(), before, "a read-only file is not replaced behind your back")
        finally:
            os.chmod(target, 0o644)
        target.unlink()
        os.symlink(self.tmp / "nowhere" / "settings.json", target)
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(target.is_symlink())

    def test_hand_edited_rules_are_backed_up_once_and_kept(self):
        self.install()
        rules = self.home / ".claude" / "CLAUDE.md"
        self.assertEqual(oct(rules.stat().st_mode & 0o777), "0o644")
        rules.write_text("MY HAND EDIT\n")
        self.install()
        backups = [p for p in rules.parent.iterdir() if p.name.startswith("CLAUDE.md.bak-")]
        self.assertEqual([b.read_text() for b in backups], ["MY HAND EDIT\n"])
        self.install()
        self.install()
        after = [p for p in rules.parent.iterdir() if p.name.startswith("CLAUDE.md.bak-")]
        self.assertEqual([b.read_text() for b in after], ["MY HAND EDIT\n"], "generated copies are not backed up over it")
        time.sleep(1.1)                                   # backups are named by the second
        rules.write_text("A SECOND, DIFFERENT EDIT\n")
        self.install()
        later = sorted(b.read_text() for b in rules.parent.iterdir() if b.name.startswith("CLAUDE.md.bak-"))
        self.assertEqual(later, ["A SECOND, DIFFERENT EDIT\n", "MY HAND EDIT\n"], "a new edit is kept too, next to the old one")

    def test_symlinked_rules_file_stays_a_symlink(self):
        real = self.tmp / "dotfiles-CLAUDE.md"
        real.write_text("old\n")
        os.symlink(real, self.home / ".claude" / "CLAUDE.md")
        self.install()
        self.assertTrue((self.home / ".claude" / "CLAUDE.md").is_symlink())
        self.assertIn("Behavioral guidelines", real.read_text())

    def test_unwritable_zshrc_does_not_abort(self):
        os.chmod(self.home / ".zshrc", 0o444)
        try:
            r = self.install()
        finally:
            os.chmod(self.home / ".zshrc", 0o644)
        self.assertEqual(r.returncode, 1)
        self.assertIn("could not write", r.stderr)
        self.assertIn("these steps failed: zsh-trigger", r.stderr)
        self.assertTrue((self.home / ".claude" / "settings.json").exists())
        self.assertTrue((self.home / ".git-templates" / "hooks" / "pre-commit").exists())

    def test_stale_lock_from_a_dead_install_is_cleared(self):
        os.symlink("999999", self.shared / ".install.lock")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_stale_lock_folder_from_an_older_installer_is_cleared(self):
        make(self.shared / ".install.lock")
        (self.shared / ".install.lock" / "pid").write_text("999999")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_lock_held_by_a_running_installer_is_respected_and_left_in_place(self):
        fake = make(self.tmp / "running") / "install.sh"
        fake.write_text("#!/bin/bash\nsleep 30\n")
        other = subprocess.Popen(["/bin/bash", str(fake)])
        try:
            os.symlink(str(other.pid), self.shared / ".install.lock")
            r = self.install(env={"AI_INSTALL_LOCK_WAIT": "2"})
            self.assertEqual(r.returncode, 1)
            self.assertIn("another install (pid %d) is still running" % other.pid, r.stderr)
            self.assertEqual(os.readlink(self.shared / ".install.lock"), str(other.pid), "someone else's lock is not removed")
            self.assertFalse((self.shared / "current").exists(), "nothing was installed")
        finally:
            other.kill()
            other.wait()

    def test_lock_naming_a_live_process_that_is_not_an_installer_is_cleared(self):
        os.symlink(str(os.getpid()), self.shared / ".install.lock")       # the pid was reused by another program
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "2"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_upgrade_from_the_copy_in_place_layout(self):
        for name in ("bin", "engine", "rules"):
            make(self.shared / name, {"old.txt": "old"})
        (self.shared / "RULES.md").write_text("old rules\n")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("bin", "engine", "rules", "RULES.md"):
            self.assertEqual(os.readlink(self.shared / name), "current/" + name)
        self.assertFalse((self.shared / "bin" / "old.txt").exists())
        self.assertEqual([p.name for p in (self.shared / "releases").iterdir() if p.name.startswith(".")], [])

    def test_failed_switch_leaves_the_previous_install_whole(self):
        for name in ("bin", "engine"):
            make(self.shared / name, {"old.txt": "old"})
        make(self.shared / "current", {"in-the-way.txt": "x"})        # a folder here cannot be replaced by the link
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.shared / "bin" / "old.txt").read_text(), "old", "old tools still there")
        self.assertFalse((self.shared / "bin").is_symlink())
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_link_pointing_somewhere_else_is_corrected(self):
        self.install()
        os.remove(self.shared / "skills")
        os.symlink("/nonexistent/skills", self.shared / "skills")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(os.readlink(self.shared / "skills"), "current/skills")
        self.assertTrue((self.shared / "skills" / "testing-guide" / "SKILL.md").exists())

    def test_leftover_stage_folder_from_a_killed_install_is_removed_after_a_day(self):
        old = make(self.shared / "releases" / ".stage-old", {"x": "1"})
        fresh = make(self.shared / "releases" / ".stage-fresh", {"x": "1"})
        two_days = time.time() - 2 * 86400
        os.utime(old, (two_days, two_days))
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists(), "one that may belong to a running install is left")

    def test_one_agent_failing_does_not_stop_the_rest(self):
        make(self.home / ".gemini")
        (self.home / ".gemini" / "GEMINI.md").write_text("mine\n")
        os.chmod(self.home / ".gemini" / "GEMINI.md", 0o444)
        os.chmod(self.home / ".gemini", 0o555)
        try:
            r = self.install()
        finally:
            os.chmod(self.home / ".gemini", 0o755)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not fully installed: gemini-cli", r.stderr)
        self.assertEqual((self.home / ".gemini" / "GEMINI.md").read_text(), "mine\n")
        self.assertTrue((self.home / ".claude" / "CLAUDE.md").exists(), "other agents were installed")
        self.assertTrue((self.home / ".git-templates" / "hooks" / "pre-commit").exists(), "and so were the git hooks")
        self.assertFalse(os.path.lexists(self.shared / ".install.lock"))

    def test_cursor_and_devin_print_their_manual_steps(self):
        make(self.home / ".cursor")
        out = self.install().stdout
        self.assertIn("Cursor reads instructions from account settings", out)
        self.assertIn("Devin reads AGENTS.md", out)

    def test_symlinked_settings_keep_their_link_and_mode(self):
        real = make(self.tmp / "dotfiles") / "settings.json"
        real.write_text(json.dumps({"env": {"TOKEN": "t"}}))
        os.chmod(real, 0o600)
        os.symlink(real, self.home / ".claude" / "settings.json")
        self.assertEqual(self.install().returncode, 0)
        self.assertTrue((self.home / ".claude" / "settings.json").is_symlink())
        data = json.loads(real.read_text())
        self.assertEqual(data["env"], {"TOKEN": "t"})
        self.assertIn("SessionStart", data["hooks"])
        self.assertEqual(os.stat(real).st_mode & 0o777, 0o600)

    def test_new_settings_file_is_private_and_empty_one_is_filled(self):
        self.install()
        self.assertEqual(os.stat(self.home / ".claude" / "settings.json").st_mode & 0o777, 0o600)
        (self.home / ".claude" / "settings.json").write_text("")
        r = self.install()
        self.assertNotIn("not a JSON object", r.stderr)
        self.assertIn("SessionStart", self.settings()["hooks"])

    def test_our_hook_spelled_with_tilde_or_home_is_not_doubled(self):
        self.write_json(self.home / ".claude" / "settings.json", {"hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/prompt-route.py"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/session-start.py"},
                                        {"type": "command", "command": "~/bin/mine.sh"}]}]}})
        self.install()
        hooks = self.settings()["hooks"]
        prompt = [h["command"] for g in hooks["UserPromptSubmit"] for h in g["hooks"]]
        start = [h["command"] for g in hooks["SessionStart"] for h in g["hooks"]]
        self.assertEqual(len(prompt), 1, prompt)
        self.assertEqual(sorted(c.split("/")[-1] for c in start), ["mine.sh", "session-start.py"])

    def test_custom_template_dir_is_respected(self):
        (self.home / ".gitconfig").write_text("[user]\n\temail = %s\n[init]\n\ttemplateDir = ~/my-templates\n" % ME)
        r = self.install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("left as is", r.stdout)
        self.assertEqual(git(self.home, "config", "--global", "--get", "init.templateDir").stdout.strip(), "~/my-templates")
        self.assertFalse((self.home / ".git-templates").exists())

    def test_trailing_slash_template_dir_counts_as_ours(self):
        (self.home / ".gitconfig").write_text("[user]\n\temail = %s\n[init]\n\ttemplateDir = ~/.git-templates/\n" % ME)
        self.install()
        self.assertTrue((self.home / ".git-templates" / "hooks" / "pre-commit").exists())

    def test_hooks_from_an_older_install_are_replaced_not_doubled(self):
        hooks = make(self.home / ".git-templates" / "hooks")
        (hooks / "commit-msg").write_text(OLD_HOOK)
        self.install()
        self.assertFalse((hooks / "commit-msg.local").exists())
        self.assertIn("ai-dotfiles-hook", (hooks / "commit-msg").read_text())
        # an earlier buggy upgrade may have left our own hook as .local: it is cleaned up
        # an earlier upgrade may have left an exact copy of our hook as .local: it would run twice, so it goes
        (hooks / "pre-commit.local").write_bytes((ROOT / "hooks" / "git" / "pre-commit").read_bytes())
        self.install()
        self.assertFalse((hooks / "pre-commit.local").exists())

    def test_local_hook_built_from_a_copy_of_ours_is_yours(self):
        hooks = make(self.home / ".git-templates" / "hooks")
        mine = (ROOT / "hooks" / "git" / "pre-commit").read_text() + "\n# my extra check\nexit 0\n"
        (hooks / "pre-commit.local").write_text(mine)
        self.install()
        self.install()
        self.assertEqual((hooks / "pre-commit.local").read_text(), mine)

    def test_your_own_local_hook_that_mentions_ours_is_kept(self):
        hooks = make(self.home / ".git-templates" / "hooks")
        mine = "#!/bin/sh\n# mine: run my linter before the ai-dotfiles-hook and its universal output-hygiene gate\nexit 0\n"
        (hooks / "pre-commit.local").write_text(mine)
        self.install()
        self.install()
        self.assertEqual((hooks / "pre-commit.local").read_text(), mine)

    def test_foreign_hooks_are_kept_and_never_overwritten(self):
        hooks = make(self.home / ".git-templates" / "hooks")
        (hooks / "pre-commit").write_text(FOREIGN)
        os.chmod(hooks / "pre-commit", 0o755)
        (hooks / "commit-msg").write_text(FOREIGN)             # a hook you had switched off: not executable
        os.chmod(hooks / "commit-msg", 0o644)
        r = self.install()
        self.assertEqual((hooks / "pre-commit.local").read_text(), FOREIGN)
        self.assertTrue(os.access(hooks / "pre-commit.local", os.X_OK))
        self.assertFalse(os.access(hooks / "commit-msg.local", os.X_OK), "a hook that was off is not switched on")
        self.assertIn("stays off", r.stdout)
        (hooks / "pre-commit").write_text("#!/bin/sh\n# a second foreign hook\n")
        r = self.install()
        self.assertEqual((hooks / "pre-commit").read_text(), "#!/bin/sh\n# a second foreign hook\n")
        self.assertEqual((hooks / "pre-commit.local").read_text(), FOREIGN)
        self.assertIn("left alone", r.stderr)

    def test_existing_repos(self):
        self.install()
        plain = git_init(self.docs / "plain")
        husky = git_init(self.docs / "husky")
        git(husky, "config", "core.hooksPath", ".husky")
        shutil.rmtree(husky / ".git" / "hooks")      # the template put ours there at init
        bare = git_init(self.docs / "nohooks")
        shutil.rmtree(bare / ".git" / "hooks")
        spaced = git_init(self.docs / "has space")
        deep4 = git_init(self.docs / "a" / "b" / "c" / "four")
        deep5 = git_init(self.docs / "a" / "b" / "c" / "d" / "five")
        for repo in (deep4, deep5):
            shutil.rmtree(repo / ".git" / "hooks")
            os.mkdir(repo / ".git" / "hooks")
        outside = make(self.tmp / "outside-hooks")
        linked = git_init(self.docs / "linked")
        shutil.rmtree(linked / ".git" / "hooks")
        os.symlink(outside, linked / ".git" / "hooks")
        linkedhook = git_init(self.docs / "linkedhook")
        (self.home / "victim-hook").write_text("keep\n")
        os.remove(linkedhook / ".git" / "hooks" / "pre-commit")
        os.symlink(self.home / "victim-hook", linkedhook / ".git" / "hooks" / "pre-commit")
        r = self.install("--existing-repos", str(self.docs))
        self.assertEqual(r.returncode, 1, "a partly hooked repo (linkedhook) is a failed step")
        self.assertIn("these steps failed: existing-repos", r.stderr)
        self.assertTrue((plain / ".git" / "hooks" / "post-merge").exists())
        self.assertTrue((bare / ".git" / "hooks" / "pre-commit").exists())
        self.assertTrue((spaced / ".git" / "hooks" / "pre-commit").exists())
        self.assertFalse((husky / ".git" / "hooks").exists())
        self.assertIn("skip", r.stdout)
        self.assertIn("pre-commit", os.listdir(deep4 / ".git" / "hooks"), "a repo four levels below DIR is reached")
        self.assertNotIn("pre-commit", os.listdir(deep5 / ".git" / "hooks"), "five levels is past the limit")
        self.assertEqual(os.listdir(outside), [], "a symlinked hooks folder is not written through")
        self.assertIn("its hooks folder is a symlink", r.stdout)
        self.assertEqual((self.home / "victim-hook").read_text(), "keep\n", "a symlinked hook is not written through")
        self.assertTrue((linkedhook / ".git" / "hooks" / "commit-msg").exists(), "the other hooks are still installed")
        self.assertIn("partly hooked %s" % linkedhook, r.stderr)
        bad = self.install("--existing-repos", str(self.docs / "missing"))
        self.assertEqual(bad.returncode, 2)
        self.assertIn("not a folder", bad.stderr)

    def test_arguments(self):
        r = self.install("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--existing-repos DIR", r.stdout)
        self.assertFalse((self.shared / "current").exists(), "--help installs nothing")
        for args in (("--dry-run",), ("--existing-repos",), ("--dry-run", "--existing-repos", str(self.docs)), ("extra",)):
            r = self.install(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertFalse((self.shared / "current").exists(), args)

    def test_lock_problems_are_named_for_what_they_are(self):
        os.symlink("not-a-pid", self.shared / ".install.lock")
        r = self.install()
        self.assertEqual(r.returncode, 0, "a lock that names no process is cleared")
        r = self.install(env={"AI_INSTALL_LOCK_WAIT": "abc"})
        self.assertEqual(r.returncode, 0, "a bad wait value falls back to the default")
        os.chmod(self.shared, 0o555)
        try:
            r = self.install()
        finally:
            os.chmod(self.shared, 0o755)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot write to", r.stderr)
        self.assertNotIn("another install", r.stderr)

    def test_files_of_yours_in_the_old_layout_are_kept(self):
        make(self.shared / "bin", {"my-own-script": "#!/bin/sh\n", "harness": "edited by me\n",
                                   "check-deps": (ROOT / "bin" / "check-deps").read_text()})
        make(self.shared / "config", {"my-local.json": "{}"})
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        kept = [p for p in self.shared.iterdir() if p.name.startswith("kept-from-old-layout-")]
        self.assertEqual(len(kept), 1)
        self.assertTrue((kept[0] / "bin" / "my-own-script").exists())
        self.assertTrue((kept[0] / "config" / "my-local.json").exists())
        self.assertTrue((kept[0] / "bin" / "harness").exists(), "a file you changed is kept even if the release has one")
        self.assertFalse((kept[0] / "bin" / "check-deps").exists(), "an identical copy is not")
        self.assertIn(str(kept[0]), r.stdout)

    def test_upgrade_that_stops_half_way_keeps_your_files_and_says_so(self):
        make(self.shared / "bin", {"my-own-script": "#!/bin/sh\n"})
        make(self.shared / "engine", {"old.py": "x = 1\n"})
        os.chmod(self.shared / "engine", 0o555)          # this folder cannot be moved aside
        try:
            r = self.install()
        finally:
            os.chmod(self.shared / "engine", 0o755)
        self.assertEqual(r.returncode, 1)
        self.assertIn("partly installed", r.stderr)
        self.assertNotIn("nothing was installed", r.stderr)
        kept = [p for p in self.shared.iterdir() if p.name.startswith("kept-from-old-layout-")]
        self.assertEqual(len(kept), 1, r.stderr)
        self.assertTrue((kept[0] / "bin" / "my-own-script").exists())
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((kept[0] / "bin" / "my-own-script").exists(), "a later install does not remove it")

    def test_current_that_is_a_folder_is_reported_not_crashed_on(self):
        make(self.shared / "current", {"x": "1"})
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not a link", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual([p.name for p in (self.shared / "releases").iterdir()] if (self.shared / "releases").exists() else [], [])

    def test_failed_step_is_named_and_the_rest_still_runs(self):
        make(self.home / ".git-templates" / "hooks")
        os.chmod(self.home / ".git-templates" / "hooks", 0o555)
        try:
            r = self.install()
        finally:
            os.chmod(self.home / ".git-templates" / "hooks", 0o755)
        self.assertEqual(r.returncode, 1)
        self.assertIn("these steps failed: git-hooks", r.stderr)
        self.assertTrue((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertTrue((self.shared / "current").is_symlink())

    def test_skills_removed_from_the_repo_are_pruned_and_your_own_are_kept(self):
        self.install()
        skills = self.home / ".claude" / "skills"
        make(skills / "my-own-skill", {"SKILL.md": "mine"})
        import hashlib
        listing = self.shared / "generated" / ("skills-" + hashlib.sha1(str(skills).encode()).hexdigest()[:16])
        self.assertTrue(listing.exists())
        make(skills / "retired-skill", {"SKILL.md": "ours, once"})
        with open(listing, "a") as fh:
            fh.write("retired-skill\n../escape\n")
        r = self.install()
        self.assertFalse((skills / "retired-skill").exists())
        self.assertIn("gone  skill retired-skill", r.stdout)
        self.assertTrue((skills / "my-own-skill" / "SKILL.md").exists())
        self.assertTrue((skills / "testing-guide" / "SKILL.md").exists())


class GitHooks(Installed):
    def copy_hooks(self, repo, names):
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        for name in names:
            (hooks / name).write_bytes((ROOT / "hooks" / "git" / name).read_bytes())
            os.chmod(hooks / name, 0o755)
        return hooks

    def commit(self, repo, message, env=None):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.name=x", "-c", "user.email=" + ME, "commit", "-m", message],
                              capture_output=True, text=True, env=env or git_env())

    def test_kept_hook_runs_first_and_can_block_a_commit(self):
        self.install()
        repo = git_init(self.docs / "r")
        hooks = self.copy_hooks(repo, ("pre-commit", "commit-msg", "post-checkout"))
        (hooks / "pre-commit.local").write_text("#!/bin/sh\nexit 3\n")
        os.chmod(hooks / "pre-commit.local", 0o755)
        (repo / "a.txt").write_text("a")
        git(repo, "add", "-A")
        self.assertNotEqual(self.commit(repo, "x").returncode, 0)
        os.remove(hooks / "pre-commit.local")
        (hooks / "post-checkout.local").write_text("#!/bin/sh\nexit 9\n")
        os.chmod(hooks / "post-checkout.local", 0o755)
        ok = self.commit(repo, "real change\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertNotIn("Co-Authored-By", git(repo, "log", "-1", "--format=%B").stdout)
        self.assertEqual(git(repo, "checkout", "-q", "-b", "other", check=False).returncode, 0, "post hooks never fail git")

    def test_pre_commit_blocks_hidden_text_and_survives_a_broken_scanner(self):
        self.install()
        repo = git_init(self.docs / "h")
        self.copy_hooks(repo, ("pre-commit",))
        (repo / "x.py").write_text("x = 1" + ZERO_WIDTH_SPACE + "\n", encoding="utf-8")
        git(repo, "add", "-A")
        r = self.commit(repo, "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Commit blocked", r.stderr)
        broken = self.tmp / "broken-rules"
        make(broken / "bin")
        (broken / "bin" / "content-hygiene").write_text("#!/bin/sh\nexit 2\n")
        os.chmod(broken / "bin" / "content-hygiene", 0o755)
        env = git_env()
        env["AI_RULES_HOME"] = str(broken)
        # A scanner that starts and then fails blocks with a clear message rather than crashing
        # the hook or letting the files through unchecked.
        r = self.commit(repo, "x", env=env)
        self.assertNotEqual(r.returncode, 0, r.stderr)
        self.assertIn("scanner failed part way", r.stderr)

    def test_pre_commit_judges_what_is_staged_not_what_is_on_disk(self):
        self.install()
        repo = git_init(self.docs / "staged")
        self.copy_hooks(repo, ("pre-commit",))
        (repo / "x.py").write_text("x = 1" + ZERO_WIDTH_SPACE + "\n", encoding="utf-8")
        git(repo, "add", "x.py")
        (repo / "x.py").write_text("x = 1\n")                      # clean on disk, dirty in the index
        r = self.commit(repo, "sneak")
        self.assertNotEqual(r.returncode, 0, "the staged copy is what gets committed")
        self.assertIn("x.py:1:6", r.stderr)
        self.assertNotIn(str(self.tmp), r.stderr.split("Commit blocked")[1].split("These are defects")[0],
                         "paths in the report are repo paths, not the temporary copy")
        git(repo, "add", "x.py")
        (repo / "x.py").write_text("x = 1" + ZERO_WIDTH_SPACE + "\n", encoding="utf-8")   # dirty on disk, clean in the index
        r = self.commit(repo, "fine")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pre_commit_handles_dash_names_deletions_and_symlinks(self):
        self.install()
        repo = git_init(self.docs / "odd")
        self.copy_hooks(repo, ("pre-commit",))
        (repo / "--self-test").write_text("ok\n")
        (self.home / "outside.py").write_text("x = 1" + ZERO_WIDTH_SPACE + "\n", encoding="utf-8")
        os.symlink(self.home / "outside.py", repo / "link.py")
        os.remove(repo / "commit-0.txt")
        git(repo, "add", "-A")
        r = self.commit(repo, "odd names")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("passed", r.stdout + r.stderr, "a file name is never taken as an option")

    def test_clone_of_someone_elses_repo_changes_nothing_tracked(self):
        self.install()
        origin = git_init(self.tmp / "origin", authors=("someone@else.com",), files={"package.json": "{}", "AGENTS.md": "# Theirs\n"})
        commit_all(origin, email="someone@else.com")
        dest = self.docs / "cloned"
        subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True, env=git_env())
        for _ in range(60):
            if (dest / ".harness" / "AGENTS.md").exists():
                break
            time.sleep(0.25)
        self.assertTrue((dest / ".harness" / "AGENTS.md").exists(), "the clone trigger set the project up locally")
        self.assertEqual(self.status(dest), "")
        self.assertEqual((dest / "AGENTS.md").read_text(), "# Theirs\n")
        self.assertFalse((dest / ".fieldbook").exists())


class DoctorAndCli(Installed):
    def test_doctor_passes_after_install_and_reports_drift_and_missing_hooks(self):
        self.install()
        proj = make(self.docs / "app", {"package.json": "{}"})
        self.harness("auto", "--trigger", "cd", "--cwd", str(proj))
        r = self.harness("doctor", str(proj))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("installed copy matches", r.stdout)
        self.assertIn("generated block (full mode)", r.stdout)
        self.assertNotIn("OVER", r.stdout)
        with open(self.shared / "current" / "shell" / "harness.zsh", "a") as fh:
            fh.write("# drift\n")
        self.assertIn("DIFF", self.harness("doctor", str(proj)).stdout)
        self.install()
        cfg = self.settings()
        cfg["hooks"]["SessionStart"] = []
        cfg["note"] = "session-start.py is mentioned here but not registered"
        self.write_json(self.home / ".claude" / "settings.json", cfg)
        r = self.harness("doctor", str(proj))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISS Claude Code hook session-start.py", r.stdout)

    def test_doctor_counts_local_mode_and_flags_oversized_project_files(self):
        self.install()
        team = git_init(self.docs / "team", authors=(ME, "b@x.com"), files={"package.json": "{}", "CLAUDE.md": "x " * 4000})
        commit_all(team)
        self.harness("auto", "--trigger", "cd", "--cwd", str(team))
        r = self.harness("doctor", str(team))
        self.assertIn("generated block (local mode)", r.stdout)
        self.assertIn("OVER project files", r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_doctor_ignores_hostile_project_files(self):
        self.install()
        proj = make(self.docs / "evil", {"package.json": "{}"})
        os.symlink("/dev/zero", proj / "AGENTS.md")
        (proj / "CLAUDE.md").write_text("@/etc/passwd\n@../../.zshrc\n")
        r = self.harness("doctor", str(proj))
        self.assertIn("project files (evil)", r.stdout)

    def test_cli_status_init_remove_plan(self):
        self.install()
        proj = make(self.docs / "cli", {"package.json": json.dumps({"scripts": {"test": "jest"}})})
        out = self.harness("status", str(proj)).stdout
        self.assertIn("not set up yet", out)
        self.assertIn("full (no git yet)", out)
        self.assertIn("command   test: npm run test", out)
        self.assertIn("setup:", self.harness("init", str(proj)).stdout)
        self.assertIn("state     set up", self.harness("status", str(proj)).stdout)
        self.assertIn("done     .harness-skip written", self.harness("remove", str(proj)).stdout)
        self.assertFalse((proj / "AGENTS.md").exists())
        self.assertIn("excluded  yes", self.harness("status", str(proj)).stdout)
        self.assertIn("setup:", self.harness("init", str(proj)).stdout)
        self.assertTrue((proj / "AGENTS.md").exists())
        self.assertEqual(self.harness("status", str(self.home)).stdout.strip(), "no project here: home")
        self.assertEqual(self.harness("init", str(self.docs)).returncode, 3)
        plan = json.loads(self.harness("plan", "--task", "fix the failing tests", str(proj)).stdout)
        self.assertIn("testing-guide", [i["name"] for i in plan["selected"]["skills"]])
        r = self.harness("nonsense")
        self.assertEqual(r.returncode, 3)
        self.assertIn("unknown command 'nonsense'", r.stderr)
        self.assertIn("nothing to change yet", self.harness("learn").stdout)
        self.assertEqual(json.loads(self.harness("eval").stdout), {})

    def test_cli_trust_and_untrust(self):
        self.install()
        repo = git_init(self.docs / "mine", files={"package.json": "{}"})
        commit_all(repo)
        self.harness("auto", "--trigger", "cd", "--cwd", str(repo))
        self.assertIn("local: nothing git tracks is touched", self.harness("status", str(repo)).stdout)
        self.assertEqual(self.status(repo), "")
        out = self.harness("trust", str(repo)).stdout
        self.assertIn("trusted: %s" % repo, out)
        self.assertIn("(full mode)", out)
        self.assertIn("full (trusted)", self.harness("status", str(repo)).stdout)
        self.assertTrue((repo / "AGENTS.md").exists())
        self.assertFalse((repo / "CLAUDE.local.md").exists())
        self.assertIn("already trusted", self.harness("trust", str(repo)).stdout)
        out = self.harness("untrust", str(repo)).stdout
        self.assertIn("no longer trusted", out)
        self.assertIn("(local mode)", out)
        self.assertFalse((repo / "AGENTS.md").exists())
        self.assertIn("already not trusted", self.harness("untrust", str(repo)).stdout)
        plain = make(self.docs / "plainp", {"package.json": "{}"})
        self.assertIn("nothing to trust", self.harness("trust", str(plain)).stdout)
        self.assertFalse((self.shared / "trusted").read_text().count(str(plain)))
        self.assertEqual(self.harness("trust", str(self.docs)).returncode, 3)

    def test_cli_resolves_relative_folders_before_leaving_them(self):
        self.install()
        proj = make(self.docs / "rel", {"package.json": "{}"})
        make(proj / "src")
        self.harness("auto", "--trigger", "cd", "--cwd", ".", cwd=proj / "src")
        self.assertTrue((proj / "AGENTS.md").exists())
        self.assertIn("project   %s" % proj, self.harness("status", cwd=proj / "src").stdout)
        self.assertIn("project   %s" % proj, self.harness("status", "src", cwd=proj).stdout)
        plan = json.loads(self.harness("plan", "--task", "fix the failing tests", cwd=proj / "src").stdout)
        self.assertIn("nodejs", plan["project_tags"], "the plan is for the project, not the subfolder")

    def test_zsh_cd_trigger(self):
        self.install()
        proj = make(self.docs / "zapp", {"package.json": "{}"})
        subprocess.run(["zsh", "-ic", "cd %s" % proj], capture_output=True, text=True, env=dict(os.environ), timeout=30)
        end = time.time() + 30                    # the trigger runs in the background; wait for it
        while time.time() < end and not (proj / "AGENTS.md").exists():
            time.sleep(0.2)
        self.assertTrue((proj / "AGENTS.md").exists())


class SelfUpdate(Installed):
    def test_update_allowed_only_forward_on_the_installed_branch_with_a_clean_tree(self):
        from engine import doctor
        src = git_init(self.tmp / "src", files={"install.sh": "#!/bin/sh\n"})
        commit_all(src)
        first = git(src, "rev-parse", "HEAD").stdout.strip()
        branch = git(src, "symbolic-ref", "--short", "HEAD").stdout.strip()
        (self.shared / "installed-commit").write_text(first + "\n")
        (self.shared / "installed-branch").write_text(branch + "\n")
        self.assertFalse(doctor.update_allowed(src), "nothing new")
        (src / "a.txt").write_text("a")
        self.assertFalse(doctor.update_allowed(src), "dirty tree")
        commit_all(src)
        self.assertTrue(doctor.update_allowed(src))
        (src / "b.txt").write_text("b")
        self.assertFalse(doctor.update_allowed(src), "a newer commit, but the tree is dirty")
        commit_all(src)
        git(src, "checkout", "-q", "-b", "other")
        self.assertFalse(doctor.update_allowed(src), "another branch")
        git(src, "checkout", "-q", branch)
        (self.shared / "installed-commit").write_text("uncommitted\n")
        self.assertFalse(doctor.update_allowed(src), "installed from a dirty tree")
        (self.shared / "installed-commit").write_text(git(src, "rev-parse", "HEAD").stdout)
        git(src, "reset", "-q", "--hard", first)
        self.assertFalse(doctor.update_allowed(src), "an older commit")

    def test_commits_that_arrive_from_elsewhere_are_never_installed_automatically(self):
        from engine import doctor
        src = git_init(self.tmp / "src2", files={"install.sh": "#!/bin/sh\n"})
        commit_all(src)
        branch = git(src, "symbolic-ref", "--short", "HEAD").stdout.strip()

        def installed_now():
            (self.shared / "installed-commit").write_text(git(src, "rev-parse", "HEAD").stdout)
            (self.shared / "installed-branch").write_text(branch + "\n")

        installed_now()
        (src / "a.txt").write_text("a")
        commit_all(src)
        (src / "b.txt").write_text("b")
        commit_all(src)
        self.assertTrue(doctor.update_allowed(src), "two local commits")
        installed_now()

        remote = self.tmp / "remote"
        subprocess.run(["git", "clone", "-q", str(src), str(remote)], check=True, env=git_env())
        (remote / "theirs.txt").write_text("x")
        commit_all(remote, email="someone@else.com")
        git(src, "pull", "-q", str(remote), branch)
        self.assertEqual(git(src, "status", "--porcelain").stdout, "")
        self.assertFalse(doctor.update_allowed(src), "a pulled commit")
        (src / "c.txt").write_text("c")
        commit_all(src)
        self.assertFalse(doctor.update_allowed(src), "a local commit on top of a pulled one still carries it")
        installed_now()                                    # the user ran ./install.sh
        (src / "d.txt").write_text("d")
        commit_all(src)
        self.assertTrue(doctor.update_allowed(src), "local work after a deliberate install")
        installed_now()

        git(src, "checkout", "-q", "-b", "side")
        (src / "s.txt").write_text("s")
        commit_all(src)
        git(src, "checkout", "-q", branch)
        git(src, "merge", "-q", "--ff-only", "side")
        self.assertFalse(doctor.update_allowed(src), "a merge, even of your own branch")
        installed_now()
        git(src, "commit", "-q", "--amend", "-m", "reworded", "--allow-empty")
        self.assertFalse(doctor.update_allowed(src), "an amended commit does not descend from the installed one")
        os.remove(src / ".git" / "logs" / "HEAD")
        (src / "e.txt").write_text("e")
        commit_all(src)
        self.assertFalse(doctor.update_allowed(src), "no record of how HEAD got here")
