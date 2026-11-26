"""Round 19: scanner behaviours that had no test of their own. Each case is one the scanner must
judge by the rule named in its test, so a change to that rule changes the result."""
import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

SCANNER = ROOT / "bin" / "content-hygiene"
_loader = importlib.machinery.SourceFileLoader("content_hygiene_under_test", str(SCANNER))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
ch = importlib.util.module_from_spec(_spec)
_loader.exec_module(ch)

ADMIN = "adm" + chr(0x131) + "n"
WORKFLOW = "x/.github/workflows/ci.yml"


def rows(text, name):
    found = ch.scan(text, name)[0]
    return len([f for f in found if f.sev == ch.HARD]), len([f for f in found if f.sev == ch.SOFT])


class CiShell(unittest.TestCase):
    def test_backtick_substitution_ends_and_its_command_word_is_exact(self):
        root = tempfile.TemporaryDirectory(prefix="gaps-")
        self.addCleanup(root.cleanup)
        d = Path(root.name).resolve() / ".github" / "workflows"
        d.mkdir(parents=True)
        for body, status in (("run: echo `x`\n", 0), ("run: echo `%s`\n" % ADMIN, 1)):
            f = d / "ci.yml"
            f.write_text(body, encoding="utf-8")
            try:
                r = subprocess.run([sys.executable, str(SCANNER), "--quiet", str(f)], capture_output=True, timeout=10)
            except subprocess.TimeoutExpired:
                self.fail("the scanner hung on %r" % body)
            self.assertEqual(r.returncode, status, r.stdout)

    def test_word_after_a_prefix_command_is_exact(self):
        for script in ("sudo %s -v", "exec %s", "if %s; then ls; fi", "if true; then %s; fi", "for i in 1; do %s; done"):
            with self.subTest(script=script):
                self.assertEqual(rows("run: " + script % ADMIN + "\n", WORKFLOW), (1, 0))

    def test_argument_after_a_prefix_command_is_text(self):
        self.assertEqual(rows("run: sudo ls %s\n" % ADMIN, WORKFLOW), (0, 1))


class CiKeys(unittest.TestCase):
    def test_env_group_and_template_values_are_exact(self):
        for key in ("group", "template"):
            for parent in ("env", "variables"):
                with self.subTest(key=key, parent=parent):
                    self.assertEqual(rows("%s:\n  %s: %s\n" % (parent, key, ADMIN), WORKFLOW), (1, 0))

    def test_other_env_values_are_text(self):
        self.assertEqual(rows("env:\n  other: %s\n" % ADMIN, WORKFLOW), (0, 1))

    def test_context_value_is_text(self):
        self.assertEqual(rows("context: %s\n" % ADMIN, WORKFLOW), (0, 1))


class JsonKeys(unittest.TestCase):
    def test_author_at_the_top_is_text_and_inside_dependencies_a_package(self):
        self.assertEqual(rows('{"author": "%s"}\n' % ADMIN, "package.json"), (0, 1))
        self.assertEqual(rows('{"dependencies": {"author": "%s"}}\n' % ADMIN, "package.json"), (1, 0))

    def test_homepage_is_text_only_at_the_top(self):
        self.assertEqual(rows('{"homepage": "%s"}\n' % ADMIN, "package.json"), (0, 1))
        self.assertEqual(rows('{"dependencies": {"homepage": "%s"}}\n' % ADMIN, "package.json"), (1, 0))
        self.assertEqual(rows('{"config": {"homepage": "%s"}}\n' % ADMIN, "package.json"), (1, 0))


class JsRegexAfterHead(unittest.TestCase):
    def test_slash_after_the_head_of_if_while_for_with_starts_a_regex(self):
        # Read as a division, the backtick would open a template string that hides the next line.
        for head in ("if (s)", "while (s)", "for (;;)", "with (s)"):
            with self.subTest(head=head):
                self.assertEqual(rows("%s /`/.test(s);\n%s();\nconst t = `x`;\n" % (head, ADMIN), "x.js"), (1, 0))


class Decoding(unittest.TestCase):
    def test_cookie_on_line_three_is_ignored(self):
        text = ch.decode(b"a = 1\nb = 2\n# coding: cp1251\nx = '\xcf\xf0'\n", "x.py")[0]
        self.assertEqual(text, "a = 1\nb = 2\n# coding: cp1251\nx = '" + chr(0xFFFD) * 2 + "'\n")

    def test_cookie_on_line_two_is_read(self):
        text = ch.decode(b"#!/usr/bin/python\n# coding: cp1251\nx = '\xcf\xf0'\n", "x.py")[0]
        self.assertEqual(text, "#!/usr/bin/python\n# coding: cp1251\nx = '" + chr(0x41F) + chr(0x440) + "'\n")

    def test_coding_comment_in_a_js_file_declares_nothing(self):
        text = ch.decode(b"# coding: cp1251\nx = '\xcf\xf0';\n", "x.js")[0]
        self.assertEqual(text, "# coding: cp1251\nx = '" + chr(0xFFFD) * 2 + "';\n")

    def test_multibyte_legacy_text_beside_a_hidden_character_decodes_whole(self):
        for codec, word in (("shift_jis", chr(0x65E5) + chr(0x672C) + chr(0x8A9E)), ("gbk", chr(0x4E2D) + chr(0x6587) + chr(0x5B57))):
            with self.subTest(codec=codec):
                raw = ("# coding: %s\nX = '" % codec).encode("ascii") + word.encode(codec) + b"'  # " + chr(0x200B).encode("utf-8") + b"\n"
                text = ch.decode(raw, "x.py")[0]
                self.assertEqual(text, "# coding: %s\nX = '%s'  # %s\n" % (codec, word, chr(0x200B)))
                self.assertEqual([f.sev for f in ch.scan(text, "x.py")[0]], [ch.HARD])

    def test_multibyte_legacy_text_alone_passes(self):
        for codec, word in (("shift_jis", chr(0x65E5) + chr(0x672C) + chr(0x8A9E)), ("gbk", chr(0x4E2D) + chr(0x6587) + chr(0x5B57))):
            with self.subTest(codec=codec):
                raw = ("# coding: %s\nX = '" % codec).encode("ascii") + word.encode(codec) + b"'\n"
                text = ch.decode(raw, "x.py")[0]
                self.assertEqual(text, "# coding: %s\nX = '%s'\n" % (codec, word))
                self.assertEqual(ch.scan(text, "x.py")[0], [])


class NoCapCli(unittest.TestCase):
    def run_cli(self, *args):
        root = tempfile.TemporaryDirectory(prefix="gaps-")
        self.addCleanup(root.cleanup)
        f = Path(root.name) / "many.py"
        f.write_text("".join("b%s\n" % chr(0x200B) for _ in range(300)), encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCANNER), "--quiet", *args, str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stderr)
        return len(r.stdout.splitlines())

    def test_no_cap_prints_every_finding(self):
        self.assertEqual(self.run_cli("--no-cap"), 300)

    def test_default_is_capped(self):
        self.assertEqual(self.run_cli(), ch.MAX_FINDINGS + 1)

    def test_no_cap_with_lines_prints_every_finding_in_them(self):
        self.assertEqual(self.run_cli("--no-cap", "--lines", "1-300"), 300)

    def test_lines_alone_is_capped(self):
        self.assertEqual(self.run_cli("--lines", "1-300"), ch.MAX_FINDINGS + 1)


if __name__ == "__main__":
    unittest.main()
