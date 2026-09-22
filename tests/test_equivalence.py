# SPDX-License-Identifier: MIT
"""The six shipped detectors, against the same six written as data.

`ruleprobe/detectors/common.py` is the reference: `ruleprobe/detectors/common.yaml` has to
produce the same hits, event for event, over every corpus case and over the fixture
transcripts. This is what makes the declarative format a re-expression of the engine rather
than a second, subtly different one.

Run: python3 -m unittest discover -s tests
"""
import os
import unittest

from ruleprobe import DEFAULT, Registry, iter_sessions, run
from ruleprobe.declarative import load
from ruleprobe.matchers import compile_detector
from test_detectors import CASES
from test_readers import FIXTURES

COMMON_YAML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "ruleprobe", "detectors", "common.yaml")


def declarative_registry():
    document, lines = load(COMMON_YAML)
    registry = Registry()
    for entry in document["detectors"]:
        registry.add(compile_detector(entry, COMMON_YAML, lines))
    return registry


class EquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.declarative = declarative_registry()

    def test_the_file_expresses_exactly_the_shipped_six(self):
        self.assertEqual(self.declarative.ids(), DEFAULT.ids())

    def test_every_corpus_case_gives_the_same_hits_both_ways(self):
        for did, cases in CASES.items():
            for i, (events, expected) in enumerate(cases):
                with self.subTest(detector=did, case=i):
                    python = run(events, registry=DEFAULT, strict=True).get(did, [])
                    data = run(events, registry=self.declarative, strict=True).get(did, [])
                    self.assertEqual(len(python), expected)
                    self.assertEqual(list(data), list(python))

    def test_the_fixture_transcripts_give_the_same_hits_both_ways(self):
        sessions = list(iter_sessions(root=FIXTURES))
        self.assertTrue(sessions, "no fixture transcripts to compare over")
        for session in sessions:
            with self.subTest(session=session.id):
                python = run(session.events, registry=DEFAULT, strict=True)
                data = run(session.events, registry=self.declarative, strict=True)
                self.assertEqual(dict((k, list(v)) for k, v in data.items()),
                                 dict((k, list(v)) for k, v in python.items()))

    def test_a_malformed_event_is_no_more_fatal_to_a_declarative_detector(self):
        from test_detectors import MalformedEventTests
        for shape in MalformedEventTests.SHAPES:
            with self.subTest(shape=str(shape.get("input", shape))[:40]):
                self.assertEqual(run([shape], registry=self.declarative, strict=True), {})

    def test_the_declarative_six_carry_the_same_rule_names(self):
        for shipped in DEFAULT:
            self.assertEqual(self.declarative.get(shipped.id).rule, shipped.rule)


if __name__ == "__main__":
    unittest.main()
