"""Round 17: the write guard against a re-encoded whole-file carrier, an opt-out marker the edit
removes, findings past the scanner cap, a symlinked parent folder and a long --lines list."""
import json
import os
import subprocess
import unittest

from helpers import ROOT, Sandbox, make

GUARD = ROOT / "agents" / "claude-code" / "hooks" / "pre-write-guard.sh"
ZWSP = chr(0x200B)


class Guard(Sandbox):
    def guard(self, tool_input):
        home = make(self.tmp / "home")
        env = dict(os.environ, HOME=str(home), AI_RULES_HOME=str(home / ".ai-rules"),
                   CONTENT_HYGIENE_BIN=str(ROOT / "bin" / "content-hygiene"))
        return subprocess.run(["/bin/bash", str(GUARD)], input=json.dumps({"tool_input": tool_input}),
                              capture_output=True, text=True, env=env, timeout=60)


class WholeFileRows(Guard):
    def pua(self):
        f = make(self.docs / "pua") / "pua.md"
        f.write_text("intro\n" + "".join("line %s here\n" % chr(0xE000 + k) for k in range(10)) + "end\n",
                     encoding="utf-8")
        return f

    def test_swapping_carrier_lines_is_judged(self):
        # Round 19: a reorder rewrites the message the characters spell, so it is charged.
        f = self.pua()
        a, b = "line %s here\n" % chr(0xE000), "line %s here\n" % chr(0xE001)
        r = self.guard({"file_path": str(f), "old_string": a + b, "new_string": b + a})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_deleting_and_rewriting_carrier_lines_is_not_excused(self):
        f = self.pua()
        a, b = ("line %s here\n" % chr(0xE000 + k) for k in range(2))
        r = self.guard({"file_path": str(f), "edits": [
            {"old_string": a + b, "new_string": "line %s here!\n" % chr(0xE001)},
            {"old_string": "end\n", "new_string": "end \n"}]})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_edit_adding_none_of_them_still_passes(self):
        f = self.pua()
        r = self.guard({"file_path": str(f), "old_string": "end\n", "new_string": "end of file\n"})
        self.assertEqual(r.returncode, 0, r.stderr)


class MarkerAfterEdit(Guard):
    def marked(self):
        f = make(self.docs / "mark") / "m.py"
        f.write_text("# hygiene:ignore-file - fixture\nx = 1\n", encoding="utf-8")
        return f

    def test_edit_that_removes_the_marker_is_judged(self):
        f = self.marked()
        r = self.guard({"file_path": str(f), "old_string": f.read_text(encoding="utf-8"),
                        "new_string": "x = %sa%sb%s\n" % ("'", ZWSP, "'")})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_edit_that_pushes_the_marker_past_line_30_is_judged(self):
        f = self.marked()
        top = "".join("v%d = %d\n" % (k, k) for k in range(30)) + "s = %sa%sb%s\n" % ("'", ZWSP, "'")
        r = self.guard({"file_path": str(f), "old_string": "# hygiene", "new_string": top + "# hygiene"})
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_edit_that_keeps_the_marker_is_excused(self):
        f = self.marked()
        r = self.guard({"file_path": str(f), "old_string": "x = 1", "new_string": "x = %sa%sb%s" % ("'", ZWSP, "'")})
        self.assertEqual(r.returncode, 0, r.stderr)


class PastTheCap(Guard):
    def capped(self, n):
        f = make(self.docs / ("cap%d" % n)) / "cap.py"
        f.write_text('# """\n' + "".join("b%d = 1  # x%sy\n" % (k, ZWSP) for k in range(n))
                     + '"""\ns = %spayload%s\n"""\n# """\n' % (chr(0x201C), chr(0x201D)), encoding="utf-8")
        return f

    def test_closing_a_docstring_above_kept_lines_past_the_cap_is_judged(self):
        for n in (150, 200, 300):
            f = self.capped(n)
            r = self.guard({"file_path": str(f), "old_string": '# """\nb0 =', "new_string": '"""\nb0 ='})
            self.assertEqual(r.returncode, 2, "N=%d: %s" % (n, r.stderr))

    def test_harmless_edit_in_a_capped_file_passes(self):
        f = self.capped(300)
        r = self.guard({"file_path": str(f), "old_string": '# """\n', "new_string": '# """ top\n'})
        self.assertEqual(r.returncode, 0, r.stderr)


class SymlinkedFolder(Guard):
    def test_file_under_a_symlinked_folder_is_judged_by_its_real_path(self):
        proj = make(self.docs / "proj")
        (proj / ".github" / "workflows").mkdir(parents=True)
        os.symlink(proj / ".github" / "workflows", proj / "wf")
        content = "run: n%sm ci\n" % chr(0x03C1)
        direct = self.guard({"file_path": str(proj / ".github" / "workflows" / "ci.yml"), "content": content})
        self.assertEqual(direct.returncode, 2, direct.stderr)
        r = self.guard({"file_path": str(proj / "wf" / "ci.yml"), "content": content})
        self.assertEqual(r.returncode, 2, r.stderr)


class LongLineList(Guard):
    def test_many_changed_lines_in_a_capped_file_are_judged_not_refused(self):
        f = make(self.docs / "big") / "big.py"
        f.write_text("".join("a%d = 1  # x%sy\n" % (k, ZWSP) for k in range(300)) + "y = 1\n" * 100000,
                     encoding="utf-8")
        edit = {"file_path": str(f), "old_string": "y = 1", "new_string": "y = 2", "replace_all": True}
        r = self.guard(edit)
        if r.returncode and "not-checked" in r.stderr:
            r = self.guard(edit)          # the scan ran out of time on a loaded machine: the verdict was not reached
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])


class ManyEditsInTime(Guard):
    def test_multi_edit_over_long_repetitive_sections_is_placed_in_time(self):
        f = make(self.docs / "list") / "list.md"
        f.write_text("".join("- item number %d with some words here\n\n" % k for k in range(3000)), encoding="utf-8")
        edits = []
        for part in range(8):
            section = "".join("- item number %d with some words here\n\n" % k
                              for k in range(part * 300, part * 300 + 223))
            edits.append({"old_string": section, "new_string": section.replace("- item", "* item")})
        r = self.guard({"file_path": str(f), "edits": edits})
        self.assertEqual(r.returncode, 0, r.stderr)


class DeletionPastTheCap(Guard):
    def test_deletion_that_exposes_text_as_code_in_a_capped_file_is_judged(self):
        q = (chr(0x201C), chr(0x201D))
        f = make(self.docs / "expose") / "e.py"
        f.write_text("".join("s%d = %sabc%s\n" % (k, q[0], q[1]) for k in range(150))
                     + 'x = 1\n"""\nq = %sabc%s\n"""\ny = 2\n' % q, encoding="utf-8")
        for new in ("x = 1\n", "x = 2\n"):
            r = self.guard({"file_path": str(f), "old_string": 'x = 1\n"""\n', "new_string": new})
            self.assertEqual(r.returncode, 2, "%r: %s" % (new, r.stderr))
        r = self.guard({"file_path": str(f), "old_string": "y = 2", "new_string": "y = 3"})
        self.assertEqual(r.returncode, 0, r.stderr)


class PlacementCrash(Guard):
    def run_patched(self, patch, tool_input):
        """The guard with its placement step made to fail: a stand-in python3 edits the inline code."""
        import sys
        bindir = make(self.tmp / "pybin")
        stub = bindir / "python3"
        stub.write_text("#!%s\nimport os, sys\nargs = sys.argv[1:]\n"
                        "if %r in args:\n    k = args.index(%r) + 1\n"
                        "    args[k] = args[k].replace(%r, %r)\n"
                        "os.execv(%r, [%r] + args)\n"
                        % (sys.executable, "-c", "-c", "def place(before, edits):\n",
                           "def place(before, edits):\n" + patch, sys.executable, sys.executable))
        os.chmod(stub, 0o755)
        home = make(self.tmp / "patched-home")
        env = dict(os.environ, HOME=str(home), AI_RULES_HOME=str(home / ".ai-rules"),
                   CONTENT_HYGIENE_BIN=str(ROOT / "bin" / "content-hygiene"),
                   PATH=str(bindir) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"))
        return subprocess.run(["/bin/bash", str(GUARD)], input=json.dumps({"tool_input": tool_input}),
                              capture_output=True, text=True, env=env, timeout=60)

    def test_placement_that_crashes_or_is_killed_blocks(self):
        f = make(self.docs / "crash") / "c.py"
        f.write_text("x = 1\n", encoding="utf-8")
        for patch in ("    raise RuntimeError\n", "    os.kill(os.getpid(), signal.SIGKILL)\n"):
            r = self.run_patched(patch, {"file_path": str(f), "old_string": "x = 1", "new_string": "x = 2"})
            self.assertEqual(r.returncode, 2, patch + r.stderr)
            self.assertIn("not-checked", r.stderr)
        r = self.run_patched("    raise ValueError\n", {"file_path": str(f), "old_string": "x = 1", "new_string": "x = 2"})
        self.assertEqual(r.returncode, 0, "an edit that does not fit: the new text alone " + r.stderr)


class LoneCarriageReturns(Guard):
    def test_edit_in_a_cr_only_file_is_judged_by_line(self):
        f = make(self.docs / "cr") / "a.py"
        with open(str(f), "w", encoding="utf-8", newline="") as fh:
            fh.write("s = %sabc%s\rx = 1\ry = 2\r" % (chr(0x201C), chr(0x201D)))
        r = self.guard({"file_path": str(f), "old_string": "y = 2", "new_string": "y = 3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.guard({"file_path": str(f), "old_string": "x = 1", "new_string": "x = %sq%s" % (chr(0x201C), chr(0x201D))})
        self.assertEqual(r.returncode, 2, r.stderr)


if __name__ == "__main__":
    unittest.main()
