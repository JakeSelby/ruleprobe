# SPDX-License-Identifier: MIT
"""Opportunities and hits agree, for every compiled detector over every session we hold.

An `absent` hit is an opportunity not followed and an `order` hit is a followed one, so over
any event list `hits == opportunities - followed` for `absent` and `hits == followed` for
`order`, where `opportunities` leaves out the undecided ones. The sessions are the labelled
corpus, the fixture transcripts and every compiled detector's own `examples:` cases. No
shipped detector counts opportunities yet, so the detectors checked are the shipped ones, the
rule files under `docs/rules` and the ones below, which read the same sessions.

Run: python3 -m unittest discover -s tests
"""
import os
import unittest

from corpus import bash
from ruleprobe import Registry, analyse, iter_sessions, load_bundle, run
from ruleprobe.declarative import load
from ruleprobe.matchers import compile_detector
from ruleprobe.shell import MAX_COMMAND
from ruleprobe.validity import load_corpus
from test_readers import FIXTURES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_YAML = os.path.join(ROOT, "ruleprobe", "detectors", "common.yaml")
UNREAD = "git push origin 'main"
TOO_LONG = "pytest -q -k " + "x" * MAX_COMMAND

SPECS = [
    ("order", {"id": "o/commit-then-push", "event": "session", "when": {"order": {
        "first": {"git": {"subcommand": "commit"}},
        "then": {"git": {"subcommand": "push"}}, "within": 3}}}),
    ("order", {"id": "o/cat-then-filter", "event": "session", "when": {"order": {
        "first": {"command": {"name": "cat"}},
        "then": {"command": {"name": ["grep", "sed", "head"]}}, "within": 2}}}),
    ("order", {"id": "o/push-then-log", "event": "session", "when": {"order": {
        "first": {"git": {"subcommand": "push"}},
        "then": {"git": {"subcommand": "log"}}, "within": 5}},
        "examples": {"fire": [{"events": [{"kind": "tool_use", "name": "Bash", "id": "tu1",
                                           "input": {"command": "git push"}},
                                          {"kind": "tool_use", "name": "Bash", "id": "tu2",
                                           "input": {"command": "git log"}}]}],
                     "skip": [{"events": [{"kind": "tool_use", "name": "Bash", "id": "tu1",
                                           "input": {"command": UNREAD}},
                                          {"kind": "tool_use", "name": "Bash", "id": "tu2",
                                           "input": {"command": "git log"}}],
                               "note": "the push nobody could read"}]}}),
    ("absent", {"id": "a/push-per-turn", "event": "session", "when": {"absent": {
        "of": {"git": {"subcommand": "push"}}, "scope": "turn"}}}),
    ("absent", {"id": "a/test-per-turn", "event": "session", "when": {"absent": {
        "of": {"command": {"name": ["pytest", "python"]}}, "scope": "turn"}},
        "examples": {"fire": [{"bash": "ls"}],
                     "skip": [{"bash": "pytest -q"},
                              {"bash": TOO_LONG, "note": "a test run nobody could read"}]}}),
    ("absent", {"id": "a/write-per-turn", "event": "session", "when": {"absent": {
        "of": {"tool": ["Write", "Edit"]}, "scope": "turn"}}}),
]

#: Sessions that put the undecided cases in front of every detector above.
UNDECIDED = [
    [bash(UNREAD, turn=1, id="tu1"), bash("git log", turn=1, id="tu2")],
    [bash("git commit -m a", turn=1, id="tu1"), bash(UNREAD, turn=1, id="tu2")],
    [bash(TOO_LONG, turn=1, id="tu1"), bash("ls", turn=2, id="tu2")],
]


def compiled():
    """`(polarity or None, detector)` for every detector this test compiles."""
    out = [(kind, compile_detector(dict(spec, rule=spec["id"].split("/")[0]), "<test>"))
           for kind, spec in SPECS]
    document, lines = load(COMMON_YAML)
    out.extend((None, compile_detector(entry, COMMON_YAML, lines))
               for entry in document["detectors"])
    bundle = load_bundle(rules_dir=os.path.join(ROOT, "docs", "rules"), config=False)
    assert not bundle.findings, bundle.findings
    out.extend((None, detector) for detector in bundle.detectors)
    return out


def sessions(detectors):
    out = [labelled.session.events for labelled in load_corpus()]
    out.extend(session.events for session in iter_sessions(root=FIXTURES))
    for _kind, detector in detectors:
        if detector.examples:
            out.extend(events for _note, events in
                       list(detector.examples.fire) + list(detector.examples.skip))
    return out + UNDECIDED


class IdentityTests(unittest.TestCase):
    def test_hits_are_what_the_opportunities_say_for_every_compiled_detector(self):
        detectors = compiled()
        totals = {"order": [0, 0, 0, 0], "absent": [0, 0, 0, 0]}
        for kind, detector in detectors:
            if detector.opportunities is None:
                continue
            self.assertIn(kind, totals, "%s counts opportunities; name its polarity here"
                          % detector.id)
            one = Registry([detector])
            for index, events in enumerate(sessions(detectors)):
                with self.subTest(detector=detector.id, session=index):
                    ctx = analyse(events)
                    found = detector.opportunities(ctx.events, ctx)
                    for triple in found:
                        self.assertIn(triple[2], (True, False, None))
                    followed = sum(1 for t in found if t[2] is True)
                    undecided = sum(1 for t in found if t[2] is None)
                    opportunities = len(found) - undecided
                    hits = len(run(events, registry=one, strict=True).get(detector.id, []))
                    if kind == "absent":
                        self.assertEqual(hits, opportunities - followed)
                    else:
                        self.assertEqual(hits, followed)
                    for i, n in enumerate((opportunities, followed, undecided, hits)):
                        totals[kind][i] += n
        for kind, (opportunities, followed, undecided, hits) in totals.items():
            with self.subTest(kind=kind):
                # Not vacuous: each kind saw followed, not-followed and undecided ones.
                self.assertGreater(followed, 0)
                self.assertGreater(opportunities - followed, 0)
                self.assertGreater(undecided, 0)

    def test_only_order_and_turn_scoped_absent_count_opportunities(self):
        for kind, detector in compiled():
            with self.subTest(detector=detector.id):
                self.assertEqual(detector.opportunities is not None, kind is not None)


if __name__ == "__main__":
    unittest.main()
