"""Round 21 scanner and write-guard regressions that need exact findings."""
import os
import subprocess
import sys
import time
import unittest

from helpers import ROOT, make
from test_round18_guard import Guard

SCANNER = ROOT / "bin" / "content-hygiene"
SOFT_HYPHEN = chr(0x00AD)
ZWSP = chr(0x200B)


class ScannerGaps(unittest.TestCase):
    def scan(self, text, name):
        return subprocess.run([sys.executable, str(SCANNER), "--stdin", "--name", name, "--quiet"],
                              input=text, capture_output=True, text=True)

    def assert_finding(self, text, name, where, rule):
        result = self.scan(text, name)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        fields = result.stdout.splitlines()[0].split()
        self.assertEqual(fields[:3], ["HARD", "%s:%s" % (name, where), rule], result.stdout)

    def test_halfwidth_idn_dot_splits_labels_before_host_judgment(self):
        text = "p%spaypal%scom\n" % (chr(0x0430), chr(0xFF61))
        self.assert_finding(text, "x.txt", "1:1", "homoglyph")

    def test_gnumakefile_uses_make_recipe_mode(self):
        text = "all:\n\t@echo %s.com\n" % "".join(chr(c) for c in (0x0430, 0x0440, 0x0440, 0x04CF, 0x0435))
        result = self.scan(text, "GNUmakefile")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("GNUmakefile:2:8", result.stdout)
        self.assertIn("(in a host name)", result.stdout)

    def test_optional_catch_block_keeps_following_regex_out_of_a_string(self):
        text = "try { s.x() } catch { }\n/[%s]/.test(s) && console.log(\"a%sb\");\n" % (chr(0x0430), SOFT_HYPHEN)
        self.assert_finding(text, "x.js", "2:32", "invisible-char")

    def test_strict_script_yield_starts_a_regex(self):
        text = "\"use strict\";\nyield /[%s]/.test(s) && console.log(\"a%sb\");\n" % (chr(0x0430), SOFT_HYPHEN)
        self.assert_finding(text, "x.js", "2:38", "invisible-char")

    def test_mjs_is_a_module_without_import_or_export(self):
        text = "yield /[%s]/.test(s) && console.log(\"a%sb\");\n" % (chr(0x0430), SOFT_HYPHEN)
        self.assert_finding(text, "x.mjs", "1:38", "invisible-char")


class GuardGaps(Guard):
    def test_utf16_be_file_is_placed_and_scanned(self):
        path = make(self.docs / "be") / "x.py"
        before = "x = 1\n\"\"\"\nif x:%sy = 2\n\"\"\"\n" % chr(0x00A0)
        with open(str(path), "wb") as fh:
            fh.write(b"\xfe\xff" + before.encode("utf-16-be"))
        result = self.guard({"file_path": str(path), "old_string": "x = 1\n\"\"\"\n",
                             "new_string": "x = 1\n"})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("x.py:2:6", result.stderr)

    def test_refused_later_creation_edit_still_scans_first_text(self):
        path = make(self.docs / "refused") / "new.py"
        result = self.guard({"file_path": str(path), "edits": [
            {"old_string": "", "new_string": "x = \"%s\"\n" % ZWSP},
            {"old_string": "missing", "new_string": "x = 2\n"}]})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ZERO WIDTH SPACE", result.stderr)

    def test_refused_later_creation_edit_scans_its_own_new_text(self):
        path = make(self.docs / "refused-later") / "new.py"
        result = self.guard({"file_path": str(path), "edits": [
            {"old_string": "", "new_string": "x = 1\n"},
            {"old_string": "missing", "new_string": "y = \"%s\"\n" % ZWSP}]})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ZERO WIDTH SPACE", result.stderr)

    def test_symlink_is_typed_by_its_target(self):
        target = make(self.docs / "links") / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        link = target.with_name("notes.md")
        os.symlink(target, link)
        result = self.guard({"file_path": str(link), "content": "x = %sbad%s\n" %
                             (chr(0x201C), chr(0x201D))})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("target.py:1:5 non-ascii-punct", result.stderr)

    def scanner(self, delay):
        script = self.tmp / ("scanner-%s" % delay)
        script.write_text("#!/usr/bin/env python3\nimport sys, time\n"
                          "if '--help' not in sys.argv:\n    time.sleep(%r)\n" % delay,
                          encoding="utf-8")
        script.chmod(0o755)
        return script

    def test_normal_creation_keeps_enough_scan_budget(self):
        text = "x = 1\n" * 50000
        result = self.guard({"file_path": str(self.docs / "normal.py"), "edits": [
            {"old_string": "", "new_string": text}]}, scanner=self.scanner(2))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_slow_scanner_blocks_as_not_checked(self):
        started = time.monotonic()
        result = self.guard({"file_path": str(self.docs / "slow.py"), "edits": [
            {"old_string": "", "new_string": "x = 1\n"}]}, scanner=self.scanner(30))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not-checked", result.stderr)
        self.assertLess(time.monotonic() - started, 13)


if __name__ == "__main__":
    unittest.main()
