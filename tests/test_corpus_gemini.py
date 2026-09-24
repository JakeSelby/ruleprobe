# SPDX-License-Identifier: MIT
"""The Gemini CLI sessions in the shipped corpus, and what they must keep measuring.

Runtime-neutral is a claim the corpus makes true: every detector that can fire on a Gemini
session is labelled on those sessions with five positives and five near-misses, and meets the
floor on them alone. Two cannot fire, by the reader's design, and are left out: `cache-hygiene/compact`, because
Gemini's history rewrite is not told apart from truncation, and `cache-hygiene/model-switch`,
because a Gemini event carries no model.

Run: python3 -m unittest discover -s tests
"""
import os
import unittest

from ruleprobe import DEFAULT
from ruleprobe.rules import catalog_detectors
from ruleprobe.registry import Registry
from ruleprobe.validity import DEFAULT_FLOOR, below_floor, load_corpus, score_corpus

NOT_ON_GEMINI = ("cache-hygiene/compact", "cache-hygiene/model-switch")


def _registry():
    """The shipped detectors and every catalog entry, as `ruleprobe corpus` scores them."""
    registry = Registry(list(DEFAULT))
    for detector in catalog_detectors():
        if detector.id not in registry.ids():
            registry.add(detector)
    return registry


class GeminiCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("RULEPROBE_CORPUS", None)
        cls.registry = _registry()
        cls.gemini = [c for c in load_corpus() if c.session.runtime == "gemini"]
        cls.scores = score_corpus(cls.registry, corpus=cls.gemini)

    def by_name(self, name):
        return [c for c in self.gemini if c.name == name][0]

    def test_every_applicable_detector_has_five_positives_and_five_near_misses_on_gemini(self):
        for detector_id in self.registry.ids():
            if detector_id in NOT_ON_GEMINI:
                continue
            score = self.scores[detector_id]
            with self.subTest(detector=detector_id):
                self.assertGreaterEqual(score.positives, 5)
                self.assertGreaterEqual(score.negatives, 5)

    def test_every_applicable_detector_meets_the_floor_on_gemini_alone(self):
        self.assertEqual(below_floor(self.scores, DEFAULT_FLOOR), [])

    def test_a_posix_root_reads_the_shell_as_bash_and_a_windows_root_keeps_it_native(self):
        posix = self.by_name("gemini-shell.jsonl").session
        windows = self.by_name("gemini-windows.jsonl").session
        self.assertEqual(posix.repo, "example-repo")
        self.assertEqual(windows.repo, "example-repo-win")
        names = lambda s: set(e["name"] for e in s.events if e["kind"] == "tool_use")
        self.assertIn("Bash", names(posix))
        self.assertNotIn("run_shell_command", names(posix))
        self.assertIn("run_shell_command", names(windows))
        self.assertNotIn("Bash", names(windows))

    def test_a_tool_response_record_starts_no_turn(self):
        # Each session writes a functionResponse `user` record after every tool call, and
        # the prompts alone number the turns: five prompts, five turns.
        for name, prompts in (("gemini-shell.jsonl", 5), ("gemini-git.jsonl", 5),
                              ("gemini-windows.jsonl", 2)):
            events = self.by_name(name).session.events
            with self.subTest(session=name):
                turns = [e["turn"] for e in events if e["kind"] == "user_prompt"]
                self.assertEqual(turns, list(range(1, prompts + 1)))
                self.assertEqual(max(e["turn"] for e in events), prompts)

    def test_a_prompt_straight_after_a_tool_response_opens_the_next_turn(self):
        events = self.by_name("gemini-shell.jsonl").session.events
        at = [i for i, e in enumerate(events)
              if e["kind"] == "user_prompt" and e["turn"] == 3][0]
        self.assertEqual(events[at - 1]["kind"], "tool_result")
        self.assertEqual(events[at - 1]["turn"], 2)


if __name__ == "__main__":
    unittest.main()
