# SPDX-License-Identifier: MIT
"""The report: the denominator, the notes, and the three groupings."""
import unittest

from ruleprobe import Detector, Registry, measure, report
from ruleprobe.readers import claude_code
from ruleprobe.report import folded_rules
from test_readers import CLAUDE


def row(hits, repo="demo", stances=None, **extra):
    out = {"session_id": "s", "repo": repo, "rules": dict(hits), "stances": stances or {}}
    out.update(extra)
    return out


REGISTRY = Registry([Detector("a/one", "a", "session", lambda e, c: []),
                     Detector("a/two", "a", "session", lambda e, c: [])])


class DenominatorTests(unittest.TestCase):
    def test_only_a_row_with_a_rules_map_is_evidence(self):
        rows = [row({"a/one": 1}), {"session_id": "legacy"},
                row({"a/one": 9}, rules_errors=[{"detector": "a/two", "error": "KeyError"}])]
        text = report(rows, registry=REGISTRY)
        self.assertIn("2 session(s) carry no rule data (1 unmeasured, 1 errored)", text)
        # The denominator is 1: the errored row's nine hits are not counted either.
        self.assertIn("a/one                                       1         1     1", text)

    def test_no_measured_row_says_so_rather_than_printing_an_empty_table(self):
        self.assertIn("no measured sessions", report([{"session_id": "legacy"}]))

    def test_a_detector_that_never_fired_is_still_a_line(self):
        self.assertIn("a/two", report([row({"a/one": 1})], registry=REGISTRY))


class NoteTests(unittest.TestCase):
    def test_no_note_is_printed_until_there_are_enough_sessions(self):
        rows = [row({"a/one": 1}) for _ in range(5)]
        text = report(rows, min_sessions=20, registry=REGISTRY)
        self.assertNotIn("promote?", text)
        self.assertNotIn("unobserved", text)

    def test_a_common_observable_is_flagged_for_promotion(self):
        rows = [row({"a/one": 1}) for _ in range(5)] + [row({}) for _ in range(5)]
        text = report(rows, min_sessions=10, promote_share=0.30, registry=REGISTRY)
        self.assertIn("promote?", text.split("a/one")[1].split("\n")[0])
        self.assertIn("unobserved", text.split("a/two")[1])

    def test_the_share_is_sessions_that_fired_over_measured_sessions(self):
        rows = [row({"a/one": 3}), row({}), row({}), row({})]
        line = [x for x in report(rows, registry=REGISTRY).split("\n")
                if x.startswith("a/one")][0]
        self.assertIn("25%", line)
        self.assertIn("3", line.split()[1])


class FoldTests(unittest.TestCase):
    def test_a_renamed_detector_is_counted_under_its_successor(self):
        registry = REGISTRY.copy().rename("a/old", "a/one")
        rows = [row({"a/old": 2, "a/one": 1})]
        self.assertEqual(folded_rules(rows[0], registry.renamed), {"a/one": 3})
        line = [x for x in report(rows, registry=registry).split("\n")
                if x.startswith("a/one")][0]
        self.assertIn("3", line.split()[1])
        self.assertNotIn("a/old", report(rows, registry=registry))

    def test_an_unparsable_count_is_read_as_zero_rather_than_raising(self):
        self.assertEqual(folded_rules({"rules": {"a/one": None, "a/two": "x", 7: 1}}, {}),
                         {"a/one": 0, "a/two": 0})


class GroupingTests(unittest.TestCase):
    def test_by_repo_totals_each_repository_and_names_its_top_detectors(self):
        rows = [row({"a/one": 2}, repo="alpha"), row({"a/two": 1}, repo="alpha"),
                row({"a/one": 1}, repo="beta")]
        text = report(rows, by="repo", registry=REGISTRY)
        alpha = [x for x in text.split("\n") if x.startswith("alpha")][0]
        self.assertIn("2", alpha.split()[1])
        self.assertIn("a/one 2", alpha)

    def test_by_stance_groups_on_every_dimension_a_row_ran_under(self):
        rows = [row({"a/one": 1}, stances={"commits": "conventional", "voice": "terse"}),
                row({"a/one": 1}, stances={"commits": "conventional"})]
        text = report(rows, by="stance", registry=REGISTRY)
        self.assertIn("commits=conventional", text)
        self.assertIn("voice=terse", text)

    def test_a_row_with_no_stances_is_its_own_group(self):
        self.assertIn("(no stances)", report([row({"a/one": 1})], by="stance",
                                             registry=REGISTRY))

    def test_a_rescanned_row_is_excluded_from_the_stance_grouping(self):
        rows = [row({"a/one": 1}, stances={"commits": "conventional"},
                    stances_source="rescan")]
        text = report(rows, by="stance", registry=REGISTRY)
        self.assertIn("1 rescanned session(s) excluded", text)
        self.assertIn("no sessions with a known stance", text)

    def test_an_unknown_grouping_is_refused(self):
        with self.assertRaises(ValueError):
            report([row({"a/one": 1})], by="phase-of-the-moon")


class MeasureTests(unittest.TestCase):
    def test_a_row_carries_the_sessions_identity_and_its_counts(self):
        measured = measure(claude_code.read(CLAUDE))
        self.assertEqual(measured["repo"], "demo-repo")
        self.assertEqual(measured["runtime"], "claude-code")
        self.assertEqual(measured["rules"]["verification/no-verify"], 1)
        self.assertNotIn("rules_errors", measured)

    def test_a_detector_that_raises_marks_the_row_rather_than_losing_it(self):
        def boom(events, ctx):
            raise ValueError("no")

        registry = Registry([Detector("a/boom", "a", "session", boom)])
        measured = measure(claude_code.read(CLAUDE), registry=registry)
        self.assertEqual(measured["rules"], {})
        self.assertEqual(measured["rules_errors"],
                         [{"detector": "a/boom", "error": "ValueError"}])
        self.assertIn("1 errored", report([measured], registry=registry))


if __name__ == "__main__":
    unittest.main()
