# SPDX-License-Identifier: MIT
"""The report: the denominator, the notes, and the three groupings."""
import inspect
import json
import os
import unittest
from unittest import mock

from corpus import bash, prompt
from ruleprobe import (DEFAULT, Detector, Registry, compile_detector, contract_data, matchers,
                       measure, report, run)
from ruleprobe.events import Hit, Session
from ruleprobe.readers import claude_code
from ruleprobe.report import (KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION, errored_detectors,
                              folded_rules, report_data)
from test_readers import CLAUDE
from test_registry import traced_file_reads


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


def line_for(text, detector_id):
    return [x for x in text.split("\n") if x.split() and x.split()[0] == detector_id]


class PersistedFoldTests(unittest.TestCase):
    """Rows stored under a retired id count under the current one, however it was retired."""

    def test_a_shipped_rename_folds_with_no_map_of_your_own(self):
        rows = [row({"a/gone": 2, "a/one": 1}), row({"a/gone": 4})]
        with mock.patch.dict(contract_data.RENAMED, {"a/gone": "a/one"}):
            data = report_data(rows, registry=REGISTRY)
            text = report(rows, registry=REGISTRY)
            self.assertEqual(folded_rules(rows[0], REGISTRY.fold_map()), {"a/one": 3})
        entry = [d for d in data["detectors"] if d["detector"] == "a/one"][0]
        self.assertEqual((entry["hits"], entry["sessions"], entry["of"]), (7, 2, 2))
        self.assertNotIn("a/gone", [d["detector"] for d in data["detectors"]])
        self.assertEqual(line_for(text, "a/one")[0].split()[1:3], ["7", "2"])
        self.assertEqual(line_for(text, "a/gone"), [])

    def test_a_chain_of_renames_folds_to_its_end(self):
        registry = REGISTRY.copy().rename("a/older", "a/old").rename("a/old", "a/one")
        rows = [row({"a/older": 1}), row({"a/old": 2}), row({"a/one": 4})]
        self.assertEqual(folded_rules(rows[0], registry.fold_map()), {"a/one": 1})
        data = report_data(rows, registry=registry)
        self.assertEqual([(d["detector"], d["hits"], d["sessions"]) for d in data["detectors"]],
                         [("a/one", 7, 3), ("a/two", 0, 0)])

    def test_a_chain_across_the_shipped_and_the_consumer_map_folds_to_its_end(self):
        rows = [row({"a/gone": 1}, repo="r"), row({"a/old": 2}, repo="r")]
        with mock.patch.dict(contract_data.RENAMED, {"a/gone": "a/old"}):
            registry = REGISTRY.copy().rename("a/old", "a/one")
            data = report_data(rows, by="repo", registry=registry)
        self.assertEqual(data["groups"][0]["top"], [["a/one", 3]])

    def test_a_raw_chained_map_folds_to_its_end_without_the_shipped_map(self):
        raw = {"a/older": "a/old", "a/old": "a/one"}
        errored = row({}, rules_errors=[{"detector": "a/older", "error": "KeyError"}])
        with mock.patch.dict(contract_data.RENAMED, {"a/one": "a/two"}):
            self.assertEqual(folded_rules(row({"a/older": 1, "a/old": 2}), raw), {"a/one": 3})
            self.assertEqual(errored_detectors(errored, raw), {"a/one"})

    def test_an_error_under_a_retired_id_is_charged_to_the_current_one(self):
        registry = REGISTRY.copy().rename("a/older", "a/old").rename("a/old", "a/one")
        errored = row({"a/two": 1}, rules_errors=[{"detector": "a/older", "error": "KeyError"}])
        self.assertEqual(errored_detectors(errored, registry.fold_map()), {"a/one"})
        data = report_data([row({"a/one": 1}), errored], registry=registry)
        self.assertEqual(data["errors"], {"a/one": 1})
        entry = [d for d in data["detectors"] if d["detector"] == "a/one"][0]
        self.assertEqual(entry["of"], 1)


class EmittedFoldMapTests(unittest.TestCase):
    def test_the_result_carries_the_effective_fold_map(self):
        registry = REGISTRY.copy().rename("a/older", "a/old").rename("a/old", "a/one")
        with mock.patch.dict(contract_data.RENAMED, {"a/gone": "a/two"}):
            for by in ("rule", "repo", "stance"):
                with self.subTest(by=by):
                    data = report_data([row({"a/one": 1})], by=by, registry=registry)
                    self.assertEqual(data["renamed"], {"a/gone": "a/two", "a/old": "a/one",
                                                       "a/older": "a/one"})
            self.assertEqual(report_data([], registry=registry)["renamed"]["a/older"], "a/one")

    def test_a_stored_result_folds_a_retired_id_with_no_registry(self):
        registry = REGISTRY.copy().rename("a/older", "a/old").rename("a/old", "a/one")
        stored = json.dumps(report_data([row({"a/one": 1})], registry=registry))
        # A reader with no registry and no ruleprobe: the saved map is the whole fold.
        renamed = json.loads(stored)["renamed"]
        stored_row = {"a/older": 2, "a/one": 1}
        folded = {}
        for did, n in stored_row.items():
            folded[renamed.get(did, did)] = folded.get(renamed.get(did, did), 0) + n
        self.assertEqual(folded, {"a/one": 3})

    def test_a_consumer_undo_of_a_shipped_rename_holds_through_report_data(self):
        registry = Registry(list(REGISTRY), renamed={"a/old": "a/old"})
        rows = [row({"a/old": 2, "a/one": 1}), row({"a/old": 1})]
        with mock.patch.dict(contract_data.RENAMED, {"a/old": "a/one"}):
            data = report_data(rows, registry=registry)
        hits = dict((d["detector"], d["hits"]) for d in data["detectors"])
        self.assertEqual(hits, {"a/old": 3, "a/one": 1, "a/two": 0})
        # The emitted map shows the override, and applied as it stands it moves nothing.
        self.assertEqual(data["renamed"], {"a/old": "a/old"})
        self.assertEqual(folded_rules(rows[0], data["renamed"]), {"a/old": 2, "a/one": 1})

    def test_the_emitted_map_agrees_with_the_counts_under_a_shipped_chain(self):
        registry = REGISTRY.copy().rename("a/old", "a/one")
        rows = [row({"a/gone": 2}), row({"a/old": 1})]
        with mock.patch.dict(contract_data.RENAMED, {"a/gone": "a/old"}):
            data = report_data(rows, registry=registry)
        self.assertEqual(data["renamed"], {"a/gone": "a/one", "a/old": "a/one"})
        stored = {}
        for r in rows:
            for did, n in r["rules"].items():
                key = data["renamed"].get(did, did)
                stored[key] = stored.get(key, 0) + n
        hits = dict((d["detector"], d["hits"]) for d in data["detectors"] if d["hits"])
        self.assertEqual(hits, stored)

    def test_no_rename_emits_an_empty_map(self):
        self.assertEqual(report_data([row({"a/one": 1})], registry=REGISTRY)["renamed"], {})


class NoFileReadTests(unittest.TestCase):
    def test_report_data_reads_no_file(self):
        registry = REGISTRY.copy().rename("a/old", "a/one")
        rows = [row({"a/old": 1}), row({"a/one": 2}, schema_version=2),
                row({}, rules_errors=[{"detector": "a/old", "error": "KeyError"}])]
        with traced_file_reads() as seen:
            for by in ("rule", "repo", "stance"):
                report_data(rows, by=by, registry=registry)
            report(rows, registry=registry)
        self.assertEqual(seen, [])


UNREAD_PUSH = "git push origin 'main"
README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "README.md")


def fixed(*triples):
    """An `opportunities` callable returning `triples` whatever it is handed."""
    return lambda events, ctx: list(triples)


def never_called(test):
    def opportunities(events, ctx):
        test.fail("opportunities was called for a gated-off detector")
    return opportunities


class ComplianceTests(unittest.TestCase):
    def session(self):
        return claude_code.read(CLAUDE)

    def test_followed_not_followed_and_undecided_are_counted_apart(self):
        registry = Registry([Detector("a/opp", "a", "session", lambda e, c: [],
                                      opportunities=fixed((1, "t1", True), (1, "t2", False),
                                                          (2, "t3", None), (2, "t4", True)))])
        measured = measure(self.session(), registry=registry)
        # The undecided triple is in `undecided` only: three opportunities, not four.
        self.assertEqual(measured["compliance"],
                         {"a/opp": {"opportunities": 3, "followed": 2, "undecided": 1}})
        self.assertNotIn("rules_errors", measured)

    def test_a_compiled_order_detector_is_counted_over_its_own_session(self):
        detector = compile_detector({"id": "o/commit-then-push", "event": "session",
                                     "when": {"order": {
                                         "first": {"git": {"subcommand": "commit"}},
                                         "then": {"git": {"subcommand": "push"}},
                                         "within": 3}}})
        events = [bash("git commit -m a", turn=1, id="tu1"), bash("git push", turn=1, id="tu2"),
                  bash("git commit -m b", turn=2, id="tu3"), bash(UNREAD_PUSH, turn=2, id="tu4"),
                  prompt(turn=3), bash("git commit -m c", turn=3, id="tu5")]
        session = Session("s", "demo", "claude-code", events, None, None, None)
        measured = measure(session, registry=Registry([detector]))
        # Followed at tu1 and not followed at tu5. The command nobody could read at tu4 leaves
        # tu3 undecided, and is an undecided opening of its own: two opportunities, two
        # undecided, and neither undecided one counted as not followed.
        self.assertEqual(measured["compliance"], {"o/commit-then-push": {
            "opportunities": 2, "followed": 1, "undecided": 2}})
        # An `order` hit is a followed opportunity.
        self.assertEqual(measured["rules"], {"o/commit-then-push": 1})

    def test_a_detector_with_no_opportunities_has_no_entry(self):
        registry = Registry([Detector("a/plain", "a", "session", lambda e, c: []),
                             Detector("a/opp", "a", "session", lambda e, c: [],
                                      opportunities=fixed((1, "t1", True)))])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(sorted(measured["compliance"]), ["a/opp"])

    def test_a_row_with_no_opportunity_defining_detector_has_no_compliance_key(self):
        registry = Registry([Detector("a/plain", "a", "session", lambda e, c: [])])
        self.assertNotIn("compliance", measure(self.session(), registry=registry))

    def test_a_gated_off_detector_is_never_asked_for_opportunities(self):
        registry = Registry([
            Detector("a/gated", "a", "session", lambda e, c: [], ("commits", None),
                     opportunities=never_called(self)),
            Detector("a/on", "a", "session", lambda e, c: [],
                     opportunities=fixed((1, "t1", False)))])
        measured = measure(self.session(), stances={"commits": "off"}, registry=registry)
        self.assertEqual(measured["compliance"],
                         {"a/on": {"opportunities": 1, "followed": 0, "undecided": 0}})
        # Gated off alone, it leaves no compliance key at all.
        alone = Registry([registry.get("a/gated")])
        self.assertNotIn("compliance", measure(self.session(), registry=alone))

    def test_a_gate_that_allows_the_stance_calls_it(self):
        registry = Registry([Detector("a/gated", "a", "session", lambda e, c: [],
                                      ("commits", ("conventional",)),
                                      opportunities=fixed((1, "t1", True)))])
        measured = measure(self.session(), stances={"commits": "conventional"},
                           registry=registry)
        self.assertEqual(measured["compliance"]["a/gated"]["followed"], 1)

    def test_a_raising_opportunities_costs_only_its_own_compliance_entry(self):
        def boom(events, ctx):
            raise ValueError("no")

        registry = Registry([
            Detector("a/boom", "a", "session", lambda e, c: [(1, "t1")], opportunities=boom),
            Detector("a/fine", "a", "session", lambda e, c: [(1, "t1"), (2, "t2")],
                     opportunities=fixed((1, "t1", True)))])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(measured["rules_errors"], [
            {"detector": "a/boom", "error": "ValueError", "hook": "opportunities"}])
        self.assertEqual(measured["compliance"],
                         {"a/fine": {"opportunities": 1, "followed": 1, "undecided": 0}})
        self.assertEqual(measured["rules"], {"a/boom": 1, "a/fine": 2})
        # Its `fn` ran, so its hits and its denominator stand and the report is unchanged.
        data = report_data([measured], registry=registry)
        self.assertEqual([(d["detector"], d["hits"], d["of"]) for d in data["detectors"]],
                         [("a/boom", 1, 1), ("a/fine", 2, 1)])
        self.assertNotIn("raised", report([measured], registry=registry))

    def test_a_malformed_result_is_the_detectors_error(self):
        malformed = {
            "None": None,
            "a string": "abc",
            "a dict": {(1, "t1"): True},
            "not iterable": 5,
            "a pair": [(1, "t1")],
            "a four-tuple": [(1, "t1", True, "x")],
            "not a sequence": [{"turn": 1}],
            "an int for followed": [(1, "t1", 1)],
            "a string for followed": [(1, "t1", "yes")],
            "one bad triple among good": [(1, "t1", True), (2, "t2", 0)],
        }
        for label, result in sorted(malformed.items()):
            with self.subTest(label):
                registry = Registry([
                    Detector("a/bad", "a", "session", lambda e, c: [],
                             opportunities=lambda e, c, result=result: result),
                    Detector("a/fine", "a", "session", lambda e, c: [],
                             opportunities=fixed((1, "t1", None)))])
                measured = measure(self.session(), registry=registry)
                self.assertEqual(measured["rules_errors"], [
                    {"detector": "a/bad", "error": "MalformedOpportunities",
                     "hook": "opportunities"}])
                self.assertEqual(measured["compliance"],
                                 {"a/fine": {"opportunities": 0, "followed": 0,
                                             "undecided": 1}})

    def test_a_typeerror_the_callable_raises_is_not_called_malformed(self):
        def broken(events, ctx):
            raise TypeError("a bug of its own")

        registry = Registry([Detector("a/bad", "a", "session", lambda e, c: [],
                                      opportunities=broken)])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(measured["rules_errors"], [
            {"detector": "a/bad", "error": "TypeError", "hook": "opportunities"}])

    def test_an_empty_result_or_a_tuple_of_lists_is_well_formed(self):
        registry = Registry([
            Detector("a/empty", "a", "session", lambda e, c: [], opportunities=fixed()),
            Detector("a/lists", "a", "session", lambda e, c: [],
                     opportunities=lambda e, c: ([1, "t1", False], [2, None, True]))])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(measured["compliance"], {
            "a/empty": {"opportunities": 0, "followed": 0, "undecided": 0},
            "a/lists": {"opportunities": 2, "followed": 1, "undecided": 0}})
        self.assertNotIn("rules_errors", measured)

    def test_a_raising_fn_leaves_its_compliance_standing(self):
        def boom(events, ctx):
            raise KeyError("no")

        registry = Registry([Detector("a/boom", "a", "session", boom,
                                      opportunities=fixed((1, "t1", False)))])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(measured["rules_errors"], [{"detector": "a/boom", "error": "KeyError"}])
        self.assertEqual(measured["compliance"],
                         {"a/boom": {"opportunities": 1, "followed": 0, "undecided": 0}})

    def test_detectors_are_asked_in_id_order_whatever_the_registration_order(self):
        asked = []

        def record(detector_id):
            def opportunities(events, ctx):
                asked.append(detector_id)
                raise RuntimeError(detector_id)
            return opportunities

        registry = Registry([Detector(did, "a", "session", lambda e, c: [],
                                      opportunities=record(did))
                             for did in ("a/zeta", "a/alpha", "a/mid")])
        measured = measure(self.session(), registry=registry)
        self.assertEqual(asked, ["a/alpha", "a/mid", "a/zeta"])
        self.assertEqual([e["detector"] for e in measured["rules_errors"]], asked)
        self.assertEqual(measured["compliance"], {})

    def test_a_compiled_detector_evaluates_once_per_session(self):
        specs = [{"id": "o/commit-then-push", "event": "session", "when": {"order": {
                     "first": {"git": {"subcommand": "commit"}},
                     "then": {"git": {"subcommand": "push"}}, "within": 3}}},
                 {"id": "a/test-per-turn", "event": "session", "when": {"absent": {
                     "of": {"command": {"name": "pytest"}}, "scope": "turn"}}}]
        registry = Registry([compile_detector(spec) for spec in specs])
        events = [bash("git commit -m a", turn=1, id="tu1"), bash("git push", turn=1, id="tu2"),
                  prompt(turn=2), bash("pytest -q", turn=2, id="tu3")]
        session = Session("s", "demo", "claude-code", events, None, None, None)
        with mock.patch.object(matchers, "_Env", wraps=matchers._Env) as env:
            measured = measure(session, registry=registry)
        # One evaluation per detector: `fn` and `opportunities` read the same one.
        self.assertEqual(env.call_count, 2)
        self.assertEqual(sorted(measured["compliance"]), ["a/test-per-turn",
                                                          "o/commit-then-push"])

    def test_opportunities_is_handed_the_context_fn_was(self):
        seen = {}

        def fn(events, ctx):
            seen["fn"] = (events, ctx)
            return []

        def pushes(events, ctx):
            seen["opportunities"] = (events, ctx)
            return [(p.turn, p.id, "--force" not in p.command)
                    for p in ctx.bash if p.command.startswith("git push")]

        events = [bash("git push", turn=1, id="tu1"), bash("git push --force", turn=2, id="tu2"),
                  bash("ls", turn=2, id="tu3")]
        session = Session("s", "demo", "claude-code", events, None, None, None)
        registry = Registry([Detector("a/force", "a", "bash", fn, opportunities=pushes)])
        measured = measure(session, registry=registry)
        self.assertEqual(measured["compliance"],
                         {"a/force": {"opportunities": 2, "followed": 1, "undecided": 0}})
        self.assertIs(seen["opportunities"][0], seen["fn"][0])
        self.assertIs(seen["opportunities"][1], seen["fn"][1])

    def test_run_is_unchanged_and_never_asks_for_opportunities(self):
        # The call shape the README declares, not a copy of today's signature.
        with open(README, encoding="utf-8") as handle:
            declared = [line.split("#")[0].strip() for line in handle
                        if line.startswith("run(")]
        self.assertEqual(len(declared), 1)
        actual = "run" + str(inspect.signature(run)).replace(repr(DEFAULT), "DEFAULT")
        self.assertEqual(actual, declared[0])
        registry = Registry([Detector("a/opp", "a", "session", lambda e, c: [(1, "t1")],
                                      opportunities=never_called(self))])
        errors = []
        hits = run(self.session().events, registry=registry, errors=errors)
        self.assertEqual(hits, {"a/opp": [Hit("a/opp", 1, "t1")]})
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
