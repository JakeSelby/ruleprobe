# SPDX-License-Identifier: MIT
"""Every matcher, one case that hits and one that does not, and every way a spec can be
wrong.

A matcher is compiled and run through `run()` rather than called directly, so what these
assert is what a report would count.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import FAKE_KEY, bash, compact, prompt, say, tool_use
from ruleprobe import Registry, run
from ruleprobe.declarative import DeclarativeError, parse_with_lines
from ruleprobe.matchers import compile_detector

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

    def test_an_empty_session_is_still_an_absence(self):
        when = {"absent": {"of": {"tool": "Write"}}}
        self.assertEqual(count(when, [], event="session"), 1)


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


if __name__ == "__main__":
    unittest.main()
