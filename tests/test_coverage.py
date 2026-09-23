# SPDX-License-Identifier: MIT
"""The measured share: what fraction of a rules directory anything checks, in the coverage
block and in `report --json`.

Run: python3 -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

from ruleprobe.cli import main
from ruleprobe.rules import Bundle, RuleEntry
from test_readers import FIXTURES
from test_rules import DARK, MEASURED, UNMEASURED


def entry(rule, state):
    return RuleEntry(rule, "/rules/%s.md" % rule, state, "", [])


class ShareTests(unittest.TestCase):
    def test_the_share_is_measured_over_every_rule_dark_ones_included(self):
        bundle = Bundle(rules=[entry("a", "measured"), entry("b", "measured"),
                               entry("c", "dark"), entry("d", "unmeasured")])
        self.assertEqual(bundle.coverage(),
                         {"measured": 2, "dark": 1, "unmeasured": 1, "share": 0.5})

    def test_the_coverage_line_prints_the_counts_and_the_share(self):
        bundle = Bundle(rules=[entry("a", "measured"), entry("b", "measured"),
                               entry("c", "dark"), entry("d", "unmeasured")])
        first = bundle.summary(relative_to="/").split("\n")[0]
        self.assertEqual(first, "rules: 2 measured, 1 dark, 1 unmeasured (50% measured)")

    def test_the_printed_share_is_floored_so_a_gap_never_reads_as_complete(self):
        rules = [entry("m%d" % i, "measured") for i in range(199)] + [entry("u", "unmeasured")]
        first = Bundle(rules=rules).summary(relative_to="/").split("\n")[0]
        self.assertTrue(first.endswith("(99% measured)"), first)

    def test_a_third_floors_rather_than_rounds(self):
        bundle = Bundle(rules=[entry("a", "measured"), entry("b", "measured"),
                               entry("c", "dark")])
        self.assertIn("(66% measured)", bundle.summary(relative_to="/"))

    def test_zero_rules_have_no_share_and_print_no_coverage_line(self):
        bundle = Bundle()
        self.assertEqual(bundle.coverage(),
                         {"measured": 0, "dark": 0, "unmeasured": 0, "share": None})
        self.assertEqual(bundle.summary(), "")

    def test_all_dark_is_a_share_of_zero_not_no_share(self):
        bundle = Bundle(rules=[entry("a", "dark")])
        self.assertEqual(bundle.coverage()["share"], 0.0)
        self.assertIn("(0% measured)", bundle.summary(relative_to="/"))


class CliCoverageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        rules = os.path.join(self.dir, "rules")
        os.makedirs(rules)
        for name, text in (("house-style", MEASURED), ("secrets", DARK),
                           ("working-style", UNMEASURED)):
            with open(os.path.join(rules, name + ".md"), "w", encoding="utf-8") as handle:
                handle.write(text)
        self.rules = rules

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        saved, sys.stderr = sys.stderr, err
        try:
            code = main(list(argv), out=out)
        finally:
            sys.stderr = saved
        return code, out.getvalue(), err.getvalue()

    def test_report_prints_the_counts_and_the_share(self):
        code, text, _ = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                     "--rules", self.rules)
        self.assertEqual(code, 0)
        self.assertIn("rules: 1 measured, 1 dark, 1 unmeasured (33% measured)", text)

    def test_json_carries_the_same_counts_and_share(self):
        code, text, err = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                       "--rules", self.rules, "--json")
        self.assertEqual(code, 0)
        coverage = json.loads(text)["coverage"]
        self.assertEqual({k: coverage[k] for k in ("measured", "dark", "unmeasured")},
                         {"measured": 1, "dark": 1, "unmeasured": 1})
        self.assertAlmostEqual(coverage["share"], 1 / 3.0)
        self.assertIn("rules: 1 measured, 1 dark, 1 unmeasured (33% measured)", err)

    def test_json_with_no_rules_carries_zero_counts_and_no_share(self):
        code, text, err = self.run_cli("report", "--root", FIXTURES, "--no-config", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["coverage"],
                         {"measured": 0, "dark": 0, "unmeasured": 0, "share": None})
        self.assertNotIn("measured)", err)


if __name__ == "__main__":
    unittest.main()
