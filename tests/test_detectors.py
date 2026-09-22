# SPDX-License-Identifier: MIT
"""Corpus tests for the shipped detectors.

`CASES` is keyed by detector id and holds `(events, expected_hits)` pairs. A test asserts
that every detector in the default registry has at least one case that hits and one that
does not, so a detector cannot ship without evidence on both sides.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import FAKE_KEY, bash, compact, prompt, say, tool_use
from ruleprobe import DEFAULT, Detector, analyse, counts, run
from ruleprobe.shell import MAX_COMMAND

HUGE = "echo " + "x" * (100 * 1024)

CASES = {
    "transcript-hygiene/whole-file-cat": [
        ([bash("cat docs/how-it-works.md")], 1),
        ([bash("cat a | head -20")], 0),
        ([bash("cat <<EOF > out.txt\nbody\nEOF")], 0),
        ([bash("sed -n '1,40p' docs/how-it-works.md")], 0),
        ([bash("cat a b")], 0),
        ([bash("cat \\\n  foo.txt | grep x")], 0),
        ([bash("cat \\\n  foo.txt")], 1),
    ],
    "transcript-hygiene/unfiltered-find": [
        ([bash("find .")], 1),
        ([bash("find . -name x")], 0),
        ([bash("find . | head -20")], 0),
        ([bash("find src -type f -maxdepth 2")], 0),
        ([bash("find . -regex '.*py'")], 0),
        ([bash("find . -exec cat {} \\;")], 0),
        ([bash("find . > list.txt")], 0),
    ],
    "verification/no-verify": [
        ([bash("git commit --no-verify -m 'feat(x): y'")], 1),
        ([bash("cd x && git commit --no-verify")], 1),
        ([bash("git commit -n -m 'feat(x): y'")], 1),
        ([bash("SKIP=ruff git commit -m 'feat(x): y'")], 1),
        ([bash("SKIP=ruff pre-commit run --all-files")], 1),
        ([bash("git -c core.hooksPath=/dev/null commit -m 'feat(x): y'")], 1),
        ([bash("git commit -m 'feat(x): y'")], 0),
        ([bash("git push -n origin main")], 0),
        # The flag and the assignment named, not used: an argument to another command.
        ([bash("grep -rn 'SKIP=' docs/")], 0),
        ([bash("grep -rn -- --no-verify docs/")], 0),
        ([bash("rg 'core.hooksPath=' docs/")], 0),
    ],
    "secrets/secret-in-write": [
        ([tool_use("Write", {"file_path": "a.py", "content": "KEY = '%s'\n" % FAKE_KEY})], 1),
        ([tool_use("Edit", {"file_path": "a.py", "new_string": "key = '%s'" % FAKE_KEY})], 1),
        ([bash("cat > .env <<EOF\nAWS_ACCESS_KEY_ID=%s\nEOF" % FAKE_KEY)], 1),
        ([tool_use("Write", {"file_path": "a.py", "content": "KEY = os.environ['AWS_KEY']\n"})], 0),
        ([bash("cat > a.txt <<EOF\nnothing secret\nEOF")], 0),
    ],
    "cache-hygiene/compact": [
        ([compact(), prompt(turn=2)], 1),
        ([compact(), compact(turn=2)], 2),
        ([prompt(), say("a")], 0),
    ],
    "cache-hygiene/model-switch": [
        ([say("a", model="claude-opus-5"), say("b", turn=2, model="claude-sonnet-5")], 1),
        ([say("a", model="claude-opus-5"), say("b", turn=2, model="claude-opus-5")], 0),
        ([say("a", model="claude-opus-5"), say("b", turn=2, model="<synthetic>"),
          say("c", turn=3, model="claude-opus-5")], 0),
        ([say("a", model="")], 0),
    ],
}


class CorpusTests(unittest.TestCase):
    def test_every_detector_has_a_hitting_case_and_a_clean_one(self):
        for did in DEFAULT.ids():
            with self.subTest(detector=did):
                cases = CASES.get(did)
                self.assertTrue(cases, msg="no corpus case for %s" % did)
                self.assertTrue(any(n > 0 for _, n in cases), msg="no positive case")
                self.assertTrue(any(n == 0 for _, n in cases), msg="no negative case")

    def test_the_corpus_names_no_detector_the_registry_lacks(self):
        self.assertEqual(sorted(set(CASES) - set(DEFAULT.ids())), [])

    def test_every_case_yields_its_expected_hit_count(self):
        # strict=True re-raises: run() swallows a detector's exception at runtime, which
        # would otherwise let a detector that always raises pass every negative case.
        for did, cases in CASES.items():
            for i, (events, expected) in enumerate(cases):
                with self.subTest(detector=did, case=i):
                    hits = run(events, strict=True).get(did, [])
                    self.assertEqual(len(hits), expected)

    def test_a_hit_is_an_id_a_turn_and_a_tool_use_id_and_never_a_snippet(self):
        hits = run([bash("cat a.md", turn=3, id="tu9")])["transcript-hygiene/whole-file-cat"]
        self.assertEqual(list(hits[0]), ["transcript-hygiene/whole-file-cat", 3, "tu9"])
        for did, cases in CASES.items():
            for events, _ in cases:
                for one in run(events).get(did, []):
                    self.assertEqual(len(one), 3)
                    self.assertEqual(one.id, did)
                    self.assertIsInstance(one.turn, int)
                    self.assertTrue(one.tool_use_id is None
                                    or isinstance(one.tool_use_id, str))

    def test_detectors_with_no_hits_are_omitted(self):
        self.assertEqual(run([bash("git status")]), {})

    def test_every_shipped_detector_carries_an_id_a_rule_and_an_event_kind(self):
        for detector in DEFAULT:
            self.assertIn("/", detector.id)
            self.assertTrue(detector.rule and "/" not in detector.rule)
            self.assertTrue(callable(detector.fn))
            self.assertIsNone(detector.gate, msg="a shipped detector is always on")


class ErrorTests(unittest.TestCase):
    def test_a_raising_detector_is_swallowed_at_runtime_and_raised_under_strict(self):
        def boom(events, ctx):
            raise RuntimeError("detector is broken")

        registry = DEFAULT.copy()
        registry.add(Detector("test/boom", "test", "session", boom))
        errors = []
        self.assertEqual(run([bash("ls")], registry=registry, errors=errors), {})
        self.assertEqual(errors, [{"detector": "test/boom", "error": "RuntimeError"}])
        with self.assertRaises(RuntimeError):
            run([bash("ls")], registry=registry, strict=True)

    def test_the_shipped_registry_is_not_mutated_by_a_copy(self):
        registry = DEFAULT.copy()
        registry.add(Detector("test/extra", "test", "session", lambda e, c: []))
        self.assertNotIn("test/extra", DEFAULT)


class CountTests(unittest.TestCase):
    def test_counts_every_capped_tool_whether_or_not_a_detector_fires(self):
        events = [tool_use("WebSearch", {"query": "q"}, id="s%d" % i) for i in range(3)]
        events += [tool_use("Agent", {"prompt": "go"}, id="a1"),
                   tool_use("AskUserQuestion", {"questions": []}, id="q1"),
                   bash("ls")]
        self.assertEqual(counts(events), {"web_search": 3, "agent": 1, "ask_user": 1})

    def test_an_empty_session_counts_zero(self):
        self.assertEqual(counts([]), {"web_search": 0, "agent": 0, "ask_user": 0})

    def test_a_malformed_event_is_skipped_rather_than_fatal(self):
        events = ["not a dict", None, 7,
                  tool_use("WebSearch", {"query": "q"}, id="s1")]
        self.assertEqual(counts(events)["web_search"], 1)
        self.assertEqual(run(events), {})


class MalformedEventTests(unittest.TestCase):
    """A transcript is machine-written but not schema-checked. No shape may raise out of
    run(): a session that loses its record loses the whole report, not one detector."""

    SHAPES = [
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash", "input": {"command": 5}},
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash",
         "input": {"command": ["cat", "x"]}},
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash",
         "input": {"command": b"cat x"}},
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash", "input": "cat x"},
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Agent", "input": {"prompt": 7}},
        {"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Write", "input": {"content": None}},
        {"kind": "assistant_text", "turn": 1, "final": True, "text": 3, "model": 9},
        {"kind": "tool_result", "turn": 1, "tool_name": "Agent", "text": None},
    ]

    def test_no_shape_raises_and_no_detector_fires(self):
        for shape in self.SHAPES:
            with self.subTest(shape=str(shape.get("input", shape))[:40]):
                for strict in (False, True):
                    self.assertEqual(run([shape], strict=strict), {})

    def test_the_whole_event_list_may_be_the_wrong_shape(self):
        for events in (None, 7, "not events", {"kind": "tool_use"}):
            with self.subTest(events=str(events)):
                self.assertEqual(run(events), {})
                self.assertEqual(run(events, strict=True), {})

    def test_a_malformed_event_does_not_hide_a_real_one(self):
        events = self.SHAPES + [bash("cat a.md", id="tu9")]
        self.assertIn("transcript-hygiene/whole-file-cat", run(events, strict=True))


class ParseBudgetTests(unittest.TestCase):
    def test_an_oversized_command_is_never_tokenized(self):
        parsed = analyse([bash(HUGE)]).bash[0]
        self.assertTrue(parsed.skipped)
        self.assertEqual(parsed.pipelines, [])
        self.assertGreater(len(HUGE), MAX_COMMAND)

    def test_an_oversized_command_yields_no_shell_hits_but_is_still_scanned_for_secrets(self):
        self.assertEqual(run([bash("cat " + "x" * MAX_COMMAND)], strict=True), {})
        leaky = bash("echo " + "x" * MAX_COMMAND + " " + FAKE_KEY)
        self.assertIn("secrets/secret-in-write", run([leaky], strict=True))

    def test_each_bash_command_is_parsed_once_for_every_detector(self):
        events = [bash("git commit -m 'feat(x): y'"), bash("cat a.md", id="tu2")]
        ctx = analyse(events)
        self.assertEqual([p.event for p in ctx.bash], events)


if __name__ == "__main__":
    unittest.main()
