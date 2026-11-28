"""Round 22 scanner regressions for host, script, module, and POM classification."""
import subprocess
import sys
import unittest

from helpers import ROOT


SCANNER = ROOT / "bin" / "content-hygiene"


class ScannerGaps(unittest.TestCase):
    def scan(self, text, name):
        return subprocess.run([sys.executable, str(SCANNER), "--stdin", "--name", name],
                              input=text, capture_output=True, text=True)

    def assert_scan(self, text, name, returncode, output):
        result = self.scan(text, name)
        self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
        self.assertEqual(result.stdout, output)
        self.assertEqual(result.stderr, "")

    def test_bare_host_requires_an_ascii_letter_tld(self):
        word = "".join(chr(codepoint) for codepoint in (0x0430, 0x0440, 0x0440, 0x04CF, 0x0435))
        self.assert_scan(word + ".com\n", "x.txt", 1,
                         "HARD  x.txt:1:1                    homoglyph  %r is made only of Cyrillic letters that read as Latin (in a host name)\n" % word)
        for suffix in ("com1", chr(0x0440) + chr(0x0444)):
            with self.subTest(suffix=suffix):
                self.assert_scan(word + "." + suffix + "\n", "x.txt", 0, "")

    def test_cyrillic_double_o_mixed_with_latin_blocks(self):
        name = "p" + chr(0xA698) + chr(0xA699) + "pal"
        self.assert_scan(name + " = 1\n", "x.py", 1,
                         "HARD  x.py:1:1                     homoglyph  %r mixes Latin and Cyrillic letters\n" % name)

    def test_bare_mjs_is_a_module_for_yield_regex_classification(self):
        text = "yield /[%s]/.test(s) && console.log(\"a%sb\");\n" % (chr(0x0430), chr(0x00AD))
        self.assert_scan(text, "x.mjs", 1,
                         "HARD  x.mjs:1:38                   invisible-char  U+00AD SOFT HYPHEN\n")

    def test_pom_repository_url_is_exact_while_description_is_text(self):
        word = chr(0x0131) + chr(0x015F) + chr(0x0131) + "k"
        repository = ("<project><repositories><repository><url>%s</url></repository>"
                      "</repositories></project>\n") % word
        description = "<project><description>%s</description></project>\n" % word
        self.assert_scan(repository, "pom.xml", 1,
                         "HARD  pom.xml:1:41                 homoglyph  %r mixes Latin and Latin dotless letters\n" % word)
        self.assert_scan(description, "pom.xml", 0,
                         "warn  pom.xml:1:23                 homoglyph  %r mixes Latin and Latin dotless letters\n" % word)


if __name__ == "__main__":
    unittest.main()
