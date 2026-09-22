# SPDX-License-Identifier: MIT
"""The command line, over the fixture transcripts."""
import io
import json
import unittest

from ruleprobe.cli import main
from test_readers import FIXTURES


def run_cli(*argv):
    out = io.StringIO()
    code = main(list(argv), out=out)
    return code, out.getvalue()


class ReportCommandTests(unittest.TestCase):
    def test_the_default_grouping_is_by_detector(self):
        code, text = run_cli("report", "--root", FIXTURES, "--no-config")
        self.assertEqual(code, 0)
        self.assertIn("detector", text.split("\n")[0])
        self.assertIn("verification/no-verify", text)
        self.assertIn("transcript-hygiene/unfiltered-find", text)

    def test_by_repo_names_both_repositories(self):
        code, text = run_cli("report", "--root", FIXTURES, "--no-config", "--by", "repo")
        self.assertEqual(code, 0)
        self.assertIn("demo-repo", text)
        self.assertIn("other-repo", text)

    def test_since_narrows_the_window(self):
        _, text = run_cli("report", "--root", FIXTURES, "--since", "2026-09-21", "--by", "repo")
        self.assertIn("other-repo", text)
        self.assertNotIn("demo-repo", text)

    def test_json_prints_the_rows_rather_than_the_table(self):
        code, text = run_cli("report", "--root", FIXTURES, "--json")
        rows = json.loads(text)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(r["repo"] for r in rows), ["demo-repo", "other-repo"])

    def test_an_empty_root_says_what_to_do_and_exits_non_zero(self):
        code, text = run_cli("report", "--root", FIXTURES + "/nothing-here")
        self.assertEqual(code, 1)
        self.assertIn("--root", text)

    def test_the_notes_are_tunable_from_the_command_line(self):
        _, text = run_cli("report", "--root", FIXTURES, "--min-sessions", "1",
                          "--promote-share", "0.1")
        self.assertIn("promote?", text)


class OtherCommandTests(unittest.TestCase):
    def test_detectors_lists_the_shipped_six(self):
        code, text = run_cli("detectors", "--no-config")
        self.assertEqual(code, 0)
        self.assertEqual(len([x for x in text.strip().split("\n") if x]), 6)
        self.assertIn("secrets/secret-in-write", text)

    def test_no_command_prints_the_help_and_exits_non_zero(self):
        code, text = run_cli()
        self.assertEqual(code, 1)
        self.assertIn("usage: ruleprobe", text)


if __name__ == "__main__":
    unittest.main()
