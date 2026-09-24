# SPDX-License-Identifier: MIT
"""Every matcher, one case that hits and one that does not, and every way a spec can be
wrong.

A matcher is compiled and run through `run()` rather than called directly, so what these
assert is what a report would count.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import FAKE_KEY, bash, compact, prompt, say, tool_result, tool_use
from ruleprobe import Registry, analyse, run
from ruleprobe.declarative import DeclarativeError, parse_with_lines
from ruleprobe.matchers import compile_detector
from ruleprobe.shell import MAX_COMMAND, Parsed

WRITE = tool_use("Write", {"file_path": "a/b.py", "content": "hello"})


def hits(when, events, event="tool_use", **extra):
    """The hits a one-matcher detector finds, run the way the report runs it."""
    spec = {"id": "t/x", "rule": "t", "event": event, "when": when}
    spec.update(extra)
    detector = compile_detector(spec, "<test>")
    return run(events, registry=Registry([detector]), strict=True).get("t/x", [])


def count(when, events, event="tool_use", **extra):
    return len(hits(when, events, event, **extra))


class ToolTests(unittest.TestCase):
    def test_a_tool_by_name(self):
        self.assertEqual(count({"tool": {"name": "Write"}}, [WRITE]), 1)
        self.assertEqual(count({"tool": {"name": "Edit"}}, [WRITE]), 0)

    def test_a_tool_by_glob(self):
        self.assertEqual(count({"tool": {"glob": "mcp__*__read"}},
                               [tool_use("mcp__x__read", {})]), 1)
        self.assertEqual(count({"tool": {"glob": "mcp__*__read"}},
                               [tool_use("mcp__x__write", {})]), 0)

    def test_a_list_of_names_and_the_string_shorthand(self):
        self.assertEqual(count({"tool": ["Write", "Edit"]}, [WRITE]), 1)
        self.assertEqual(count({"tool": "Write"}, [WRITE]), 1)

    def test_one_hit_per_matching_event_carrying_its_turn_and_tool_use_id(self):
        events = [tool_use("Write", {}, turn=2, id="tu7"), tool_use("Edit", {}, id="tu8")]
        self.assertEqual(list(hits({"tool": "Write"}, events)[0]), ["t/x", 2, "tu7"])


class ArgTests(unittest.TestCase):
    def test_a_path_glob(self):
        when = {"tool": "Write", "arg": {"field": "file_path", "path_glob": "*.py"}}
        self.assertEqual(count(when, [WRITE]), 1)
        self.assertEqual(count(when, [tool_use("Write", {"file_path": "a/b.md"})]), 0)

    def test_a_regex_over_a_field(self):
        when = {"arg": {"field": "content", "regex": "^hel"}}
        self.assertEqual(count(when, [WRITE]), 1)
        self.assertEqual(count({"arg": {"field": "content", "regex": "^bye"}}, [WRITE]), 0)

    def test_a_dotted_field_and_a_list_of_fields(self):
        event = tool_use("Task", {"input": {"prompt": "go deep"}})
        self.assertEqual(count({"arg": {"field": "input.prompt", "contains": "deep"}},
                               [event]), 1)
        self.assertEqual(count({"arg": {"field": ["content", "input.prompt"],
                                        "contains": "deep"}}, [event]), 1)
        self.assertEqual(count({"arg": {"field": "input.missing.deeper",
                                        "exists": True}}, [event]), 0)

    def test_exists_and_equals(self):
        self.assertEqual(count({"arg": {"field": "file_path", "exists": True}}, [WRITE]), 1)
        self.assertEqual(count({"arg": {"field": "nope", "exists": False}}, [WRITE]), 1)
        self.assertEqual(count({"arg": {"field": "file_path", "equals": "a/b.py"}},
                               [WRITE]), 1)
        self.assertEqual(count({"arg": {"field": "file_path", "equals": ["x", "y"]}},
                               [WRITE]), 0)

    def test_a_field_that_is_not_a_string_matches_no_text_constraint(self):
        event = tool_use("Write", {"content": {"not": "text"}})
        self.assertEqual(count({"arg": {"field": "content", "regex": "not"}}, [event]), 0)


class CommandTests(unittest.TestCase):
    def test_starts_with_reads_the_head_of_a_segment(self):
        when = {"command": {"starts_with": ["sudo", "pip"]}}
        self.assertEqual(count(when, [bash("sudo pip install ruff")]), 1)
        self.assertEqual(count(when, [bash("pip install ruff")]), 0)
        self.assertEqual(count(when, [bash("echo sudo pip")]), 0)

    def test_the_string_shorthand_is_starts_with(self):
        self.assertEqual(count({"command": "cat"}, [bash("cat a")]), 1)

    def test_contains_and_none_of_read_the_tokens(self):
        self.assertEqual(count({"command": {"contains": "--force"}},
                               [bash("git push --force")]), 1)
        self.assertEqual(count({"command": {"name": "grep", "none_of": ["-n"]}},
                               [bash("grep -rn x .")]), 1)
        self.assertEqual(count({"command": {"name": "grep", "none_of": ["-rn"]}},
                               [bash("grep -rn x .")]), 0)

    def test_regex_reads_the_whole_command_text_and_not_one_segment(self):
        self.assertEqual(count({"command": {"regex": "head -\\d+"}},
                               [bash("cat a | head -20")]), 1)
        self.assertEqual(count({"command": {"regex": "^tail"}},
                               [bash("cat a | head -20")]), 0)

    def test_arg_count_takes_a_number_or_a_range(self):
        self.assertEqual(count({"command": {"name": "cat", "arg_count": 1}},
                               [bash("cat a")]), 1)
        self.assertEqual(count({"command": {"name": "cat", "arg_count": 1}},
                               [bash("cat a b")]), 0)
        self.assertEqual(count({"command": {"name": "cat", "arg_count": {"min": 2}}},
                               [bash("cat a b")]), 1)
        self.assertEqual(count({"command": {"name": "cat", "arg_count": {"max": 1}}},
                               [bash("cat a b")]), 0)

    def test_sole_segment_distinguishes_a_pipeline_from_a_lone_command(self):
        when = {"command": {"name": "cat", "sole_segment": True}}
        self.assertEqual(count(when, [bash("cat a")]), 1)
        self.assertEqual(count(when, [bash("cat a | head")]), 0)
        self.assertEqual(count({"command": {"name": "cat", "sole_segment": False}},
                               [bash("cat a | head")]), 1)

    def test_redirect_is_read_per_segment(self):
        when = {"command": {"name": "cat", "redirect": False}}
        self.assertEqual(count(when, [bash("cat a")]), 1)
        self.assertEqual(count(when, [bash("cat a > b")]), 0)

    def test_unparsed_is_the_command_too_long_to_tokenize(self):
        huge = bash("echo " + "x" * (64 * 1024))
        self.assertEqual(count({"command": {"unparsed": True}}, [huge]), 1)
        self.assertEqual(count({"command": {"unparsed": True}}, [bash("ls")]), 0)

    def test_a_command_matcher_never_fires_on_another_tool(self):
        self.assertEqual(count({"command": {"name": "cat"}}, [WRITE]), 0)


class GitAndEnvTests(unittest.TestCase):
    def test_a_git_subcommand_with_a_flag(self):
        when = {"git": {"subcommand": ["push"], "args_any": ["--force"]}}
        self.assertEqual(count(when, [bash("git push --force origin main")]), 1)
        self.assertEqual(count(when, [bash("git push origin main")]), 0)
        self.assertEqual(count(when, [bash("echo git push --force")]), 0)

    def test_git_steps_over_the_options_before_the_subcommand(self):
        when = {"git": {"subcommand": ["commit"], "token_prefix": "core.hooksPath="}}
        self.assertEqual(count(when, [bash("git -c core.hooksPath=/dev/null commit -m x")]), 1)
        self.assertEqual(count(when, [bash("git -C repo commit -m x")]), 0)

    def test_args_none_excludes_a_spelling(self):
        when = {"git": {"subcommand": ["commit"], "args_none": ["--amend"]}}
        self.assertEqual(count(when, [bash("git commit -m x")]), 1)
        self.assertEqual(count(when, [bash("git commit --amend -m x")]), 0)

    def test_an_assignment_in_front_of_a_named_command(self):
        when = {"env": {"name": ["SKIP"], "command": ["git", "pre-commit"]}}
        self.assertEqual(count(when, [bash("SKIP=ruff git commit -m x")]), 1)
        self.assertEqual(count(when, [bash("SKIP=ruff make test")]), 0)
        self.assertEqual(count(when, [bash("git commit -m x")]), 0)


class TextTests(unittest.TestCase):
    def test_the_command_source_is_the_raw_text(self):
        self.assertEqual(count({"text": {"source": "command", "contains": "TODO"}},
                               [bash("echo TODO")]), 1)

    def test_the_heredoc_source_is_the_body_and_not_the_command(self):
        when = {"text": {"source": "heredocs", "regex": FAKE_KEY}}
        self.assertEqual(count(when, [bash("cat > .env <<EOF\nKEY=%s\nEOF" % FAKE_KEY)]), 1)
        self.assertEqual(count(when, [bash("echo %s" % FAKE_KEY)]), 0)

    def test_the_payload_source_falls_back_to_a_command_too_long_to_parse(self):
        when = {"text": {"source": "payload", "regex": FAKE_KEY}}
        huge = bash("echo " + "x" * (64 * 1024) + " " + FAKE_KEY)
        self.assertEqual(count(when, [huge]), 1)
        self.assertEqual(count(when, [bash("echo %s" % FAKE_KEY)]), 0)

    def test_the_assistant_source_reads_the_message(self):
        self.assertEqual(count({"text": {"source": "assistant", "contains": "sorry"}},
                               [say("sorry about that")], event="assistant_text"), 1)


class MessageTests(unittest.TestCase):
    def test_a_final_assistant_message_by_regex(self):
        events = [say("running the gate", final=False), say("all green", turn=2)]
        when = {"message": {"role": "assistant", "final": True, "regex": "green"}}
        self.assertEqual(count(when, events, event="assistant_text"), 1)
        self.assertEqual(count({"message": {"final": False, "regex": "green"}},
                               events, event="assistant_text"), 0)

    def test_a_user_prompt_carries_no_text_so_a_regex_never_matches_one(self):
        self.assertEqual(count({"message": {"role": "user"}}, [prompt()], event="session"), 1)
        self.assertEqual(count({"message": {"role": "user", "regex": "x"}}, [prompt()],
                               event="session"), 0)


class KindAndCompositionTests(unittest.TestCase):
    def test_kind_reads_the_raw_event_kind(self):
        self.assertEqual(count({"kind": "compact"}, [compact(), prompt(turn=2)],
                               event="session"), 1)

    def test_any_all_and_not(self):
        events = [WRITE]
        self.assertEqual(count({"any": [{"tool": "Edit"}, {"tool": "Write"}]}, events), 1)
        self.assertEqual(count({"all": [{"tool": "Write"},
                                        {"arg": {"field": "content",
                                                 "contains": "hello"}}]}, events), 1)
        self.assertEqual(count({"all": [{"tool": "Write"},
                                        {"arg": {"field": "content",
                                                 "contains": "bye"}}]}, events), 0)
        self.assertEqual(count({"tool": "Write", "not": {"arg": {"field": "content",
                                                                 "contains": "bye"}}},
                               events), 1)

    def test_two_keys_in_one_matcher_are_an_implicit_all(self):
        when = {"tool": "Write", "arg": {"field": "file_path", "path_glob": "*.md"}}
        self.assertEqual(count(when, [WRITE]), 0)


class OrderTests(unittest.TestCase):
    EVENTS = [bash("git add -A", id="tu1"),
              bash("git commit -m x", turn=1, id="tu2"),
              bash("git push", turn=1, id="tu3")]

    def test_one_event_followed_by_another_within_a_window(self):
        when = {"order": {"first": {"command": {"starts_with": ["git", "commit"]}},
                          "then": {"command": {"starts_with": ["git", "push"]}},
                          "within": 1}}
        found = hits(when, self.EVENTS, event="session")
        self.assertEqual([h.tool_use_id for h in found], ["tu2"])

    def test_a_window_too_narrow_to_reach_the_second_event_is_no_hit(self):
        when = {"order": {"first": {"command": {"starts_with": ["git", "add"]}},
                          "then": {"command": {"starts_with": ["git", "push"]}},
                          "within": 1}}
        self.assertEqual(count(when, self.EVENTS, event="session"), 0)


class AbsentTests(unittest.TestCase):
    def test_a_session_with_nothing_matching_is_one_hit(self):
        when = {"absent": {"of": {"command": {"starts_with": ["pytest"]}}}}
        self.assertEqual(count(when, [bash("ls")], event="session"), 1)
        self.assertEqual(count(when, [bash("pytest -q")], event="session"), 0)

    def test_turn_scope_is_one_hit_per_turn_that_saw_nothing(self):
        events = [bash("pytest -q", turn=1), bash("ls", turn=2), bash("ls", turn=3)]
        when = {"absent": {"of": {"command": {"starts_with": ["pytest"]}}, "scope": "turn"}}
        self.assertEqual([h.turn for h in hits(when, events, event="session")], [2, 3])

    def test_an_empty_session_is_no_absence_at_all(self):
        # A rollout that was aborted before anything happened is not a session in which
        # something failed to happen; counting it walks the rate towards 100% on nothing.
        when = {"absent": {"of": {"tool": "Write"}}}
        self.assertEqual(count(when, [], event="session"), 0)


class ChangeTests(unittest.TestCase):
    def test_a_field_that_differs_from_the_previous_event_of_its_kind(self):
        when = {"change": {"kind": "assistant_text", "field": "model"}}
        events = [say("a"), say("b", turn=2, model="claude-sonnet-5"),
                  say("c", turn=3, model="claude-sonnet-5")]
        self.assertEqual(count(when, events, event="session"), 1)

    def test_an_ignored_prefix_is_stepped_over_rather_than_counted(self):
        when = {"change": {"field": "model", "ignore_prefix": "<"}}
        events = [say("a"), say("b", turn=2, model="<synthetic>"), say("c", turn=3)]
        self.assertEqual(count(when, events, event="session"), 0)


class GateTests(unittest.TestCase):
    WHEN = {"tool": "Write"}

    def test_a_gated_detector_runs_only_under_its_variants(self):
        spec = {"id": "t/x", "rule": "t", "event": "tool_use", "when": self.WHEN,
                "gate": {"stance": "commits", "variants": ["conventional"]}}
        detector = compile_detector(spec, "<test>")
        registry = Registry([detector])
        self.assertTrue(run([WRITE], {"commits": "conventional"}, registry=registry))
        self.assertFalse(run([WRITE], {"commits": "loose"}, registry=registry))
        self.assertFalse(run([WRITE], {}, registry=registry))

    def test_a_gate_with_no_variants_is_any_variant_but_off(self):
        detector = compile_detector({"id": "t/x", "rule": "t", "when": self.WHEN,
                                     "gate": {"stance": "commits"}}, "<test>")
        registry = Registry([detector])
        self.assertTrue(run([WRITE], {"commits": "anything"}, registry=registry))
        self.assertFalse(run([WRITE], {"commits": "off"}, registry=registry))


class SpecErrorTests(unittest.TestCase):
    """A bad spec is a finding with a line, never a detector that quietly never fires."""

    BAD = [
        ({"rule": "t", "when": {"tool": "Write"}}, "id of the shape"),
        ({"id": "nope", "when": {"tool": "Write"}}, "id of the shape"),
        ({"id": "t/x", "rule": "a/b", "when": {"tool": "Write"}}, "no slash"),
        ({"id": "t/x"}, "needs a when"),
        ({"id": "t/x", "event": "tool-use", "when": {"tool": "Write"}}, "unknown event"),
        ({"id": "t/x", "whn": {"tool": "Write"}}, "unknown detector key"),
        ({"id": "t/x", "when": {"comand": "cat"}}, "unknown matcher"),
        ({"id": "t/x", "when": {}}, "empty matcher"),
        ({"id": "t/x", "when": "cat"}, "a matcher is a mapping"),
        ({"id": "t/x", "when": {"tool": {"nome": "Write"}}}, "unknown tool key"),
        ({"id": "t/x", "when": {"arg": {"regex": "x"}}}, "arg needs a field"),
        ({"id": "t/x", "when": {"arg": {"field": "a", "regex": "("}}}, "bad regular"),
        ({"id": "t/x", "when": {"command": {"arg_count": "two"}}}, "arg_count must be"),
        ({"id": "t/x", "when": {"command": {"sole_segment": "yes"}}}, "true or false"),
        ({"id": "t/x", "when": {"git": {"args_any": ["-n"]}}}, "git needs a subcommand"),
        ({"id": "t/x", "when": {"env": {"command": ["git"]}}}, "env needs a name"),
        ({"id": "t/x", "when": {"text": {"source": "stdout", "regex": "x"}}}, "text source"),
        ({"id": "t/x", "when": {"text": {"source": "command"}}}, "needs a regex"),
        ({"id": "t/x", "when": {"message": {"role": "tool"}}}, "message role"),
        ({"id": "t/x", "when": {"any": []}}, "non-empty list"),
        ({"id": "t/x", "when": {"any": {"tool": "Write"}}}, "non-empty list"),
        ({"id": "t/x", "event": "session", "when": {"order": {"first": {"tool": "A"}}}},
         "order needs a then"),
        ({"id": "t/x", "event": "session",
          "when": {"absent": {"of": {"tool": "A"}, "scope": "file"}}}, "absent scope"),
        ({"id": "t/x", "event": "session", "when": {"change": {}}}, "change needs a field"),
        ({"id": "t/x", "when": {"tool": "Write",
                                "gate": {"stance": "commits"}}}, "unknown matcher"),
        ({"id": "t/x", "when": {"tool": "Write"}, "gate": {"variants": ["a"]}},
         "gate needs a stance"),
    ]

    def test_each_bad_spec_says_what_is_wrong(self):
        for spec, reason in self.BAD:
            with self.subTest(spec=str(spec)[:48]):
                with self.assertRaises(DeclarativeError) as caught:
                    compile_detector(spec, "detectors.yaml")
                self.assertIn(reason, caught.exception.reason)

    def test_an_aggregate_may_not_hide_inside_a_composition(self):
        spec = {"id": "t/x", "event": "session",
                "when": {"any": [{"absent": {"of": {"tool": "Write"}}}]}}
        with self.assertRaises(DeclarativeError) as caught:
            compile_detector(spec, "detectors.yaml")
        self.assertIn("whole of a session detector", caught.exception.reason)

    def test_an_aggregate_needs_the_session_event(self):
        spec = {"id": "t/x", "event": "tool_use", "when": {"absent": {"of": {"tool": "W"}}}}
        with self.assertRaises(DeclarativeError):
            compile_detector(spec, "detectors.yaml")

    def test_an_error_carries_the_line_the_key_was_written_on(self):
        text = ("detectors:\n"
                "  - id: t/x\n"
                "    event: tool_use\n"
                "    when:\n"
                "      comand: cat\n")
        document, lines = parse_with_lines(text, "detectors.yaml")
        with self.assertRaises(DeclarativeError) as caught:
            compile_detector(document["detectors"][0], "detectors.yaml", lines)
        self.assertEqual(caught.exception.line, 5)


# --- a command the shell parse skipped (#19) ----------------------------------------

#: The inputs from #19: over-long, and an unbalanced quote, each as a bare and a `uv` call;
#: and the empty command, which the parse also skips.
SKIPPED = ("pytest -q -k " + "x" * MAX_COMMAND,
           "pytest -q -k 'foo",
           "uv run pytest -q -k " + "x" * MAX_COMMAND,
           "uv run pytest -q -k 'foo",
           "")
UNREAD_HEREDOC = "cat <<EOF\nhello " + "x" * MAX_COMMAND + "\nEOF"
UNREAD_PUSH = "git push origin 'main"
UNREAD_ENV = "FOO=1 pytest -k 'foo"
PYTEST = {"command": {"contains": "pytest"}}


def negated(matcher):
    """A matcher under `not`, on Bash calls only, so a false child is a hit."""
    return {"tool": "Bash", "not": matcher}


class UndecidedTests(unittest.TestCase):
    """Over a skipped parse a segment matcher is undecided, and no combinator makes that a
    hit. Each negative case is paired with a parsed command that does hit, so a matcher
    that never fires cannot pass."""

    def test_the_inputs_are_ones_the_parse_skipped(self):
        for command in SKIPPED + (UNREAD_PUSH, UNREAD_ENV, UNREAD_HEREDOC):
            with self.subTest(command=command[:30]):
                self.assertTrue(Parsed(bash(command)).skipped)

    def test_not_over_a_skipped_command_is_no_hit(self):
        for command in SKIPPED:
            with self.subTest(command=command[:30]):
                self.assertEqual(count(negated(PYTEST), [bash(command)]), 0)
        self.assertEqual(count(negated(PYTEST), [bash("ls")]), 1)

    def test_absent_of_a_skipped_command_is_no_hit_in_either_scope(self):
        for scope in ("session", "turn"):
            when = {"absent": {"of": PYTEST, "scope": scope}}
            for command in SKIPPED:
                with self.subTest(scope=scope, command=command[:30]):
                    self.assertEqual(count(when, [bash(command)], event="session"), 0)
            self.assertEqual(count(when, [bash("ls")], event="session"), 1)

    def test_not_and_absent_of_git_over_a_skipped_command_are_no_hit(self):
        push = {"git": {"subcommand": "push"}}
        self.assertEqual(count(negated(push), [bash(UNREAD_PUSH)]), 0)
        self.assertEqual(count({"absent": {"of": push}}, [bash(UNREAD_PUSH)],
                               event="session"), 0)
        self.assertEqual(count(negated(push), [bash("git status")]), 1)
        self.assertEqual(count({"absent": {"of": push}}, [bash("git status")],
                               event="session"), 1)

    def test_every_segment_key_is_undecided_over_a_skipped_command(self):
        # Each key, with a parsed command it is false on, so `not` of it is a hit there.
        keys = [({"command": {"name": "pytest"}}, "echo"),
                ({"command": {"starts_with": ["pytest"]}}, "echo"),
                ({"command": {"contains": "pytest"}}, "echo"),
                ({"command": {"none_of": ["-q"]}}, "echo -q"),
                ({"command": {"arg_count": 3}}, "echo"),
                ({"command": {"sole_segment": True}}, "echo | cat"),
                ({"command": {"redirect": False}}, "echo > a"),
                ({"git": {"subcommand": "push", "args_any": ["origin"]}}, "git push"),
                ({"git": {"subcommand": "push", "args_none": ["--force"]}},
                 "git push --force"),
                ({"git": {"subcommand": "push", "token_prefix": "orig"}}, "git push"),
                ({"env": {"name": "FOO"}}, "echo"),
                ({"env": {"name": "FOO", "command": "pytest"}}, "FOO=1 echo")]
        for matcher, parsed_false in keys:
            with self.subTest(matcher=matcher):
                self.assertEqual(count(negated(matcher), [bash(UNREAD_PUSH)]), 0)
                self.assertEqual(count(negated(matcher), [bash(UNREAD_ENV)]), 0)
                self.assertEqual(count(negated(matcher), [bash(parsed_false)]), 1)

    def test_regex_and_unparsed_keep_their_answer_over_a_skipped_command(self):
        skipped = [bash(SKIPPED[1])]
        self.assertEqual(count({"command": {"regex": "^pytest"}}, skipped), 1)
        self.assertEqual(count(negated({"command": {"regex": "^ls"}}), skipped), 1)
        self.assertEqual(count({"command": {"unparsed": True}}, skipped), 1)
        self.assertEqual(count(negated({"command": {"unparsed": False}}), skipped), 1)
        # A decided `regex` or `unparsed` settles the block before any segment key is read.
        self.assertEqual(count(negated({"command": {"regex": "^ls", "name": "pytest"}}),
                               skipped), 1)
        # A `regex` that holds leaves the segment key to decide, and it cannot.
        self.assertEqual(count(negated({"command": {"regex": "^pytest", "name": "pytest"}}),
                               skipped), 0)

    def test_a_heredocs_text_read_is_undecided_over_a_skipped_command(self):
        when = negated({"text": {"source": "heredocs", "contains": "hello"}})
        self.assertEqual(count(when, [bash(UNREAD_HEREDOC)]), 0)
        self.assertEqual(count(when, [bash("echo hi")]), 1)

    def test_not_of_undecided_is_undecided_and_so_is_its_double(self):
        skipped = [bash(SKIPPED[1])]
        self.assertEqual(count(negated(PYTEST), skipped), 0)
        self.assertEqual(count(negated({"not": PYTEST}), skipped), 0)
        self.assertEqual(count(negated([{"tool": "Write"}, PYTEST]), skipped), 0)
        self.assertEqual(count(negated({"not": PYTEST}), [bash("pytest -q")]), 1)
        self.assertEqual(count(negated([{"tool": "Write"}, PYTEST]), [bash("ls")]), 1)

    def test_any_is_true_on_a_true_child(self):
        self.assertEqual(count({"any": [PYTEST, {"tool": "Bash"}]}, [bash(SKIPPED[1])]), 1)

    def test_any_is_undecided_on_an_undecided_child_and_no_true_one(self):
        self.assertEqual(count(negated({"any": [{"tool": "Write"}, PYTEST]}),
                               [bash(SKIPPED[1])]), 0)
        self.assertEqual(count(negated({"any": [{"tool": "Write"}, PYTEST]}),
                               [bash("ls")]), 1)

    def test_any_is_false_when_every_child_is_false(self):
        self.assertEqual(count(negated({"any": [{"tool": "Write"}, {"tool": "Edit"}]}),
                               [bash(SKIPPED[1])]), 1)

    def test_all_is_false_on_a_false_child(self):
        self.assertEqual(count(negated({"all": [PYTEST, {"tool": "Write"}]}),
                               [bash(SKIPPED[1])]), 1)

    def test_all_is_undecided_on_an_undecided_child_and_no_false_one(self):
        self.assertEqual(count(negated({"all": [{"tool": "Bash"}, PYTEST]}),
                               [bash(SKIPPED[1])]), 0)
        self.assertEqual(count(negated({"tool": "Bash", "command": PYTEST["command"]}),
                               [bash(SKIPPED[1])]), 0)
        self.assertEqual(count(negated({"all": [{"tool": "Bash"}, PYTEST]}),
                               [bash("ls")]), 1)
        self.assertEqual(count(negated({"tool": "Bash", "command": PYTEST["command"]}),
                               [bash("ls")]), 1)

    def test_payload_and_command_text_reads_stay_decided_over_a_skipped_command(self):
        for source in ("payload", "command"):
            with self.subTest(source=source):
                when = negated({"text": {"source": source, "contains": "zzz"}})
                self.assertEqual(count(when, [bash(SKIPPED[1])]), 1)

    def test_all_is_true_when_every_child_is_true(self):
        self.assertEqual(count({"all": [{"tool": "Bash"}, {"command": {"unparsed": True}}]},
                               [bash(SKIPPED[1])]), 1)

    def test_an_undecided_when_is_no_hit(self):
        for when, fires_on in ((PYTEST, "pytest -q"), (negated(PYTEST), "ls"),
                               ({"any": [PYTEST]}, "pytest -q"),
                               ({"all": [PYTEST]}, "pytest -q")):
            with self.subTest(when=when):
                self.assertEqual(count(when, [bash(SKIPPED[0])]), 0)
                self.assertEqual(count(when, [bash(fires_on)]), 1)
        for when, unread, fires_on in (({"git": {"subcommand": "push"}}, UNREAD_PUSH, "git push"),
                                       ({"env": {"name": "FOO"}}, UNREAD_ENV, "FOO=1 echo")):
            with self.subTest(when=when):
                self.assertEqual(count(when, [bash(unread)]), 0)
                self.assertEqual(count(when, [bash(fires_on)]), 1)

    def test_order_needs_first_and_then_both_true(self):
        unread = bash(SKIPPED[1], id="tu1")
        first_undecided = {"order": {"first": {"not": {"command": {"name": "echo"}}},
                                     "then": {"git": {"subcommand": "push"}}}}
        self.assertEqual(count(first_undecided, [unread, bash("git push", id="tu2")],
                               event="session"), 0)
        self.assertEqual(count(first_undecided,
                               [bash("ls", id="tu1"), bash("git push", id="tu2")],
                               event="session"), 1)
        then_undecided = {"order": {"first": {"git": {"subcommand": "add"}},
                                    "then": {"not": {"command": {"name": "echo"}}}}}
        self.assertEqual(count(then_undecided, [bash("git add a", id="tu0"), unread],
                               event="session"), 0)
        self.assertEqual(count(then_undecided,
                               [bash("git add a", id="tu0"), bash("ls", id="tu2")],
                               event="session"), 1)

    def test_an_absent_scope_with_an_undecided_candidate_is_no_hit(self):
        events = [bash(SKIPPED[1], turn=1, id="tu1"), bash("ls", turn=2, id="tu2")]
        when = {"absent": {"of": PYTEST, "scope": "turn"}}
        self.assertEqual([h.turn for h in hits(when, events, event="session")], [2])
        when = {"absent": {"of": PYTEST, "scope": "session"}}
        self.assertEqual(count(when, events, event="session"), 0)


def opportunities(when, events):
    """The `(turn, tool_use_id, followed)` triples a one-matcher session detector counts,
    beside the hits `run()` gives it; `None` for a detector that defines none."""
    detector = compile_detector({"id": "t/x", "rule": "t", "event": "session",
                                 "when": when}, "<test>")
    if detector.opportunities is None:
        return None, hits(when, events, event="session")
    ctx = analyse(events)
    return detector.opportunities(ctx.events, ctx), hits(when, events, event="session")


class OpportunityTests(unittest.TestCase):
    ABSENT = {"absent": {"of": PYTEST, "scope": "turn"}}
    ORDER = {"order": {"first": {"git": {"subcommand": "commit"}},
                       "then": {"git": {"subcommand": "push"}}, "within": 1}}

    def test_each_turn_is_one_absent_opportunity_followed_when_of_matched_in_it(self):
        events = [bash("pytest -q", turn=1), bash("ls", turn=2),
                  bash("ls", turn=3), bash("pytest -x", turn=3, id="tu2")]
        found, hit = opportunities(self.ABSENT, events)
        self.assertEqual(found, [(1, None, True), (2, None, False), (3, None, True)])
        self.assertEqual([h.turn for h in hit], [2])

    def test_each_first_match_opens_one_order_opportunity(self):
        events = [bash("git commit -m a", id="tu1"), tool_result("ok", "Bash", "tu1"),
                  bash("git push", id="tu2"),
                  bash("git commit -m b", turn=2, id="tu3"), bash("ls", turn=2, id="tu4"),
                  bash("git push", turn=2, id="tu5")]
        found, hit = opportunities(self.ORDER, events)
        self.assertEqual(found, [(1, "tu1", True), (2, "tu3", False)])
        self.assertEqual([h.tool_use_id for h in hit], ["tu1"])

    def test_a_session_with_nothing_to_open_one_has_no_opportunity(self):
        self.assertEqual(opportunities(self.ORDER, [bash("ls")])[0], [])
        self.assertEqual(opportunities(self.ABSENT, [])[0], [])

    def test_session_scope_change_and_event_matchers_define_none(self):
        events = [bash("ls")]
        for when in ({"absent": {"of": PYTEST}}, {"absent": {"of": PYTEST, "scope": "session"}},
                     {"change": {"kind": "assistant_text", "field": "model"}}, PYTEST):
            with self.subTest(when=when):
                self.assertIsNone(opportunities(when, events)[0])

    def test_an_absent_turn_with_an_undecided_candidate_and_no_true_one_is_undecided(self):
        events = [bash(SKIPPED[1], turn=1), bash("ls", turn=1, id="tu2"),
                  bash(SKIPPED[1], turn=2), bash("pytest -q", turn=2, id="tu2"),
                  bash("ls", turn=3)]
        found, hit = opportunities(self.ABSENT, events)
        self.assertEqual(found, [(1, None, None), (2, None, True), (3, None, False)])
        self.assertEqual([h.turn for h in hit], [3])

    def test_an_undecided_first_is_an_undecided_opportunity_and_no_hit(self):
        when = {"order": {"first": {"git": {"subcommand": "push"}},
                          "then": {"command": {"name": "ls"}}}}
        found, hit = opportunities(when, [bash(UNREAD_PUSH, id="tu1"), bash("ls", id="tu2")])
        self.assertEqual((found, hit), ([(1, "tu1", None)], []))
        found, hit = opportunities(when, [bash("git push", id="tu1"), bash("ls", id="tu2")])
        self.assertEqual(found, [(1, "tu1", True)])
        self.assertEqual(len(hit), 1)

    def test_an_undecided_then_is_undecided_unless_a_true_one_follows_in_the_window(self):
        # `first` is a `regex`, which stays decided over the unread push, so the push opens
        # no undecided opportunity of its own.
        when = {"order": {"first": {"command": {"regex": "^git add"}},
                          "then": {"git": {"subcommand": "push"}}, "within": 2}}
        add, unread = bash("git add a", id="tu1"), bash(UNREAD_PUSH, id="tu2")
        cases = [([add, unread, bash("ls", id="tu3")], None, 0),
                 ([add, unread, bash("git push", id="tu3")], True, 1),
                 ([add, bash("ls", id="tu2"), bash("ls", id="tu3"), unread], False, 0)]
        for events, followed, count_ in cases:
            with self.subTest(followed=followed):
                found, hit = opportunities(when, events)
                self.assertEqual(found, [(1, "tu1", followed)])
                self.assertEqual(len(hit), count_)


class SharedEvaluationTests(unittest.TestCase):
    """`fn` and `opportunities` read one evaluation per event list."""

    def evaluations(self, calls):
        import ruleprobe.matchers as matchers
        made = []
        real = matchers._Env

        def counting(ctx):
            made.append(ctx)
            return real(ctx)

        matchers._Env = counting
        try:
            calls()
        finally:
            matchers._Env = real
        return len(made)

    def test_both_calls_on_one_list_evaluate_once_and_another_list_again(self):
        for when in (OpportunityTests.ORDER, OpportunityTests.ABSENT):
            with self.subTest(when=when):
                detector = compile_detector({"id": "t/x", "rule": "t", "event": "session",
                                             "when": when}, "<test>")
                first = analyse([bash("git commit -m a", id="tu1"), bash("git push", id="tu2")])
                second = analyse([bash("git commit -m a", id="tu1"), bash("ls", id="tu2")])
                self.assertEqual(self.evaluations(lambda: (
                    detector.fn(first.events, first),
                    detector.opportunities(first.events, first))), 1)
                self.assertEqual(self.evaluations(lambda: (
                    detector.opportunities(second.events, second),
                    detector.fn(second.events, second))), 1)
                self.assertEqual(len(detector.fn(second.events, second)),
                                 0 if "order" in when else 1)
                self.assertEqual(self.evaluations(lambda: (
                    detector.fn(first.events, first))), 1)


class SnippetTurnTests(unittest.TestCase):
    def test_a_snippet_turn_that_is_not_a_whole_number_is_refused_with_a_line(self):
        text = ("id: t/x\nevent: session\nwhen:\n  absent:\n    of: {tool: Write}\n"
                "    scope: turn\nexamples:\n  fire:\n    - event: {turn: [1], input: {}}\n")
        spec, lines = parse_with_lines(text, "<test>")
        for bad in ([1], "1", True, 1.5):
            with self.subTest(turn=bad):
                spec["examples"]["fire"][0]["event"]["turn"] = bad
                with self.assertRaisesRegex(DeclarativeError, "turn is a whole number") as cm:
                    compile_detector(spec, "<test>", lines)
                self.assertGreater(cm.exception.line, 0)
        spec["examples"]["fire"][0]["event"]["turn"] = 2
        self.assertIsNotNone(compile_detector(spec, "<test>", lines).opportunities)


# --- the keys the catalog added: `program`, `first_operand`, `arg_regex`, `message_regex` --


def count_bash(when, command):
    """The hits a one-matcher detector finds on one Bash command."""
    return count(when, [bash(command)])


class ProgramTests(unittest.TestCase):
    """`command`'s `program` and `first_operand`: the first word by basename, past leading
    assignments, and the first operand past flags and the value of a directory or file
    flag, each matched whole."""

    def test_the_basename_past_assignments_is_matched_whole(self):
        when = {"command": {"program": r"pytest"}}
        for command in ("pytest", "/usr/local/bin/pytest -x", "CI=1 A=b pytest",
                        "cd a && .venv/bin/pytest"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 1)
        for command in ("pytest-watch", "echo pytest", "CI=1", "cat bin/pytest"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 0)

    def test_the_first_operand_skips_flags_and_is_matched_whole(self):
        when = {"command": {"program": r"pip[0-9.]*", "first_operand": r"install"}}
        for command in ("pip install x", "pip3.12 -q install x", "pip --user install x"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 1)
        for command in ("pip uninstall x", "pip", "pip -q", "pip show install"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 0)

    def test_the_first_operand_steps_over_the_value_of_a_directory_or_file_flag(self):
        when = {"command": {"program": r"yarn|go|npm|g?make|mvn",
                            "first_operand": r"test"}}
        for command in ("make -C src test", "mvn -f pom.xml test", "go test ./...",
                        "make --file ci.mk test"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 1)
        for command in ("yarn --cwd test install", "go -C test build",
                        "npm --prefix test ci", "make -f test all", "make --dir test all"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(when, command), 0)

    def test_both_hold_of_one_segment(self):
        when = {"command": {"program": r"pip", "first_operand": r"install"}}
        self.assertEqual(count_bash(when, "pip list; npm install"), 0)

    def test_over_a_command_the_parse_skipped_it_is_undecided(self):
        negated = {"tool": "Bash", "not": {"command": {"program": r"pytest"}}}
        self.assertEqual(count_bash(negated, "echo 'unterminated"), 0)
        self.assertEqual(count_bash(negated, "ls"), 1)

    def test_a_bad_pattern_is_a_spec_error(self):
        for key in ("program", "first_operand"):
            with self.subTest(key=key), self.assertRaises(DeclarativeError):
                compile_detector({"id": "t/x", "rule": "t", "event": "tool_use",
                                  "when": {"command": {key: "("}}})


class ArgRegexTests(unittest.TestCase):
    """`git`'s `arg_regex`: read against one parsed argument at a time, never the raw
    command."""

    WHEN = {"git": {"subcommand": "add", "arg_regex": r"^(?:[^/]*/)*\.env\Z"}}

    def test_an_argument_matching_the_pattern_hits(self):
        self.assertEqual(count_bash(self.WHEN, "git add src config/.env"), 1)
        self.assertEqual(count_bash(self.WHEN, "git -C app add -- \".env\""), 1)

    def test_the_pattern_reads_one_argument_at_a_time(self):
        spanning = {"git": {"subcommand": "add", "arg_regex": r"src \.env"}}
        self.assertEqual(count_bash(spanning, "git add src .env"), 0)
        self.assertEqual(count_bash(spanning, "git add 'src .env'"), 1)

    def test_text_in_another_segment_or_before_the_subcommand_is_not_an_argument(self):
        self.assertEqual(count_bash(self.WHEN, "git add src; echo .env"), 0)
        self.assertEqual(count_bash(self.WHEN, "git -c core.x=.env add src"), 0)
        self.assertEqual(count_bash(self.WHEN, "git status .env"), 0)

    def test_a_list_is_alternatives(self):
        when = {"git": {"subcommand": "add", "arg_regex": [r"\.key\Z", r"\.env\Z"]}}
        self.assertEqual(count_bash(when, "git add a.key"), 1)
        self.assertEqual(count_bash(when, "git add .env"), 1)
        self.assertEqual(count_bash(when, "git add a.txt"), 0)

    def test_a_bad_pattern_is_a_spec_error(self):
        with self.assertRaises(DeclarativeError):
            compile_detector({"id": "t/x", "rule": "t", "event": "tool_use",
                              "when": {"git": {"subcommand": "add", "arg_regex": "("}}})


class MessageRegexTests(unittest.TestCase):
    """`git`'s `message_regex`: read against the call's first message."""

    WHEN = {"git": {"subcommand": "commit", "message_regex": r"^wip"}}

    def test_every_form_of_the_first_message_is_read(self):
        for command in ("git commit -m wip", "git commit --message wip",
                        "git commit --message=wip", "git commit -mwip", "git commit -am wip",
                        "git commit -sm wip", "git commit -asm wip",
                        "git commit -m wip -m 'feat: x'"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(self.WHEN, command), 1)

    def test_every_valueless_flag_may_lead_the_m_and_text_may_follow_it(self):
        for flag in "aeinopqsvz":
            with self.subTest(flag=flag):
                self.assertEqual(count_bash(self.WHEN, "git commit -%sm wip" % flag), 1)
        self.assertEqual(count_bash(self.WHEN, "git commit -amwip"), 1)
        self.assertEqual(count_bash(self.WHEN, "git commit -amfeat"), 0)
        self.assertEqual(count_bash(self.WHEN, "git commit -Fm wip"), 0)

    def test_a_heredoc_marker_inside_a_message_is_unreadable(self):
        command = "git commit -m \"wip $(cat <<'EOF'\nbody\nEOF\n)\""
        self.assertEqual(count_bash(self.WHEN, command), 0)

    def test_a_single_quoted_dollar_is_an_unread_message(self):
        # A stated under-count: the parse keeps no quoting, so `$` is unreadable anywhere.
        self.assertEqual(count_bash(self.WHEN, "git commit -m 'wip costs $5'"), 0)

    def test_a_later_message_or_a_quoted_flag_is_not_the_subject(self):
        for command in ("git commit -m 'feat: x' -m wip", "git commit --author='A -m wip'",
                        "git commit --author='A' -m 'feat: -m wip'",
                        "git commit -- -m wip", "git commit -F msg.txt",
                        "git commit -Cm wip", "git commit -m"):
            with self.subTest(command=command):
                self.assertEqual(count_bash(self.WHEN, command), 0)

    def test_an_unreadable_message_is_undecided_so_a_negation_never_counts_it(self):
        negated = {"git": {"subcommand": "commit"},
                   "not": {"git": {"subcommand": "commit", "message_regex": r"^feat"}}}
        self.assertEqual(count_bash(negated, "git commit -m 'fix: x'"), 1)
        for command in ('git commit -m "$MSG"', 'git commit -m "$(cat msg)"',
                        "git commit -m \"$(cat <<'EOF'\nfeat: x\nEOF\n)\""):
            with self.subTest(command=command):
                self.assertEqual(count_bash(negated, command), 0)
                self.assertEqual(count_bash({"git": {"subcommand": "commit",
                                                "message_regex": ""}}, command), 0)

    def test_a_readable_call_beside_an_unreadable_one_still_decides(self):
        self.assertEqual(count_bash(self.WHEN, 'git commit -m "$MSG" && git commit -m wip'), 1)

if __name__ == "__main__":
    unittest.main()
