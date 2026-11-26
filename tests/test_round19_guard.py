"""Round 19: the write guard matches old_string the way Claude Code does (curly quotes folded,
escapes read, quote style carried into the new text, an empty old_string in a multi-edit), keeps
the opt-out marker only where the edit leaves it, judges whole-file carriers by their order and
when the scanner leaves the row out, scans a large file without the cap in one round, and reads
columns back in a shell file with lone CRs."""
import unittest

from helpers import make
from test_round18_guard import FAKE, SCANNER, Guard

ZWSP = chr(0x200B)
LQ, RQ = chr(0x201C), chr(0x201D)
SQ = chr(39)


class CreatingMultiEdit(Guard):
    def test_later_edit_matched_through_curly_quotes_is_applied_and_scanned(self):
        f = make(self.docs / "loose") / "t.md"
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": "", "new_string": "# Title\n\nShe said %shi%s today.\n" % (LQ, RQ)},
            {"old_string": "She said \"hi\" today.", "new_string": "She said hi%s today." % (ZWSP * 3)}]})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_later_empty_old_string_replaces_the_whole_text(self):
        f = make(self.docs / "empty") / "n1.py"
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": "", "new_string": "s = \"\"\"\n"},
            {"old_string": "", "new_string": "x = %sa%s\n" % (LQ, RQ)}]})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_edit_that_cannot_be_placed_still_has_its_new_text_scanned(self):
        f = make(self.docs / "markup") / "m.md"
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": "", "new_string": "# Notes\n"},
            {"old_string": "<missing>", "new_string": "text%s here" % ZWSP}]})
        self.assertEqual(r.returncode, 2, r.stderr)


class MatchedLikeClaudeCode(Guard):
    def test_escaped_old_string_writes_the_unescaped_new_text(self):
        f = self.write_raw(make(self.docs / "esc") / "a.py", "a = \"caf%s\"\nb = 1\n" % chr(0xE9))
        # Claude Code writes the escapes as characters: curly quotes that delimit a string.
        r = self.guard({"file_path": str(f), "old_string": "a = \"caf\\u00e9\"",
                        "new_string": "a = \\u201ccaf\\u00e9\\u201d"})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_folded_match_that_removes_the_marker_is_judged(self):
        f = self.write_raw(make(self.docs / "m4") / "m4.py", "# hygiene:ignore-file \"x\"\ny = 1\n")
        r = self.guard({"file_path": str(f), "old_string": "# hygiene:ignore-file %sx%s" % (LQ, RQ),
                        "new_string": "z = %s%s%s" % (SQ, ZWSP, SQ)})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_quote_style_of_the_file_is_carried_into_the_new_text(self):
        f = self.write_raw(make(self.docs / "r5") / "r5.py", "# the %sgreeting%s\nmsg = \"hello\"\n" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "old_string": "# the \"greeting\"\nmsg = \"hello\"",
                        "new_string": "# the \"greeting\"\nmsg = \"bye\""})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("r5.py:2:", r.stderr)

    def test_folded_match_is_judged_in_place(self):
        f = self.write_raw(make(self.docs / "ctx") / "c.py", "t = \"a\"\ns = \"\"\"\ny = %shi%s\n\"\"\"\n" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "old_string": "t = %sa%s\ns = \"\"\"" % (LQ, RQ), "new_string": "t = \"a\""})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_plain_folded_match_adding_nothing_passes(self):
        f = self.write_raw(make(self.docs / "ok") / "o.md", "She said %shi%s.\nEnd.\n" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "old_string": "She said \"hi\".", "new_string": "She said \"hello\"."})
        self.assertEqual(r.returncode, 0, r.stderr)


class MarkerWhenNotPlaced(Guard):
    def test_slow_placement_does_not_take_the_marker_exit(self):
        f = self.write_raw(make(self.docs / "slow") / "m1.txt", "a" * 1500000 + "\n# hygiene:ignore-file\naaaa\n")
        r = self.guard({"file_path": str(f), "old_string": "a" * 20000 + "\n# hygiene:ignore-file\naaaa",
                        "new_string": "a" * 20000 + "\nx = %sq%s%s\naaaa" % (SQ, ZWSP, SQ)})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_unmatched_edit_away_from_the_marker_keeps_it(self):
        f = self.write_raw(make(self.docs / "away") / "m.py", "# hygiene:ignore-file\nx = 1\n")
        r = self.guard({"file_path": str(f), "old_string": "MISSING", "new_string": "x = \"%s\"" % ZWSP})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unmatched_edit_over_the_marker_is_judged(self):
        f = self.write_raw(make(self.docs / "over") / "m.py", "# hygiene:ignore-file\nx = 1\n")
        r = self.guard({"file_path": str(f), "old_string": "# hygiene:ignore-file\nMISSING",
                        "new_string": "x = \"%s\"" % ZWSP})
        self.assertEqual(r.returncode, 2, r.stderr)


class WholeFileCarriers(Guard):
    def test_short_runs_added_beside_a_reported_run_are_counted(self):
        old = "# Notes\n\nIntro line.\n\nlegacy %s glyphs\n\nEnd.\n" % "".join(chr(0xE000 + k) for k in range(10))
        new = "".join("para %d text%s.\n" % (k, "".join(chr(0xE010 + j) for j in range(7))) for k in range(40)) + "End.\n"
        for ext in ("md", "txt"):
            f = self.write_raw(make(self.docs / ("pua" + ext)) / ("pua." + ext), old)
            r = self.guard({"file_path": str(f), "old_string": "End.\n", "new_string": new})
            self.assertEqual(r.returncode, 2, "%s: %s" % (ext, r.stderr))

    def test_short_runs_in_code_are_left_to_the_scanner(self):
        old = "x = 1  # legacy %s glyphs\n" % "".join(chr(0xE000 + k) for k in range(10))
        f = self.write_raw(make(self.docs / "puapy") / "pua.py", old + "y = 2\n")
        r = self.guard({"file_path": str(f), "old_string": "y = 2\n", "new_string": "y = 2  # %s\n" % chr(0xE020)})
        self.assertEqual(r.returncode, 0, r.stderr)

    def perm(self):
        f = make(self.docs / "perm") / "perm.md"
        self.write_raw(f, "".join("line %d %s here\n" % (k, chr(0xE000 + k)) for k in range(16)))
        return f

    def test_reassigning_carriers_to_other_lines_is_judged(self):
        f = self.perm()
        old = "".join("line %d %s here\n" % (k, chr(0xE000 + k)) for k in range(16))
        new = "".join("line %d %s here\n" % (k, chr(0xE000 + (k * 5) % 16)) for k in range(16))
        r = self.guard({"file_path": str(f), "old_string": old, "new_string": new})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_deleting_a_carrier_line_passes(self):
        f = self.perm()
        r = self.guard({"file_path": str(f), "old_string": "line 3 %s here\n" % chr(0xE003), "new_string": ""})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_emoji_presentation_selector_is_not_a_hidden_selector(self):
        han = "".join("word %s%s here\n" % (chr(0x5B57), chr(0xE0100)) for _ in range(16))
        f = self.write_raw(make(self.docs / "ivs") / "ivs.md", han + "end\n")
        r = self.guard({"file_path": str(f), "old_string": "end\n", "new_string": "end %s%s\n" % (chr(0x2764), chr(0xFE0F))})
        self.assertEqual(r.returncode, 0, r.stderr)


class NoCapFromTheStart(Guard):
    def fake(self, no_cap):
        script = self.tmp / "fake-hygiene"
        script.write_text(FAKE % str(SCANNER), encoding="utf-8")
        script.chmod(0o755)
        log = self.tmp / ("scan19-%s.log" % no_cap)
        extra = {"FAKE_LOG": str(log)}
        if no_cap:
            extra["FAKE_NO_CAP"] = "1"
        return script, log, extra

    def large(self):
        f = make(self.docs / "big") / "big.py"
        body = ['# """\n'] + ["b%d = 1  # x%sy some padding text to make it longer\n" % (k, ZWSP) for k in range(3000)]
        body += ['"""\n', "s = %spayload%s\n" % (LQ, RQ), '"""\n', '# """\n']
        self.write_raw(f, "".join(body))
        return f

    def test_large_file_is_one_scan_per_side_without_the_cap(self):
        f = self.large()
        script, log, extra = self.fake(True)
        r = self.guard({"file_path": str(f), "old_string": '# """\nb0 =', "new_string": '"""\nb0 ='},
                       scanner=script, extra=extra)
        self.assertEqual(r.returncode, 2, r.stderr[-2000:])
        self.assertIn("big.py:3003:", r.stderr)
        scans = [s for s in log.read_text(encoding="utf-8").splitlines() if "--help" not in s]
        self.assertEqual(len(scans), 2, scans)
        self.assertTrue(all("--no-cap" in s and "--lines" not in s for s in scans), scans)

    def test_large_file_falls_back_to_the_tail_scan_without_no_cap(self):
        f = self.large()
        script, log, extra = self.fake(False)
        r = self.guard({"file_path": str(f), "old_string": '# """\nb0 =', "new_string": '"""\nb0 ='},
                       scanner=script, extra=extra)
        self.assertEqual(r.returncode, 2, r.stderr[-2000:])
        scans = log.read_text(encoding="utf-8").splitlines()
        self.assertTrue([s for s in scans if "--lines" in s], scans)
        self.assertFalse([s for s in scans if "--no-cap" in s], scans)


class LoneCrShell(Guard):
    def fixture(self):
        return self.write_raw(make(self.docs / "c7") / "c7.sh", "echo a\recho %s%s%s\recho c\r" % (SQ, ZWSP, SQ))

    def test_edit_elsewhere_is_not_charged_with_old_findings(self):
        f = self.fixture()
        r = self.guard({"file_path": str(f), "old_string": "echo c", "new_string": "echo d"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_new_finding_past_the_first_cr_is_charged(self):
        f = self.fixture()
        r = self.guard({"file_path": str(f), "old_string": "echo c", "new_string": "echo %sc%s" % (SQ, ZWSP + SQ)})
        self.assertEqual(r.returncode, 2, r.stderr)


if __name__ == "__main__":
    unittest.main()
