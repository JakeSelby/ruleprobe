# SPDX-License-Identifier: MIT
"""One regression test per finding of the pre-release review (issue #2).

Each test is the reviewer's own input, kept verbatim where it was concrete, so a fix that
is later undone fails here under the number it was reported as.
"""
import os
import tempfile
import unittest

from corpus import bash, tool_use
from ruleprobe import Detector, Registry, iter_sessions, report, run
from ruleprobe.matchers import compile_detector
from ruleprobe.shell import Parsed, pipelines, strip_heredocs


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


if __name__ == "__main__":
    unittest.main()
