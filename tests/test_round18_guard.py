"""Round 18: the write guard with an opt-out marker behind lone CRs, a multi-edit Claude Code would
refuse, a project-relative path, a lone surrogate, scans past the cap in one pass and a reorder
of a whole-file carrier."""
import json
import os
import subprocess
import sys
import time
import unittest

from helpers import ROOT, Sandbox, make

GUARD = ROOT / "agents" / "claude-code" / "hooks" / "pre-write-guard.sh"
SCANNER = ROOT / "bin" / "content-hygiene"
ZWSP = chr(0x200B)
LQ, RQ = chr(0x201C), chr(0x201D)

# A stand-in scanner: it logs its arguments, answers --help with or without --no-cap, and runs
# the real scanner (without its cap when --no-cap is given).
FAKE = """import os, sys
REAL = %r
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(" ".join(a for a in args if not a.startswith("--name")) + "\\n")
if "--help" in args:
    print("usage: content-hygiene [--lines LINES]" + (" [--no-cap]" if os.environ.get("FAKE_NO_CAP") else ""))
    sys.exit(0)
with open(REAL, encoding="utf-8") as fh:
    src = fh.read()
if "--no-cap" in args:
    args.remove("--no-cap")
    src = src.replace("MAX_FINDINGS = 200", "MAX_FINDINGS = 10 ** 9")
sys.argv = [REAL] + args
exec(compile(src, REAL, "exec"), {"__name__": "__main__", "__file__": REAL})
"""


class Guard(Sandbox):
    def guard(self, tool_input, cwd=None, hook_cwd=None, scanner=None, extra=None):
        home = make(self.tmp / "home")
        env = dict(os.environ, HOME=str(home), AI_RULES_HOME=str(home / ".ai-rules"),
                   CONTENT_HYGIENE_BIN=str(scanner or SCANNER), **(extra or {}))
        hook = {"tool_input": tool_input}
        if hook_cwd is not None:
            hook["cwd"] = hook_cwd
        return subprocess.run(["/bin/bash", str(GUARD)], input=json.dumps(hook), capture_output=True,
                              text=True, env=env, timeout=60, cwd=cwd)

    def write_raw(self, path, text):
        with open(str(path), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path


class CrOnlyMarker(Guard):
    def test_marker_pushed_past_line_30_by_lone_crs_is_judged(self):
        f = self.write_raw(make(self.docs / "crm") / "m.py", "# hygiene:ignore-file\rx=1\r")
        new = "pad\r" * 31 + "# hygiene:ignore-file\rx=\"%s\"\r" % ZWSP
        r = self.guard({"file_path": str(f), "old_string": "# hygiene:ignore-file\rx=1\r", "new_string": new})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_marker_kept_at_the_top_still_excuses(self):
        f = self.write_raw(make(self.docs / "crk") / "m.py", "# hygiene:ignore-file\rx=1\r")
        r = self.guard({"file_path": str(f), "old_string": "x=1", "new_string": "x=\"%s\"" % ZWSP})
        self.assertEqual(r.returncode, 0, r.stderr)


class RefusedMultiEdit(Guard):
    # Round 20: a refused multi-edit writes nothing, so its new text is scanned (it used to pass).
    def test_creating_multi_edit_with_an_unmatched_edit_is_still_scanned(self):
        d = make(self.docs / "mk")
        empty = self.write_raw(d / "e.py", "")
        for f in (empty, d / "new.py"):
            r = self.guard({"file_path": str(f), "edits": [{"old_string": "", "new_string": "x=\"%s\"\n" % ZWSP},
                                                           {"old_string": "MISSING", "new_string": "ok"}]})
            self.assertEqual(r.returncode, 2, r.stderr)

    def test_multi_edit_with_an_unmatched_or_ambiguous_edit_is_still_scanned(self):
        f = self.write_raw(make(self.docs / "me") / "a.py", "a = 1\nb = 2\ny = 1\ny = 1\n")
        dirty = {"old_string": "a = 1", "new_string": "a = \"%s\"" % ZWSP}
        for bad in ({"old_string": "MISSING", "new_string": "ok"}, {"old_string": "y = 1", "new_string": "y = 3"}):
            r = self.guard({"file_path": str(f), "edits": [dirty, bad]})
            self.assertEqual(r.returncode, 2, "%r: %s" % (bad, r.stderr))
        for good in ({"old_string": "b = 2", "new_string": "b = 3"},
                     {"old_string": "y = 1", "new_string": "y = 3", "replace_all": True}):
            r = self.guard({"file_path": str(f), "edits": [dirty, good]})
            self.assertEqual(r.returncode, 2, "%r: %s" % (good, r.stderr))

    def test_edit_claude_code_may_still_match_is_judged(self):
        f = self.write_raw(make(self.docs / "mq") / "a.py", "a = 1\ns = \"x\"\n")
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": "a = 1", "new_string": "a = \"%s\"" % ZWSP},
            {"old_string": "s = %sx%s" % (LQ, RQ), "new_string": "s = 2"}]})
        self.assertEqual(r.returncode, 2, r.stderr)


class RelativePath(Guard):
    def test_relative_path_through_a_symlinked_folder_is_judged_by_its_real_path(self):
        proj = make(self.docs / "proj")
        (proj / ".github" / "workflows").mkdir(parents=True)
        os.symlink(proj / ".github" / "workflows", proj / "wf")
        content = "run: n%sm ci\n" % chr(0x03C1)
        tool = {"file_path": "wf/ci.yml", "content": content}
        r = self.guard(tool, hook_cwd=str(proj))
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.guard(tool, cwd=str(proj))
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.guard({"file_path": "plain.yml", "content": content}, hook_cwd=str(proj))
        self.assertEqual(r.returncode, 0, r.stderr)


class LoneSurrogate(Guard):
    def test_lone_surrogate_reaches_the_scanner_as_utf8_replacement_character(self):
        # A recording scanner, so the bytes decide: a surrogate encoded as such (ED A0 80) would
        # not be UTF-8 and would send the real scanner to the legacy codec named in the cookie.
        seen = self.tmp / "stdin.bin"
        script = self.tmp / "record-hygiene"
        script.write_text("import sys\nif '--stdin' in sys.argv:\n    open(%r, 'wb').write(sys.stdin.buffer.read())\n"
                          % str(seen), encoding="utf-8")
        script.chmod(0o755)
        content = "# coding: cp1251\nx = 1\ny = 1  # %s\n" % chr(0xD800)
        r = self.guard({"file_path": str(self.docs / "s.py"), "content": content}, scanner=script)
        self.assertEqual(r.returncode, 0, r.stderr)
        raw = seen.read_bytes()
        self.assertEqual(raw.decode("utf-8"), "# coding: cp1251\nx = 1\ny = 1  # \ufffd\n")


class CarrierReorder(Guard):
    def pua(self):
        f = make(self.docs / "pua") / "pua.md"
        f.write_text("".join("Line %d %s here.\n" % (k, chr(0xE000 + k)) for k in range(30)), encoding="utf-8")
        return f

    def test_swapping_two_lines_is_judged(self):
        # Round 19: the order of the carrier characters is the message, so a swap is charged.
        f = self.pua()
        a, b = ("Line %d %s here.\n" % (k, chr(0xE000 + k)) for k in range(2))
        r = self.guard({"file_path": str(f), "old_string": a + b, "new_string": b + a})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_bringing_in_a_new_one_is_judged(self):
        f = self.pua()
        r = self.guard({"file_path": str(f), "old_string": "Line 0 %s" % chr(0xE000),
                        "new_string": "Line 0 %s" % chr(0xE100)})
        self.assertEqual(r.returncode, 2, r.stderr)


class OneScanPastTheCap(Guard):
    def fake(self, no_cap):
        script = self.tmp / "fake-hygiene"
        script.write_text(FAKE % str(SCANNER), encoding="utf-8")
        script.chmod(0o755)
        log = self.tmp / ("scan-%s.log" % no_cap)
        extra = {"FAKE_LOG": str(log)}
        if no_cap:
            extra["FAKE_NO_CAP"] = "1"
        return script, log, extra

    def capped(self, n):
        f = make(self.docs / ("cap%d" % n)) / "cap.py"
        f.write_text('# """\n' + "".join("b%d = 1  # x%sy\n" % (k, ZWSP) for k in range(n))
                     + '"""\ns = %spayload%s\n"""\n# """\n' % (LQ, RQ), encoding="utf-8")
        return f

    def test_tail_is_judged_with_and_without_no_cap(self):
        f = self.capped(300)
        for no_cap in (False, True):
            script, log, extra = self.fake(no_cap)
            r = self.guard({"file_path": str(f), "old_string": '# """\nb0 =', "new_string": '"""\nb0 ='},
                           scanner=script, extra=extra)
            self.assertEqual(r.returncode, 2, "no_cap=%s: %s" % (no_cap, r.stderr))
            scans = log.read_text(encoding="utf-8").splitlines()
            tails = [s for s in scans if "--lines" in s]
            self.assertTrue(tails, scans)
            self.assertEqual(all("--no-cap" in s for s in tails), no_cap, scans)
            if no_cap:
                self.assertLessEqual(len(tails), 2, "one tail scan, one scan of the old file: %s" % scans)

    def test_real_scanner_judges_an_edit_past_the_cap(self):
        f = make(self.docs / "realcap") / "cap.py"
        f.write_text("".join("b%d = 1  # x%sy\n" % (k, ZWSP) for k in range(300)) + "tail = 1\n", encoding="utf-8")
        r = self.guard({"file_path": str(f), "old_string": "tail = 1", "new_string": "tail = %sq%s" % (LQ, RQ)})
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.guard({"file_path": str(f), "old_string": "tail = 1", "new_string": "tail = 2"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_large_capped_file_edit_is_one_tail_scan(self):
        f = make(self.docs / "large") / "large.py"
        body = ["def compute():\n", "    return 1\n"]
        for k in range(10000):
            body.append("x_%d = %svalue%s\n" % (k, LQ, RQ) if k % 10 == 0
                        else "y_%d = some_function(argument_one, argument_two)\n" % k)
        f.write_text("".join(body), encoding="utf-8")
        script, log, extra = self.fake(True)
        started = time.monotonic()
        r = self.guard({"file_path": str(f), "old_string": "def compute():", "new_string": "def calc():"},
                       scanner=script, extra=extra)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        scans = log.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len([s for s in scans if "--lines" in s]), 2, scans)
        self.assertLess(time.monotonic() - started, 13)

    def test_no_tail_scan_when_nothing_is_capped(self):
        f = make(self.docs / "small") / "a.py"
        f.write_text("x = 1\ny = %sq%s\n" % (LQ, RQ), encoding="utf-8")
        script, log, extra = self.fake(True)
        r = self.guard({"file_path": str(f), "old_string": "x = 1", "new_string": "x = 2"}, scanner=script, extra=extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        scans = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(scans), 2, scans)
        self.assertFalse([s for s in scans if "--lines" in s or "--help" in s], scans)


if __name__ == "__main__":
    unittest.main()
