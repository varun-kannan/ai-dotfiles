"""Round 25 regressions for GitHub YAML spans and Python 3.9 dependencies."""
import runpy
import subprocess
import sys
import unittest

from helpers import ROOT


SCANNER = ROOT / "bin" / "content-hygiene"


class GitHubYamlGaps(unittest.TestCase):
    def scan(self, text):
        return subprocess.run(
            [sys.executable, str(SCANNER), "--stdin", "--name", ".github/workflows/ci.yml"],
            input=text,
            capture_output=True,
            text=True,
        )

    def test_quoted_braces_do_not_end_an_expression(self):
        text = "concurrency: [${{ format('}}', env.adm%sn) }}]\n" % chr(0x131)
        result = self.scan(text)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("HARD", result.stdout)

    def test_quoted_flow_key_and_doubled_quote_stay_text(self):
        text = "steps:\n  - with: {\"message\": 'I%sl''dan'}\n" % (chr(0x15F) + chr(0x131))
        result = self.scan(text)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("warn", result.stdout)


class Python39Dependencies(unittest.TestCase):
    def test_python39_fallback_does_not_include_tomllib(self):
        marker = object()
        saved = getattr(sys, "stdlib_module_names", marker)
        if saved is not marker:
            del sys.stdlib_module_names
        try:
            values = runpy.run_path(str(ROOT / "bin" / "check-deps"), run_name="check_deps_round25")
        finally:
            if saved is not marker:
                sys.stdlib_module_names = saved
        self.assertNotIn("tomllib", values["PY_STDLIB"])


if __name__ == "__main__":
    unittest.main()
