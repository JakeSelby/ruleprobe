# SPDX-License-Identifier: MIT
"""One session in several transcript files: a copied or renamed project folder, a worktree's.

`iter_sessions` counts one session per runtime and session id. Of the files carrying one, it
keeps the one with the most events, the first in path order on a tie, and notes the rest as
copies set aside. The transcripts here are synthetic, written into a temporary directory.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ruleprobe import iter_sessions, run
from ruleprobe.cli import main
from ruleprobe import readers
from ruleprobe.readers import COPY, claude_code, codex, gemini, iter_file_sessions
from ruleprobe.validity import CorpusError, load_corpus

SESSION = "sess-copied"
AGENT = "a1b2c3d4"


def _line(kind, message=None, session=SESSION, second=0, **extra):
    entry = {"type": kind, "sessionId": session, "cwd": "/work/demo-repo",
             "timestamp": "2026-09-20T10:00:%02dZ" % second}
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


def _transcript(calls, session=SESSION, **extra):
    """A prompt, then one Bash call per `(id, command)`: one event more than `calls`."""
    lines = [_prompt("Ship it.", session=session, **extra)]
    for n, (use_id, command) in enumerate(calls):
        lines.append(_call(use_id, command, session=session, second=n + 1, **extra))
    return lines


NO_VERIFY = [("toolu_1", "git commit --no-verify -m wip")]
LONGER = NO_VERIFY + [("toolu_2", "ls")]


def _codex(kind, payload, second=0):
    return {"type": kind, "timestamp": "2026-09-21T08:00:%02d.000Z" % second,
            "payload": payload}


def _rollout(rollout_id, commands):
    lines = [_codex("session_meta", {"id": rollout_id, "cwd": "/work/demo-repo"})]
    for n, command in enumerate(commands):
        lines.append(_codex("response_item", {
            "type": "function_call", "name": "exec_command", "call_id": "call_%d" % n,
            "arguments": json.dumps({"cmd": command})}, n + 1))
    return lines


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

    def read(self, **kw):
        errors = []
        sessions = list(iter_sessions(root=self.root, errors=errors, **kw))
        return sessions, errors


def _notes(errors):
    return [(e["path"], e["error"], e.get("kept")) for e in errors]


class ClaudeCodeCopyTests(_Files):
    def test_identical_files_in_two_project_folders_are_one_session(self):
        first = self.write("proj-a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        second = self.write("proj-b/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        sessions, errors = self.read()
        self.assertEqual([(s.id, s.path) for s in sessions], [(SESSION, first)])
        self.assertEqual(_notes(errors), [(second, COPY, first)])
        hits = [h for s in sessions for h in run(s.events).get("verification/no-verify", [])]
        self.assertEqual(len(hits), 1)

    def test_of_two_differing_files_the_one_with_more_events_is_kept(self):
        shorter = self.write("proj-a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        longer = self.write("proj-b/%s.jsonl" % SESSION, _transcript(LONGER))
        sessions, errors = self.read()
        self.assertEqual([s.path for s in sessions], [longer])
        self.assertEqual(len(sessions[0].events), 3)
        self.assertEqual(_notes(errors), [(shorter, COPY, longer)])

    def test_on_a_tie_the_first_in_path_order_is_kept(self):
        first = self.write("proj-a/%s.jsonl" % SESSION, _transcript([("toolu_1", "ls")]))
        second = self.write("proj-b/%s.jsonl" % SESSION, _transcript([("toolu_1", "pwd")]))
        sessions, errors = self.read()
        self.assertEqual([s.path for s in sessions], [first])
        self.assertEqual(_notes(errors), [(second, COPY, first)])

    def test_a_subagent_file_is_not_merged_with_its_parent(self):
        parent = self.write("proj-a/%s.jsonl" % SESSION, _transcript(LONGER))
        agent = _transcript(NO_VERIFY, isSidechain=True, agentId=AGENT)
        sub = self.write("proj-a/%s/subagents/agent-%s.jsonl" % (SESSION, AGENT), agent)
        sessions, errors = self.read()
        self.assertEqual(sorted((s.id, s.path) for s in sessions),
                         [(SESSION, parent), (SESSION + "/" + AGENT, sub)])
        self.assertEqual(errors, [])

    def test_a_copied_subagent_file_is_one_subagent_session(self):
        agent = _transcript(NO_VERIFY, isSidechain=True, agentId=AGENT)
        first = self.write("proj-a/%s/subagents/agent-%s.jsonl" % (SESSION, AGENT), agent)
        second = self.write("proj-b/%s/subagents/agent-%s.jsonl" % (SESSION, AGENT), agent)
        sessions, errors = self.read()
        self.assertEqual([(s.id, s.path) for s in sessions], [(SESSION + "/" + AGENT, first)])
        self.assertEqual(_notes(errors), [(second, COPY, first)])

    def test_session_key_is_the_id_read_gives(self):
        late_id = [{"type": "summary", "summary": "x"}] + _transcript(NO_VERIFY)
        no_id = [dict(line, sessionId="") for line in _transcript(NO_VERIFY)]
        cases = {
            "parent.jsonl": _transcript(NO_VERIFY),
            "late.jsonl": late_id,
            "sub.jsonl": _transcript(NO_VERIFY, isSidechain=True, agentId=AGENT),
            "two-agents.jsonl": [_prompt("a", isSidechain=True, agentId="one"),
                                 _prompt("b", isSidechain=True, agentId="two")],
            "torn.jsonl": _transcript(NO_VERIFY) + ['{"type": "assist'],
            "list-id.jsonl": _transcript(NO_VERIFY, session=["a", 1]),
            "object-id.jsonl": _transcript(NO_VERIFY, session={"id": "x"}),
        }
        for name, lines in sorted(cases.items()):
            with self.subTest(name=name):
                path = self.write(name, lines)
                self.assertEqual(claude_code.session_key(path),
                                 claude_code.read(path, empty=True).id)
        self.assertEqual(claude_code.session_key(os.path.join(self.root, "list-id.jsonl")),
                         "['a', 1]")
        # Known only by its stem, a file is nobody's copy: it has no key.
        stem = self.write("stem-only.jsonl", no_id)
        self.assertIsNone(claude_code.session_key(stem))
        self.assertEqual(claude_code.read(stem).id, "stem-only")
        self.assertIsNone(claude_code.session_key(os.path.join(self.root, "absent.jsonl")))

    def test_a_session_id_that_is_a_list_or_object_does_not_stop_the_read(self):
        for n, session in enumerate((["a", 1], {"id": "x"})):
            with self.subTest(session=session):
                first = self.write("%d/a/t.jsonl" % n, _transcript(NO_VERIFY, session=session))
                second = self.write("%d/b/t.jsonl" % n, _transcript(NO_VERIFY, session=session))
                errors = []
                sessions = list(iter_sessions(root=os.path.join(self.root, str(n)),
                                              errors=errors))
                self.assertEqual([(s.id, s.path) for s in sessions], [(str(session), first)])
                self.assertEqual(_notes(errors), [(second, COPY, first)])

    def test_files_known_only_by_one_stem_are_not_copies(self):
        no_id = [dict(line, sessionId="") for line in _transcript(NO_VERIFY)]
        first = self.write("proj-a/session.jsonl", no_id)
        second = self.write("proj-b/session.jsonl", no_id)
        sessions, errors = self.read()
        self.assertEqual([(s.id, s.path) for s in sessions],
                         [("session", first), ("session", second)])
        self.assertEqual(errors, [])

    def test_copy_notes_come_in_path_order(self):
        a = self.write("a/%s.jsonl" % SESSION, _transcript(LONGER))
        b = self.write("b/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        c = self.write("c/%s.jsonl" % SESSION, _transcript(LONGER + [("toolu_3", "pwd")]))
        sessions, errors = self.read()
        self.assertEqual([s.path for s in sessions], [c])
        self.assertEqual(_notes(errors), [(a, COPY, c), (b, COPY, c)])

    def test_a_file_whose_id_changed_after_the_key_pass_is_its_own_session(self):
        # The key pass saw `other.jsonl` as this session; by the read it names another.
        first = self.write("a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        moved = self.write("b/other.jsonl", _transcript(LONGER, session="other"))
        key = claude_code.session_key
        stale = {moved: SESSION}
        with mock.patch.object(claude_code, "session_key",
                               lambda path: stale.get(path) or key(path)):
            sessions, errors = self.read()
        self.assertEqual([(s.id, s.path) for s in sessions],
                         [(SESSION, first), ("other", moved)])
        self.assertEqual(errors, [])

    def test_an_address_is_yielded_once_and_the_first_stands(self):
        # Two groups meet at one address only when the key pass and the read disagree. The
        # first session yielded stands, although the later one has more events.
        first = self.write("a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        later = self.write("b/%s.jsonl" % SESSION, _transcript(LONGER))
        key = claude_code.session_key
        stale = {later: "stale"}
        with mock.patch.object(claude_code, "session_key",
                               lambda path: stale.get(path) or key(path)):
            sessions, errors = self.read()
        self.assertEqual([s.path for s in sessions], [first])
        self.assertEqual(_notes(errors), [(later, COPY, first)])

    def test_a_reader_without_session_key_is_an_error(self):
        self.write("a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        with mock.patch.object(claude_code, "session_key", None):
            del claude_code.session_key
            with self.assertRaises(AttributeError):
                self.read()

    def test_a_copy_with_no_event_is_no_session_not_a_copy(self):
        full = self.write("proj-a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        empty = self.write("proj-b/%s.jsonl" % SESSION,
                           [_line("system", subtype="informational")])
        sessions, errors = self.read()
        self.assertEqual([s.path for s in sessions], [full])
        self.assertEqual(_notes(errors), [(empty, "no session in it", None)])

    def test_since_drops_an_old_copy_before_one_is_kept(self):
        old = [dict(line, timestamp="2026-01-05T10:00:00Z") for line in _transcript(LONGER)]
        self.write("proj-a/%s.jsonl" % SESSION, old)
        new = self.write("proj-b/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        sessions, errors = self.read(since="2026-09-01")
        self.assertEqual([s.path for s in sessions], [new])
        self.assertEqual(errors, [])

    def test_a_session_is_yielded_where_its_first_file_falls(self):
        self.write("a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        self.write("b/other.jsonl", _transcript(NO_VERIFY, session="other"))
        kept = self.write("c/%s.jsonl" % SESSION, _transcript(LONGER))
        sessions, _errors = self.read()
        self.assertEqual([(s.id, s.path) for s in sessions],
                         [(SESSION, kept), ("other", os.path.join(self.root, "b",
                                                                  "other.jsonl"))])

    def test_the_result_does_not_depend_on_the_order_files_are_found(self):
        self.write("proj-b/%s.jsonl" % SESSION, _transcript([("toolu_1", "pwd")]))
        self.write("proj-a/%s.jsonl" % SESSION, _transcript([("toolu_1", "ls")]))
        self.write("proj-c/other.jsonl", _transcript(LONGER, session="other"))
        self.write("proj-a/other.jsonl", _transcript(NO_VERIFY, session="other"))
        found = readers._paths

        def shape():
            sessions, errors = self.read()
            return [(s.id, s.path, len(s.events)) for s in sessions], _notes(errors)

        expected = shape()
        with mock.patch.object(readers, "_paths",
                               lambda *a: list(reversed(found(*a)))) as reversed_paths:
            self.assertEqual(shape(), expected)
        self.assertNotEqual(found(self.root, "auto"), reversed_paths(self.root, "auto"))
        self.assertEqual([path for path, _e, _k in expected[1]],
                         [os.path.join(self.root, "proj-a", "other.jsonl"),
                          os.path.join(self.root, "proj-b", "%s.jsonl" % SESSION)])


class CodexCopyTests(_Files):
    def test_a_copied_rollout_is_one_session(self):
        first = self.write("2026/09/21/rollout-1.jsonl", _rollout("r-1", ["ls"]))
        longer = self.write("copy/rollout-1.jsonl", _rollout("r-1", ["ls", "pwd"]))
        other = self.write("2026/09/21/rollout-2.jsonl", _rollout("r-2", ["ls"]))
        sessions, errors = self.read(runtime="codex")
        self.assertEqual([(s.id, s.path) for s in sessions], [("r-1", longer), ("r-2", other)])
        self.assertEqual(_notes(errors), [(first, COPY, longer)])

    def test_session_key_is_the_rollouts_own_id(self):
        inherited = _rollout("child", ["ls"]) + [_codex("session_meta", {"id": "parent"})]
        path = self.write("rollout-child.jsonl", inherited)
        self.assertEqual(codex.session_key(path), "child")
        self.assertEqual(codex.session_key(path), codex.read(path).id)
        stem = self.write("rollout-stem.jsonl", _rollout("", ["ls"]))
        self.assertIsNone(codex.session_key(stem))
        self.assertEqual(codex.read(stem).id, "rollout-stem")
        listed = self.write("rollout-list.jsonl", _rollout(["r", 1], ["ls"]))
        self.assertEqual(codex.session_key(listed), codex.read(listed).id)


class GeminiCopyTests(_Files):
    def gemini(self, relative, session_id, prompts):
        project, name = relative.split("/", 1)
        os.makedirs(os.path.join(self.root, project), exist_ok=True)
        with open(os.path.join(self.root, project, ".project_root"), "w") as handle:
            handle.write("/work/demo-repo")
        records = [{"sessionId": session_id, "projectHash": "demo",
                    "startTime": "2026-09-20T10:00:00.000Z",
                    "lastUpdated": "2026-09-20T10:00:00.000Z"}]
        for n, text in enumerate(prompts):
            records.append({"id": "m%d" % n, "timestamp": "2026-09-20T10:%02d:00.000Z" % n,
                            "type": "user", "content": [{"text": text}]})
        return self.write(os.path.join(project, "chats", name), records)

    def test_a_copied_gemini_session_is_one_session(self):
        shorter = self.gemini("proj-a/session-1.jsonl", "g-1", ["Go."])
        longer = self.gemini("proj-b/session-1.jsonl", "g-1", ["Go.", "And on."])
        other = self.gemini("proj-b/session-2.jsonl", "g-2", ["Go."])
        sessions, errors = self.read(runtime="gemini")
        self.assertEqual([(s.id, s.path) for s in sessions], [("g-1", longer), ("g-2", other)])
        self.assertEqual(_notes(errors), [(shorter, COPY, longer)])

    def test_session_key_is_the_id_read_gives_nested_parts_included(self):
        nested = self.gemini("proj-a/g-parent/session-sub.jsonl", "g-sub", ["Go."])
        self.assertEqual(gemini.session_key(nested), "g-parent/g-sub")
        self.assertEqual(gemini.session_key(nested), gemini.read(nested).id)
        bare = self.gemini("proj-a/session-bare.jsonl", "", ["Go."])
        self.assertIsNone(gemini.session_key(bare))
        self.assertEqual(gemini.read(bare).id, "session-bare")



class NoteTests(_Files):
    def test_the_cli_names_copies_apart_from_failures(self):
        self.write("proj-a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        self.write("proj-b/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["report", "--root", self.root, "--no-config"], out=out)
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue().splitlines()[0],
                         "1 transcript(s) set aside as copies of a session read from another "
                         "file: proj-b/%s.jsonl (kept proj-a/%s.jsonl)" % (SESSION, SESSION))
        self.write("proj-c/empty.jsonl", [{"type": "summary", "summary": "x"}])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            main(["report", "--root", self.root, "--no-config"], out=io.StringIO())
        self.assertTrue(err.getvalue().startswith(
            "1 transcript(s) produced no session: empty.jsonl (no session in it); "
            "1 transcript(s) set aside as copies"), err.getvalue())


    def test_the_note_names_three_copies_then_counts_the_rest(self):
        for folder in "abcde":
            self.write("%s/%s.jsonl" % (folder, SESSION), _transcript(NO_VERIFY))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            main(["report", "--root", self.root, "--no-config"], out=io.StringIO())
        self.assertEqual(err.getvalue().splitlines()[0],
                         "4 transcript(s) set aside as copies of a session read from another "
                         "file: b/{0}.jsonl (kept a/{0}.jsonl), c/{0}.jsonl (kept a/{0}.jsonl), "
                         "d/{0}.jsonl (kept a/{0}.jsonl), and 1 more".format(SESSION))

    def test_report_json_keeps_copies_out_of_read_errors(self):
        first = self.write("proj-a/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        second = self.write("proj-b/%s.jsonl" % SESSION, _transcript(NO_VERIFY))
        empty = self.write("proj-c/empty.jsonl", [{"type": "summary", "summary": "x"}])
        out = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(["report", "--root", self.root, "--no-config", "--json"], out=out)
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["read_errors"], [{"path": empty, "error": "no session in it"}])
        self.assertEqual(data["copies"], [{"path": second, "error": COPY, "kept": first}])


class CorpusTests(_Files):
    """A labelled corpus names each session by its file, so it reads every file."""

    def test_two_corpus_files_sharing_a_session_id_are_both_read(self):
        self.write("sessions/positive.jsonl", _transcript(NO_VERIFY))
        self.write("sessions/near-miss.jsonl", _transcript([("toolu_1", "git commit -m wip")]))
        with open(os.path.join(self.root, "labels.yaml"), "w") as handle:
            handle.write("version: 1\nsessions:\n"
                         "  - session: positive.jsonl\n    labels:\n"
                         "      - at: \"1:toolu_1\"\n        fire: [verification/no-verify]\n"
                         "  - session: near-miss.jsonl\n    labels:\n"
                         "      - at: \"1:toolu_1\"\n        near: [verification/no-verify]\n")
        self.assertEqual([s.name for s in load_corpus(self.root)],
                         ["positive.jsonl", "near-miss.jsonl"])
        self.assertEqual(len(list(iter_file_sessions(root=self.root))), 2)

    def test_two_corpus_files_of_one_name_are_still_refused(self):
        self.write("sessions/a/same.jsonl", _transcript(NO_VERIFY))
        self.write("sessions/b/same.jsonl", _transcript(NO_VERIFY))
        with open(os.path.join(self.root, "labels.yaml"), "w") as handle:
            handle.write("version: 1\nsessions:\n  - session: same.jsonl\n")
        with self.assertRaisesRegex(CorpusError, "two session files are named same"):
            load_corpus(self.root)


if __name__ == "__main__":
    unittest.main()
