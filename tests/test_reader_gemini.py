# SPDX-License-Identifier: MIT
"""The Gemini CLI reader, over session trees built here from the documented record shapes.

Each test writes a `~/.gemini/tmp`-shaped tree into a temporary directory: a project
directory holding `.project_root` and a `chats/` directory of sessions. The trees are built
in the test, not kept under `tests/fixtures/`, because the other suites read that whole
directory as a mixed-runtime root and count what is in it. No record here comes from a real
session.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ruleprobe import iter_sessions, run
from ruleprobe.cli import main
from ruleprobe.readers import RUNTIMES, _detect, claude_code, codex, gemini

SESSION_ID = "0b5e7c1a-0000-4000-8000-000000000001"


def meta(session_id=SESSION_ID, **extra):
    return dict({"sessionId": session_id, "projectHash": "demo-project",
                 "startTime": "2026-09-20T10:00:00.000Z",
                 "lastUpdated": "2026-09-20T10:00:00.000Z"}, **extra)


def user(mid, text, second=0, **extra):
    return dict({"id": mid, "timestamp": "2026-09-20T10:%02d:00.000Z" % second,
                 "type": "user", "content": [{"text": text}]}, **extra)


def response(mid, call_id, name, output, second=0):
    """A `user` record made only of a tool's `functionResponse`: not a prompt."""
    return {"id": mid, "timestamp": "2026-09-20T10:%02d:00.000Z" % second, "type": "user",
            "content": [{"functionResponse": {"id": call_id, "name": name,
                                              "response": {"output": output}}}]}


def call(call_id, name, args, output="ok", error=None):
    reply = {"error": error} if error is not None else {"output": output}
    return {"id": call_id, "name": name, "args": args,
            "status": "error" if error is not None else "success",
            "timestamp": "2026-09-20T10:00:00.000Z",
            "result": [{"functionResponse": {"id": call_id, "name": name,
                                             "response": reply}}]}


def gemini_record(mid, text="", calls=None, model="gemini-2.5-pro", second=0, **extra):
    record = {"id": mid, "timestamp": "2026-09-20T10:%02d:00.000Z" % second,
              "type": "gemini", "content": text, "model": model}
    if calls is not None:
        record["toolCalls"] = calls
    record.update(extra)
    return record


class Tree(object):
    """A temporary `~/.gemini/tmp` with one project directory in it."""

    def __init__(self, project_root="/workspace/demo-project", slug="demo-project"):
        self.base = tempfile.mkdtemp()
        self.project = os.path.join(self.base, slug)
        self.chats = os.path.join(self.project, "chats")
        os.makedirs(self.chats)
        if project_root is not None:
            with open(os.path.join(self.project, ".project_root"), "w",
                      encoding="utf-8") as handle:
                handle.write(project_root + "\n")

    def write(self, name, records, directory=None):
        path = os.path.join(directory or self.chats, name)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(record if isinstance(record, str) else json.dumps(record))
                handle.write("\n")
        return path

    def session(self, records, name="session-2026-09-20T10-00-0b5e7c1a.jsonl"):
        return gemini.read(self.write(name, records))

    def close(self):
        shutil.rmtree(self.base, ignore_errors=True)


class TreeTest(unittest.TestCase):
    project_root = "/workspace/demo-project"

    def setUp(self):
        self.tree = Tree(self.project_root)
        self.addCleanup(self.tree.close)

    def kinds(self, session):
        return [e["kind"] for e in session.events]

    def uses(self, session):
        return [e for e in session.events if e["kind"] == "tool_use"]


class RuntimeSelectionTests(TreeTest):
    """AC 1: `--runtime gemini` reads the sessions, and `auto` includes them."""

    def setUp(self):
        TreeTest.setUp(self)
        self.path = self.tree.write("session-2026-09-20T10-00-0b5e7c1a.jsonl",
                                    [meta(), user("u1", "hello"),
                                     gemini_record("g1", "Hi.")])

    def test_gemini_is_a_registered_runtime(self):
        self.assertIs(RUNTIMES["gemini"], gemini)
        self.assertEqual(gemini.ROOT, os.path.join("~", ".gemini", "tmp"))

    def test_the_named_runtime_reads_the_session(self):
        sessions = list(iter_sessions(root=self.tree.base, runtime="gemini"))
        self.assertEqual([(s.runtime, s.id) for s in sessions], [("gemini", SESSION_ID)])

    def test_auto_decides_a_gemini_session_by_its_metadata_line(self):
        self.assertIs(_detect(self.path), gemini)
        sessions = list(iter_sessions(root=self.tree.base))
        self.assertEqual([s.runtime for s in sessions], ["gemini"])

    def test_a_claude_code_line_naming_a_session_id_is_still_claude_code(self):
        other = self.tree.write("claude.jsonl", [{"type": "user", "sessionId": "s-1",
                                                  "message": {"content": "hi"}}],
                                directory=self.tree.base)
        self.assertIs(_detect(other), claude_code)

    def test_auto_with_no_root_reads_the_gemini_default_location(self):
        empty = os.path.join(self.tree.base, "empty")
        with mock.patch.object(gemini, "ROOT", self.tree.base), \
                mock.patch.object(claude_code, "ROOT", empty), \
                mock.patch.object(codex, "ROOT", empty):
            sessions = list(iter_sessions())
        self.assertEqual([s.runtime for s in sessions], ["gemini"])

    def test_the_cli_accepts_the_runtime(self):
        out = io.StringIO()
        code = main(["report", "--root", self.tree.base, "--runtime", "gemini",
                     "--no-config", "--json"], out=out)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["measured"], 1)

    def test_the_session_knows_its_id_repo_times_and_runtime(self):
        session = gemini.read(self.path)
        self.assertEqual(session.repo, "demo-project")
        self.assertEqual(session.runtime, "gemini")
        self.assertEqual(session.started, "2026-09-20T10:00:00.000Z")
        self.assertEqual(session.ended[:10], "2026-09-20")


class ToolMappingTests(TreeTest):
    """AC 2: the shell is `Bash` with `command`; `write_file` and `replace` are exact; the
    rest stay native."""

    def calls(self, *calls):
        return self.tree.session([meta(), user("u1", "go"),
                                  gemini_record("g1", "", list(calls))])

    def test_run_shell_command_is_bash_with_command_on_a_posix_root(self):
        session = self.calls(call("c1", "run_shell_command",
                                  {"command": "cat README.md", "dir_path": "src"},
                                  output="# demo"))
        use = self.uses(session)[0]
        self.assertEqual(use["name"], "Bash")
        self.assertEqual(use["input"], {"command": "cat README.md", "dir_path": "src"})
        result = [e for e in session.events if e["kind"] == "tool_result"][0]
        self.assertEqual((result["tool_name"], result["text"]), ("Bash", "# demo"))
        self.assertEqual(sorted(run(session.events, strict=True)),
                         ["transcript-hygiene/whole-file-cat"])

    def test_write_file_is_write_and_replace_is_edit_with_their_native_keys_kept(self):
        session = self.calls(
            call("c1", "write_file", {"file_path": "/workspace/demo-project/a.txt",
                                      "content": "x"}),
            call("c2", "replace", {"file_path": "/workspace/demo-project/a.txt",
                                   "instruction": "swap", "old_string": "x",
                                   "new_string": "y", "allow_multiple": True}))
        write, edit = self.uses(session)
        self.assertEqual(write["name"], "Write")
        self.assertEqual(edit["name"], "Edit")
        self.assertEqual(edit["input"], {"file_path": "/workspace/demo-project/a.txt",
                                         "instruction": "swap", "old_string": "x",
                                         "new_string": "y", "allow_multiple": True})
        self.assertNotIn("replace_all", edit["input"])

    def test_a_relative_file_path_resolves_against_the_project_root(self):
        session = self.calls(call("c1", "write_file",
                                  {"file_path": "src/../config/a.ini", "content": "x"}))
        self.assertEqual(self.uses(session)[0]["input"]["file_path"],
                         "/workspace/demo-project/config/a.ini")

    def test_every_other_tool_keeps_its_native_name(self):
        names = ["read_file", "read_many_files", "list_directory", "glob", "grep_search",
                 "write_todos", "invoke_agent"]
        session = self.calls(*[call("c%d" % i, name, {"file_path": "a"})
                               for i, name in enumerate(names)])
        self.assertEqual([u["name"] for u in self.uses(session)], names)

    def test_invoke_agent_is_not_counted_as_an_agent_call(self):
        from ruleprobe.events import counts
        session = self.calls(call("c1", "invoke_agent", {"prompt": "look around"}))
        self.assertEqual(counts(session.events)["agent"], 0)

    def test_an_errored_call_carries_its_error_as_the_result_text(self):
        session = self.calls(call("c1", "run_shell_command", {"command": "false"},
                                  error="exit 1"))
        result = [e for e in session.events if e["kind"] == "tool_result"][0]
        self.assertEqual(result["text"], "exit 1")


class WindowsShellTests(TreeTest):
    """Decision 2: a drive-letter root keeps the shell native, since its command is
    PowerShell."""

    project_root = "C:\\work\\demo-project"

    def test_the_shell_stays_native_and_no_bash_detector_reads_it(self):
        session = self.tree.session([meta(), user("u1", "go"), gemini_record(
            "g1", "", [call("c1", "run_shell_command", {"command": "cat README.md"})])])
        self.assertEqual(self.uses(session)[0]["name"], "run_shell_command")
        self.assertEqual(run(session.events, strict=True), {})

    def test_the_repo_is_the_last_component_of_the_windows_root(self):
        session = self.tree.session([meta(), user("u1", "go")])
        self.assertEqual(session.repo, "demo-project")

    def test_write_file_is_still_write_and_a_relative_path_is_left_as_written(self):
        session = self.tree.session([meta(), user("u1", "go"), gemini_record(
            "g1", "", [call("c1", "write_file", {"file_path": "a.txt", "content": "x"})])])
        use = self.uses(session)[0]
        self.assertEqual((use["name"], use["input"]["file_path"]), ("Write", "a.txt"))


class NoProjectRootTests(TreeTest):
    """With no `.project_root` the platform is unknown: the shell stays native, the repo is
    unknown, and a relative path is left as written."""

    project_root = None

    def test_the_shell_stays_native_and_the_repo_is_unknown(self):
        session = self.tree.session([meta(), user("u1", "go"), gemini_record(
            "g1", "", [call("c1", "run_shell_command", {"command": "cat README.md"}),
                       call("c2", "write_file", {"file_path": "a.txt", "content": "x"})])])
        shell, write = self.uses(session)
        self.assertEqual(shell["name"], "run_shell_command")
        self.assertEqual(write["input"]["file_path"], "a.txt")
        self.assertEqual(session.repo, "")


class ErrorTests(TreeTest):
    """AC 3: a malformed line is skipped, an unreadable file lands in `errors`, and a
    missing root yields nothing and no error."""

    def test_a_malformed_line_is_skipped_and_the_file_still_reads(self):
        session = self.tree.session([meta(), '{"id": "u0", "type": "us', "[1, 2]",
                                     user("u1", "hello"), gemini_record("g1", "Hi.")])
        self.assertEqual(self.kinds(session), ["user_prompt", "assistant_text"])

    def test_an_unreadable_file_lands_in_errors_with_its_path(self):
        path = os.path.join(self.tree.chats, "session-gone.jsonl")
        os.symlink(os.path.join(self.tree.base, "no-such-file"), path)
        errors = []
        sessions = list(iter_sessions(root=self.tree.base, runtime="gemini", errors=errors))
        self.assertEqual(sessions, [])
        self.assertEqual([e["path"] for e in errors], [path])

    def test_a_missing_root_yields_nothing_and_no_error(self):
        errors = []
        missing = os.path.join(self.tree.base, "not-there")
        with mock.patch.object(gemini, "ROOT", missing):
            self.assertEqual(list(iter_sessions(runtime="gemini", errors=errors)), [])
        self.assertEqual(gemini.transcripts(missing), [])
        self.assertEqual(errors, [])

    def test_a_file_with_no_session_and_no_event_is_none(self):
        self.assertIsNone(self.tree.session(["not json", {"$rewindTo": "x"}]))


class TurnAndFinalTests(TreeTest):
    """AC 4 and decision 3: a turn starts at a `user` record that is not all
    `functionResponse` parts; `final` is the last non-empty, non-thought text before the
    next prompt."""

    def setUp(self):
        TreeTest.setUp(self)
        self.session = self.tree.session([
            meta(),
            user("u1", "fix the build", 1),
            gemini_record("g1", [{"text": "Thinking about it.", "thought": True}], [
                call("c1", "run_shell_command", {"command": "make"})], second=2),
            response("r1", "c1", "run_shell_command", "ok", 3),
            gemini_record("g2", "Looking at the log.", second=4),
            gemini_record("g3", [{"text": "Hidden.", "thought": True},
                                 {"text": "Fixed."}], second=5),
            gemini_record("g4", "", [call("c2", "read_file", {"file_path": "x"})],
                          second=6),
            {"id": "i1", "timestamp": "2026-09-20T10:07:00.000Z", "type": "info",
             "content": "Checkpoint saved."},
            {"id": "w1", "timestamp": "2026-09-20T10:08:00.000Z", "type": "warning",
             "content": "Slow response."},
            {"id": "e1", "timestamp": "2026-09-20T10:09:00.000Z", "type": "error",
             "content": "Quota."},
            user("u2", "thanks", 10, displayContent=[{"text": "thanks!"}]),
            gemini_record("g5", "You're welcome.", second=11),
        ])

    def test_turn_increments_on_prompts_and_not_on_tool_responses(self):
        prompts = [e for e in self.session.events if e["kind"] == "user_prompt"]
        self.assertEqual([(e["turn"], e["text"]) for e in prompts],
                         [(1, "fix the build"), (2, "thanks!")])
        self.assertEqual(sorted(set(e["turn"] for e in self.session.events)), [1, 2])

    def test_final_is_the_last_non_empty_non_thought_text_before_the_next_prompt(self):
        texts = [(e["turn"], e["text"], e["final"]) for e in self.session.events
                 if e["kind"] == "assistant_text"]
        self.assertEqual(texts, [(1, "Looking at the log.", False), (1, "Fixed.", True),
                                 (2, "You're welcome.", True)])

    def test_ui_notices_make_no_event(self):
        self.assertEqual(self.kinds(self.session),
                         ["user_prompt", "tool_use", "tool_result", "assistant_text",
                          "assistant_text", "tool_use", "tool_result", "user_prompt",
                          "assistant_text"])


class RecordTests(TreeTest):
    """The record rules from the format: last line wins by id, `$rewindTo` and
    `$set.messages` are not followed, and the model is read per record."""

    def test_a_message_appended_twice_is_one_event_in_its_first_place(self):
        first = gemini_record("g1", "", [call("c1", "read_file", {"file_path": "a"})])
        second = gemini_record("g1", "Done.", [call("c1", "read_file", {"file_path": "a"}),
                                               call("c2", "read_file", {"file_path": "b"})])
        session = self.tree.session([meta(), user("u1", "go"), first,
                                     gemini_record("g2", "Later."), second])
        self.assertEqual([(e["kind"], e.get("id") or e.get("text")) for e in session.events
                          if e["kind"] in ("tool_use", "assistant_text")],
                         [("assistant_text", "Done."), ("tool_use", "c1"),
                          ("tool_use", "c2"), ("assistant_text", "Later.")])

    def test_a_rewind_keeps_the_rewound_calls(self):
        session = self.tree.session([
            meta(), user("u1", "go"),
            gemini_record("g1", "", [call("c1", "run_shell_command",
                                          {"command": "git commit --no-verify -m x"})]),
            {"$rewindTo": "u1"}, user("u2", "again")])
        self.assertEqual([u["id"] for u in self.uses(session)], ["c1"])
        self.assertIn("verification/no-verify", run(session.events, strict=True))

    def test_a_set_messages_rewrite_makes_no_compact_event_and_no_event_of_its_own(self):
        rewritten = gemini_record("g9", "Summary.", [call("c9", "run_shell_command",
                                                          {"command": "cat a"})])
        session = self.tree.session([
            meta(), user("u1", "go"), gemini_record("g1", "One."),
            {"$set": {"messages": [user("s1", "summary of the chat"), rewritten],
                      "lastUpdated": "2026-09-20T11:00:00.000Z"}},
            user("u2", "next"), gemini_record("g2", "Two.")])
        self.assertNotIn("compact", self.kinds(session))
        self.assertEqual(self.uses(session), [])
        self.assertEqual([e["turn"] for e in session.events if e["kind"] == "user_prompt"],
                         [1, 2])
        self.assertEqual(session.ended, "2026-09-20T11:00:00.000Z")

    def test_no_model_is_recorded_so_a_router_switch_is_not_counted(self):
        session = self.tree.session([
            meta(), user("u1", "go"), gemini_record("g1", "Pro.", model="gemini-2.5-pro"),
            user("u2", "more"), gemini_record("g2", "Flash.", model="gemini-2.5-flash")])
        self.assertEqual([e["model"] for e in session.events if e["kind"] == "assistant_text"],
                         ["", ""])
        self.assertNotIn("cache-hygiene/model-switch", run(session.events, strict=True))


class LayoutTests(TreeTest):
    """Where sessions are found: under `chats/`, a subagent in its own file, and a legacy
    `.json` only when no `.jsonl` of the same session is beside it."""

    def test_only_files_under_a_chats_directory_are_sessions(self):
        self.tree.write("logs.jsonl", [{"x": 1}], directory=self.tree.project)
        path = self.tree.write("session-a.jsonl", [meta(), user("u1", "go")])
        self.assertEqual(gemini.transcripts(self.tree.base), [path])

    def test_a_subagent_file_is_read_as_its_own_session(self):
        parent = self.tree.write("session-p.jsonl", [meta(), user("u1", "go"), gemini_record(
            "g1", "", [call("c1", "invoke_agent", {"prompt": "look"})])])
        child = self.tree.write("sub-1.jsonl",
                                [meta("sub-1", kind="subagent"), user("u1", "look"),
                                 gemini_record("g1", "Looked.")],
                                directory=os.path.join(self.tree.chats, SESSION_ID))
        self.assertEqual(gemini.transcripts(self.tree.base), sorted([parent, child]))
        sessions = dict((s.id, s) for s in iter_sessions(root=self.tree.base))
        child_id = SESSION_ID + "/sub-1"
        self.assertEqual(sorted(sessions), sorted([SESSION_ID, child_id]))
        self.assertEqual(sessions[child_id].repo, "demo-project")
        self.assertEqual([e["text"] for e in sessions[child_id].events
                          if e["kind"] == "assistant_text"], ["Looked."])

    def test_a_subagent_repeating_its_parents_id_still_has_an_id_of_its_own(self):
        self.tree.write("session-p.jsonl", [meta(), user("u1", "go")])
        self.tree.write("child.jsonl", [meta(kind="subagent"), user("u1", "look")],
                        directory=os.path.join(self.tree.chats, SESSION_ID))
        ids = sorted(s.id for s in iter_sessions(root=self.tree.base, runtime="gemini"))
        self.assertEqual(ids, [SESSION_ID, SESSION_ID + "/" + SESSION_ID])

    def test_a_file_deeper_under_chats_still_finds_the_project_root(self):
        session = gemini.read(self.tree.write(
            "deep.jsonl", [meta("deep"), user("u1", "go"), gemini_record(
                "g1", "", [call("c1", "run_shell_command", {"command": "ls"})])],
            directory=os.path.join(self.tree.chats, "a", "b")))
        self.assertEqual((session.id, session.repo), ("a/b/deep", "demo-project"))
        self.assertEqual(self.uses(session)[0]["name"], "Bash")

    def test_the_jsonl_is_preferred_over_a_legacy_json_of_the_same_session(self):
        legacy = self.tree.write("session-old.json", [json.dumps(meta())])
        self.assertEqual(gemini.transcripts(self.tree.base), [legacy])
        current = self.tree.write("session-old.jsonl", [meta(), user("u1", "go")])
        self.assertEqual(gemini.transcripts(self.tree.base), [current])

    def test_a_legacy_json_object_is_read(self):
        record = meta(messages=[user("u1", "go"), gemini_record("g1", "Done.", [
            call("c1", "write_file", {"file_path": "a.txt", "content": "x"})])])
        path = os.path.join(self.tree.chats, "session-old.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
        session = gemini.read(path)
        self.assertEqual(session.id, SESSION_ID)
        self.assertEqual(self.kinds(session), ["user_prompt", "assistant_text", "tool_use",
                                               "tool_result"])
        self.assertEqual(self.uses(session)[0]["input"]["file_path"],
                         "/workspace/demo-project/a.txt")


class RootWalkTests(TreeTest):
    """Decision 5 and the legacy format under `--root`, through `iter_sessions`."""

    def ids(self, root, runtime):
        return sorted(s.id for s in iter_sessions(root=root, runtime=runtime))

    def test_a_named_root_reads_only_files_below_chats(self):
        self.tree.write("stray.jsonl", [meta("stray"), user("u1", "go")],
                        directory=self.tree.project)
        self.tree.write("session-a.jsonl", [meta("a"), user("u1", "go")])
        self.assertEqual(self.ids(self.tree.base, "gemini"), ["a"])

    def test_a_chats_directory_above_the_root_does_not_count(self):
        root = os.path.join(self.tree.chats, "archive")
        self.tree.write("session-a.jsonl", [meta("a"), user("u1", "go")], directory=root)
        self.assertEqual(self.ids(root, "gemini"), [])

    def test_the_chats_directory_itself_may_be_the_root(self):
        self.tree.write("session-a.jsonl", [meta("a"), user("u1", "go")])
        self.assertEqual(self.ids(self.tree.chats, "gemini"), ["a"])

    def legacy(self, name="session-old.json"):
        path = os.path.join(self.tree.chats, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(meta("old", messages=[user("u1", "go"), gemini_record("g1", "Done.")]),
                      handle, indent=2)
        return path

    def test_a_legacy_json_is_read_under_a_named_root_and_under_auto(self):
        self.legacy()
        self.assertEqual(self.ids(self.tree.base, "gemini"), ["old"])
        sessions = list(iter_sessions(root=self.tree.base))
        self.assertEqual([(s.runtime, s.id) for s in sessions], [("gemini", "old")])

    def test_a_legacy_json_beside_its_jsonl_is_read_once_as_the_jsonl(self):
        self.legacy()
        jsonl = self.tree.write("session-old.jsonl", [meta("old"), user("u1", "go")])
        for runtime in ("gemini", "auto"):
            with self.subTest(runtime=runtime):
                sessions = list(iter_sessions(root=self.tree.base, runtime=runtime))
                self.assertEqual([s.path for s in sessions], [jsonl])

    def test_auto_reads_a_file_opening_on_a_message_record_as_gemini(self):
        path = self.tree.write("session-cut.jsonl", [user("u1", "go"),
                                                     gemini_record("g1", "Done.")])
        rewind = self.tree.write("session-rw.jsonl", [{"$rewindTo": "u1"},
                                                      user("u2", "again")])
        update = self.tree.write("session-set.jsonl", [{"$set": {"lastUpdated": "x"}},
                                                       user("u3", "more")])
        for each in (path, rewind, update):
            with self.subTest(path=os.path.basename(each)):
                self.assertIs(_detect(each), gemini)
        self.assertEqual(sorted(s.runtime for s in iter_sessions(root=self.tree.base)),
                         ["gemini"] * 3)


class RobustnessTests(TreeTest):
    """Shapes a live writer or an older version may leave."""

    def one(self, *records):
        return self.tree.session([meta(), user("u1", "go")] + list(records))

    def test_args_that_are_missing_or_not_an_object_read_as_an_empty_input(self):
        missing = call("c1", "run_shell_command", {})
        del missing["args"]
        session = self.one(gemini_record("g1", "", [
            missing, dict(call("c2", "write_file", {}), args="a string"),
            dict(call("c3", "replace", {}), args=["a", "list"])]))
        self.assertEqual([u["input"] for u in self.uses(session)], [{}, {}, {}])

    def test_a_non_list_messages_on_the_metadata_line_is_ignored(self):
        for listed in ({"u1": user("u1", "go")}, 7, "text"):
            with self.subTest(messages=listed):
                path = self.tree.write("session-2026-09-20T10-00-0b5e7c1a.jsonl",
                                       [meta(messages=listed)])
                self.assertIsNone(gemini.read(path))
                session = gemini.read(path, empty=True)
                self.assertEqual((session.id, session.events), (SESSION_ID, []))

    def test_a_file_with_no_event_is_no_session_unless_asked_for_an_empty_one(self):
        path = self.tree.write("session-2026-09-20T10-00-0b5e7c1a.jsonl", [meta()])
        self.assertIsNone(gemini.read(path))
        self.assertEqual(gemini.read(path, empty=True).events, [])
        errors = []
        self.assertEqual(list(iter_sessions(root=self.tree.base, runtime="gemini",
                                            errors=errors)), [])
        self.assertEqual([e["error"] for e in errors], ["no session in it"])

    def test_a_file_name_with_no_dot_is_the_id_when_no_metadata_names_one(self):
        session = gemini.read(self.tree.write("sessionfile", [user("u1", "go")]))
        self.assertEqual(session.id, "sessionfile")

    def test_an_empty_display_content_falls_back_to_the_content(self):
        for shown in ([], "", [{"text": ""}]):
            with self.subTest(displayContent=shown):
                session = self.tree.session([meta(),
                                             user("u1", "the prompt", displayContent=shown)])
                self.assertEqual(session.events[0]["text"], "the prompt")

    def test_an_empty_or_missing_result_makes_no_tool_result(self):
        empty_list = dict(call("c1", "read_file", {}), result=[])
        empty_map = dict(call("c2", "read_file", {}), result={})
        missing = call("c3", "read_file", {})
        del missing["result"]
        session = self.one(gemini_record("g1", "", [empty_list, empty_map, missing]))
        self.assertEqual(self.kinds(session), ["user_prompt", "tool_use", "tool_use",
                                               "tool_use"])

    def test_text_parts_in_a_result_are_read_beside_the_function_response(self):
        shell = dict(call("c1", "run_shell_command", {"command": "ls"}),
                     result=["plain", {"text": "a text part"},
                             {"functionResponse": {"id": "c1", "name": "run_shell_command",
                                                   "response": {"output": "the output"}}}])
        result = [e for e in self.one(gemini_record("g1", "", [shell])).events
                  if e["kind"] == "tool_result"][0]
        self.assertEqual(result["text"], "plain\na text part\nthe output")

    def test_a_path_climbing_out_of_the_root_is_left_as_written(self):
        session = self.one(gemini_record("g1", "", [
            call("c1", "write_file", {"file_path": "../elsewhere/a.txt", "content": "x"}),
            call("c2", "replace", {"file_path": "./src/a.txt", "new_string": "y"})]))
        self.assertEqual([u["input"]["file_path"] for u in self.uses(session)],
                         ["../elsewhere/a.txt", "/workspace/demo-project/src/a.txt"])

    def test_a_user_record_with_empty_content_is_a_prompt(self):
        session = self.tree.session([meta(), dict(user("u1", ""), content=[]),
                                     dict(user("u2", ""), content="")])
        self.assertEqual([(e["kind"], e["turn"]) for e in session.events],
                         [("user_prompt", 1), ("user_prompt", 2)])

    def test_a_turn_with_no_assistant_text_has_no_final(self):
        session = self.tree.session([
            meta(), user("u1", "go"), gemini_record("g1", "Answer."),
            user("u2", "run it"), gemini_record("g2", "", [call("c1", "read_file", {})]),
            user("u3", "thanks")])
        self.assertEqual([(e["turn"], e["final"]) for e in session.events
                          if e["kind"] == "assistant_text"], [(1, True)])


if __name__ == "__main__":
    unittest.main()
