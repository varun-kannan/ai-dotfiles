"""Round 20: the write guard builds a new file inside the child it can stop, reads a file the way
Claude Code does (UTF-16 by its byte order mark, invalid UTF-8 replaced, CRLF matched as LF),
blocks an edit to a file too large to place unless it only adds text, scans the new text of an
edit Claude Code refuses instead of letting it pass, reads columns back from the first CR in a
shell file with lone CRs, and exempts the tooling by name only where it is installed."""
import time
import unittest

from helpers import make
from test_round18_guard import Guard

ZWSP, NBSP = chr(0x200B), chr(0x00A0)
LQ, RQ = chr(0x201C), chr(0x201D)

DOCSTRING = "x = 1\n\"\"\"\nif x:%sy = 2\n\"\"\"\n" % NBSP
EXPOSE = {"old_string": "x = 1\n\"\"\"\n", "new_string": "x = 1\n"}


class CreationInTime(Guard):
    def test_slow_creating_multi_edit_blocks_well_inside_the_hook_limit(self):
        f = make(self.docs / "slow") / "new.py"
        made = "x = '%s'\n" % ZWSP + "a" * 1000000 + "ba\n"
        t = time.monotonic()
        r = self.guard({"file_path": str(f), "edits": [{"old_string": "", "new_string": made},
                                                       {"old_string": "a" * 50000 + "ba", "new_string": "a"}]})
        took = time.monotonic() - t
        self.assertEqual(r.returncode, 2, r.stderr[-1000:])
        self.assertLess(took, 11, "decided in %.1f s" % took)


class ReadLikeClaudeCode(Guard):
    def fixture(self, name, raw):
        f = make(self.docs / name) / ("%s.py" % name)
        with open(str(f), "wb") as fh:
            fh.write(raw)
        return f

    def kinds(self):
        return {"utf16": b"\xff\xfe" + DOCSTRING.encode("utf-16-le"),
                "badbyte": DOCSTRING.encode("utf-8") + b"# caf\xe9\n",
                "large": DOCSTRING.encode("utf-8") + b"# padding line for size\n" * 90000}

    def test_deletion_exposing_hidden_text_is_judged_in_every_kind_of_file(self):
        for name, raw in self.kinds().items():
            r = self.guard(dict(EXPOSE, file_path=str(self.fixture(name, raw))))
            self.assertEqual(r.returncode, 2, "%s: %s" % (name, r.stderr[-1000:]))

    def test_clean_edit_passes_in_every_kind_of_file(self):
        for name, raw in self.kinds().items():
            r = self.guard({"file_path": str(self.fixture(name + "ok", raw)),
                            "old_string": "x = 1\n", "new_string": "x = 1\nz = 3\n"})
            self.assertEqual(r.returncode, 0, "%s: %s" % (name, r.stderr[-1000:]))

    def test_large_file_edit_that_replaces_text_is_not_checked(self):
        f = self.fixture("large2", self.kinds()["large"])
        r = self.guard({"file_path": str(f), "old_string": "y = 2", "new_string": "y = 3"})
        self.assertEqual(r.returncode, 2, r.stderr[-1000:])
        self.assertIn("not-checked", r.stderr)


class CrlfMatchedAsLf(Guard):
    def crlf(self, name, text):
        return self.write_raw(make(self.docs / name) / ("%s.py" % name), text)

    def test_multi_edit_with_a_folded_match_in_a_crlf_file_is_judged(self):
        f = self.crlf("c3", "# say %shi%s\r\nx = 1\r\ny = 2\r\n" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": "# say \"hi\"\nx = 1", "new_string": "# say \"hi\"\nx = 3"},
            {"old_string": "y = 2", "new_string": "y = 2  # %s" % ZWSP}]})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_quote_style_is_carried_into_the_new_text_of_a_crlf_file(self):
        f = self.crlf("c4", "# say %shi%s\r\nx = 1\r\n" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "old_string": "# say \"hi\"\nx = 1",
                        "new_string": "# say \"hi\"\nx = print(\"yo\")"})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("c4.py:2:", r.stderr)

    def test_plain_edit_to_a_crlf_file_passes(self):
        f = self.crlf("c5", "a = 1\r\nb = 2\r\n")
        r = self.guard({"file_path": str(f), "old_string": "a = 1\nb = 2", "new_string": "a = 1\nb = 3"})
        self.assertEqual(r.returncode, 0, r.stderr)


class RefusedEditIsScanned(Guard):
    def test_refused_multi_edit_has_its_new_text_scanned(self):
        f = self.write_raw(make(self.docs / "nf") / "a.py", "a = 1\na = 1\n")
        for bad in ({"old_string": "MISSING", "new_string": "ok"}, {"old_string": "a = 1", "new_string": "a = 2"}):
            r = self.guard({"file_path": str(f), "edits": [bad, {"old_string": "b", "new_string": "b = \"%s\"" % ZWSP}]})
            self.assertEqual(r.returncode, 2, "%r: %s" % (bad, r.stderr))

    def test_refused_clean_multi_edit_passes(self):
        f = self.write_raw(make(self.docs / "nfc") / "a.py", "a = 1\n")
        r = self.guard({"file_path": str(f), "edits": [{"old_string": "MISSING", "new_string": "b = 2"}]})
        self.assertEqual(r.returncode, 0, r.stderr)


class LoneCrColumn(Guard):
    def test_edit_on_the_first_line_is_not_charged_with_the_first_cr(self):
        f = self.write_raw(make(self.docs / "cr6") / "cr6.sh", "echo a\recho %sx%s\recho b\r" % (LQ, RQ))
        r = self.guard({"file_path": str(f), "old_string": "echo a", "new_string": "echo aaaa"})
        self.assertEqual(r.returncode, 0, r.stderr)


class ToolingExemption(Guard):
    def test_tooling_names_are_exempt_only_where_installed(self):
        dirty = "a = 1%s\n" % ZWSP
        home = self.tmp / "home"
        proj = make(self.docs / "proj" / "real")
        for name in ("post-write-audit.sh", "pre-write-guard.sh", "content-hygiene"):
            r = self.guard({"file_path": str(proj / name), "content": dirty})
            self.assertEqual(r.returncode, 2, "%s: %s" % (name, r.stderr))
        hooks = make(home / ".claude" / "hooks")
        tools = make(home / ".ai-rules" / "bin")
        for f in (hooks / "post-write-audit.sh", hooks / "pre-write-guard.sh", tools / "content-hygiene"):
            r = self.guard({"file_path": str(f), "content": dirty})
            self.assertEqual(r.returncode, 0, "%s: %s" % (f, r.stderr))


if __name__ == "__main__":
    unittest.main()
