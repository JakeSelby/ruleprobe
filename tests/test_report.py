# SPDX-License-Identifier: MIT
"""The report: the denominator, the notes, and the three groupings."""
import unittest

from ruleprobe import Detector, Registry, measure, report
from ruleprobe.readers import claude_code
from ruleprobe.report import (KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION, folded_rules,
                              report_data)
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
        self.assertIn("1 session(s) carry no rule data", text)
        self.assertIn("1 detector(s) raised in 1 session(s): a/two (1)", text)
        # `a/two` raised in one of the two measured rows, so its denominator is 1 and
        # `a/one` keeps both: an error costs the detector that raised and nobody else.
        self.assertIn("a/one                                      10         2     2", text)
        self.assertIn("a/two                                       0         0     1", text)

    def test_an_error_naming_no_detector_still_drops_the_row_whole(self):
        rows = [row({"a/one": 1}), row({"a/one": 9}, rules_error="boom")]
        text = report(rows, registry=REGISTRY)
        self.assertIn("1 session(s) carry an error naming no detector", text)
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
        self.assertIn("1 detector(s) raised in 1 session(s): a/boom (1)",
                      report([measured], registry=registry))


class SchemaVersionTests(unittest.TestCase):
    def test_measure_writes_the_current_schema_version(self):
        measured = measure(claude_code.read(CLAUDE))
        self.assertEqual(SCHEMA_VERSION, 2)
        self.assertEqual(measured["schema_version"], 2)

    def test_the_written_version_is_the_highest_known_one(self):
        # Bumping one without the other would make `measure()` write rows `report_data` drops.
        self.assertEqual(SCHEMA_VERSION, max(KNOWN_SCHEMA_VERSIONS))

    def test_a_row_marked_schema_1_is_counted_as_before(self):
        data = report_data([row({"a/one": 3}, schema_version=1)], registry=REGISTRY)
        self.assertEqual((data["measured"], data["unknown_schema"]), (1, 0))
        self.assertEqual((data["detectors"][0]["hits"], data["detectors"][0]["of"]), (3, 1))

    def test_a_null_schema_version_is_read_as_absent_and_counted_as_before(self):
        data = report_data([row({"a/one": 3}, schema_version=None)], registry=REGISTRY)
        self.assertEqual((data["measured"], data["unknown_schema"]), (1, 0))
        self.assertEqual((data["detectors"][0]["hits"], data["detectors"][0]["of"]), (3, 1))

    def test_an_excluded_row_stays_out_of_the_repo_and_stance_groupings(self):
        rows = [row({"a/one": 1}, repo="kept", stances={"d": "v"}),
                row({"a/one": 9}, repo="newer", stances={"d": "w"}, schema_version=3)]
        by_repo = report_data(rows, by="repo", registry=REGISTRY)
        self.assertEqual([(g["key"], g["hits"]) for g in by_repo["groups"]], [("kept", 1)])
        by_stance = report_data(rows, by="stance", registry=REGISTRY)
        self.assertEqual([(g["key"], g["hits"]) for g in by_stance["groups"]], [("d=v", 1)])

    def test_a_row_with_no_schema_version_is_schema_1_and_counted_as_before(self):
        legacy = row({"a/one": 3})
        self.assertNotIn("schema_version", legacy)
        data = report_data([legacy, row({"a/one": 1}, schema_version=2)], registry=REGISTRY)
        self.assertEqual(data["measured"], 2)
        self.assertEqual(data["unknown_schema"], 0)
        self.assertEqual(data["detectors"][0],
                         {"detector": "a/one", "hits": 4, "sessions": 2, "of": 2,
                          "share": 1.0, "note": ""})

    def test_a_row_above_the_highest_known_version_is_excluded_and_reported(self):
        rows = [row({"a/one": 1}), row({"a/one": 9}, schema_version=3),
                {"session_id": "legacy"}]
        data = report_data(rows, registry=REGISTRY)
        self.assertEqual((data["measured"], data["unmeasured"], data["unknown_schema"]),
                         (1, 1, 1))
        # Out of the hits and out of the denominator, not a session with no hit.
        self.assertEqual((data["detectors"][0]["hits"], data["detectors"][0]["of"]), (1, 1))
        text = report(rows, registry=REGISTRY)
        self.assertIn("1 session(s) carry no rule data", text)
        self.assertIn("1 session(s) carry a schema_version this release does not know"
                      " (highest known: 2) and are excluded", text)

    def test_a_version_that_is_not_a_known_one_is_excluded_like_a_newer_one(self):
        for bad in ("2", 2.0, True, 0, -1, [2]):
            with self.subTest(schema_version=bad):
                data = report_data([row({"a/one": 1}), row({"a/one": 9}, schema_version=bad)],
                                   registry=REGISTRY)
                self.assertEqual((data["measured"], data["unknown_schema"]), (1, 1))

    def test_a_newer_row_is_excluded_even_without_a_rules_map(self):
        data = report_data([{"session_id": "s", "schema_version": 3}], registry=REGISTRY)
        self.assertEqual((data["unmeasured"], data["unknown_schema"]), (0, 1))

    def test_every_result_carries_the_schema_version(self):
        for by in ("rule", "repo", "stance"):
            with self.subTest(by=by):
                self.assertEqual(report_data([row({"a/one": 1})], by=by,
                                             registry=REGISTRY)["schema_version"], 2)
        self.assertEqual(report_data([], registry=REGISTRY)["schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
