# SPDX-License-Identifier: MIT
"""A Claude Code subagent's own transcript, and a transcript of either runtime that
yields no event.

Newer Claude Code writes each subagent to `<session>/subagents/agent-<id>.jsonl` and marks
every line of it `isSidechain`, with an `agentId` and the parent's `sessionId`. The
transcripts here are synthetic, written line by line into a temporary directory.
"""
import json
import os
import shutil
import tempfile
import unittest

from ruleprobe import iter_sessions, run
from ruleprobe.readers import claude_code, codex

PARENT = "sess-parent"
AGENT = "a1b2c3d4"


def _line(kind, message=None, **extra):
    entry = {"type": kind, "sessionId": PARENT, "cwd": "/work/demo-repo",
             "timestamp": "2026-09-20T10:00:%02dZ" % extra.pop("second", 0)}
    if message is not None:
        entry["message"] = message
    entry.update(extra)
    return entry


def _prompt(text, **extra):
    return _line("user", {"role": "user", "content": text}, **extra)


def _call(use_id, command, **extra):
    return _line("assistant", {"id": "msg-" + use_id, "role": "assistant", "model": "model-a",
                               "content": [{"type": "tool_use", "id": use_id, "name": "Bash",
                                            "input": {"command": command}}]}, **extra)


def _result(use_id, text, **extra):
    return _line("user", {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": use_id, "content": text}]}, **extra)


def _say(mid, text, **extra):
    return _line("assistant", {"id": mid, "role": "assistant", "model": "model-a",
                               "content": [{"type": "text", "text": text}]}, **extra)


def _agent(**extra):
    return dict(isSidechain=True, agentId=AGENT, **extra)


SUBAGENT = [
    _prompt("Find the failing test.", **_agent(second=1)),
    _line("attachment", **_agent(second=1)),
    _call("toolu_a", "git commit --no-verify -m wip", **_agent(second=2)),
    _result("toolu_a", "ok", **_agent(second=3)),
    _say("msg-t1", "Found it.", **_agent(second=4)),
    _prompt("Now fix it.", **_agent(second=5)),
    _say("msg-t2", "Fixed.", **_agent(second=6)),
]


class _Files(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def write(self, relative, lines):
        path = os.path.join(self.root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
        return path


class SubagentFileTests(_Files):
    def setUp(self):
        super().setUp()
        self.path = self.write(os.path.join(PARENT, "subagents", "agent-%s.jsonl" % AGENT),
                               SUBAGENT)
        self.session = claude_code.read(self.path)

    def test_it_is_a_session_keyed_by_its_agent_id(self):
        self.assertIsNotNone(self.session)
        self.assertEqual(self.session.id, AGENT)
        self.assertEqual(self.session.repo, "demo-repo")
        self.assertEqual((self.session.started, self.session.ended),
                         ("2026-09-20T10:00:01Z", "2026-09-20T10:00:06Z"))

    def test_its_first_user_line_is_the_prompt_of_turn_one(self):
        first = self.session.events[0]
        self.assertEqual((first["kind"], first["turn"], first["text"]),
                         ("user_prompt", 1, "Find the failing test."))

    def test_turns_final_messages_and_models_come_out_as_in_a_parent(self):
        shape = [(e["kind"], e["turn"], e.get("final")) for e in self.session.events]
        self.assertEqual(shape, [("user_prompt", 1, None), ("tool_use", 1, None),
                                 ("tool_result", 1, None), ("assistant_text", 1, True),
                                 ("user_prompt", 2, None), ("assistant_text", 2, True)])
        self.assertEqual({e["model"] for e in self.session.events
                          if e["kind"] == "assistant_text"}, {"model-a"})
        self.assertEqual(self.session.events[2]["tool_name"], "Bash")

    def test_the_detectors_read_its_tool_calls(self):
        self.assertIn("verification/no-verify", run(self.session.events))

    def test_it_reads_the_same_twice(self):
        self.assertEqual(claude_code.read(self.path), self.session)

    def test_it_is_told_by_content_not_by_its_path(self):
        elsewhere = self.write("flat.jsonl", SUBAGENT)
        self.assertEqual(claude_code.read(elsewhere).events, self.session.events)

    def test_a_compaction_inside_it_is_read(self):
        path = self.write("compacted.jsonl", SUBAGENT[:2] + [
            _line("system", subtype="compact_boundary", **_agent())] + SUBAGENT[2:])
        kinds = [e["kind"] for e in claude_code.read(path).events]
        self.assertEqual(kinds[:2], ["user_prompt", "compact"])

    def test_iter_sessions_yields_the_parent_and_the_subagent_in_path_order(self):
        self.write(PARENT + ".jsonl", [_prompt("Delegate it."), _say("msg-p", "Done.")])
        ids = [s.id for s in iter_sessions(root=self.root)]
        self.assertEqual(ids, [PARENT, AGENT])


class ParentSidechainTests(_Files):
    def test_a_parents_sidechain_lines_stay_skipped(self):
        path = self.write("parent.jsonl", [
            _prompt("Delegate it."),
            _call("toolu_s", "git commit --no-verify -m wip", isSidechain=True),
            _call("toolu_t", "git commit --no-verify -m side", **_agent()),
            _say("msg-p", "Done."),
        ])
        session = claude_code.read(path)
        self.assertEqual(session.id, PARENT)
        self.assertEqual([e["kind"] for e in session.events], ["user_prompt", "assistant_text"])
        self.assertNotIn("verification/no-verify", run(session.events))

    def test_a_file_mixing_agent_ids_is_not_one_agents_own(self):
        other = dict(isSidechain=True, agentId="ffff0000")
        path = self.write("mixed.jsonl", [_prompt("One.", **_agent()),
                                          _say("msg-o", "Two.", **other)])
        self.assertIsNone(claude_code.read(path))

    def test_sidechain_lines_without_an_agent_id_are_not_a_subagent_file(self):
        path = self.write("anonymous.jsonl", [_prompt("One.", isSidechain=True),
                                              _say("msg-a", "Two.", isSidechain=True)])
        self.assertIsNone(claude_code.read(path))


class NoEventTests(_Files):
    def test_a_transcript_with_no_event_is_no_session_and_a_note(self):
        empty = self.write("empty.jsonl", [_line("attachment"), _line("summary"), "{half a"])
        self.write("blank.jsonl", [])
        self.assertIsNone(claude_code.read(empty))
        errors = []
        self.assertEqual(list(iter_sessions(root=self.root, errors=errors)), [])
        self.assertEqual([(os.path.basename(e["path"]), e["error"]) for e in errors],
                         [("blank.jsonl", "no session in it"),
                          ("empty.jsonl", "no session in it")])

    def test_meta_lines_alone_are_no_session(self):
        path = self.write("meta.jsonl", [_prompt("<command>", isMeta=True)])
        self.assertIsNone(claude_code.read(path))


def _codex(kind, payload, second=0):
    return {"type": kind, "timestamp": "2026-09-21T08:00:%02d.000Z" % second, "payload": payload}


class CodexNoEventTests(_Files):
    META = _codex("session_meta", {"id": "rollout-empty", "cwd": "/work/demo-repo"})

    def test_a_rollout_with_a_session_id_and_no_event_is_no_session_and_a_note(self):
        empty = self.write("a-rollout.jsonl", [self.META,
                                               _codex("turn_context", {"model": "model-b"}, 1)])
        self.write("b-rollout.jsonl", [self.META])
        full = self.write("c-rollout.jsonl", [self.META, _codex("response_item", {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "Go."}]}, 2)])
        self.assertIsNone(codex.read(empty))
        errors = []
        sessions = list(iter_sessions(root=self.root, runtime="codex", errors=errors))
        self.assertEqual([s.path for s in sessions], [full])
        self.assertEqual([(os.path.basename(e["path"]), e["error"]) for e in errors],
                         [("a-rollout.jsonl", "no session in it"),
                          ("b-rollout.jsonl", "no session in it")])


if __name__ == "__main__":
    unittest.main()
