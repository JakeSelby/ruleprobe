# SPDX-License-Identifier: MIT
"""One regression test per finding of the pre-release review (issue #2).

Each test is the reviewer's own input, kept verbatim where it was concrete, so a fix that
is later undone fails here under the number it was reported as.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from corpus import bash, tool_use
from ruleprobe import Detector, Registry, iter_sessions, measure, report, run
from ruleprobe.cli import _since, main
from ruleprobe.declarative import DeclarativeError, parse
from ruleprobe.matchers import compile_detector
from ruleprobe.readers import claude_code, codex
from ruleprobe.report import report_data
from ruleprobe.shell import MAX_COMMAND, Parsed, pipelines, strip_heredocs


def parsed(command):
    return Parsed(bash(command))


def detector(**spec):
    return compile_detector(dict({"id": "t/x", "rule": "t", "event": "tool_use"}, **spec))


def fires(spec, events):
    return bool(run(events, registry=Registry([detector(**spec)]), strict=True))


def rows(*hits, **extra):
    out = []
    for hit in hits:
        row = {"session_id": "s", "repo": "demo", "rules": dict(hit)}
        row.update(extra)
        out.append(row)
    return out


class ShellFindingTests(unittest.TestCase):
    def test_finding_03_escaped_heredoc_delimiter(self):
        command = "cat <<\\EOF > n.md\nfind /\nEOF"
        self.assertEqual(strip_heredocs(command)[1], ["find /"])
        self.assertEqual(pipelines(command)[0][0][0], "cat")
        self.assertEqual(run([bash(command)]), {})

    def test_finding_04_an_indented_terminator_does_not_close_a_plain_heredoc(self):
        command = "cat <<EOF > n.md\n  EOF\nfind /\nEOF"
        self.assertEqual(strip_heredocs(command)[1], ["  EOF\nfind /"])
        self.assertEqual(run([bash(command)]), {})

    def test_finding_04_a_dash_heredoc_still_closes_on_a_tabbed_terminator(self):
        self.assertEqual(strip_heredocs("cat <<-EOF\n\tbody\n\tEOF\nls")[1], ["\tbody"])

    def test_finding_05_an_unbalanced_quote_is_unparsed_not_invisible(self):
        p = parsed('echo "unclosed')
        self.assertTrue(p.skipped)
        self.assertEqual(p.pipelines, [])

    def test_finding_05_an_unparsable_command_is_visible_as_unparsed(self):
        spec = {"when": {"command": {"unparsed": True}}}
        self.assertTrue(fires(spec, [bash('echo "unclosed')]))
        self.assertFalse(fires(spec, [bash("echo closed")]))


class DenominatorFindingTests(unittest.TestCase):
    REGISTRY = Registry([Detector("a/one", "a", "session", lambda e, c: []),
                         Detector("a/two", "a", "session", lambda e, c: [])])

    def test_finding_06_one_raising_detector_costs_only_its_own_denominator(self):
        measured = rows({"a/one": 1})
        measured += rows({"a/one": 9},
                         rules_errors=[{"detector": "a/two", "error": "KeyError"}])
        text = report(measured, registry=self.REGISTRY)
        one = [x for x in text.split("\n") if x.startswith("a/one")][0]
        two = [x for x in text.split("\n") if x.startswith("a/two")][0]
        self.assertEqual(one.split()[1:4], ["10", "2", "2"])
        self.assertEqual(two.split()[1:4], ["0", "0", "1"])

    def test_finding_07_an_unhashable_field_value_does_not_raise(self):
        spec = {"when": {"arg": {"field": "edits", "equals": ["x"]}}}
        events = [tool_use("Edit", {"edits": [{"old": "a"}]})]
        self.assertFalse(fires(spec, events))

    def test_finding_07_equals_still_matches_a_list_written_in_the_spec(self):
        spec = {"when": {"arg": {"field": "edits", "equals": [["a", "b"]]}}}
        self.assertTrue(fires(spec, [tool_use("Edit", {"edits": ["a", "b"]})]))

    def test_finding_20_a_transcript_that_yields_no_session_is_counted(self):
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "half.jsonl"), "w") as handle:
                handle.write('{"type": "user", "mes\n')
            self.assertEqual(list(iter_sessions(root=directory, errors=errors)), [])
        self.assertEqual([e["error"] for e in errors], ["no session in it"])

    def test_finding_20_the_cli_says_how_many_transcripts_produced_nothing(self):
        from ruleprobe.cli import _read_errors_line

        self.assertIn("2 transcript(s) produced no session",
                      _read_errors_line([{"path": "/t/a.jsonl", "error": "ValueError"},
                                         {"path": "/t/b.jsonl", "error": "OSError"}]))
        self.assertEqual(_read_errors_line([]), "")


class MatcherFindingTests(unittest.TestCase):
    def test_finding_08_an_event_less_session_is_not_an_absence(self):
        spec = {"event": "session",
                "when": {"absent": {"of": {"command": {"name": ["pytest"]}},
                                    "scope": "session"}}}
        self.assertFalse(fires(spec, []))
        self.assertTrue(fires(spec, [bash("ls")]))

    def test_finding_10_a_rename_removes_the_detector_it_renamed(self):
        registry = Registry([Detector("a/old", "a", "session", lambda e, c: [(1, None)]),
                             Detector("a/one", "a", "session", lambda e, c: [(1, None)])])
        registry.rename("a/old", "a/one")
        self.assertEqual(registry.ids(), ["a/one"])
        self.assertEqual(sorted(run([bash("ls")], registry=registry)), ["a/one"])
        text = report(rows({"a/old": 1, "a/one": 1}), registry=registry)
        self.assertNotIn("a/old", text)
        self.assertIn("a/one", text)

    def test_finding_12_command_contains_is_a_substring_of_a_token(self):
        spec = {"when": {"command": {"contains": "no-verify"}}}
        self.assertTrue(fires(spec, [bash("git commit --no-verify -m x")]))
        self.assertFalse(fires(spec, [bash("git commit -m x")]))

    def test_finding_13_a_list_of_command_regexes_is_alternatives(self):
        spec = {"when": {"command": {"regex": ["^ruff ", "^black "]}}}
        self.assertTrue(fires(spec, [bash("ruff check .")]))
        self.assertTrue(fires(spec, [bash("black .")]))
        self.assertFalse(fires(spec, [bash("pytest -q")]))

    def test_finding_21_order_within_does_not_spend_its_budget_on_tool_results(self):
        spec = {"event": "session",
                "when": {"order": {"first": {"command": {"name": ["git"]}},
                                   "then": {"command": {"name": ["pytest"]}},
                                   "within": 2}}}
        events = [bash("git add -A", id="t1"),
                  {"kind": "tool_result", "turn": 1, "tool_use_id": "t1",
                   "tool_name": "Bash", "text": ""},
                  bash("ls", turn=1, id="t2"),
                  {"kind": "tool_result", "turn": 1, "tool_use_id": "t2",
                   "tool_name": "Bash", "text": ""},
                  bash("pytest -q", turn=1, id="t3")]
        self.assertTrue(fires(spec, events))

    def test_finding_22_a_path_glob_does_not_cross_a_separator(self):
        spec = {"when": {"arg": {"field": "file_path", "path_glob": "src/*.py"}}}
        self.assertTrue(fires(spec, [tool_use("Write", {"file_path": "/w/repo/src/a.py"})]))
        self.assertFalse(fires(spec, [tool_use("Write",
                                               {"file_path": "/w/repo/src/deep/a.py"})]))

    def test_finding_22_a_double_star_is_how_any_depth_is_asked_for(self):
        spec = {"when": {"arg": {"field": "file_path", "path_glob": "tests/**"}}}
        self.assertTrue(fires(spec, [tool_use("Write", {"file_path": "/w/tests/x/y.py"})]))
        self.assertFalse(fires(spec, [tool_use("Write", {"file_path": "/w/src/y.py"})]))


class ParserFindingTests(unittest.TestCase):
    def test_finding_14_an_escaped_quote_inside_a_string_is_not_a_comment(self):
        document = parse('regex: "a\\" # b"\n')
        self.assertEqual(document, {"regex": 'a" # b'})

    def test_finding_15_a_pair_in_a_flow_sequence_is_a_one_key_mapping(self):
        self.assertEqual(parse("when: [a: b, c]\n"), {"when": [{"a": "b"}, "c"]})

    def test_finding_16_a_yaml_1_1_boolean_word_is_refused_rather_than_guessed(self):
        for text in ("k: yes\n", "k: no\n", "k: On\n", "k: OFF\n"):
            with self.subTest(text=text):
                with self.assertRaises(DeclarativeError):
                    parse(text)
        self.assertEqual(parse('k: "no"\n'), {"k": "no"})
        self.assertEqual(parse("k: true\n"), {"k": True})

    def test_finding_16_a_leading_zero_number_is_refused_rather_than_read_as_ten(self):
        with self.assertRaises(DeclarativeError):
            parse("within: 010\n")
        self.assertEqual(parse("within: 10\n"), {"within": 10})
        self.assertEqual(parse("within: 0\n"), {"within": 0})

    def test_finding_19_a_claude_prompt_quoting_session_meta_is_not_a_codex_rollout(self):
        line = json.dumps({"type": "user", "sessionId": "s-1", "cwd": "/w/repo",
                           "timestamp": "2026-09-20T10:00:00.000Z",
                           "message": {"role": "user",
                                       "content": 'why is "session_meta" first?'}})
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "quoting.jsonl")
            with open(path, "w") as handle:
                handle.write(line + "\n")
            sessions = list(iter_sessions(root=directory))
        self.assertEqual([s.runtime for s in sessions], ["claude-code"])


class GatingFindingTests(unittest.TestCase):
    """Findings 1, 2, 11 and 24: the command line as the only way a gate, a stance or a
    JSON denominator is reachable."""

    GATED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "gated-detector.yaml")
    FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            return main(list(argv), out=out), out.getvalue()

    def test_finding_01_a_gated_detector_fires_once_the_stance_is_passed(self):
        code, text = self.run_cli("report", "--root", self.FIXTURES, "--no-config",
                                  "--detectors", self.GATED,
                                  "--stance", "commits=conventional")
        self.assertEqual(code, 0)
        line = [x for x in text.split("\n") if x.startswith("gated/commit")][0]
        self.assertEqual(line.split()[1:4], ["1", "1", "2"])

    def test_finding_01_the_same_detector_is_silent_with_no_stance(self):
        _code, text = self.run_cli("report", "--root", self.FIXTURES, "--no-config",
                                   "--detectors", self.GATED)
        line = [x for x in text.split("\n") if x.startswith("gated/commit")][0]
        self.assertEqual(line.split()[1:4], ["0", "0", "2"])

    def test_finding_01_the_detector_listing_names_the_stance_a_gate_wants(self):
        _code, text = self.run_cli("detectors", "--no-config", "--detectors", self.GATED)
        self.assertIn("gated on --stance commits=conventional", text)

    def test_finding_02_by_stance_groups_on_what_the_command_line_was_given(self):
        _code, text = self.run_cli("report", "--root", self.FIXTURES, "--no-config",
                                   "--by", "stance", "--stance", "commits=conventional")
        self.assertIn("commits=conventional", text)
        self.assertNotIn("(no stances)", text)

    def test_finding_02_a_stance_without_a_variant_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_cli("report", "--root", self.FIXTURES, "--stance", "commits")

    def test_finding_11_json_applies_the_same_denominator_and_min_sessions(self):
        _code, text = self.run_cli("report", "--root", self.FIXTURES, "--no-config",
                                   "--min-sessions", "1", "--frequent-share", "0.1",
                                   "--json")
        data = json.loads(text)
        self.assertEqual(data["min_sessions"], 1)
        self.assertEqual(data["frequent_share"], 0.1)
        notes = dict((d["detector"], d["note"]) for d in data["detectors"])
        self.assertIn("frequent", set(notes.values()))
        self.assertEqual(data["detectors"][0]["of"], data["measured"])

    def test_finding_11_json_folds_a_rename_the_way_the_table_does(self):
        registry = Registry([Detector("a/one", "a", "session", lambda e, c: [])])
        registry.rename("a/old", "a/one")
        data = report_data(rows({"a/old": 2, "a/one": 1}), registry=registry)
        self.assertEqual([(d["detector"], d["hits"]) for d in data["detectors"]],
                         [("a/one", 3)])

    def test_finding_11_json_exits_non_zero_on_an_empty_root_like_the_table(self):
        empty = os.path.join(self.FIXTURES, "nothing-here")
        self.assertEqual(self.run_cli("report", "--root", empty, "--json")[0], 1)
        self.assertEqual(self.run_cli("report", "--root", empty)[0], 1)

    def test_finding_24_a_bare_year_is_refused_rather_than_read_as_days(self):
        with self.assertRaises(SystemExit):
            self.run_cli("report", "--root", self.FIXTURES, "--since", "2024")
        self.assertEqual(_since("30"), 30)
        self.assertEqual(_since("2024-01-01"), "2024-01-01")


def write_session(directory, name, lines):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


class ReaderFindingTests(unittest.TestCase):
    def test_finding_17_a_streamed_partial_block_is_one_message_not_two(self):
        lines = [
            {"type": "user", "sessionId": "s", "cwd": "/w/repo",
             "message": {"role": "user", "content": "go"}},
            {"type": "assistant", "sessionId": "s",
             "message": {"id": "msg_1", "model": "m", "content": [{"type": "text",
                                                                   "text": "I will "}]}},
            {"type": "assistant", "sessionId": "s",
             "message": {"id": "msg_1", "model": "m",
                         "content": [{"type": "text", "text": "I will run tests."}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            session = claude_code.read(write_session(directory, "s.jsonl", lines))
        texts = [e for e in session.events if e["kind"] == "assistant_text"]
        self.assertEqual([e["text"] for e in texts], ["I will run tests."])

    def test_finding_17_the_user_prompt_carries_its_text_on_claude_code(self):
        lines = [{"type": "user", "sessionId": "s", "cwd": "/w/repo",
                  "message": {"role": "user", "content": "run the tests"}}]
        with tempfile.TemporaryDirectory() as directory:
            session = claude_code.read(write_session(directory, "s.jsonl", lines))
        prompts = [e for e in session.events if e["kind"] == "user_prompt"]
        self.assertEqual([e["text"] for e in prompts], ["run the tests"])

    def test_finding_18_a_codex_user_message_is_a_user_prompt(self):
        lines = [
            {"type": "session_meta", "payload": {"id": "r-1", "cwd": "/w/repo"}},
            {"type": "turn_context", "payload": {"model": "gpt-5-codex"}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "run the tests"}]}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "Ran them."}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            session = codex.read(write_session(directory, "r.jsonl", lines))
        prompts = [e for e in session.events if e["kind"] == "user_prompt"]
        self.assertEqual([e["text"] for e in prompts], ["run the tests"])
        spec = {"event": "assistant_text", "when": {"message": {"role": "user"}}}
        self.assertTrue(fires(dict(spec, event="session"), session.events))

    def test_finding_18_the_final_message_is_derived_and_not_read_from_phase(self):
        lines = [
            {"type": "session_meta", "payload": {"id": "r-1", "cwd": "/w/repo"}},
            {"type": "turn_context", "payload": {"model": "gpt-5-codex"}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "Working."}]}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "and now?"}]}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "Done."}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            session = codex.read(write_session(directory, "r.jsonl", lines))
        texts = [e for e in session.events if e["kind"] == "assistant_text"]
        self.assertEqual([(e["text"], e["final"]) for e in texts],
                         [("Working.", True), ("Done.", True)])


class ClaimFindingTests(unittest.TestCase):
    """Finding 23: two shipped files claimed the corpus file used every matcher. Where the
    claim was false, the claim is what changed, so these assert the claim is gone."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def read(self, *parts):
        with open(os.path.join(self.ROOT, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_finding_23_neither_file_claims_every_matcher_is_used(self):
        self.assertNotIn("every matcher the format has is",
                         self.read("ruleprobe", "detectors", "common.yaml"))
        self.assertNotIn("uses all\nbut four", self.read("README.md"))
        self.assertNotIn("uses all but four", self.read("README.md"))

    def test_finding_23_the_matchers_the_shipped_six_leave_out_are_named(self):
        readme = self.read("README.md")
        for name in ("`message`, `order`, `absent` and `not`",):
            self.assertIn(name, readme)


class BlindSpotTests(unittest.TestCase):
    """Finding 25: the cases the reviewer found no test for and that no other test here
    covers - a truncated JSONL line, a command past the size cap, and an errored row's
    effect on a rate through `measure()` rather than on a hand-written row."""

    def test_finding_25_a_garbage_line_does_not_cost_the_rest_of_the_transcript(self):
        lines = ['{"type": "user", "sessionId": "s", "cwd": "/w/repo", '
                 '"message": {"role": "user", "content": "go"}}',
                 "not json at all",
                 '{"type": "assistant", "sessionId": "s", "message": {"id": "m", '
                 '"model": "x", "content": [{"type": "text", "text": "Done."}]}}',
                 '{"type": "assistant", "sessionId": "s", "mess']
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "s.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
            session = claude_code.read(path)
        self.assertEqual([e["kind"] for e in session.events],
                         ["user_prompt", "assistant_text"])

    def test_finding_25_a_command_past_the_size_cap_is_unparsed_and_not_scanned(self):
        p = parsed("echo " + "x" * (MAX_COMMAND + 1))
        self.assertTrue(p.skipped)
        self.assertEqual(p.pipelines, [])

    def test_finding_25_an_errored_detector_leaves_the_rate_it_could_not_measure(self):
        def boom(events, ctx):
            raise ValueError("no")

        registry = Registry([Detector("a/boom", "a", "session", boom),
                             Detector("a/fine", "a", "session", lambda e, c: [(1, None)])])
        session = list(iter_sessions(root=GatingFindingTests.FIXTURES))[0]
        measured = measure(session, registry=registry)
        self.assertEqual(measured["rules"], {"a/fine": 1})
        data = report_data([measured], registry=registry)
        by_id = dict((d["detector"], d) for d in data["detectors"])
        self.assertEqual(by_id["a/boom"]["of"], 0)
        self.assertEqual(by_id["a/fine"]["of"], 1)


if __name__ == "__main__":
    unittest.main()
