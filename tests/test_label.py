# SPDX-License-Identifier: MIT
"""`ruleprobe label`, the event-schema corpus session it writes, and the YAML emitter.

Every secret here is fake and assembled at run time, so a scanner reading this file finds
concatenations rather than key shapes.
"""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from corpus import FAKE_KEY
from ruleprobe import Bundle, DEFAULT, Detector, Registry
from ruleprobe.cli import main
from ruleprobe.declarative import DeclarativeError, emit, load, parse
from ruleprobe.detectors.common import REDACTED, SECRET_PATTERNS
from ruleprobe.validity import (CorpusError, load_corpus, load_events, read_events,
                                score_corpus)
from test_explain import claude_transcript

NO_VERIFY = "verification/no-verify"


def run_cli_err(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        code = main(list(argv), out=out)
    return code, out.getvalue(), err.getvalue()


def tree(base):
    """`{relative path: bytes}` for every file under `base`, and each directory as None."""
    found = {}
    for directory, dirs, files in os.walk(base):
        for name in dirs:
            found[os.path.relpath(os.path.join(directory, name), base)] = None
        for name in files:
            path = os.path.join(directory, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, base)] = handle.read()
    return found


class EmitTests(unittest.TestCase):
    ENTRY = {"session": "wrong-hit.events.jsonl",
             "labels": [{"at": "1:tu-c1", "near": ["transcript-hygiene/whole-file-cat"]}]}

    def test_the_label_entry_round_trips_at_every_indent(self):
        for value in (self.ENTRY, [self.ENTRY], {"version": 1, "sessions": [self.ENTRY]}):
            for indent in (0, 2, 4):
                with self.subTest(value=value, indent=indent):
                    self.assertEqual(parse(emit(value, indent)), value)

    def test_a_key_shaped_like_a_hit_key_is_quoted(self):
        text = emit({"at": "1:tu-c1"})
        self.assertEqual(text, 'at: "1:tu-c1"\n')
        self.assertEqual(emit({"at": "12:-"}), 'at: "12:-"\n')

    def test_every_scalar_shape_round_trips(self):
        value = {"none": None, "t": True, "f": False, "int": -3, "float": 1.5,
                 "empty": "", "true": "true", "yes": "yes", "octal": "010", "num": "12",
                 "hash": "#x", "colon": "a: b", "quote": "it's", "double": 'say "hi"',
                 "both": "it's \"q\"", "backslash": "a\\d+", "accent": "caf\u00e9",
                 "dash": "-x", "flow": "[a]", "amp": "&x", "list": [], "map": {},
                 "nested": [[1, 2], [{"a": [3]}]], "quoted key: x": 1, "1:k": "v"}
        self.assertEqual(parse(emit(value)), value)

    def test_emit_reads_back_through_load(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        path = os.path.join(scratch.name, "labels.yaml")
        with open(path, "w") as handle:
            handle.write(emit({"version": 1, "sessions": [self.ENTRY]}))
        self.assertEqual(load(path)[0], {"version": 1, "sessions": [self.ENTRY]})

    def test_what_the_subset_cannot_spell_is_refused(self):
        for value in ("a\nb", "a\rb", "a\x1cb", "a\tb", "a\u2028b", {1: "a"},
                      set([1]), object(), float("nan"), float("inf"), (1, 2)):
            with self.subTest(value=value):
                with self.assertRaises(DeclarativeError):
                    emit({"k": value})


class EventsSessionTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.base = scratch.name
        os.mkdir(os.path.join(self.base, "sessions"))

    def write(self, name, text):
        path = os.path.join(self.base, name)
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def test_turn_and_final_are_taken_as_written(self):
        events = [{"kind": "assistant_text", "turn": 37, "text": "done", "final": False},
                  {"kind": "tool_use", "turn": 37, "id": "tu-1", "name": "Bash",
                   "input": {"command": "ls"}}]
        path = self.write("sessions/late.events.jsonl",
                          "".join(json.dumps(e) + "\n" for e in events) + "\n")
        session = load_events(path)
        self.assertEqual(session.events, events)
        self.assertEqual((session.id, session.runtime), ("late", "events"))

    def test_a_malformed_line_is_refused_with_its_line(self):
        for text, line in (("not json\n", 1), ('{"kind": "x", "turn": 1}\n[1]\n', 2),
                           ('{"turn": 1}\n', 1), ('{"kind": "x", "turn": true}\n', 1),
                           ('{"kind": "x", "turn": "1"}\n', 1)):
            with self.subTest(text=text):
                with self.assertRaisesRegex(CorpusError, ":%d: " % line):
                    read_events(text, "s.events.jsonl")

    def test_an_empty_file_is_refused(self):
        path = self.write("sessions/empty.events.jsonl", "\n")
        with self.assertRaisesRegex(CorpusError, "holds no event"):
            load_events(path)

    def test_the_corpus_scores_an_events_session_beside_a_native_one(self):
        with open(os.path.join(os.path.dirname(__file__), "fixtures",
                               "claude-code-session.jsonl")) as handle:
            self.write("sessions/native.jsonl", handle.read())
        event = {"kind": "tool_use", "turn": 37, "id": "tu-1", "name": "Bash",
                 "input": {"command": "git commit --no-verify -m wip"}}
        self.write("sessions/field.events.jsonl", json.dumps(event) + "\n")
        self.write("labels.yaml", "version: 1\nsessions:\n"
                   "  - session: native.jsonl\n    labels: []\n"
                   '  - session: field.events.jsonl\n    labels:\n'
                   '      - at: "37:tu-1"\n        near: [%s]\n' % NO_VERIFY)
        corpus = load_corpus(self.base)
        self.assertEqual([c.name for c in corpus], ["native.jsonl", "field.events.jsonl"])
        score = score_corpus(DEFAULT, corpus=corpus)[NO_VERIFY]
        # The fixture's own no-verify hit is unlabelled, so it counts as a false positive too.
        self.assertEqual((score.negatives, score.fp), (1, 2))


class LabelTests(unittest.TestCase):
    """The command end to end, over a synthetic transcript and a scratch corpus."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = scratch.name
        self.root = os.path.join(self.scratch, "transcripts")
        self.corpus = os.path.join(self.scratch, "mine")
        self.sibling = os.path.join(self.scratch, "elsewhere")
        for path in (self.root, self.corpus, self.sibling):
            os.mkdir(path)

    def transcript(self, uses, session_id="sess-1", name="t.jsonl"):
        with open(os.path.join(self.root, name), "w") as handle:
            handle.write(claude_transcript(session_id, uses))

    def label(self, *extra, **kw):
        argv = ["label", "--root", self.root, "--no-config",
                "--session", kw.get("session", "claude-code:sess-1"),
                "--detector", kw.get("detector", NO_VERIFY),
                "--key", kw.get("key", "1:toolu_1"),
                "--corpus", kw.get("corpus", self.corpus),
                "--name", kw.get("name", "wrong-hit")]
        return run_cli_err(*(argv + list(extra)))

    def written(self):
        path = os.path.join(self.corpus, "sessions", "wrong-hit.events.jsonl")
        with open(path) as handle:
            events = handle.read()
        with open(os.path.join(self.corpus, "labels.yaml")) as handle:
            labels = handle.read()
        return events, labels

    def assertRefused(self, why, *extra, **kw):
        before = tree(self.scratch)
        code, text, err = self.label(*extra, **kw)
        self.assertEqual((code, text), (2, ""), err)
        self.assertIn("label: refused: ", err)
        self.assertRegex(err, why)
        self.assertEqual(tree(self.scratch), before)
        return err

    # --- what it writes -------------------------------------------------------------

    def test_it_writes_the_one_event_and_one_near_label_and_nothing_else(self):
        self.transcript([("toolu_0", "Bash", {"command": "ls"}),
                         ("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        before = tree(self.scratch)
        code, text, err = self.label()
        self.assertEqual(code, 0, err)
        after = tree(self.scratch)
        added = sorted(set(after) - set(before))
        self.assertEqual(added, ["mine/labels.yaml", "mine/sessions",
                                 "mine/sessions/wrong-hit.events.jsonl"])
        self.assertEqual(dict((k, after[k]) for k in before), before)
        events, labels = self.written()
        self.assertEqual([json.loads(line) for line in events.splitlines()], [
            {"kind": "tool_use", "turn": 1, "id": "toolu_1", "name": "Bash",
             "input": {"command": "git commit --no-verify -m wip"}}])
        self.assertEqual(parse(labels), {"version": 1, "sessions": [
            {"session": "wrong-hit.events.jsonl",
             "labels": [{"at": "1:toolu_1", "near": [NO_VERIFY]}]}]})
        self.assertIn("near %s at 1:toolu_1" % NO_VERIFY, text)

    def test_the_corpus_rerun_counts_the_new_negative(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        self.assertEqual(self.label()[0], 0)
        code, text, _err = run_cli_err("corpus", "--no-config", "--corpus", self.corpus,
                                       "--json")
        score = json.loads(text)["detectors"][NO_VERIFY]
        self.assertEqual((score["negatives"], score["fp"], score["tp"]), (1, 1, 0))
        self.assertEqual(code, 1)  # a wrong hit, now on the record, is under the floor

    def test_a_retired_detector_id_is_labelled_under_its_current_id(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        registry = DEFAULT.copy().rename("old/no-verify", NO_VERIFY)
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            code, _text, err = self.label(detector="old/no-verify")
        self.assertEqual(code, 0, err)
        self.assertIn("- " + NO_VERIFY, self.written()[1])

    # --- secrets -----------------------------------------------------------------------

    def test_a_secret_in_the_event_is_in_no_written_file(self):
        command = "git commit --no-verify -m 'rotate %s'" % FAKE_KEY
        self.transcript([("toolu_1", "Bash", {"command": command})])
        code, text, err = self.label()
        self.assertEqual(code, 0, err)
        for body in self.written() + (text,):
            self.assertNotIn(FAKE_KEY, body)
            self.assertFalse(any(re.search(p, body) for p in SECRET_PATTERNS))
        self.assertIn(REDACTED, self.written()[0])

    def test_a_value_under_a_secret_named_key_goes_with_its_key(self):
        def deploys(events, ctx):
            return [(e["turn"], e["id"]) for e in events
                    if e.get("kind") == "tool_use" and e.get("name") == "Deploy"]

        self.transcript([("toolu_1", "Deploy", {"target": "staging",
                                                "password": "hunter" + "2" * 6,
                                                "nested": {"client_secret": ["x" * 9]}})])
        registry = Registry([Detector("x/deploy", "x", "tool_use", deploys)])
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            code, _text, err = self.label(detector="x/deploy")
        self.assertEqual(code, 0, err)
        event = json.loads(self.written()[0])
        self.assertEqual(event["input"], {"target": "staging", REDACTED: REDACTED,
                                          "nested": {REDACTED: REDACTED}})

    def test_an_escape_that_completes_a_key_name_is_refused(self):
        # Each is left alone by redaction as a raw string, and spells a key name once its
        # control or format character is written as a JSON escape.
        for n, hidden in enumerate(("\x1client_secret" + "\n  hunter" + "2" * 6,
                                    "\u202aws_secret" + "_access_key\n  hunter" + "3" * 6)):
            with self.subTest(n=n):
                self.transcript([("toolu_1", "Bash",
                                  {"command": "git commit --no-verify -m '%s'" % hidden})])
                self.assertRefused("secret shape would survive")

    def test_redaction_that_changes_the_matched_field_is_refused(self):
        self.transcript([("toolu_1", "Write", {"file_path": "/tmp/demo-repo/.env",
                                               "content": "KEY=%s\n" % FAKE_KEY})])
        err = self.assertRefused("redaction changed what secrets/secret-in-write matched",
                                 detector="secrets/secret-in-write")
        self.assertNotIn(FAKE_KEY, err)

    def test_a_hit_that_needs_the_events_around_it_is_refused(self):
        def second_use(events, ctx):
            uses = [e for e in events if e.get("kind") == "tool_use"]
            return [(e["turn"], e["id"]) for e in uses[1:]]

        self.transcript([("toolu_0", "Bash", {"command": "ls"}),
                         ("toolu_1", "Bash", {"command": "ls"})])
        registry = Registry([Detector("x/second", "x", "tool_use", second_use)])
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            self.assertRefused("needs events around it", detector="x/second")

    # --- refusals ------------------------------------------------------------------------

    def test_a_session_hit_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        self.assertRefused("1:- is a session hit", key="1:-",
                           detector="cache-hygiene/compact")

    def test_a_name_that_is_not_a_plain_stem_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        for name in ("", ".hidden", "..", "../elsewhere/x", "a/b", "a\\b", "a..b",
                     os.path.join(self.sibling, "x"), "a\nb"):
            with self.subTest(name=name):
                self.assertRefused("not a plain file stem", name=name)

    def test_no_session_or_two_at_the_address_is_refused(self):
        use = [("toolu_1", "Bash", {"command": "git commit --no-verify"})]
        self.transcript(use)
        self.assertRefused("no session claude-code:other", session="claude-code:other")
        self.assertRefused("no session sess-1", session="sess-1")
        self.transcript(use, name="copy.jsonl")
        self.assertRefused("2 sessions are at claude-code:sess-1")

    def test_no_hit_at_the_key_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        self.assertRefused("has no hit at 1:toolu_1")
        self.assertRefused("has no hit at 9:nothing", key="9:nothing")

    def test_an_unknown_or_gated_detector_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.assertRefused("no detector nobody/here is loaded", detector="nobody/here")
        gated = Detector("x/gated", "x", "tool_use", lambda events, ctx: [(1, "toolu_1")],
                         gate=("commits", None))
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), Registry([gated]))):
            self.assertRefused("gated on a stance", "--stance", "commits=any",
                               detector="x/gated")

    def test_an_existing_session_file_or_a_missing_corpus_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.assertRefused("is not a directory",
                           corpus=os.path.join(self.scratch, "not-made"))
        os.mkdir(os.path.join(self.corpus, "sessions"))
        with open(os.path.join(self.corpus, "sessions", "wrong-hit.events.jsonl"), "w"):
            pass
        self.assertRefused("already exists")

    def test_a_link_out_of_the_corpus_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        os.symlink(self.sibling, os.path.join(self.corpus, "sessions"))
        self.assertRefused("is a link")

    # --- labels.yaml -------------------------------------------------------------------

    HAND_WRITTEN = ("# my corpus\nversion: 1  # kept\n\nsessions:\n"
                    "- session: old.events.jsonl  # flush-left entries\n"
                    "  labels:\n  - at: \"1:tu-1\"\n    fire: [%s]\n" % NO_VERIFY)

    def hand_written(self, text=None):
        os.mkdir(os.path.join(self.corpus, "sessions"))
        with open(os.path.join(self.corpus, "sessions", "old.events.jsonl"), "w") as handle:
            handle.write(json.dumps({"kind": "tool_use", "turn": 1, "id": "tu-1",
                                     "name": "Bash",
                                     "input": {"command": "git commit --no-verify"}}) + "\n")
        path = os.path.join(self.corpus, "labels.yaml")
        with open(path, "w") as handle:
            handle.write(self.HAND_WRITTEN if text is None else text)
        return path

    def test_an_existing_file_is_appended_to_and_keeps_its_comments(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        path = self.hand_written(self.HAND_WRITTEN.rstrip("\n"))  # no final newline
        code, text, err = self.label()
        self.assertEqual(code, 0, err)
        self.assertIn("appended to", text)
        with open(path) as handle:
            after = handle.read()
        self.assertTrue(after.startswith(self.HAND_WRITTEN.rstrip("\n") + "\n- session:"))
        document = load(path)[0]
        self.assertEqual(document["sessions"][-1], {
            "session": "wrong-hit.events.jsonl",
            "labels": [{"at": "1:toolu_1", "near": [NO_VERIFY]}]})
        self.assertEqual(len(document["sessions"]), 2)

    def test_a_session_already_named_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        self.assertRefused("old.events.jsonl already exists", name="old")
        os.remove(os.path.join(self.corpus, "sessions", "old.events.jsonl"))
        self.assertRefused("already names old.events.jsonl", name="old")

    def test_sessions_not_last_or_not_appendable_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written(self.HAND_WRITTEN + "owner: me\n")
        self.assertRefused("sessions is not the last key")
        with open(path, "w") as handle:
            handle.write("version: 1\nsessions: []\n")
        self.assertRefused("would not read back as the old document plus one entry")
        with open(path, "w") as handle:
            handle.write("version: 1\nsessions: [\n")
        self.assertRefused("cannot read")

    def test_a_failure_after_writing_restores_everything(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        for failure in (CorpusError("broken"), OSError("disk full"), KeyError("x")):
            with self.subTest(failure=failure):
                before = tree(self.scratch)
                with mock.patch("ruleprobe.cli.load_corpus", side_effect=failure):
                    code, _text, err = self.label()
                self.assertEqual(code, 2)
                self.assertIn("nothing was kept", err)
                self.assertEqual(tree(self.scratch), before)

    def test_a_failure_removes_a_created_labels_file_and_sessions_directory(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        before = tree(self.scratch)
        with mock.patch("ruleprobe.cli.score_corpus", side_effect=CorpusError("broken")):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("broken; nothing was kept", err)
        self.assertEqual(tree(self.scratch), before)

    def test_a_negative_the_read_back_does_not_score_is_rolled_back(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        before = tree(self.scratch)
        with mock.patch("ruleprobe.cli.score_corpus",
                        return_value={NO_VERIFY: mock.Mock(negatives=1, fp=0)}):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("did not score the new negative", err)
        self.assertEqual(tree(self.scratch), before)


if __name__ == "__main__":
    unittest.main()
