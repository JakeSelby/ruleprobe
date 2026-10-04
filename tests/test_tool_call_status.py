# SPDX-License-Identifier: MIT
"""A tool call counts as a tool use exactly when it ran, on every reader.

A call the user refused or cancelled, one a permission rule denied, and one stopped by a check
before the tool ran make no `tool_use` and no `tool_result`, so no detector counts it, for a
violation or for compliance. A call that ran and reported failure still counts: a test run
that exits non-zero is a test run. Every transcript here is synthetic, written in a temporary
directory from the shapes each runtime writes.
"""
import json
import os
import shutil
import tempfile
import unittest

from ruleprobe import Registry, analyse, run
from ruleprobe.readers import claude_code, codex
from ruleprobe.rules import _CATALOG

from test_reader_gemini import TreeTest, call, gemini_record, meta, user

SECRET = "aws_access_key_id = AKIAEXAMPLE000000000\n"
SECRET_IN_WRITE = "secrets/secret-in-write"
TEST_AFTER_CHANGE = "testing/test-after-change"
UNFILTERED_FIND = "transcript-hygiene/unfiltered-find"


def tested(events):
    """The test-after-change hits: changes a later test run followed."""
    detector = dict((d.id, d) for _p, d in _CATALOG)[TEST_AFTER_CHANGE]
    hits = run(events, registry=Registry([detector]), strict=True).get(TEST_AFTER_CHANGE, [])
    return [(h.turn, h.tool_use_id) for h in hits]


def uses(session):
    return [e["id"] for e in session.events if e["kind"] == "tool_use"]


def results(session):
    return [e["tool_use_id"] for e in session.events if e["kind"] == "tool_result"]


class Temporary(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, True)

    def write(self, lines):
        path = os.path.join(self.base, "transcript.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")
        return path


class GeminiTests(TreeTest):
    """Gemini CLI records `status` on each call: only `success` counts."""

    def session(self, *calls):
        return self.tree.session([meta(), user("u1", "go"), gemini_record("g1", "", list(calls))])

    def with_status(self, record, status, error):
        record = dict(record, status=status)
        record["result"] = [{"functionResponse": {"id": record["id"], "name": record["name"],
                                                  "response": {"error": error}}}]
        return record

    def test_a_cancelled_write_makes_no_event_and_no_secret_hit(self):
        declined = self.with_status(
            call("w1", "write_file", {"file_path": "/workspace/demo-project/a.ini",
                                      "content": SECRET}),
            "cancelled", "[Operation Cancelled] Reason: User denied execution.")
        session = self.session(declined)
        self.assertEqual((uses(session), results(session)), ([], []))
        self.assertNotIn(SECRET_IN_WRITE, run(session.events))

    def test_an_errored_call_makes_no_event(self):
        refused = self.with_status(
            call("w1", "write_file", {"file_path": "/workspace/demo-project/a.ini",
                                      "content": SECRET}),
            "error", "Tool execution denied by policy.")
        session = self.session(refused)
        self.assertEqual((uses(session), results(session)), ([], []))
        self.assertNotIn(SECRET_IN_WRITE, run(session.events))

    def test_a_call_in_any_other_status_makes_no_event(self):
        for status in ("executing", "scheduled", None):
            with self.subTest(status=status):
                record = call("c1", "run_shell_command", {"command": "pytest"})
                record = dict(record, status=status) if status else \
                    dict((k, v) for k, v in record.items() if k != "status")
                self.assertEqual(uses(self.session(record)), [])

    def test_a_test_run_that_exits_non_zero_still_follows_the_change(self):
        session = self.session(
            call("e1", "replace", {"file_path": "src/app.py", "old_string": "30",
                                   "new_string": "60"}),
            call("t1", "run_shell_command", {"command": "python3 -m pytest -q"},
                 output="1 failed, 3 passed\nExit Code: 1"))
        self.assertEqual(uses(session), ["e1", "t1"])
        self.assertEqual(tested(session.events), [(1, "e1")])

    def test_a_declined_change_opens_no_opportunity(self):
        declined = self.with_status(
            call("e1", "replace", {"file_path": "src/app.py", "old_string": "30",
                                   "new_string": "60"}),
            "cancelled", "[Operation Cancelled] Reason: User denied execution.")
        session = self.session(declined)
        detector = dict((d.id, d) for _p, d in _CATALOG)[TEST_AFTER_CHANGE]
        self.assertEqual(detector.opportunities(session.events, analyse(session.events)), [])


class ClaudeCodeTests(Temporary):
    """Claude Code answers a call that never ran with a fixed error result."""

    def line(self, kind, content, **extra):
        message = {"role": kind, "content": content}
        if kind == "assistant":
            message = {"id": "msg_%d" % len(self.lines), "model": "claude-opus-5",
                       "content": content}
        line = dict({"type": kind, "timestamp": "2026-09-20T10:00:%02d.000Z" % len(self.lines),
                     "sessionId": "sess-status", "cwd": "/workspace/demo-repo",
                     "message": message}, **extra)
        self.lines.append(line)

    def call(self, use_id, name, arguments, result, is_error=False, **extra):
        self.line("assistant", [{"type": "tool_use", "id": use_id, "name": name,
                                 "input": arguments}])
        block = {"type": "tool_result", "tool_use_id": use_id, "content": result}
        if is_error:
            block["is_error"] = True
        self.line("user", [block], **extra)

    def read(self):
        return claude_code.read(self.write(self.lines))

    def setUp(self):
        Temporary.setUp(self)
        self.lines = []
        self.line("user", "store the credentials")

    def write_secret(self, result, is_error=True, **extra):
        self.call("w1", "Write", {"file_path": "/workspace/demo-repo/a.ini", "content": SECRET},
                  result, is_error, **extra)

    def test_a_rejected_write_makes_no_event_and_no_secret_hit(self):
        self.write_secret("The user doesn't want to proceed with this tool use. The tool use "
                          "was rejected (eg. if it was a file edit, the new_string was NOT "
                          "written to the file). STOP what you are doing and wait for the user "
                          "to tell you how to proceed.", toolUseResult="User rejected tool use")
        session = self.read()
        self.assertEqual((uses(session), results(session)), ([], []))
        self.assertNotIn(SECRET_IN_WRITE, run(session.events))

    def test_each_refusal_shape_makes_no_event(self):
        refusals = [
            ("The user doesn't want to take this action right now. STOP what you are doing.",
             {}),
            ("[Request interrupted by user for tool use]", {}),
            ("[Tool call not completed: an approval request was still unanswered.]", {}),
            ("[Tool call did not complete: the turn was ended to deliver a message.]", {}),
            ("[Tool call interrupted: the session ended.]", {}),
            ("PreToolUse:Write hook error: [./guard.sh]: writes to deploy/ are blocked", {}),
            ("Permission to use Write has been denied.", {}),
            ("<tool_use_error>InputValidationError: content is missing</tool_use_error>", {}),
            ("<tool_use_error>File has not been read yet.</tool_use_error>", {}),
            ("<tool_use_error>Cancelled: parallel tool call Bash errored</tool_use_error>", {}),
            ("<tool_use_error>A rule denies Write</tool_use_error>",
             {"toolDenialKind": "permission-rule"}),
            ([{"type": "text", "text": "anything"}], {"toolDenialKind": "user-rejected"}),
        ]
        for text, extra in refusals:
            with self.subTest(text=text):
                self.lines = self.lines[:1]
                self.write_secret(text, **extra)
                session = self.read()
                self.assertEqual((uses(session), results(session)), ([], []))

    def test_a_result_that_is_not_an_error_counts_whatever_it_says(self):
        self.write_secret("Permission to use this file is granted.", is_error=False)
        self.assertEqual(uses(self.read()), ["w1"])

    def test_a_hook_error_after_the_tool_ran_counts(self):
        self.write_secret("PostToolUse:Write hook error: [./lint.sh]: formatting failed")
        self.assertEqual(uses(self.read()), ["w1"])

    def test_each_result_on_a_line_of_several_is_decided_by_its_own_text(self):
        self.line("assistant", [
            {"type": "tool_use", "id": "w1", "name": "Write",
             "input": {"file_path": "/workspace/demo-repo/a.ini", "content": SECRET}},
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "python3 -m pytest -q"}}])
        self.line("user", [
            {"type": "tool_result", "tool_use_id": "w1", "is_error": True,
             "content": "The user doesn't want to proceed with this tool use."},
            {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
             "content": "Exit code 1\n1 failed"}],
            toolDenialKind="user-rejected", toolUseResult="User rejected tool use")
        session = self.read()
        self.assertEqual((uses(session), results(session)), (["t1"], ["t1"]))
        self.assertNotIn(SECRET_IN_WRITE, run(session.events))

    def test_an_error_the_running_tool_raised_counts(self):
        self.write_secret("<tool_use_error>Error calling tool (Write): EACCES: permission "
                          "denied</tool_use_error>")
        session = self.read()
        self.assertEqual(uses(session), ["w1"])
        self.assertIn(SECRET_IN_WRITE, run(session.events))

    def test_a_test_run_that_exits_non_zero_still_follows_the_change(self):
        self.call("e1", "Edit", {"file_path": "/workspace/demo-repo/src/app.py",
                                 "old_string": "30", "new_string": "60"}, "Edited")
        self.call("t1", "Bash", {"command": "python3 -m pytest -q"},
                  "Exit code 1\n1 failed, 3 passed", is_error=True,
                  toolUseResult="Error: Exit code 1")
        session = self.read()
        self.assertEqual(uses(session), ["e1", "t1"])
        self.assertEqual(tested(session.events), [(1, "e1")])

    def test_a_rejected_test_run_does_not_follow_the_change(self):
        self.call("e1", "Edit", {"file_path": "/workspace/demo-repo/src/app.py",
                                 "old_string": "30", "new_string": "60"}, "Edited")
        self.call("t1", "Bash", {"command": "python3 -m pytest -q"},
                  "The user doesn't want to proceed with this tool use.", is_error=True)
        session = self.read()
        self.assertEqual(uses(session), ["e1"])
        self.assertEqual(tested(session.events), [])


class CodexTests(Temporary):
    """Codex answers a call that never ran with a fixed output."""

    def setUp(self):
        Temporary.setUp(self)
        self.lines = [
            {"type": "session_meta", "timestamp": "2026-09-20T10:00:00.000Z",
             "payload": {"id": "rollout-status", "cwd": "/workspace/demo-repo"}},
            {"type": "turn_context", "timestamp": "2026-09-20T10:00:01.000Z",
             "payload": {"model": "gpt-5-codex"}},
            {"type": "response_item", "timestamp": "2026-09-20T10:00:01.500Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "go"}]}},
        ]

    def item(self, payload):
        self.lines.append({"type": "response_item", "timestamp": "2026-09-20T10:00:02.000Z",
                           "payload": payload})

    def exec_call(self, call_id, cmd, output):
        self.item({"type": "function_call", "call_id": call_id, "name": "exec_command",
                   "arguments": json.dumps({"cmd": cmd})})
        self.item({"type": "function_call_output", "call_id": call_id, "output": output})

    def patch(self, call_id, output):
        self.item({"type": "custom_tool_call", "call_id": call_id, "name": "apply_patch",
                   "input": "*** Begin Patch\n*** Update File: src/app.py\n*** End Patch\n"})
        self.item({"type": "custom_tool_call_output", "call_id": call_id, "output": output})

    def read(self):
        return codex.read(self.write(self.lines))

    def test_a_rejected_or_aborted_command_makes_no_event_and_no_hit(self):
        for output in ("exec command rejected by user", "aborted",
                       [{"type": "input_text", "text": "aborted"}]):
            with self.subTest(output=output):
                self.lines = self.lines[:3]
                self.exec_call("c1", "find /", output)
                session = self.read()
                self.assertEqual((uses(session), results(session)), ([], []))
                self.assertNotIn(UNFILTERED_FIND, run(session.events))

    def test_a_rejected_patch_opens_no_opportunity(self):
        for output in ("patch rejected by user", "patch rejected: writing outside of the "
                       "project; rejected by user approval settings"):
            with self.subTest(output=output):
                self.lines = self.lines[:3]
                self.patch("p1", output)
                self.exec_call("t1", "pytest -q", "Process exited with code 0\nOutput:\n4 passed")
                session = self.read()
                self.assertEqual(uses(session), ["t1"])
                self.assertEqual(tested(session.events), [])

    def test_a_patch_that_failed_verification_opens_no_opportunity(self):
        self.patch("p1", "apply_patch verification failed: Failed to find expected lines in "
                         "src/app.py")
        self.exec_call("t1", "pytest -q", "Process exited with code 0\nOutput:\n4 passed")
        session = self.read()
        self.assertEqual(uses(session), ["t1"])
        self.assertEqual(tested(session.events), [])

    def test_output_that_only_contains_a_refusal_word_ran(self):
        for output in ("Process exited with code 1\nOutput:\naborted",
                       "Process exited with code 0\nOutput:\nexec command rejected by user",
                       "Output:\napply_patch verification failed: in a log line"):
            with self.subTest(output=output):
                self.lines = self.lines[:3]
                self.exec_call("c1", "find /", output)
                session = self.read()
                self.assertEqual(uses(session), ["c1"])
                self.assertIn(UNFILTERED_FIND, run(session.events))

    def test_a_command_that_ran_counts_whatever_its_exit_code(self):
        self.exec_call("c1", "find /", "Process exited with code 1\nOutput:\nfind: denied")
        session = self.read()
        self.assertEqual(uses(session), ["c1"])
        self.assertIn(UNFILTERED_FIND, run(session.events))

    def test_a_test_run_that_exits_non_zero_still_follows_the_change(self):
        self.patch("p1", "Success. Updated the following files:\nM src/app.py")
        self.exec_call("t1", "python3 -m pytest -q",
                       "Process exited with code 1\nOutput:\n1 failed, 3 passed")
        session = self.read()
        self.assertEqual(uses(session), ["p1", "t1"])
        self.assertEqual(tested(session.events), [(1, "p1")])


if __name__ == "__main__":
    unittest.main()
