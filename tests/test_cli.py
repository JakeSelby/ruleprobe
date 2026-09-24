# SPDX-License-Identifier: MIT
"""The command line, over the fixture transcripts."""
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from ruleprobe import contract_data
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

    def test_json_prints_the_same_report_as_data_and_the_rows_with_it(self):
        code, text = run_cli("report", "--root", FIXTURES, "--json")
        data = json.loads(text)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(r["repo"] for r in data["rows"]),
                         ["demo-repo", "other-repo"])
        self.assertEqual(data["measured"], 2)
        self.assertEqual([d["of"] for d in data["detectors"]], [2] * len(data["detectors"]))

    def test_json_carries_the_schema_version_on_the_result_and_every_row(self):
        _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--json")
        data = json.loads(text)
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual([r["schema_version"] for r in data["rows"]], [2, 2])

    def test_json_carries_the_effective_fold_map_beside_the_rows(self):
        retired = {"verification/old-no-verify": "verification/no-verify"}
        with mock.patch.dict(contract_data.RENAMED, retired):
            _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--json")
        data = json.loads(text)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["renamed"], retired)

    def test_json_is_byte_identical_across_two_runs(self):
        # Separate processes under different hash seeds, so an order that depends on set or
        # dict hashing shows up as a difference rather than a repeat. It guards hash order
        # only: two runs over one directory walk it the same way.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outputs = []
        for seed in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            done = subprocess.run(
                [sys.executable, "-m", "ruleprobe", "report", "--root", FIXTURES,
                 "--no-config", "--json", "--validity"],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.strip())
            outputs.append(done.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_an_empty_root_says_what_to_do_and_exits_non_zero(self):
        code, text = run_cli("report", "--root", FIXTURES + "/nothing-here")
        self.assertEqual(code, 1)
        self.assertIn("--root", text)

    def test_the_notes_are_tunable_from_the_command_line(self):
        _, text = run_cli("report", "--root", FIXTURES, "--min-sessions", "1",
                          "--promote-share", "0.1")
        self.assertIn("frequent", text)


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
