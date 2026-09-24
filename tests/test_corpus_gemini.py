# SPDX-License-Identifier: MIT
"""The Gemini CLI sessions in the shipped corpus, and what they must keep measuring.

Runtime-neutral is a claim the corpus makes true: every detector that can fire on a Gemini
session carries five positives and five near-misses on the two sessions under a POSIX project
root, where the shell reads as `Bash`, and meets the floor there. The session under a Windows
root guards the mapping instead: its shell stays native, so no detector may read it. Two
detectors cannot fire on Gemini at all, by the reader's design: `cache-hygiene/compact`,
because Gemini's history rewrite is not told apart from truncation, and
`cache-hygiene/model-switch`, because a Gemini event carries no model.

Run: python3 -m unittest discover -s tests
"""
import os
import unittest
from unittest import mock

from ruleprobe import DEFAULT
from ruleprobe.registry import Registry, run
from ruleprobe.rules import catalog_detectors
from ruleprobe.validity import (DEFAULT_FLOOR, below_floor, hit_key, load_corpus,
                                score_corpus)

NOT_ON_GEMINI = ("cache-hygiene/compact", "cache-hygiene/model-switch")
POSIX = ("gemini-shell.jsonl", "gemini-git.jsonl")
WINDOWS = "gemini-windows.jsonl"


def _registry():
    """The shipped detectors and every catalog entry, folded as `ruleprobe corpus` folds
    them."""
    registry = Registry(list(DEFAULT))
    for detector in catalog_detectors(registry.fold_map()):
        if detector.id not in registry.ids():
            registry.add(detector)
    return registry


class GeminiCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch = mock.patch.dict(os.environ)
        patch.start()
        cls.addClassCleanup(patch.stop)
        os.environ.pop("RULEPROBE_CORPUS", None)
        cls.registry = _registry()
        cls.gemini = [c for c in load_corpus() if c.session.runtime == "gemini"]
        cls.posix = [c for c in cls.gemini if c.name in POSIX]

    def by_name(self, name):
        return [c for c in self.gemini if c.name == name][0]

    def applicable(self):
        return [d for d in self.registry.ids() if d not in NOT_ON_GEMINI]

    def test_the_posix_sessions_carry_five_positives_and_five_near_misses_per_detector(self):
        self.assertEqual(sorted(c.name for c in self.posix), sorted(POSIX))
        for detector_id in self.applicable():
            fire = sum(len(c.fire.get(detector_id, ())) for c in self.posix)
            near = sum(len(c.near.get(detector_id, ())) for c in self.posix)
            with self.subTest(detector=detector_id):
                self.assertGreaterEqual(fire, 5)
                self.assertGreaterEqual(near, 5)

    def test_every_applicable_detector_meets_the_floor_on_the_posix_sessions(self):
        scores = score_corpus(self.registry, corpus=self.posix)
        self.assertEqual(below_floor(scores, DEFAULT_FLOOR), [])
        for detector_id in self.applicable():
            with self.subTest(detector=detector_id):
                self.assertTrue(scores[detector_id].scored)

    def test_no_detector_reads_a_shell_call_under_a_windows_root(self):
        session = self.by_name(WINDOWS).session
        shell = set("%s:%s" % (e["turn"], e["id"]) for e in session.events
                    if e["kind"] == "tool_use" and e["name"] == "run_shell_command")
        self.assertTrue(shell)
        self.assertFalse([e for e in session.events if e.get("name") == "Bash"])
        hits = run(session.events, registry=self.registry, strict=True)
        for detector_id, found in hits.items():
            with self.subTest(detector=detector_id):
                self.assertFalse(set(hit_key(h) for h in found) & shell)
        self.assertEqual(sorted(hits), ["secrets/secret-in-write"])

    def test_compaction_and_model_switch_never_fire_on_gemini(self):
        for labelled in self.gemini:
            hits = run(labelled.session.events, registry=self.registry, strict=True)
            for detector_id in NOT_ON_GEMINI:
                with self.subTest(session=labelled.name, detector=detector_id):
                    self.assertEqual(hits.get(detector_id, []), [])

    def test_a_posix_root_reads_the_shell_as_bash_and_a_windows_root_keeps_it_native(self):
        posix = self.by_name("gemini-shell.jsonl").session
        windows = self.by_name(WINDOWS).session
        self.assertEqual(posix.repo, "example-repo")
        self.assertEqual(windows.repo, "example-repo-win")
        names = lambda s: set(e["name"] for e in s.events if e["kind"] == "tool_use")
        self.assertIn("Bash", names(posix))
        self.assertNotIn("run_shell_command", names(posix))
        self.assertIn("run_shell_command", names(windows))
        self.assertNotIn("Bash", names(windows))

    def test_a_tool_response_record_starts_no_turn(self):
        # Each session writes a functionResponse `user` record after every tool call, and
        # the prompts alone number the turns: one turn per prompt.
        for name, prompts in (("gemini-shell.jsonl", 5), ("gemini-git.jsonl", 5),
                              (WINDOWS, 2)):
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
