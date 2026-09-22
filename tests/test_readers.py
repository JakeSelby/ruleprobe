# SPDX-License-Identifier: MIT
"""The readers, over two hand-written transcripts.

`tests/fixtures/claude-code-session.jsonl` and `tests/fixtures/codex-rollout.jsonl` are
written by hand from the line shapes each runtime documents in its own files: a dozen lines
each, no real content, no paths anyone's machine has. They carry the three shapes that are
easy to get wrong - a block written twice, a subagent's sidechain line, and a tool call whose
arguments arrive as a JSON string - because those are what a reader has to get right.
"""
import os
import unittest

from ruleprobe import iter_sessions, run
from ruleprobe.readers import claude_code, codex

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
CLAUDE = os.path.join(FIXTURES, "claude-code-session.jsonl")
CODEX = os.path.join(FIXTURES, "codex-rollout.jsonl")


class ClaudeCodeTests(unittest.TestCase):
    def setUp(self):
        self.session = claude_code.read(CLAUDE)

    def test_the_session_knows_its_id_repo_and_runtime(self):
        self.assertEqual(self.session.id, "sess-1")
        self.assertEqual(self.session.repo, "demo-repo")
        self.assertEqual(self.session.runtime, "claude-code")
        self.assertEqual(self.session.ended[:10], "2026-09-20")

    def test_a_block_written_twice_is_one_event(self):
        uses = [e for e in self.session.events if e["kind"] == "tool_use"]
        self.assertEqual([e["id"] for e in uses], ["toolu_1", "toolu_2"])

    def test_a_sidechain_line_is_the_subagents_work_and_makes_no_event(self):
        self.assertNotIn("transcript-hygiene/unfiltered-find", run(self.session.events))

    def test_the_last_assistant_text_is_the_final_one(self):
        finals = [e for e in self.session.events
                  if e["kind"] == "assistant_text" and e["final"]]
        self.assertEqual([e["text"] for e in finals], ["Fixed."])

    def test_a_tool_result_carries_the_name_of_the_call_it_answers(self):
        results = [e for e in self.session.events if e["kind"] == "tool_result"]
        self.assertEqual(results[0]["tool_name"], "Bash")
        self.assertIn("timeout: 30", results[0]["text"])

    def test_the_detectors_read_it(self):
        hits = run(self.session.events, strict=True)
        self.assertEqual(sorted(hits), ["cache-hygiene/compact", "cache-hygiene/model-switch",
                                        "transcript-hygiene/whole-file-cat",
                                        "verification/no-verify"])


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.session = codex.read(CODEX)

    def test_the_rollout_knows_its_id_repo_and_runtime(self):
        self.assertEqual(self.session.id, "rollout-1")
        self.assertEqual(self.session.repo, "other-repo")
        self.assertEqual(self.session.runtime, "codex")

    def test_exec_command_is_read_as_bash_and_its_arguments_are_json(self):
        use = [e for e in self.session.events if e["kind"] == "tool_use"][0]
        self.assertEqual(use["name"], "Bash")
        self.assertEqual(use["input"]["command"], "find .")

    def test_the_model_is_the_one_the_turn_named(self):
        texts = [e for e in self.session.events if e["kind"] == "assistant_text"]
        self.assertEqual(texts[0]["model"], "gpt-5.1-codex")
        self.assertTrue(texts[0]["final"])

    def test_the_detectors_read_it(self):
        self.assertEqual(sorted(run(self.session.events, strict=True)),
                         ["transcript-hygiene/unfiltered-find"])


class IterSessionTests(unittest.TestCase):
    def test_a_mixed_directory_is_read_by_deciding_each_file_on_its_first_line(self):
        sessions = list(iter_sessions(root=FIXTURES))
        self.assertEqual(sorted(s.runtime for s in sessions), ["claude-code", "codex"])

    def test_a_named_runtime_reads_only_what_that_reader_understands(self):
        # Both files are offered to the Codex reader; the Claude Code one names no session
        # and holds no response item, so it yields nothing rather than a hollow row.
        sessions = list(iter_sessions(root=FIXTURES, runtime="codex"))
        self.assertEqual([(s.runtime, s.id) for s in sessions], [("codex", "rollout-1")])

    def test_an_unknown_runtime_is_refused(self):
        with self.assertRaises(ValueError):
            list(iter_sessions(root=FIXTURES, runtime="emacs"))

    def test_since_drops_the_transcripts_that_ended_before_it(self):
        self.assertEqual(len(list(iter_sessions(root=FIXTURES, since="2026-01-01"))), 2)
        self.assertEqual(len(list(iter_sessions(root=FIXTURES, since="2026-09-21"))), 1)
        self.assertEqual(list(iter_sessions(root=FIXTURES, since="2026-09-30")), [])

    def test_an_empty_directory_yields_nothing_rather_than_raising(self):
        self.assertEqual(list(iter_sessions(root=os.path.join(FIXTURES, "nothing-here"))), [])


if __name__ == "__main__":
    unittest.main()
