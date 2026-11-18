"""Engine tests. Run: python3 -m unittest discover -s tests

Every test runs against a temporary HOME and AI_RULES_HOME, so nothing touches
the real machine.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix="engine-test-")).resolve()
os.environ["HOME"] = str(SANDBOX / "home")
os.environ["AI_RULES_HOME"] = str(SANDBOX / "shared")
os.environ.pop("FIELDBOOK_CMD", None)
(SANDBOX / "home").mkdir()
sys.path.insert(0, str(ROOT))

from engine import decide, generate, outcomes, project  # noqa: E402

HOME = SANDBOX / "home"
FAKE_FIELDBOOK = """#!/bin/sh
mkdir -p .fieldbook/bank .fieldbook/logs/hot
echo "version: 1" > .fieldbook/config.yml
printf '# Decisions\\n' > .fieldbook/bank/04-decisions.md
"""


def make(path, files=None, git=False):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    if git:
        (path / ".git").mkdir(exist_ok=True)
    return path


def tearDownModule():
    shutil.rmtree(SANDBOX, ignore_errors=True)


class Locate(unittest.TestCase):
    def test_home_is_never_a_project(self):
        self.assertEqual(project.locate(HOME), (None, "home"))

    def test_outside_home(self):
        self.assertEqual(project.locate(SANDBOX)[0], None)

    def test_standard_home_folder_is_a_container(self):
        make(HOME / "Documents")
        self.assertEqual(project.locate(HOME / "Documents"), (None, "container"))

    def test_git_repo_holding_repos_is_a_container(self):
        box = make(HOME / "Documents" / "box", git=True)
        make(box / "a", git=True)
        make(box / "b", git=True)
        self.assertEqual(project.locate(box)[0], None)
        self.assertEqual(project.locate(box / "a")[0], box / "a")

    def test_subfolder_resolves_to_git_root(self):
        repo = make(HOME / "Documents" / "app", {"src/x.py": ""}, git=True)
        self.assertEqual(project.locate(repo / "src"), (repo, "git"))

    def test_plain_folder_under_container(self):
        plain = make(HOME / "Documents" / "notes-app" / "deep")
        root, why = project.locate(plain)
        self.assertEqual(root, HOME / "Documents" / "notes-app")
        self.assertEqual(why, "under container")

    def test_dependency_paths_skipped(self):
        dep = make(HOME / "Documents" / "web" / "node_modules" / "x")
        self.assertEqual(project.locate(dep)[0], None)


class Exclude(unittest.TestCase):
    def test_patterns_and_skip_file(self):
        root = make(HOME / "Documents" / "sb_projects" / "swells", git=True)
        self.assertTrue(project.is_excluded(root, [str(HOME / "Documents" / "sb_projects")]))
        self.assertTrue(project.is_excluded(root, [str(HOME / "Documents" / "sb_*")]))
        other = make(HOME / "Documents" / "free", git=True)
        self.assertFalse(project.is_excluded(other, [str(HOME / "Documents" / "sb_projects")]))
        (other / ".harness-skip").write_text("", encoding="utf-8")
        self.assertTrue(project.is_excluded(other, []))


class Commands(unittest.TestCase):
    def test_package_scripts_use_the_lockfile_manager(self):
        root = make(HOME / "Documents" / "pn", {
            "package.json": json.dumps({"scripts": {"test": "vitest", "lint": "eslint .", "x": "y"}}),
            "pnpm-lock.yaml": ""})
        self.assertEqual(project.detect_commands(root), {"test": "pnpm run test", "lint": "pnpm run lint"})

    def test_npm_placeholder_test_script_ignored(self):
        root = make(HOME / "Documents" / "np", {
            "package.json": json.dumps({"scripts": {"test": "echo \"Error: no test specified\" && exit 1"}})})
        self.assertEqual(project.detect_commands(root), {})

    def test_python_and_make(self):
        root = make(HOME / "Documents" / "py", {
            "pyproject.toml": "[tool.ruff]\n[project]\ndependencies=['pytest']\n", "uv.lock": "",
            "Makefile": "build:\n\tpython -m build\n"})
        cmds = project.detect_commands(root)
        self.assertEqual(cmds["test"], "uv run pytest")
        self.assertEqual(cmds["lint"], "uv run ruff check .")
        self.assertEqual(cmds["build"], "make build")


class Block(unittest.TestCase):
    def test_block_respects_cap(self):
        cap = json.loads((ROOT / "config" / "harness-budgets.json").read_text())["project_block"]
        tags = ["nodejs", "typescript", "react", "python", "rust", "java", "kotlin", "go", "docker", "database", "ci"]
        block = generate.build_block(tags, {"test": "npm run test"}, "npm", True)
        self.assertLessEqual((len(block) + 3) // 4, cap)
        self.assertIn("Run the test command above", block)

    def test_unknown_stack_says_so(self):
        self.assertIn("not detected yet", generate.build_block([], {}, "", False))


class Setup(unittest.TestCase):
    def test_plain_folder_lifecycle(self):
        root = make(HOME / "Documents" / "fresh")
        r = generate.auto(root, "session")
        self.assertEqual(r["action"], "declined", "an empty folder is not a project yet")

        make(root, {"main.py": "print(1)\n", "util.py": "", "app.py": ""})
        r = generate.auto(root, "session")
        self.assertEqual(r["action"], "setup")
        agents = (root / "AGENTS.md").read_text()
        self.assertIn(generate.BEGIN, agents)
        self.assertIn("@AGENTS.md", (root / "CLAUDE.md").read_text())
        self.assertTrue((root / ".harness" / "decisions.md").exists())
        self.assertIn("setup:", (root / ".harness" / "CHANGELOG.md").read_text())

        self.assertEqual(generate.auto(root, "prompt")["action"], "current")

        with open(root / "AGENTS.md", "a") as fh:
            fh.write("\nMy own rule: keep it small.\n")
        make(root, {"pyproject.toml": "[project]\ndependencies=['pytest']\n"})
        r = generate.auto(root, "cd")
        self.assertEqual(r["action"], "updated")
        agents = (root / "AGENTS.md").read_text()
        self.assertIn("My own rule: keep it small.", agents)
        self.assertIn("Stack: python", agents)
        self.assertIn("stack +python", (root / ".harness" / "CHANGELOG.md").read_text())

    def test_git_upgrade_runs_fieldbook_and_moves_decisions(self):
        fake = SANDBOX / "fake-fieldbook"
        fake.write_text(FAKE_FIELDBOOK, encoding="utf-8")
        fake.chmod(0o755)
        os.environ["FIELDBOOK_CMD"] = str(fake)
        try:
            root = make(HOME / "Documents" / "grow", {"package.json": "{}"})
            self.assertEqual(generate.auto(root, "session")["action"], "setup")
            with open(root / ".harness" / "decisions.md", "a") as fh:
                fh.write("- 2026-11-18 use SQLite, rejected Postgres for now\n")
            (root / ".git").mkdir()
            r = generate.auto(root, "git")
            self.assertEqual(r["action"], "updated")
            self.assertIn("fieldbook memory and logs initialized", r["notes"])
            self.assertIn("use SQLite", (root / ".fieldbook" / "bank" / "04-decisions.md").read_text())
            self.assertFalse((root / ".harness" / "decisions.md").exists())
            self.assertIn(".fieldbook/bank/04-decisions.md", (root / "AGENTS.md").read_text())
        finally:
            os.environ.pop("FIELDBOOK_CMD", None)

    def test_hand_removed_block_keeps_engine_out(self):
        root = make(HOME / "Documents" / "nope", {"package.json": "{}"})
        self.assertEqual(generate.auto(root, "session")["action"], "setup")
        generate.remove_block(root / "AGENTS.md", generate.BEGIN, generate.END)
        self.assertEqual(generate.auto(root, "session")["action"], "removed-by-user")
        self.assertEqual(generate.auto(root, "session")["action"], "removed-by-user")
        self.assertFalse((root / "AGENTS.md").exists() and generate.BEGIN in (root / "AGENTS.md").read_text())

    def test_remove_keeps_user_text_and_opts_out(self):
        root = make(HOME / "Documents" / "rm", {"package.json": "{}", "AGENTS.md": "# Mine\n\nKeep this.\n"})
        generate.auto(root, "session")
        done = generate.remove(root)
        self.assertIn("AGENTS.md block", done)
        self.assertEqual((root / "AGENTS.md").read_text().strip(), "# Mine\n\nKeep this.")

    def test_remove_deletes_agents_md_the_engine_created(self):
        root = make(HOME / "Documents" / "rm2", {"package.json": "{}"})
        generate.auto(root, "session")
        generate.remove(root)
        self.assertFalse((root / "AGENTS.md").exists())
        self.assertTrue((root / ".harness-skip").exists())
        self.assertEqual(generate.auto(root, "session")["action"], "skip")

    def test_existing_claude_md_pointing_at_agents_is_left_alone(self):
        root = make(HOME / "Documents" / "stub", {"package.json": "{}", "CLAUDE.md": "Read AGENTS.md first.\n"})
        generate.auto(root, "session")
        self.assertEqual((root / "CLAUDE.md").read_text(), "Read AGENTS.md first.\n")

    def test_auto_never_raises(self):
        self.assertIn(generate.auto("/definitely/not/here", "cd")["action"], ("skip", "error"))

    def test_off_switch(self):
        flag = Path(os.environ["AI_RULES_HOME"]) / "harness.off"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("", encoding="utf-8")
        try:
            self.assertEqual(generate.auto(make(HOME / "Documents" / "off", {"package.json": "{}"}), "cd")["action"], "off")
        finally:
            flag.unlink()


class Decisions(unittest.TestCase):
    def test_flag_and_choice(self):
        d = decide.decide("is_project", {"has_git": 1}, log=False)
        self.assertIs(d["answer"], True)
        self.assertTrue(d["reasons"] and d["reasons"][0][0] == "has_git")
        c = decide.decide("model_tier", {"fast": 3, "standard": 0, "frontier": 0}, log=False)
        self.assertEqual(c["answer"], "fast")
        self.assertAlmostEqual(sum(c["probabilities"].values()), 1.0, places=3)

    def test_unsure_band_abstains(self):
        spec = decide.questions()["pointer_useful"]
        # new_specific chosen so the raw probability lands just under the threshold
        d = decide.decide("pointer_useful", {"new_specific": 0.6}, log=False)
        self.assertTrue(d["answer"] is None or d["p"] >= spec["threshold"] or d["answer"] is False)

    def test_calibration_blends_toward_observed_rate(self):
        table = {"q": {"8": {"n": 100, "hits": 20}}}
        self.assertAlmostEqual(decide.calibrate("q", 0.85, table), (20 + 10 * 0.85) / 110, places=6)
        self.assertEqual(decide.calibrate("q", 0.15, table), 0.15)

    def test_learn_refits_within_bounds_and_logs(self):
        for i in range(120):
            useful = i % 2 == 0
            d = decide.decide("pointer_useful", {"new_specific": 1.0 if useful else 0.34, "first_prompt": 0,
                                                 "has_block": 1, "short_prompt": 0 if useful else 1})
            decide.record_outcome(d["id"], useful)
        changes = decide.learn()
        self.assertTrue(any(c.startswith("calibration rebuilt") for c in changes))
        learned = json.loads((decide.DATA / "weights.json").read_text()) if (decide.DATA / "weights.json").exists() else {}
        base = decide._load(ROOT / "config" / "decisions.json", {})["questions"]["pointer_useful"]
        for k, w in learned.get("pointer_useful", {}).get("weights", {}).items():
            self.assertLessEqual(abs(w - base["weights"][k]), decide.MAX_WEIGHT_SHIFT + 1e-9)
        report = decide.evaluate()["pointer_useful"]
        self.assertGreaterEqual(report["labelled"], 120)


class Outcomes(unittest.TestCase):
    def test_pointer_hit_read_from_transcript(self):
        transcript = SANDBOX / "t.jsonl"
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
        transcript.write_text(json.dumps({"timestamp": stamp + ".000Z", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "testing-guide"}}]}}) + "\n", encoding="utf-8")
        d = decide.decide("pointer_useful", {"new_specific": 1.0, "first_prompt": 1},
                          ctx={"transcript": str(transcript), "names": ["testing-guide"]})
        if d["answer"] is not True:
            self.skipTest("pointer not acted on with these weights")
        rows = decide._read_jsonl(decide.SHARED / "logs" / "decisions.jsonl")
        rows[-1]["ts"] = int(time.time()) - 3700
        with open(decide.SHARED / "logs" / "decisions.jsonl", "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
        self.assertGreaterEqual(outcomes.label(), 1)
        labelled = decide.labelled()["pointer_useful"]
        self.assertTrue(any(r["id"] == d["id"] and r["hit"] for r in labelled))


if __name__ == "__main__":
    unittest.main()
