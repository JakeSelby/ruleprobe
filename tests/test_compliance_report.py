# SPDX-License-Identifier: MIT
"""Compliance in the report: opportunities and followed beside hits per session, never in
place of them."""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import ruleprobe
from ruleprobe import Detector, Registry, contract_data, report
from ruleprobe.cli import main
from ruleprobe.report import (RULE_MIN_OPPORTUNITIES, folded_compliance, malformed_compliance,
                              opportunity_errors, report_data)
from test_readers import FIXTURES


def row(hits, compliance=None, repo="demo", stances=None, **extra):
    out = {"session_id": "s", "repo": repo, "rules": dict(hits), "stances": stances or {}}
    if compliance is not None:
        out["compliance"] = compliance
    out.update(extra)
    return out


def tally(opportunities, followed, undecided=0):
    return {"opportunities": opportunities, "followed": followed, "undecided": undecided}


def opp_error(detector_id, error="ValueError"):
    return {"detector": detector_id, "error": error, "hook": "opportunities"}


REGISTRY = Registry([Detector("a/plain", "a", "session", lambda e, c: []),
                     Detector("o/order", "o", "session", lambda e, c: [])])


def entry(data, detector_id):
    return [d for d in data["detectors"] if d["detector"] == detector_id][0]


def line(text, detector_id):
    return [x for x in text.split("\n") if x.split() and x.split()[0] == detector_id][0]


class PerDetectorTests(unittest.TestCase):
    def test_opportunities_followed_and_undecided_sum_over_sessions(self):
        rows = [row({"o/order": 2}, {"o/order": tally(3, 2, 1)}),
                row({"o/order": 1}, {"o/order": tally(2, 1)})]
        data = report_data(rows, registry=REGISTRY, min_opportunities=5)
        got = entry(data, "o/order")
        self.assertEqual((got["opportunities"], got["followed"], got["undecided"]), (5, 3, 1))
        self.assertEqual(got["compliance_rate"], 0.6)
        # Beside the hit figures, not in place of them.
        self.assertEqual((got["hits"], got["sessions"], got["of"]), (3, 2, 2))
        self.assertEqual(data["min_opportunities"], 5)

    def test_the_table_prints_the_same_numbers_beside_hits_per_session(self):
        rows = [row({"o/order": 2}, {"o/order": tally(3, 2, 1)}),
                row({"o/order": 1}, {"o/order": tally(2, 1)})]
        text = report(rows, registry=REGISTRY, min_opportunities=5)
        head = text.split("\n")[0].split()
        self.assertEqual(head, ["detector", "hits", "sessions", "of", "share",
                                "opportunities", "followed", "undecided", "rate", "note"])
        self.assertEqual(line(text, "o/order").split(),
                         ["o/order", "3", "2", "2", "100%", "5", "3", "1", "60%"])

    def test_a_detector_with_no_opportunity_prints_hits_only(self):
        rows = [row({"a/plain": 1, "o/order": 0}, {"o/order": tally(1, 1)})]
        data = report_data(rows, registry=REGISTRY)
        plain = entry(data, "a/plain")
        for key in ("opportunities", "followed", "undecided", "compliance_rate"):
            self.assertNotIn(key, plain)
        self.assertEqual(line(report(rows, registry=REGISTRY), "a/plain").split(),
                         ["a/plain", "1", "1", "1", "100%"])

    def test_with_no_compliance_anywhere_the_table_is_unchanged(self):
        text = report([row({"a/plain": 1})], registry=REGISTRY)
        self.assertEqual(text.split("\n")[0].split(),
                         ["detector", "hits", "sessions", "of", "share", "note"])
        self.assertNotIn("opportunities", entry(report_data([row({"a/plain": 1})],
                                                            registry=REGISTRY), "o/order"))


class MinimumTests(unittest.TestCase):
    def test_the_default_minimum_is_twenty(self):
        self.assertEqual(RULE_MIN_OPPORTUNITIES, 20)
        self.assertEqual(report_data([], registry=REGISTRY)["min_opportunities"], 20)

    def test_below_the_minimum_the_counts_print_and_the_rate_is_null(self):
        rows = [row({"o/order": 1}, {"o/order": tally(19, 18)})]
        got = entry(report_data(rows, registry=REGISTRY), "o/order")
        self.assertEqual((got["opportunities"], got["followed"]), (19, 18))
        self.assertIn("compliance_rate", got)
        self.assertIsNone(got["compliance_rate"])
        self.assertEqual(line(report(rows, registry=REGISTRY), "o/order").split()[5:9],
                         ["19", "18", "0", "-"])

    def test_at_the_minimum_the_rate_is_shown(self):
        rows = [row({"o/order": 1}, {"o/order": tally(20, 15)})]
        self.assertEqual(entry(report_data(rows, registry=REGISTRY),
                               "o/order")["compliance_rate"], 0.75)

    def test_undecided_points_do_not_count_toward_the_minimum(self):
        rows = [row({}, {"o/order": tally(10, 10, 30)})]
        self.assertIsNone(entry(report_data(rows, registry=REGISTRY),
                                "o/order")["compliance_rate"])

    def test_no_opportunity_at_all_has_no_rate_even_with_no_minimum(self):
        rows = [row({}, {"o/order": tally(0, 0, 2)})]
        got = entry(report_data(rows, registry=REGISTRY, min_opportunities=0), "o/order")
        self.assertIsNone(got["compliance_rate"])


class ZeroOpportunityTests(unittest.TestCase):
    """A detector with the hook but no opportunity is not a detector without the hook."""

    def test_the_hook_with_zero_opportunities_prints_zeros_and_no_rate(self):
        rows = [row({"o/order": 0}, {"o/order": tally(0, 0)})]
        got = entry(report_data(rows, registry=REGISTRY, min_opportunities=0), "o/order")
        self.assertEqual((got["opportunities"], got["followed"], got["undecided"],
                          got["compliance_rate"]), (0, 0, 0, None))
        self.assertEqual(line(report(rows, registry=REGISTRY), "o/order").split()[5:9],
                         ["0", "0", "0", "-"])


class RateDisplayTests(unittest.TestCase):
    def rate_cell(self, opportunities, followed):
        rows = [row({"o/order": 1}, {"o/order": tally(opportunities, followed)})]
        return line(report(rows, registry=REGISTRY, min_opportunities=1), "o/order").split()[8]

    def test_a_rate_never_rounds_onto_all_or_none(self):
        self.assertEqual(self.rate_cell(1000, 999), "99%")
        self.assertEqual(self.rate_cell(300, 1), "1%")
        self.assertEqual(self.rate_cell(1000, 1000), "100%")
        self.assertEqual(self.rate_cell(300, 0), "0%")
        self.assertEqual(self.rate_cell(4, 3), "75%")

    def test_the_data_keeps_the_exact_rate(self):
        rows = [row({}, {"o/order": tally(1000, 999)})]
        self.assertEqual(entry(report_data(rows, registry=REGISTRY),
                               "o/order")["compliance_rate"], 0.999)


class GroupingTests(unittest.TestCase):
    ROWS = [row({"o/order": 1}, {"o/order": tally(3, 2)}, repo="r1",
                stances={"commits": "on"}),
            row({"o/order": 1}, {"o/order": tally(4, 4, 1)}, repo="r1",
                stances={"commits": "off"}),
            row({"a/plain": 2}, repo="r2", stances={"commits": "on"})]

    def test_by_repo_groups_compliance_as_it_groups_hits(self):
        data = report_data(self.ROWS, by="repo", registry=REGISTRY, min_opportunities=5)
        groups = dict((g["key"], g) for g in data["groups"])
        self.assertEqual(groups["r1"]["compliance"], {"o/order": {
            "opportunities": 7, "followed": 6, "undecided": 1, "compliance_rate": 6 / 7.0}})
        self.assertEqual(groups["r2"]["compliance"], {})
        self.assertEqual(groups["r1"]["hits"], 2)

    def test_by_stance_groups_compliance_and_applies_the_minimum_per_group(self):
        data = report_data(self.ROWS, by="stance", registry=REGISTRY, min_opportunities=4)
        groups = dict((g["key"], g) for g in data["groups"])
        # Four in `off` reaches the minimum; three in `on` does not.
        self.assertEqual(groups["commits=off"]["compliance"]["o/order"]["compliance_rate"],
                         1.0)
        self.assertIsNone(groups["commits=on"]["compliance"]["o/order"]["compliance_rate"])
        self.assertEqual(groups["commits=on"]["compliance"]["o/order"]["opportunities"], 3)

    def test_the_grouped_table_prints_the_same_numbers(self):
        text = report(self.ROWS, by="repo", registry=REGISTRY, min_opportunities=5)
        self.assertIn("  o/order: opportunities 7, followed 6, undecided 1, rate 86%", text)
        text = report(self.ROWS, by="repo", registry=REGISTRY)
        self.assertIn("  o/order: opportunities 7, followed 6, undecided 1, rate -", text)

    def test_a_rescanned_row_is_out_of_stance_compliance_too(self):
        rows = self.ROWS + [row({}, {"o/order": tally(50, 0)}, stances={"commits": "on"},
                                stances_source="rescan")]
        data = report_data(rows, by="stance", registry=REGISTRY)
        groups = dict((g["key"], g) for g in data["groups"])
        self.assertEqual(groups["commits=on"]["compliance"]["o/order"]["opportunities"], 3)


class FoldTests(unittest.TestCase):
    def test_a_retired_id_folds_into_the_current_one(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        rows = [row({"o/old": 1}, {"o/old": tally(2, 1, 1)}),
                row({"o/order": 1}, {"o/order": tally(3, 3)})]
        self.assertEqual(folded_compliance(rows[0], registry.renamed),
                         {"o/order": tally(2, 1, 1)})
        data = report_data(rows, registry=registry, min_opportunities=1)
        got = entry(data, "o/order")
        self.assertEqual((got["opportunities"], got["followed"], got["undecided"]), (5, 4, 1))
        self.assertNotIn("o/old", [d["detector"] for d in data["detectors"]])

    def test_a_row_keyed_by_both_ids_sums_them(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        both = row({}, {"o/old": tally(1, 0), "o/order": tally(2, 2, 1)})
        self.assertEqual(folded_compliance(both, registry.renamed),
                         {"o/order": tally(3, 2, 1)})

    def test_a_retired_ids_hits_and_compliance_fold_to_the_same_current_id(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        rows = [row({"o/old": 3}, {"o/old": tally(4, 2)})]
        data = report_data(rows, registry=registry, min_opportunities=1)
        got = entry(data, "o/order")
        self.assertEqual((got["hits"], got["opportunities"], got["followed"]), (3, 4, 2))
        self.assertEqual([d["detector"] for d in data["detectors"]], ["a/plain", "o/order"])

    def test_a_shipped_rename_folds_compliance_with_no_map_of_your_own(self):
        rows = [row({"o/gone": 1}, {"o/gone": tally(4, 1)})]
        with mock.patch.dict(contract_data.RENAMED, {"o/gone": "o/order"}):
            got = entry(report_data(rows, registry=REGISTRY), "o/order")
        self.assertEqual(got["opportunities"], 4)

    def test_a_malformed_tally_is_left_out_rather_than_read_as_zero(self):
        compliance = {"o/order": {"opportunities": "3", "followed": 1, "undecided": 0},
                      "o/x": tally(1, 2), "o/y": None, "o/z": {"opportunities": True,
                                                               "followed": 0, "undecided": 0},
                      "o/neg": tally(-1, 0), 7: tally(1, 1), "o/ok": tally(1, 1)}
        self.assertEqual(folded_compliance(row({}, compliance), {}), {"o/ok": tally(1, 1)})
        self.assertEqual(folded_compliance(row({}, "nope"), {}), {})
        self.assertEqual(malformed_compliance(row({}, compliance), {}),
                         {"o/order", "o/x", "o/y", "o/z", "o/neg"})

    def test_a_malformed_tally_is_counted_and_noted_never_silent(self):
        rows = [row({"o/order": 1}, {"o/order": tally(-1, 0)}),
                row({"o/order": 1}, {"o/order": tally(4, 3)})]
        data = report_data(rows, registry=REGISTRY, min_opportunities=1)
        self.assertEqual(data["malformed_compliance"], {"o/order": 1})
        self.assertIn("1 detector(s) carry an unreadable compliance entry in 1 session(s): "
                      "o/order (1)", data["notes"])
        got = entry(data, "o/order")
        self.assertEqual((got["opportunities"], got["followed"]), (4, 3))
        self.assertEqual((got["hits"], got["of"]), (2, 2))

    def test_an_unreadable_compliance_map_is_counted_and_noted(self):
        for bad in ([], "x", {7: tally(1, 1), "o/order": tally(2, 1)}):
            rows = [row({"o/order": 1}, bad), row({"o/order": 1}, {"o/order": tally(3, 3)})]
            data = report_data(rows, registry=REGISTRY, min_opportunities=1)
            self.assertEqual(data["unreadable_compliance"], 1, bad)
            self.assertIn("1 session(s) carry a compliance map, or a key in one, naming no"
                          " detector", data["notes"])
            # The row's hits still count; its readable entries, if any, still sum.
            got = entry(data, "o/order")
            self.assertEqual(got["hits"], 2)
            self.assertEqual(got["opportunities"], 5 if isinstance(bad, dict) else 3, bad)

    def test_a_null_compliance_is_read_as_absent(self):
        stored = row({})
        stored["compliance"] = None
        data = report_data([stored], registry=REGISTRY)
        self.assertEqual(data["unreadable_compliance"], 0)

    def test_a_malformed_retired_entry_drops_the_folded_sum_for_that_session(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        rows = [row({}, {"o/old": tally(-1, 0), "o/order": tally(2, 2)})]
        data = report_data(rows, registry=registry)
        # A partial sum after the fold would be a false figure: the session is out.
        self.assertEqual(entry(data, "o/order")["opportunities"], 0)
        self.assertEqual(data["malformed_compliance"], {"o/order": 1})


class OpportunityErrorTests(unittest.TestCase):
    """A failing or malformed `opportunities` is never silent in the report."""

    def rows(self):
        return [row({"o/order": 2}, {"o/order": tally(5, 5)}),
                row({"o/order": 1}, rules_errors=[opp_error("o/order")]),
                row({"o/order": 1}, rules_errors=[opp_error("o/order",
                                                            "MalformedOpportunities")])]

    def test_the_session_leaves_compliance_and_its_hits_stand(self):
        data = report_data(self.rows(), registry=REGISTRY, min_opportunities=1)
        got = entry(data, "o/order")
        self.assertEqual((got["hits"], got["sessions"], got["of"]), (4, 3, 3))
        self.assertEqual((got["opportunities"], got["followed"]), (5, 5))
        self.assertEqual(data["errors"], {})

    def test_the_count_is_carried_and_noted(self):
        data = report_data(self.rows(), registry=REGISTRY)
        self.assertEqual(data["opportunity_errors"], {"o/order": 2})
        self.assertIn("1 detector(s) failed to count opportunities in 2 session(s): "
                      "o/order (2)", data["notes"])
        self.assertIn("1 detector(s) failed to count opportunities",
                      report(self.rows(), registry=REGISTRY))

    def test_no_failure_carries_an_empty_count_and_no_note(self):
        data = report_data([row({}, {"o/order": tally(1, 1)})], registry=REGISTRY)
        self.assertEqual(data["opportunity_errors"], {})
        self.assertFalse([n for n in data["notes"] if "opportunities" in n])

    def test_a_failure_in_every_session_still_shows_the_detector_with_zero(self):
        rows = [row({"o/order": 1}, rules_errors=[opp_error("o/order")])]
        got = entry(report_data(rows, registry=REGISTRY), "o/order")
        self.assertEqual((got["opportunities"], got["compliance_rate"]), (0, None))

    def test_an_entry_beside_a_failure_for_the_same_detector_is_not_counted(self):
        rows = [row({}, {"o/order": tally(9, 0)}, rules_errors=[opp_error("o/order")])]
        self.assertEqual(entry(report_data(rows, registry=REGISTRY),
                               "o/order")["opportunities"], 0)

    def test_a_session_whose_fn_raised_is_out_of_that_detectors_compliance(self):
        rows = [row({}, {"o/order": tally(9, 0)},
                    rules_errors=[{"detector": "o/order", "error": "ValueError"}]),
                row({}, {"o/order": tally(2, 2)})]
        got = entry(report_data(rows, registry=REGISTRY, min_opportunities=1), "o/order")
        self.assertEqual((got["opportunities"], got["compliance_rate"]), (2, 1.0))

    def test_a_failure_under_a_retired_id_is_charged_to_the_current_one(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        failing = row({}, rules_errors=[opp_error("o/old")])
        self.assertEqual(opportunity_errors(failing, registry.renamed), {"o/order"})
        self.assertEqual(report_data([failing], registry=registry)["opportunity_errors"],
                         {"o/order": 1})

    def test_a_group_where_every_session_failed_shows_the_detector_at_zero(self):
        rows = [row({}, repo="r1", rules_errors=[opp_error("o/order")]),
                row({}, {"o/order": tally(2, 1)}, repo="r2")]
        groups = dict((g["key"], g) for g in
                      report_data(rows, by="repo", registry=REGISTRY)["groups"])
        self.assertEqual(groups["r1"]["compliance"], {"o/order": {
            "opportunities": 0, "followed": 0, "undecided": 0, "compliance_rate": None}})
        self.assertIn("  o/order: opportunities 0, followed 0, undecided 0, rate -",
                      report(rows, by="repo", registry=REGISTRY))

    def test_an_unregistered_id_with_only_compliance_or_a_failure_gets_a_line(self):
        rows = [row({}, {"x/stored": tally(3, 1)}, rules_errors=[opp_error("x/failed")])]
        data = report_data(rows, registry=REGISTRY)
        self.assertEqual(entry(data, "x/stored")["opportunities"], 3)
        self.assertEqual(entry(data, "x/stored")["hits"], 0)
        self.assertEqual(entry(data, "x/failed")["opportunities"], 0)
        self.assertEqual([d["detector"] for d in data["detectors"]],
                         ["a/plain", "o/order", "x/failed", "x/stored"])

    def test_a_rescanned_session_is_not_counted_among_the_failures(self):
        rows = [row({}, stances={"c": "on"}, rules_errors=[opp_error("o/order")]),
                row({}, stances={"c": "on"}, stances_source="rescan",
                    rules_errors=[opp_error("o/order"), opp_error("o/other")])]
        data = report_data(rows, by="stance", registry=REGISTRY)
        self.assertEqual(data["opportunity_errors"], {"o/order": 1})
        # By rule nothing is filtered, so both sessions count.
        self.assertEqual(report_data(rows, registry=REGISTRY)["opportunity_errors"],
                         {"o/order": 2, "o/other": 1})

    def test_the_hits_stand_sentence_is_printed_once(self):
        rows = [row({}, {"o/order": tally(-1, 0)}, rules_errors=[opp_error("o/other")]),
                row({}, [])]
        notes = report_data(rows, registry=REGISTRY)["notes"]
        self.assertEqual(len([n for n in notes if n.endswith("its hits stand")]), 1)
        self.assertEqual(notes[-1], "each is out of its own compliance figures for those"
                                    " sessions; its hits stand")

    def test_by_stance_counts_fn_errors_over_the_same_sessions(self):
        raised = {"detector": "a/plain", "error": "ValueError"}
        rows = [row({}, stances={"c": "on"}, rules_errors=[raised, opp_error("o/order")]),
                row({}, stances={"c": "on"}, stances_source="rescan",
                    rules_errors=[raised, opp_error("o/order")])]
        data = report_data(rows, by="stance", registry=REGISTRY)
        self.assertEqual(data["errors"], {"a/plain": 1})
        self.assertEqual(data["opportunity_errors"], {"o/order": 1})
        self.assertIn("1 detector(s) raised in 1 session(s): a/plain (1)", data["notes"])
        self.assertEqual(report_data(rows, registry=REGISTRY)["errors"], {"a/plain": 2})

    def test_an_id_known_only_from_compliance_is_never_unobserved(self):
        rows = [row({}, {"x/stored": tally(1, 1)}, rules_errors=[opp_error("x/failed")])
                for _ in range(3)]
        data = report_data(rows, registry=REGISTRY, min_sessions=1)
        self.assertEqual(entry(data, "x/failed")["note"], "")
        self.assertEqual(entry(data, "x/stored")["note"], "")
        # A registered detector with no hit still is.
        self.assertEqual(entry(data, "o/order")["note"], "unobserved")

    def test_a_failure_leaves_the_session_out_of_its_group_too(self):
        rows = [row({}, {"o/order": tally(3, 1)}, repo="r1"),
                row({}, {"o/order": tally(9, 9)}, repo="r1",
                    rules_errors=[opp_error("o/order")])]
        group = report_data(rows, by="repo", registry=REGISTRY)["groups"][0]
        self.assertEqual(group["compliance"]["o/order"]["opportunities"], 3)


class MarkerTests(unittest.TestCase):
    def test_the_threshold_marker_is_frequent_and_advises_nothing(self):
        rows = [row({"a/plain": 1}) for _ in range(5)] + [row({}) for _ in range(5)]
        data = report_data(rows, min_sessions=10, frequent_share=0.30, registry=REGISTRY)
        self.assertEqual(entry(data, "a/plain")["note"], "frequent")
        text = report(rows, min_sessions=10, frequent_share=0.30, registry=REGISTRY)
        self.assertEqual(line(text, "a/plain").split()[-1], "frequent")
        self.assertNotIn("promote", text)


class MinimumArgumentTests(unittest.TestCase):
    def test_a_minimum_that_is_not_an_integer_is_refused(self):
        for bad in (True, 2.5, "20", None):
            with self.assertRaises(TypeError):
                report_data([], min_opportunities=bad)
            with self.assertRaises(TypeError):
                report([], min_opportunities=bad)

    def test_the_default_is_exported_from_the_package_root(self):
        self.assertIn("RULE_MIN_OPPORTUNITIES", ruleprobe.__all__)
        self.assertEqual(ruleprobe.RULE_MIN_OPPORTUNITIES, 20)


class LayoutTests(unittest.TestCase):
    ROWS = ([row({"a/plain": 1, "o/order": 1}, {"o/order": tally(30, 21, 2)})]
            + [row({"a/plain": 1}, {"o/order": tally(0, 0)}) for _ in range(20)])

    def test_the_note_starts_under_its_header_beside_compliance_columns(self):
        text = report(self.ROWS, registry=REGISTRY)
        head = text.split("\n")[0]
        plain = line(text, "a/plain")
        self.assertEqual(plain.index("frequent"), head.index("note"))
        self.assertEqual(len(line(text, "o/order")), head.index("note") - 2)
        self.assertTrue(line(text, "o/order").endswith("70%"))
        self.assertTrue(head.index("rate") + len("rate") == len(line(text, "o/order")))

    def test_the_plain_table_puts_every_note_and_validity_under_its_header(self):
        rows = [row({"a/plain": 1}) for _ in range(20)]
        text = report(rows, registry=REGISTRY, validity={})
        head = text.split("\n")[0]
        self.assertEqual(head.split(), ["detector", "hits", "sessions", "of", "share", "note",
                                        "validity"])
        self.assertEqual(line(text, "a/plain").index("frequent"), head.index("note"))
        self.assertEqual(line(text, "o/order").index("unobserved"), head.index("note"))
        for did in ("a/plain", "o/order"):
            self.assertEqual(line(text, did).index("not in the corpus"),
                             head.index("validity"), did)
        # The share cell ends where its header does.
        self.assertEqual(line(text, "a/plain").index("100%") + 4,
                         head.index("share") + len("share"))

    def test_compliance_columns_and_the_validity_column_line_up(self):
        text = report(self.ROWS, registry=REGISTRY, validity={})
        head = text.split("\n")[0]
        self.assertEqual(head.split()[-6:], ["opportunities", "followed", "undecided", "rate",
                                             "note", "validity"])
        self.assertEqual(line(text, "a/plain").index("frequent"), head.index("note"))
        for did in ("a/plain", "o/order"):
            got = line(text, did)
            self.assertEqual(got.index("not in the corpus"), head.index("validity"), did)
        self.assertEqual(line(text, "o/order").split()[5:9], ["30", "21", "2", "70%"])

    def test_by_stance_prints_each_groups_compliance_under_it(self):
        rows = [row({"o/order": 1}, {"o/order": tally(3, 2)}, stances={"c": "on"}),
                row({"o/order": 1}, {"o/order": tally(4, 4, 1)}, stances={"c": "off"})]
        lines = report(rows, by="stance", registry=REGISTRY, min_opportunities=4).split("\n")
        self.assertEqual(lines[0].split(), ["stance", "sessions", "hits", "top", "detectors"])
        self.assertEqual(lines[2].split()[:3], ["c=off", "1", "1"])
        self.assertEqual(lines[3], "  o/order: opportunities 4, followed 4, undecided 1, rate 100%")
        self.assertEqual(lines[4].split()[:3], ["c=on", "1", "1"])
        self.assertEqual(lines[5], "  o/order: opportunities 3, followed 2, undecided 0, rate -")


class DeterminismTests(unittest.TestCase):
    def test_the_same_rows_give_byte_identical_json(self):
        registry = REGISTRY.copy().rename("o/old", "o/order")
        rows = [row({"o/order": 1, "a/plain": 1},
                    {"o/order": tally(3, 2), "o/old": tally(1, 1)}, repo="r2",
                    stances={"b": "x", "a": "y"}),
                row({}, {"o/z": tally(1, 0), "o/order": tally(2, 1, 1)}, repo="r1",
                    rules_errors=[opp_error("o/z"), opp_error("o/old")])]
        for by in ("rule", "repo", "stance"):
            # Dumped as `report --json` dumps it, from the same rows reported twice.
            first = json.dumps(report_data(rows, by=by, registry=registry), indent=2,
                               sort_keys=True)
            again = json.dumps(report_data(rows, by=by, registry=registry), indent=2,
                               sort_keys=True)
            self.assertEqual(first, again, by)


ORDER_DETECTOR = """version: 1

detectors:
  - id: fixture/commit-then-push
    rule: fixture
    event: session
    when:
      order:
        first: {git: {subcommand: commit}}
        then: {git: {subcommand: push}}
        within: 3
"""


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.detectors = os.path.join(self.tmp, "detectors.yaml")
        with open(self.detectors, "w") as fh:
            fh.write(ORDER_DETECTOR)

    def run_cli(self, *argv):
        out = io.StringIO()
        code = main(["report", "--root", FIXTURES, "--no-config", "--detectors",
                     self.detectors] + list(argv), out=out)
        return code, out.getvalue()

    def test_the_flag_sets_the_minimum(self):
        _, text = self.run_cli("--json", "--min-opportunities", "1")
        data = json.loads(text)
        self.assertEqual(data["min_opportunities"], 1)
        got = entry(data, "fixture/commit-then-push")
        # One commit and no push in the fixtures: one opportunity, not followed.
        self.assertEqual((got["opportunities"], got["followed"], got["compliance_rate"]),
                         (1, 0, 0.0))
        _, table = self.run_cli("--min-opportunities", "1")
        self.assertEqual(line(table, "fixture/commit-then-push").split()[5:9],
                         ["1", "0", "0", "0%"])

    def test_the_default_minimum_prints_no_rate(self):
        _, text = self.run_cli("--json")
        data = json.loads(text)
        self.assertEqual(data["min_opportunities"], 20)
        self.assertIsNone(entry(data, "fixture/commit-then-push")["compliance_rate"])
        _, table = self.run_cli()
        self.assertEqual(line(table, "fixture/commit-then-push").split()[8], "-")

    def test_json_is_byte_identical_across_two_runs(self):
        self.assertEqual(self.run_cli("--json", "--by", "repo")[1],
                         self.run_cli("--json", "--by", "repo")[1])
        self.assertEqual(self.run_cli("--json")[1], self.run_cli("--json")[1])


if __name__ == "__main__":
    unittest.main()
