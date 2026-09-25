# SPDX-License-Identifier: MIT
"""The labelled corpus, and what it says about each detector.

Three separate things are under test here and they fail for different reasons:

- the *loader*, which must refuse a broken corpus loudly rather than score against it;
- the *arithmetic*, checked against one case computed by hand rather than by the code;
- the *shipped corpus itself*, which must keep at least five positives and five negatives
  for every detector the package ships, or the number beside that detector is not evidence.

Run: python3 -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from ruleprobe import DEFAULT, Registry, contract_data
from ruleprobe.cli import main
from ruleprobe.detectors.catalog import ENTRIES
from ruleprobe.matchers import compile_detector
from ruleprobe.registry import Detector
from ruleprobe.validity import (BINDING_RECALL_FLOOR, ZOO_FILE, CorpusError, DEFAULT_FLOOR,
                                Score, below_floor, binding_as_dict, binding_failures,
                                binding_table, corpus_dir, event_key, hit_key, load_corpus,
                                load_zoo, score_binding, score_corpus, score_examples,
                                scores_as_dict, total, validity, validity_note,
                                validity_table)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")


def cc_lines(events):
    """A Claude Code transcript holding `events`, as a list of JSONL lines.

    `events` is a list of `("prompt", None)` or `("bash", (id, command))` pairs, which is
    every shape these tests need: a turn boundary and a tool use in it.
    """
    lines = []
    for index, (kind, payload) in enumerate(events):
        stamp = "2026-01-01T00:00:%02d.000Z" % index
        head = {"timestamp": stamp, "sessionId": "t", "cwd": "/workspace/example-repo"}
        if kind == "prompt":
            head.update({"type": "user", "message": {"role": "user", "content": "go"}})
        else:
            use_id, command = payload
            head.update({"type": "assistant",
                         "message": {"id": "msg-%d" % index, "model": "m",
                                     "content": [{"type": "tool_use", "id": use_id,
                                                  "name": "Bash",
                                                  "input": {"command": command}}]}})
        lines.append(json.dumps(head))
    return lines


#: The one session the arithmetic case runs over: four Bash calls across two turns, three
#: of which are a bare `cat`.
CASE_EVENTS = [("prompt", None),
               ("bash", ("tu-a", "cat alpha.txt")),
               ("bash", ("tu-b", "cat beta.txt")),
               ("prompt", None),
               ("bash", ("tu-c", "sed -n 1,5p gamma.txt")),
               ("bash", ("tu-d", "cat delta.txt"))]

#: Labels deliberately out of step with the detector, so every cell of the tally is
#: exercised: one hit that was wanted, two that were not, one want that never happened.
CASE_LABELS = """version: 1
sessions:
  - session: case.jsonl
    labels:
      - at: "1:tu-a"
        fire: [x/cat]
      - at: "1:tu-b"
        near: [x/cat]
      - at: "2:tu-c"
        fire: [x/cat]
        note: a want the detector cannot meet, which is a false negative
      - at: "2:tu-d"
        note: an unremarkable event, so a hit here is a false positive
"""

CAT = {"id": "x/cat", "rule": "x", "event": "tool_use",
       "when": {"command": {"starts_with": "cat"}}}


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def corpus(self, labels, sessions):
        """A corpus directory of my own: `labels.yaml` and `sessions/<name>.jsonl`.

        Each call gets a directory of its own, so one test may build two corpora.
        """
        base = tempfile.mkdtemp(dir=self.dir)
        os.mkdir(os.path.join(base, "sessions"))
        with open(os.path.join(base, "labels.yaml"), "w") as handle:
            handle.write(labels)
        for name, lines in sessions.items():
            with open(os.path.join(base, "sessions", name), "w") as handle:
                handle.write("\n".join(lines) + "\n")
        return base


class KeyTests(unittest.TestCase):
    """The key a label and a hit have to agree on."""

    def test_a_tool_use_is_keyed_by_its_id(self):
        self.assertEqual(event_key({"kind": "tool_use", "turn": 3, "id": "tu-1"}), "3:tu-1")

    def test_anything_else_is_keyed_by_its_turn_alone(self):
        self.assertEqual(event_key({"kind": "compact", "turn": 4}), "4:-")
        self.assertEqual(event_key({"kind": "tool_use", "turn": 1}), "1:-")

    def test_a_hit_with_no_tool_use_takes_the_same_dash(self):
        from ruleprobe.events import Hit
        self.assertEqual(hit_key(Hit("d", 4, None)), "4:-")
        self.assertEqual(hit_key(Hit("d", 4, "tu-9")), "4:tu-9")


class ScoreTests(unittest.TestCase):
    """The rates, where they are not simply tp over something."""

    def test_a_detector_that_fired_nowhere_and_missed_nothing_is_perfect(self):
        score = Score("d", positives=0, negatives=3)
        self.assertEqual(score.precision, 1.0)
        self.assertEqual(score.recall, 1.0)

    def test_a_detector_that_fired_nowhere_and_missed_something_has_no_precision(self):
        score = Score("d", positives=2, fn=2)
        self.assertEqual(score.precision, 0.0)
        self.assertEqual(score.recall, 0.0)
        self.assertEqual(score.f1, 0.0)

    def test_a_score_with_nothing_in_it_is_unscored(self):
        self.assertFalse(Score("d").scored)
        self.assertNotIn("precision", Score("d").as_dict())

    def test_add_sums_every_count(self):
        whole = Score("total").add(Score("a", 1, 2, 3, 4, 5)).add(Score("b", 1, 1, 1, 1, 1))
        self.assertEqual((whole.positives, whole.negatives, whole.tp, whole.fp, whole.fn),
                         (2, 3, 4, 5, 6))


class ArithmeticTests(Temp):
    """One case worked out on paper, then asserted.

    The detector fires at `1:tu-a`, `1:tu-b` and `2:tu-d`. The labels want `1:tu-a` and
    `2:tu-c`. So tp=1, fp=2, fn=1; precision 1/3, recall 1/2, and f1 = 2pr/(p+r) = 0.4.
    """

    def setUp(self):
        Temp.setUp(self)
        self.path = self.corpus(CASE_LABELS, {"case.jsonl": cc_lines(CASE_EVENTS)})
        self.registry = Registry([compile_detector(CAT)])
        self.score = score_corpus(self.registry, self.path)["x/cat"]

    def test_the_counts_are_what_the_labels_and_the_hits_make_them(self):
        self.assertEqual((self.score.tp, self.score.fp, self.score.fn), (1, 2, 1))
        self.assertEqual((self.score.positives, self.score.negatives), (2, 1))

    def test_the_rates_are_the_hand_computed_ones(self):
        self.assertAlmostEqual(self.score.precision, 1.0 / 3.0)
        self.assertAlmostEqual(self.score.recall, 0.5)
        self.assertAlmostEqual(self.score.f1, 0.4)

    def test_the_json_shape_rounds_to_four_places_and_names_the_source(self):
        data = self.score.as_dict()
        self.assertEqual(data["precision"], 0.3333)
        self.assertEqual(data["recall"], 0.5)
        self.assertEqual(data["source"], "corpus")
        self.assertTrue(data["scored"])

    def test_the_detector_is_under_the_default_floor(self):
        self.assertEqual(below_floor({"x/cat": self.score}), ["x/cat"])
        self.assertEqual(below_floor({"x/cat": self.score}, floor=0.2), [])

    def test_an_unscored_detector_is_never_under_the_floor(self):
        self.assertEqual(below_floor({"y/none": Score("y/none")}), [])

    def test_the_total_is_the_sum_and_ignores_the_unscored(self):
        whole = total({"x/cat": self.score, "y/none": Score("y/none")})
        self.assertEqual((whole.tp, whole.fp, whole.fn), (1, 2, 1))

    def test_a_detector_the_corpus_never_names_is_not_scored_against_it(self):
        """The labels are the truth about the detectors they name and about nothing else.
        `whole-file-cat` fires three times over this session and the labels never mention
        it; calling those three false positives would be the corpus scoring a detector it
        was never written for."""
        scores = score_corpus(DEFAULT, self.path)
        self.assertFalse(scores["transcript-hygiene/whole-file-cat"].scored)
        self.assertEqual(below_floor(scores), [])

    def test_a_detector_the_corpus_names_only_as_a_near_miss_is_scored(self):
        labels = ("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                  '      - at: "2:tu-c"\n        near: [x/sed]\n')
        path = self.corpus(labels, {"case.jsonl": cc_lines(CASE_EVENTS)})
        registry = Registry([compile_detector(dict(CAT, id="x/sed",
                                                   when={"command": {"name": "cat"}}))])
        score = score_corpus(registry, path)["x/sed"]
        self.assertTrue(score.scored)
        self.assertEqual((score.negatives, score.fp), (1, 3))

    def test_a_detector_nobody_labelled_is_returned_unscored_not_dropped(self):
        registry = Registry([compile_detector(CAT),
                             compile_detector(dict(CAT, id="x/npm",
                                                   when={"command": {"starts_with": "npm"}}))])
        scores = score_corpus(registry, self.path)
        self.assertEqual(sorted(scores), ["x/cat", "x/npm"])
        self.assertFalse(scores["x/npm"].scored)


class LoaderTests(Temp):
    """Everything wrong with a corpus is a `CorpusError` naming the file."""

    SESSIONS = {"case.jsonl": cc_lines(CASE_EVENTS)}

    def refuses(self, labels, fragment, sessions=None):
        path = self.corpus(labels, self.SESSIONS if sessions is None else sessions)
        with self.assertRaises(CorpusError) as caught:
            load_corpus(path)
        self.assertIn(fragment, str(caught.exception))

    def test_a_good_corpus_loads_both_ways_round(self):
        path = self.corpus(CASE_LABELS, self.SESSIONS)
        loaded = load_corpus(path)
        self.assertEqual([s.name for s in loaded], ["case.jsonl"])
        self.assertEqual(loaded[0].fire, {"x/cat": set(["1:tu-a", "2:tu-c"])})
        self.assertEqual(loaded[0].near, {"x/cat": set(["1:tu-b"])})

    def test_a_note_on_the_session_is_kept(self):
        path = self.corpus("version: 1\nsessions:\n  - session: case.jsonl\n"
                           "    note: a note\n    labels: []\n", self.SESSIONS)
        self.assertEqual(load_corpus(path)[0].note, "a note")

    def test_a_label_pointing_at_no_event_is_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                     '      - at: "9:tu-z"\n        fire: [x/cat]\n',
                     "points at no event")

    def test_two_labels_at_one_key_are_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                     '      - at: "1:tu-a"\n        fire: [x/cat]\n'
                     '      - at: "1:tu-a"\n        near: [x/cat]\n',
                     "two labels")

    def test_a_session_file_that_is_not_there_is_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: missing.jsonl\n    labels: []\n",
                     "no session file named")

    def test_a_session_file_nobody_labelled_is_fatal(self):
        self.refuses("version: 1\nsessions: []\n", "no labels for case.jsonl")

    def test_an_unknown_label_key_is_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                     '      - at: "1:tu-a"\n        fires: [x/cat]\n',
                     "unknown label key")

    def test_an_unknown_session_key_is_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: case.jsonl\n    labels: []\n"
                     "    comment: 'no'\n",
                     "unknown session key")

    def test_a_detector_id_that_is_not_a_list_of_strings_is_fatal(self):
        self.refuses("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                     '      - at: "1:tu-a"\n        fire: [1]\n',
                     "list of detector ids")

    def test_one_detector_id_may_be_written_bare(self):
        path = self.corpus("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                           '      - at: "1:tu-a"\n        fire: x/cat\n', self.SESSIONS)
        self.assertEqual(load_corpus(path)[0].fire, {"x/cat": set(["1:tu-a"])})

    def test_a_labels_file_that_is_not_a_mapping_of_sessions_is_fatal(self):
        self.refuses("version: 1\n", "expected a mapping with a sessions list")

    def test_a_labels_file_that_does_not_parse_is_fatal(self):
        self.refuses("sessions: [\n", "")

    def test_a_missing_labels_file_is_fatal(self):
        with self.assertRaises(CorpusError):
            load_corpus(os.path.join(self.dir, "nowhere"))

    def test_the_directory_argument_beats_the_environment(self):
        path = self.corpus(CASE_LABELS, self.SESSIONS)
        os.environ["RULEPROBE_CORPUS"] = "/nowhere"
        self.addCleanup(os.environ.pop, "RULEPROBE_CORPUS", None)
        self.assertEqual(corpus_dir(path), os.path.abspath(path))
        self.assertEqual(corpus_dir(), "/nowhere")

    def test_the_shipped_corpus_is_the_default(self):
        os.environ.pop("RULEPROBE_CORPUS", None)
        self.assertTrue(corpus_dir().endswith(os.path.join("ruleprobe", "corpus")))


EXAMPLES = {"id": "x/sudo", "rule": "x", "event": "tool_use",
            "when": {"command": {"starts_with": ["sudo", "pip"]}},
            "examples": {"fire": [{"bash": "sudo pip install ruff"},
                                  {"bash": "sudo pip uninstall ruff", "note": "either way"}],
                         "skip": [{"bash": "uv pip install ruff",
                                   "note": "the tool the rule asks for"},
                                  {"bash": "echo sudo pip install ruff"}]}}


class ExamplesTests(unittest.TestCase):
    """A detector that states its own cases, and one that states none."""

    def score(self, spec):
        detector = compile_detector(spec)
        return score_examples(Registry([detector]))[spec["id"]]

    def test_a_fire_case_is_a_positive_and_a_skip_case_a_negative(self):
        score = self.score(EXAMPLES)
        self.assertEqual((score.positives, score.negatives), (2, 2))
        self.assertEqual((score.tp, score.fp, score.fn), (2, 0, 0))
        self.assertEqual(score.source, "examples")

    def test_a_fire_case_the_detector_misses_is_a_false_negative(self):
        spec = dict(EXAMPLES, when={"command": {"starts_with": "npm"}})
        score = self.score(spec)
        self.assertEqual((score.tp, score.fp, score.fn), (0, 0, 2))
        self.assertEqual(score.recall, 0.0)

    def test_a_skip_case_the_detector_fires_on_is_a_false_positive(self):
        spec = dict(EXAMPLES, when={"tool": {"name": "Bash"}})
        score = self.score(spec)
        self.assertEqual((score.tp, score.fp, score.fn), (2, 2, 0))
        self.assertAlmostEqual(score.precision, 0.5)

    def test_a_detector_with_no_examples_is_unscored_and_says_so(self):
        detector = compile_detector(CAT)
        score = score_examples(Registry([detector]))["x/cat"]
        self.assertFalse(score.scored)
        self.assertEqual(validity_note({"x/cat": score}, "x/cat"), "no examples")

    def test_a_python_detector_carries_no_examples_by_default(self):
        self.assertIsNone(Detector("d", "r", "tool_use", lambda events, env: []).examples)

    def test_an_events_case_runs_a_session_detector(self):
        spec = {"id": "x/two-cats", "rule": "x", "event": "session",
                "when": {"order": {"first": {"command": {"starts_with": "cat"}},
                                   "then": {"command": {"starts_with": "grep"}}}},
                "examples": {"fire": [{"events": [{"input": {"command": "cat a"}},
                                                  {"input": {"command": "grep b a"}}]}],
                             "skip": [{"events": [{"input": {"command": "grep b a"}},
                                                  {"input": {"command": "cat a"}}]}]}}
        score = self.score(spec)
        self.assertEqual((score.tp, score.fp, score.fn), (1, 0, 0))

    def test_examples_are_only_read_when_the_corpus_does_not_label_the_detector(self):
        """The corpus is the better instrument: a detector it labels is scored from it."""
        registry = Registry([compile_detector(dict(EXAMPLES, id="x/sudo"))])
        scores = validity(registry=registry)
        self.assertEqual(scores["x/sudo"].source, "examples")


class BadExamplesTests(unittest.TestCase):
    """An examples block is compiled as strictly as the rest of a detector."""

    def refuses(self, examples, fragment):
        from ruleprobe.declarative import DeclarativeError
        with self.assertRaises(DeclarativeError) as caught:
            compile_detector(dict(CAT, examples=examples))
        self.assertIn(fragment, str(caught.exception))

    def test_an_empty_block_is_a_finding(self):
        self.refuses({"fire": [], "skip": []}, "no cases in it")

    def test_an_unknown_key_is_a_finding(self):
        self.refuses({"fires": [{"bash": "cat a"}]}, "fires")

    def test_a_case_naming_nothing_is_a_finding(self):
        self.refuses({"fire": [{"note": "nothing here"}]}, "one of bash, event or events")

    def test_a_case_naming_two_things_is_a_finding(self):
        self.refuses({"fire": [{"bash": "cat a", "event": {}}]},
                     "one of bash, event or events")

    def test_a_typo_in_an_event_snippet_is_a_finding(self):
        self.refuses({"fire": [{"event": {"inputs": {"command": "cat a"}}}]},
                     "event snippet")

    def test_a_note_that_is_not_a_string_is_a_finding(self):
        self.refuses({"fire": [{"bash": "cat a", "note": 3}]}, "note is a string")

    def test_cases_that_are_not_a_list_are_a_finding(self):
        self.refuses({"fire": {"bash": "cat a"}}, "list of cases")


class ShippedCorpusTests(unittest.TestCase):
    """The corpus as shipped. These are the assertions that make the number evidence."""

    @classmethod
    def setUpClass(cls):
        os.environ.pop("RULEPROBE_CORPUS", None)
        cls.corpus = load_corpus()
        cls.scores = score_corpus(DEFAULT)

    def test_every_shipped_detector_has_at_least_five_positives_and_five_negatives(self):
        for detector in DEFAULT:
            score = self.scores[detector.id]
            with self.subTest(detector=detector.id):
                self.assertGreaterEqual(score.positives, 5, "too few labelled positives")
                self.assertGreaterEqual(score.negatives, 5, "too few near-miss negatives")

    def test_every_shipped_detector_is_over_the_floor(self):
        self.assertEqual(below_floor(self.scores, DEFAULT_FLOOR), [])

    def test_every_transcript_shape_is_in_the_corpus(self):
        runtimes = set(labelled.session.runtime for labelled in self.corpus)
        self.assertEqual(runtimes, set(["claude-code", "codex", "gemini"]))

    def test_the_corpus_carries_no_home_path_and_no_person(self):
        """Synthetic means synthetic: a corpus with a real path in it is a leak, and a
        reader cannot tell one shipped transcript from another by eye."""
        base = corpus_dir()
        for directory, _dirs, files in os.walk(base):
            for name in sorted(files):
                path = os.path.join(directory, name)
                with open(path, encoding="utf-8") as handle:
                    body = handle.read()
                for bad in ("/Users/", "/home/", "C:\\Users"):
                    with self.subTest(file=name, pattern=bad):
                        self.assertNotIn(bad, body)

    def test_the_declarative_six_score_the_same_as_the_python_six(self):
        from test_equivalence import declarative_registry
        other = score_corpus(declarative_registry())
        self.assertEqual(dict((k, v.as_dict()) for k, v in other.items()),
                         dict((k, v.as_dict()) for k, v in self.scores.items()))


class TableTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("RULEPROBE_CORPUS", None)
        self.scores = score_corpus(DEFAULT)

    def test_the_table_has_a_row_per_detector_and_a_total(self):
        lines = validity_table(self.scores).splitlines()
        self.assertEqual(len(lines), len(DEFAULT.ids()) + 4)
        self.assertTrue(lines[-1].startswith("total"))
        self.assertIn("floor 0.90", lines[-1])

    def test_a_detector_under_the_floor_is_marked_in_its_row(self):
        scores = dict(self.scores)
        scores["x/bad"] = Score("x/bad", positives=2, tp=1, fp=1, fn=1)
        rows = [l for l in validity_table(scores).splitlines() if l.startswith("x/bad")]
        self.assertIn("below floor", rows[0])

    def test_an_unscored_detector_says_no_examples_rather_than_a_number(self):
        scores = dict(self.scores)
        scores["x/quiet"] = Score("x/quiet")
        rows = [l for l in validity_table(scores).splitlines() if l.startswith("x/quiet")]
        self.assertIn("no examples", rows[0])
        self.assertNotIn("0.00", rows[0])

    def test_the_json_shape_carries_the_floor_the_total_and_the_failures(self):
        data = scores_as_dict(self.scores, 0.99)
        self.assertEqual(data["floor"], 0.99)
        self.assertEqual(sorted(data["detectors"]), sorted(DEFAULT.ids()))
        self.assertEqual(data["total"]["detector"], "total")
        self.assertEqual(data["below_floor"], [])

    def test_a_detector_the_scores_do_not_mention_is_not_in_the_corpus(self):
        self.assertEqual(validity_note(self.scores, "x/unknown"), "not in the corpus")
        self.assertEqual(validity_note(None, "x/unknown"), "not in the corpus")


class ReadmeTests(unittest.TestCase):
    """The README quotes the table. If the corpus changes and the README does not, the
    README is a claim nobody checked, which is the thing this whole issue is against."""

    def test_the_readme_table_is_byte_identical_to_the_one_the_command_prints(self):
        os.environ.pop("RULEPROBE_CORPUS", None)
        with open(README, encoding="utf-8") as handle:
            body = handle.read()
        out = io.StringIO()
        main(["corpus", "--no-config"], out=out)
        printed = out.getvalue().rstrip("\n")
        self.assertIn("\n```\n" + printed + "\n```\n", body,
                      "README.md does not quote the current `ruleprobe corpus` table")


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        code = main(list(argv), out=out)
        return code, out.getvalue()

    def setUp(self):
        os.environ.pop("RULEPROBE_CORPUS", None)

    def test_corpus_prints_the_table_and_exits_zero_over_the_shipped_corpus(self):
        code, text = self.run_cli("corpus", "--no-config")
        self.assertEqual(code, 0)
        self.assertIn("transcript-hygiene/whole-file-cat", text)
        self.assertIn("floor 0.90", text)

    def test_a_floor_nothing_can_meet_is_a_non_zero_exit(self):
        code, text = self.run_cli("corpus", "--no-config", "--floor", "1.01")
        self.assertEqual(code, 1)
        self.assertIn("under the 1.01 floor", text)

    def test_the_json_output_is_json_and_carries_the_same_exit_code(self):
        code, text = self.run_cli("corpus", "--no-config", "--json", "--floor", "1.01")
        self.assertEqual(code, 1)
        data = json.loads(text)
        self.assertEqual(data["floor"], 1.01)
        catalog = [entry["detector"]["id"] for entry in ENTRIES]
        self.assertEqual(sorted(data["below_floor"]), sorted(set(DEFAULT.ids() + catalog)))

    def test_a_broken_corpus_is_exit_two_and_a_message_on_stderr(self):
        errors = io.StringIO()
        old, sys.stderr = sys.stderr, errors
        try:
            code, text = self.run_cli("corpus", "--no-config", "--corpus",
                                      os.path.join(ROOT, "docs"))
        finally:
            sys.stderr = old
        self.assertEqual(code, 2)
        self.assertEqual(text, "")
        self.assertIn("labels.yaml", errors.getvalue())

    def test_a_corpus_directory_of_my_own_is_scored_instead(self):
        """A corpus of my own replaces the shipped one, and since it names none of the
        shipped detectors it scores none of them: every row says so rather than calling
        each hit on an unlabelled session a false positive."""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        os.mkdir(os.path.join(base, "sessions"))
        with open(os.path.join(base, "labels.yaml"), "w") as handle:
            handle.write(CASE_LABELS)
        with open(os.path.join(base, "sessions", "case.jsonl"), "w") as handle:
            handle.write("\n".join(cc_lines(CASE_EVENTS)) + "\n")
        code, text = self.run_cli("corpus", "--no-config", "--corpus", base)
        self.assertEqual(code, 0)
        # A catalog entry restating a shipped detector scores it by its own examples.
        restated = [e["detector"]["id"] for e in ENTRIES if e["detector"]["id"] in DEFAULT]
        self.assertEqual(text.count("no examples"), len(DEFAULT.ids()) - len(restated))

    def test_the_report_carries_no_validity_column_by_default(self):
        code, text = self.run_cli("report", "--root", os.path.join(ROOT, "docs"),
                                  "--no-config")
        self.assertEqual(code, 0)
        self.assertNotIn("validity", text)
        self.assertNotIn("p=1.00", text)

    def test_the_report_carries_one_when_asked(self):
        code, text = self.run_cli("report", "--root", os.path.join(ROOT, "docs"),
                                  "--no-config", "--validity")
        self.assertEqual(code, 0)
        self.assertIn("validity", text.splitlines()[0])
        self.assertIn("p=1.00 r=1.00", text)

    def test_a_detector_of_my_own_is_annotated_no_examples_not_a_number(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, "d.json")
        with open(path, "w") as handle:
            handle.write(json.dumps({"version": 1, "detectors": [CAT]}))
        code, text = self.run_cli("report", "--root", os.path.join(ROOT, "docs"),
                                  "--no-config", "--detectors", path, "--validity")
        self.assertEqual(code, 0)
        row = [l for l in text.splitlines() if l.startswith("x/cat")][0]
        self.assertTrue(row.endswith("no examples"), row)

    def test_a_detector_with_examples_is_annotated_from_them(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, True)
        path = os.path.join(base, "d.json")
        with open(path, "w") as handle:
            handle.write(json.dumps({"version": 1, "detectors": [EXAMPLES]}))
        code, text = self.run_cli("corpus", "--no-config", "--detectors", path)
        self.assertEqual(code, 0)
        row = [l for l in text.splitlines() if l.startswith("x/sudo")][0]
        self.assertIn("1.00", row)


#: Zoo items for the binder cases: one each the section binder binds as labelled, misses,
#: binds when the label says it should not, and leaves unbound as labelled.
BOUND = {"id": "b1", "heading": "Testing",
         "lines": [["Run the tests before finishing.", "testing/test-after-change"]]}
MISSED = {"id": "b2", "heading": "Testing",
          "lines": [["Before you hand back, run the tests.", "testing/test-after-change"]]}
FALSE_BIND = {"id": "b3", "heading": "Pushing",
              "lines": [["Never force-push to main.", None]]}
NEAR = {"id": "b4", "heading": "Pushing",
        "lines": [["Never force-push to main.", None], ["Hotfixes excepted.", None]]}


class BindingTests(Temp):
    """The binder over a rules zoo: the arithmetic, the gate and the loader."""

    def zoo_corpus(self, items, raw=None):
        """A corpus of my own that holds only a rules zoo beside an empty labels file."""
        base = self.corpus("version: 1\nsessions: []\n", {})
        with open(os.path.join(base, ZOO_FILE), "w", encoding="utf-8") as handle:
            handle.write(raw if raw is not None else json.dumps({"items": items}))
        return base

    def run_cli(self, *argv):
        out, errors = io.StringIO(), io.StringIO()
        old, sys.stderr = sys.stderr, errors
        try:
            code = main(list(argv), out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), errors.getvalue()

    def test_each_cell_of_the_tally_is_what_the_labels_and_the_binds_make_it(self):
        binding = score_binding(zoo=[BOUND, MISSED, FALSE_BIND, NEAR])
        tests = binding.entries["testing/test-after-change"]
        push = binding.entries["git-safety/force-push-default"]
        self.assertEqual((tests.positives, tests.tp, tests.fp, tests.fn), (2, 1, 0, 1))
        self.assertEqual((push.positives, push.tp, push.fp, push.fn), (0, 0, 1, 0))
        self.assertEqual(binding.false_binds, [("b3", "git-safety/force-push-default")])
        self.assertEqual(binding.misses, [("b2", "testing/test-after-change")])
        self.assertEqual((binding.sections, binding.labels), (4, 5))

    def test_a_heading_label_counts_and_an_uncatalogued_label_is_set_apart(self):
        item = {"id": "h1", "heading": "Run the tests before finishing",
                "heading_label": "testing/test-after-change",
                "lines": [["Keep the suite fast.", "x/no-pattern-yet"]]}
        binding = score_binding(zoo=[item])
        self.assertEqual(binding.entries["testing/test-after-change"].tp, 1)
        self.assertEqual((binding.labels, binding.outside), (2, 1))
        self.assertNotIn("x/no-pattern-yet", binding.entries)

    def test_a_label_under_a_retired_id_counts_under_the_current_one(self):
        item = dict(BOUND, lines=[["Run the tests before finishing.", "x/old-tests"]])
        with mock.patch.dict(contract_data.RENAMED,
                             {"x/old-tests": "testing/test-after-change"}):
            binding = score_binding(zoo=[item])
        self.assertEqual(binding.entries["testing/test-after-change"].tp, 1)
        self.assertEqual(binding.outside, 0)

    def test_any_false_bind_fails_even_over_the_detector_floor(self):
        """Nineteen right and one wrong is a precision of 0.95, over 0.9, and still fails."""
        binding = score_binding(zoo=[dict(BOUND, id="b%d" % n) for n in range(19)]
                                + [FALSE_BIND])
        self.assertGreater(binding.total.precision, DEFAULT_FLOOR)
        self.assertEqual(binding_failures(binding, 0.0),
                         ["1 false bind(s): b3 git-safety/force-push-default"])

    def test_recall_under_the_recorded_floor_fails_and_at_it_passes(self):
        binding = score_binding(zoo=[BOUND, MISSED])
        self.assertEqual(binding_failures(binding, 0.5), [])
        self.assertEqual(binding_failures(binding, 0.51),
                         ["binding recall 0.50 is under the recorded 0.51"])

    def test_no_zoo_is_no_failure(self):
        self.assertEqual(binding_failures(None), [])
        self.assertIsNone(binding_as_dict(None))
        self.assertIn("not scored", binding_table(None))

    def test_a_rate_with_nothing_to_divide_is_a_dash_and_null_not_a_number(self):
        binding = score_binding(zoo=[MISSED, FALSE_BIND])
        data = binding_as_dict(binding)
        self.assertIsNone(data["entries"]["testing/test-after-change"]["precision"])
        self.assertIsNone(data["entries"]["git-safety/force-push-default"]["recall"])
        rows = dict((l.split()[0], l) for l in binding_table(binding).splitlines()[3:10])
        self.assertIn(" -    0.00", rows["testing/test-after-change"])
        self.assertTrue(rows["git-safety/force-push-default"].endswith("-  false bind"))

    def test_the_cli_exits_non_zero_on_a_false_bind_as_table_and_as_json(self):
        base = self.zoo_corpus([BOUND, FALSE_BIND])
        code, text, _err = self.run_cli("corpus", "--no-config", "--corpus", base,
                                        "--floor", "0.9")
        self.assertEqual(code, 1)
        self.assertIn("binder: 1 false bind(s): b3 git-safety/force-push-default", text)
        code, text, _err = self.run_cli("corpus", "--no-config", "--corpus", base, "--json")
        self.assertEqual(code, 1)
        data = json.loads(text)
        self.assertEqual(data["binding"]["false_binds"],
                         [{"section": "b3", "detector": "git-safety/force-push-default"}])
        self.assertEqual(data["below_floor"], [])

    def test_the_cli_exits_zero_on_a_clean_zoo_and_prints_the_binder_section(self):
        base = self.zoo_corpus([BOUND, NEAR])
        code, text, _err = self.run_cli("corpus", "--no-config", "--corpus", base)
        self.assertEqual(code, 0)
        self.assertIn("binder over the rules zoo: 2 sections, 3 labels", text)

    def test_a_corpus_of_my_own_with_no_zoo_scores_no_binding(self):
        base = self.corpus("version: 1\nsessions: []\n", {})
        self.assertIsNone(load_zoo(base))
        code, text, _err = self.run_cli("corpus", "--no-config", "--corpus", base, "--json")
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(text)["binding"])

    def test_the_shipped_corpus_without_its_zoo_is_fatal(self):
        base = self.corpus("version: 1\nsessions: []\n", {})
        # By module object: `ruleprobe.validity` as a dotted name is the function on 3.9.
        module = sys.modules["ruleprobe.validity"]
        with mock.patch.object(module, "_shipped_dir", return_value=base):
            with self.assertRaises(CorpusError) as caught:
                load_zoo(base)
        self.assertIn("no rules zoo", str(caught.exception))

    def test_a_broken_zoo_is_fatal_and_exit_two(self):
        cases = {"not json": "{",
                 "not an items list": json.dumps({"sections": []}),
                 "an unknown top-level key": json.dumps({"items": [], "extra": 1}),
                 "an unknown item key": json.dumps({"items": [dict(BOUND, note="x")]}),
                 "two items of one id": json.dumps({"items": [BOUND, BOUND]}),
                 "a line that is not a pair": json.dumps(
                     {"items": [dict(BOUND, lines=[["Run the tests."]])]}),
                 "a label that is not an id": json.dumps(
                     {"items": [dict(BOUND, lines=[["Run the tests.", 3]])]}),
                 "a heading of two lines": json.dumps(
                     {"items": [dict(BOUND, heading="A\nB")]}),
                 "a section with no text": json.dumps(
                     {"items": [dict(BOUND, lines=[["", None]])]})}
        for name, raw in cases.items():
            with self.subTest(case=name):
                base = self.zoo_corpus(None, raw=raw)
                with self.assertRaises(CorpusError):
                    score_binding(base)
                code, text, err = self.run_cli("corpus", "--no-config", "--corpus", base)
                self.assertEqual((code, text), (2, ""))
                self.assertIn("corpus:", err)


class ShippedBindingTests(unittest.TestCase):
    """The binder over the shipped zoo: the gate CI runs, and the ratchet on its recall."""

    @classmethod
    def setUpClass(cls):
        os.environ.pop("RULEPROBE_CORPUS", None)
        cls.binding = score_binding()

    def test_the_shipped_zoo_is_package_data_in_the_shipped_corpus(self):
        self.assertTrue(os.path.isfile(os.path.join(corpus_dir(), ZOO_FILE)))
        self.assertEqual((self.binding.sections, self.binding.labels), (65, 84))

    def test_the_shipped_binder_makes_no_false_bind_on_the_zoo(self):
        self.assertEqual(self.binding.false_binds, [])
        self.assertEqual(self.binding.total.precision, 1.0)
        self.assertEqual(binding_failures(self.binding), [])

    def test_the_recall_floor_is_todays_recall_rounded_down(self):
        """The ratchet: when binding improves, raise `BINDING_RECALL_FLOOR` with it."""
        recall = self.binding.total.recall
        self.assertGreaterEqual(recall, BINDING_RECALL_FLOOR)
        self.assertEqual(BINDING_RECALL_FLOOR, int(recall * 100) / 100.0,
                         "binding recall is now %.4f: raise BINDING_RECALL_FLOOR to %.2f"
                         % (recall, int(recall * 100) / 100.0))

    def test_the_json_carries_the_binder_beside_the_detectors(self):
        out = io.StringIO()
        self.assertEqual(main(["corpus", "--no-config", "--json"], out=out), 0)
        data = json.loads(out.getvalue())
        self.assertIn("detectors", data)
        binding = data["binding"]
        self.assertEqual((binding["total"]["tp"], binding["total"]["fp"],
                          binding["total"]["fn"]), (18, 0, 23))
        self.assertEqual(binding["total"]["precision"], 1.0)
        self.assertEqual((binding["recall_floor"], binding["outside_catalog"],
                          binding["failures"]), (BINDING_RECALL_FLOOR, 4, []))

    def test_two_runs_print_the_same_bytes(self):
        first, second = io.StringIO(), io.StringIO()
        main(["corpus", "--no-config", "--json"], out=first)
        main(["corpus", "--no-config", "--json"], out=second)
        self.assertEqual(first.getvalue(), second.getvalue())


class FoldTests(Temp):
    """A label written under a retired id scores the detector that id became.

    The case is the hand-computed one in `ArithmeticTests`, with its labels written under
    older names; the counts must come out the same."""

    def labels_under(self, fire_id, near_id):
        return (CASE_LABELS.replace("fire: [x/cat]", "fire: [%s]" % fire_id)
                .replace("near: [x/cat]", "near: [%s]" % near_id))

    def counts(self, score):
        return (score.tp, score.fp, score.fn, score.positives, score.negatives)

    def test_a_label_under_a_consumer_renamed_id_scores_the_current_one(self):
        path = self.corpus(self.labels_under("x/old-cat", "x/old-cat"),
                           {"case.jsonl": cc_lines(CASE_EVENTS)})
        registry = Registry([compile_detector(CAT)], {"x/old-cat": "x/cat"})
        self.assertEqual(self.counts(score_corpus(registry, path)["x/cat"]), (1, 2, 1, 2, 1))

    def test_labels_split_across_a_chain_merge_under_the_current_id(self):
        path = self.corpus(self.labels_under("x/oldest-cat", "x/old-cat"),
                           {"case.jsonl": cc_lines(CASE_EVENTS)})
        registry = Registry([compile_detector(CAT)],
                            {"x/oldest-cat": "x/old-cat", "x/old-cat": "x/cat"})
        self.assertEqual(self.counts(score_corpus(registry, path)["x/cat"]), (1, 2, 1, 2, 1))

    def test_a_shipped_rename_folds_a_label_with_no_map_of_your_own(self):
        path = self.corpus(self.labels_under("x/old-cat", "x/cat"),
                           {"case.jsonl": cc_lines(CASE_EVENTS)})
        with mock.patch.dict(contract_data.RENAMED, {"x/old-cat": "x/cat"}):
            scores = validity(Registry([compile_detector(CAT)]), path)
        self.assertEqual(self.counts(scores["x/cat"]), (1, 2, 1, 2, 1))
        self.assertNotIn("x/old-cat", scores)

    def test_without_the_fold_a_retired_label_scores_nothing(self):
        """The near miss: the same labels, no rename, and the detector is not named."""
        path = self.corpus(self.labels_under("x/old-cat", "x/old-cat"),
                           {"case.jsonl": cc_lines(CASE_EVENTS)})
        self.assertFalse(score_corpus(Registry([compile_detector(CAT)]), path)["x/cat"].scored)

    def test_fire_and_near_meeting_at_one_key_once_folded_is_fatal(self):
        labels = ("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                  '      - at: "1:tu-a"\n        fire: [x/old-cat]\n        near: [x/cat]\n')
        path = self.corpus(labels, {"case.jsonl": cc_lines(CASE_EVENTS)})
        registry = Registry([compile_detector(CAT)], {"x/old-cat": "x/cat"})
        with self.assertRaises(CorpusError) as caught:
            score_corpus(registry, path)
        self.assertIn("x/cat", str(caught.exception))
        self.assertIn("1:tu-a", str(caught.exception))
        # The near miss: without the fold they are two detectors and the corpus scores.
        self.assertTrue(score_corpus(Registry([compile_detector(CAT)]), path)["x/cat"].scored)

    def test_one_unrenamed_id_in_fire_and_near_at_one_label_still_scores(self):
        labels = ("version: 1\nsessions:\n  - session: case.jsonl\n    labels:\n"
                  '      - at: "1:tu-a"\n        fire: [x/cat]\n        near: [x/cat]\n')
        path = self.corpus(labels, {"case.jsonl": cc_lines(CASE_EVENTS)})
        for renamed in ({}, {"x/other": "x/cat"}):
            with self.subTest(renamed=renamed):
                score = score_corpus(Registry([compile_detector(CAT)], renamed), path)["x/cat"]
                self.assertEqual((score.positives, score.negatives), (1, 1))

    def test_scoring_a_corpus_under_a_fold_leaves_the_corpus_as_loaded(self):
        path = self.corpus(self.labels_under("x/old-cat", "x/old-cat"),
                           {"case.jsonl": cc_lines(CASE_EVENTS)})
        corpus = load_corpus(path)
        score_corpus(Registry([compile_detector(CAT)], {"x/old-cat": "x/cat"}), corpus=corpus)
        self.assertEqual(sorted(corpus[0].fire), ["x/old-cat"])


if __name__ == "__main__":
    unittest.main()
