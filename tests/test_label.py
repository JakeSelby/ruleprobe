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
from test_readers import FIXTURES

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

    def test_a_value_past_the_depth_or_holding_itself_is_refused(self):
        looped = []
        looped.append(looped)
        deep = inner = []
        for _n in range(40):
            inner.append([1])
            inner = inner[-1]
        for value in (looped, {"k": looped}, deep):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(DeclarativeError, "nested too deeply"):
                    emit(value)

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

    def test_two_session_files_of_one_name_are_refused(self):
        line = json.dumps({"kind": "tool_use", "turn": 1, "id": "tu-1", "name": "Bash",
                           "input": {"command": "ls"}}) + "\n"
        for sub in ("a", "b"):
            os.mkdir(os.path.join(self.base, "sessions", sub))
            self.write("sessions/%s/same.events.jsonl" % sub, line)
        self.write("labels.yaml", "version: 1\nsessions:\n  - session: same.events.jsonl\n")
        with self.assertRaisesRegex(CorpusError, "two session files are named same"):
            load_corpus(self.base)

    def test_the_shipped_corpus_has_no_two_files_of_one_name(self):
        names = [name for _d, _s, files in os.walk(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ruleprobe",
            "corpus", "sessions")) for name in files]
        self.assertEqual(len(names), len(set(names)))

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
                     os.path.join(self.sibling, "x"), "a\nb", "a\u202eb", "a\u200bb",
                     " lead", "trail ", "tab\t", "c:x", "x:stream"):
            with self.subTest(name=name):
                self.assertRefused("not a plain file stem", name=name)

    def test_no_session_or_two_at_the_address_is_refused(self):
        use = [("toolu_1", "Bash", {"command": "git commit --no-verify"})]
        self.transcript(use)
        self.assertRefused("no session claude-code:other", session="claude-code:other")
        self.assertRefused("no session sess-1", session="sess-1")
        self.transcript(use, name="copy.jsonl")
        self.assertRefused("2 sessions at claude-code:sess-1 have a hit at 1:toolu_1; "
                           "narrow --root or --since to one")

    def test_a_copied_transcript_sharing_the_session_id_is_passed_over(self):
        # A copy of a transcript carries the same session id as the original.
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        self.transcript([("toolu_1", "Bash", {"command": "ls"})], name="agent-1.jsonl")
        code, _text, err = self.label()
        self.assertEqual(code, 0, err)
        self.assertIn("--no-verify", self.written()[0])
        os.remove(os.path.join(self.root, "t.jsonl"))
        self.assertRefused("has no hit at 1:toolu_1 in claude-code:sess-1;", name="other")

    def test_no_hit_in_any_of_several_sessions_says_how_many(self):
        use = [("toolu_1", "Bash", {"command": "ls"})]
        self.transcript(use)
        self.transcript(use, name="agent-1.jsonl")
        self.assertRefused(r"no hit at 1:toolu_1 in claude-code:sess-1 \(2 sessions at it\)")

    def test_since_narrows_two_copies_to_one(self):
        use = [("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})]
        self.transcript(use)
        with open(os.path.join(self.root, "old.jsonl"), "w") as handle:
            handle.write(claude_transcript("sess-1", use).replace("2026-09-20", "2026-01-05"))
        self.assertRefused("2 sessions at claude-code:sess-1 have a hit")
        code, _text, err = self.label("--since", "2026-09-01")
        self.assertEqual(code, 0, err)

    def test_a_codex_session_is_labelled_and_runtime_is_forwarded(self):
        with open(os.path.join(FIXTURES, "codex-rollout.jsonl")) as handle:
            with open(os.path.join(self.root, "rollout.jsonl"), "w") as copy:
                copy.write(handle.read())
        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        find = "transcript-hygiene/unfiltered-find"
        self.assertRefused("no session codex:rollout-1", "--runtime", "claude-code",
                           session="codex:rollout-1", detector=find, key="1:call_1")
        code, _text, err = self.label("--runtime", "codex", session="codex:rollout-1",
                                      detector=find, key="1:call_1")
        self.assertEqual(code, 0, err)
        # The Claude Code transcript read as Codex is no session, and says so on success.
        self.assertIn("1 transcript(s) produced no session: t.jsonl", err)
        self.assertIn("find .", self.written()[0])

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
            self.assertRefused("gated on a stance", detector="x/gated")

    def test_label_takes_no_stance(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.label("--stance", "commits=any")
            with self.assertRaises(SystemExit):
                self.label("--plugins")

    def test_the_follow_up_command_carries_the_detector_sources(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        detectors = os.path.join(self.sibling, "my detectors.yaml")
        with open(detectors, "w") as handle:
            handle.write("detectors: []\n")
        code, text, err = self.label("--detectors", detectors)
        self.assertEqual(code, 0, err)
        self.assertIn("score it with: ruleprobe corpus --corpus %s --detectors '%s' "
                      "--no-config\n" % (self.corpus, detectors), text)

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
        # Moved into a subdirectory, the file is still the labelled session, and the name is
        # still taken.
        sessions = os.path.join(self.corpus, "sessions")
        os.mkdir(os.path.join(sessions, "moved"))
        os.rename(os.path.join(sessions, "old.events.jsonl"),
                  os.path.join(sessions, "moved", "old.events.jsonl"))
        self.assertRefused("already names old.events.jsonl", name="old")

    def test_a_corpus_broken_as_it_stands_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        stray = os.path.join(self.corpus, "sessions", "stray.events.jsonl")
        with open(stray, "w") as handle:
            handle.write(json.dumps({"kind": "user_prompt", "turn": 1}) + "\n")
        self.assertRefused("broken as it stands: .*no labels for stray.events.jsonl")
        os.remove(stray)
        os.remove(os.path.join(self.corpus, "sessions", "old.events.jsonl"))
        self.assertRefused("broken as it stands: .*no session file named 'old.events.jsonl'")

    def test_sessions_without_a_labels_file_are_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        os.remove(os.path.join(self.corpus, "labels.yaml"))
        self.assertRefused("holds sessions but .* has no labels.yaml")

    def test_a_non_utf8_labels_file_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written()
        with open(path, "ab") as handle:
            handle.write(b"# \xff\n")
        self.assertRefused("not UTF-8")

    def test_a_labels_link_or_directory_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        target = os.path.join(self.sibling, "labels.yaml")
        with open(target, "w") as handle:
            handle.write("version: 1\nsessions: []\n")
        path = os.path.join(self.corpus, "labels.yaml")
        os.symlink(target, path)
        self.assertRefused("labels.yaml is a link")  # the tree, the target's bytes included
        os.remove(path)
        os.mkdir(path)
        self.assertRefused("labels.yaml is a link or not a plain file")

    def test_sessions_not_last_or_not_appendable_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written(self.HAND_WRITTEN + "owner: me\n")
        self.assertRefused("sessions is not the last key")
        os.remove(os.path.join(self.corpus, "sessions", "old.events.jsonl"))
        with open(path, "w") as handle:
            handle.write("version: 1\nsessions: []\n")
        self.assertRefused("would not read back as the old document plus one entry")
        with open(path, "w") as handle:
            handle.write("version: 1\nsessions: [\n")
        self.assertRefused("broken as it stands")

    def test_an_entry_the_subset_cannot_spell_is_refused_before_a_first_write(self):
        tool_id = "toolu_\x07bell"
        self.transcript([(tool_id, "Bash", {"command": "git commit --no-verify"})])
        self.assertRefused("cannot be written in the YAML subset", key="1:" + tool_id)

    def test_the_entry_takes_the_indentation_of_the_entries_above(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        text = self.HAND_WRITTEN.replace("\n- session", "\n    - session").replace(
            "\n  labels:\n  - at: \"1:tu-1\"\n    fire", "\n      labels:\n"
            "      - at: \"1:tu-1\"\n        fire").replace(
            "sessions:\n", "sessions:\n  # the entries sit four in\n\n")
        path = self.hand_written(text)
        self.assertEqual(len(load(path)[0]["sessions"]), 1)
        code, _text, err = self.label()
        self.assertEqual(code, 0, err)
        with open(path) as handle:
            self.assertIn("\n    - session: wrong-hit.events.jsonl\n", handle.read())
        self.assertEqual(len(load_corpus(self.corpus)), 2)

    def test_a_crlf_labels_file_is_appended_to(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m wip"})])
        path = self.hand_written(self.HAND_WRITTEN.replace("\n", "\r\n"))
        code, _text, err = self.label()
        self.assertEqual(code, 0, err)
        self.assertEqual([c.name for c in load_corpus(self.corpus)],
                         ["old.events.jsonl", "wrong-hit.events.jsonl"])
        with open(path, "rb") as handle:
            self.assertTrue(handle.read().startswith(
                self.HAND_WRITTEN.replace("\n", "\r\n").encode()))

    def test_labelling_twice_appends_to_the_file_label_wrote(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m a"}),
                         ("toolu_2", "Bash", {"command": "git commit --no-verify -m b"})])
        self.assertEqual(self.label(name="first")[0], 0)
        code, text, err = self.label(key="1:toolu_2", name="second")
        self.assertEqual(code, 0, err)
        self.assertIn("appended to", text)
        corpus = load_corpus(self.corpus)
        self.assertEqual([c.name for c in corpus],
                         ["first.events.jsonl", "second.events.jsonl"])
        score = score_corpus(DEFAULT, corpus=corpus)[NO_VERIFY]
        self.assertEqual((score.negatives, score.fp), (2, 2))

    # --- detectors that raise or hit elsewhere ---------------------------------------

    def with_detector(self, fn, **kw):
        registry = Registry([Detector("x/d", "x", "tool_use", fn)])
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            return self.assertRefused(kw.pop("why"), detector="x/d", **kw)

    @staticmethod
    def uses(events):
        return [(e["turn"], e["id"]) for e in events if e.get("kind") == "tool_use"]

    def test_a_detector_raising_on_the_session_is_refused_with_its_error(self):
        def boom(events, ctx):
            raise KeyError("x")

        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        self.with_detector(boom, why="x/d raised KeyError over claude-code:sess-1")

    def test_a_detector_raising_on_the_written_event_is_refused_with_its_error(self):
        def lone(events, ctx):
            if len(events) == 1:
                raise ValueError("x")
            return self.uses(events)

        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        self.with_detector(lone, why="x/d raised ValueError over the written event")

    def test_a_second_hit_on_the_written_event_is_refused(self):
        def twice(events, ctx):
            return self.uses(events) + [(1, None)]

        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        self.with_detector(twice, why="hits at 1:toolu_1, 1:-, not only at 1:toolu_1")

    def test_more_than_one_event_at_the_key_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify -m a"}),
                         ("toolu_1", "Bash", {"command": "git commit --no-verify -m b"})])
        self.assertRefused("1:toolu_1 is more than one event")

    def test_redaction_that_changes_the_key_is_refused(self):
        tool_id = "toolu_" + FAKE_KEY
        self.transcript([(tool_id, "Bash", {"command": "git commit --no-verify"})])
        err = self.assertRefused("redaction changed the event's key", key="1:" + tool_id)
        self.assertNotIn(FAKE_KEY, err)

    # --- rollback ------------------------------------------------------------------------

    def fail_on_second(self, failure):
        """`load_corpus` as it is for the check before writing, then `failure`."""
        calls = []

        def load(directory=None):
            calls.append(directory)
            if len(calls) > 1:
                raise failure
            return load_corpus(directory)

        return mock.patch("ruleprobe.cli.load_corpus", side_effect=load)

    def test_a_corpus_or_io_failure_after_writing_restores_everything(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        for failure in (CorpusError("broken"), OSError("disk full")):
            with self.subTest(failure=failure):
                before = tree(self.scratch)
                with self.fail_on_second(failure):
                    code, _text, err = self.label()
                self.assertEqual(code, 2)
                self.assertIn("%s; nothing was kept" % failure, err)
                self.assertNotIn("detector raised", err)
                self.assertEqual(tree(self.scratch), before)

    def test_a_bug_of_label_own_is_rolled_back_and_re_raised(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        self.hand_written()
        before = tree(self.scratch)
        with self.fail_on_second(KeyError("x")):
            with self.assertRaises(KeyError):
                self.label()
        self.assertEqual(tree(self.scratch), before)

    def test_a_detector_raising_while_scoring_is_named_as_such(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        before = tree(self.scratch)
        with mock.patch("ruleprobe.cli.score_corpus", side_effect=ZeroDivisionError()):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("scoring raised ZeroDivisionError while the written corpus was "
                      "scored; nothing was kept", err)
        self.assertEqual(tree(self.scratch), before)

    def test_a_raising_detector_in_the_read_back_is_named(self):
        def boom(events, ctx):
            raise KeyError("x")

        self.transcript([("toolu_1", "Bash", {"command": "ls"})])
        before = tree(self.scratch)
        registry = Registry([Detector("x/d", "x", "tool_use",
                                      lambda events, ctx: self.uses(events)),
                             Detector("x/boom", "x", "session", boom)])
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            code, _text, err = self.label(detector="x/d")
        self.assertEqual(code, 2)
        self.assertIn("detector x/boom raised KeyError while the written corpus was scored; "
                      "nothing was kept", err)
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

    def test_a_failed_rollback_step_names_what_it_left(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        real_remove = os.remove
        events = os.path.join(self.corpus, "sessions", "wrong-hit.events.jsonl")

        def remove(path, *a, **kw):
            if path == events:
                raise PermissionError(path)
            return real_remove(path, *a, **kw)

        with mock.patch("ruleprobe.cli.score_corpus", side_effect=CorpusError("broken")), \
                mock.patch("ruleprobe.cli.os.remove", side_effect=remove):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("the rollback left behind %s (PermissionError)" % events, err)
        self.assertIn("sessions, created by label (OSError)", err)
        self.assertFalse(os.path.exists(os.path.join(self.corpus, "labels.yaml")))

    def test_a_labels_file_changed_after_the_append_is_left_and_described(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written()

        def score(*_a, **_kw):
            with open(path, "a") as handle:
                handle.write("# someone else's line\n")
            raise CorpusError("broken")

        with mock.patch("ruleprobe.cli.score_corpus", side_effect=score):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertRegex(err, "labels.yaml, left as it is: it holds \\d+ bytes that are not "
                              "the original with the new entry after it")
        with open(path) as handle:
            self.assertTrue(handle.read().endswith("# someone else's line\n"))
        self.assertFalse(os.path.exists(os.path.join(self.corpus, "sessions",
                                                     "wrong-hit.events.jsonl")))

    def test_a_failed_restore_leaves_the_file_whole_and_says_so(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written()
        with mock.patch("ruleprobe.cli.score_corpus", side_effect=CorpusError("broken")), \
                mock.patch("ruleprobe.cli.os.replace", side_effect=OSError("no replace")):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("labels.yaml, not restored: it holds the original followed by some, "
                      "all or none of the new entry (OSError)", err)
        with open(path) as handle:
            after = handle.read()
        self.assertTrue(after.startswith(self.HAND_WRITTEN))
        self.assertIn("wrong-hit.events.jsonl", after)
        self.assertEqual(sorted(os.listdir(self.corpus)), ["labels.yaml", "sessions"])

    def test_an_fdopen_failure_closes_the_descriptor_and_rolls_back(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        before = tree(self.scratch)
        real_close = os.close
        with mock.patch("ruleprobe.cli.os.fdopen", side_effect=OSError("no fdopen")), \
                mock.patch("ruleprobe.cli.os.close", side_effect=real_close) as close:
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("no fdopen; nothing was kept", err)
        self.assertEqual(close.call_count, 1)
        self.assertEqual(tree(self.scratch), before)

    def after_the_check(self, change):
        """Run `change` once `labels.yaml` has been checked and before it is written."""
        from ruleprobe import cli

        real = cli._labels_addition

        def checked(*args):
            out = real(*args)
            change()
            return out

        return mock.patch("ruleprobe.cli._labels_addition", side_effect=checked)

    def test_a_labels_file_changed_since_the_check_is_refused(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written()

        def edit():
            with open(path, "a") as handle:
                handle.write("# edited meanwhile\n")

        with self.after_the_check(edit):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("changed since it was checked; nothing was kept", err)
        with open(path) as handle:
            self.assertEqual(handle.read(), self.HAND_WRITTEN + "# edited meanwhile\n")
        self.assertEqual(os.listdir(os.path.join(self.corpus, "sessions")),
                         ["old.events.jsonl"])

    def test_a_labels_file_swapped_for_a_link_is_not_written_through(self):
        self.transcript([("toolu_1", "Bash", {"command": "git commit --no-verify"})])
        path = self.hand_written()
        target = os.path.join(self.sibling, "other.yaml")
        with open(target, "w") as handle:
            handle.write(self.HAND_WRITTEN)

        def swap():
            os.remove(path)
            os.symlink(target, path)

        with self.after_the_check(swap):
            code, _text, err = self.label()
        self.assertEqual(code, 2)
        self.assertIn("became a link or changed kind since it was checked", err)
        with open(target) as handle:
            self.assertEqual(handle.read(), self.HAND_WRITTEN)


if __name__ == "__main__":
    unittest.main()
