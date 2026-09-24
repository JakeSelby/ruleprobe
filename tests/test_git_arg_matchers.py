# SPDX-License-Identifier: MIT
"""The `git` matcher's `arg_regex` and `message_regex`: a regular expression read against one
parsed argument, or against the call's first message, never against the raw command.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import bash
from ruleprobe import Registry, run
from ruleprobe.declarative import DeclarativeError
from ruleprobe.matchers import compile_detector


def count(when, command):
    detector = compile_detector({"id": "t/x", "rule": "t", "event": "tool_use", "when": when},
                                "<test>")
    return len(run([bash(command)], registry=Registry([detector]), strict=True).get("t/x", []))


class ArgRegexTests(unittest.TestCase):
    WHEN = {"git": {"subcommand": "add", "arg_regex": r"^(?:[^/]*/)*\.env\Z"}}

    def test_an_argument_matching_the_pattern_hits(self):
        self.assertEqual(count(self.WHEN, "git add src config/.env"), 1)
        self.assertEqual(count(self.WHEN, "git -C app add -- \".env\""), 1)

    def test_the_pattern_reads_one_argument_at_a_time(self):
        spanning = {"git": {"subcommand": "add", "arg_regex": r"src \.env"}}
        self.assertEqual(count(spanning, "git add src .env"), 0)
        self.assertEqual(count(spanning, "git add 'src .env'"), 1)

    def test_text_in_another_segment_or_before_the_subcommand_is_not_an_argument(self):
        self.assertEqual(count(self.WHEN, "git add src; echo .env"), 0)
        self.assertEqual(count(self.WHEN, "git -c core.x=.env add src"), 0)
        self.assertEqual(count(self.WHEN, "git status .env"), 0)

    def test_a_list_is_alternatives(self):
        when = {"git": {"subcommand": "add", "arg_regex": [r"\.key\Z", r"\.env\Z"]}}
        self.assertEqual(count(when, "git add a.key"), 1)
        self.assertEqual(count(when, "git add .env"), 1)
        self.assertEqual(count(when, "git add a.txt"), 0)

    def test_a_bad_pattern_is_a_spec_error(self):
        with self.assertRaises(DeclarativeError):
            compile_detector({"id": "t/x", "rule": "t", "event": "tool_use",
                              "when": {"git": {"subcommand": "add", "arg_regex": "("}}})


class MessageRegexTests(unittest.TestCase):
    WHEN = {"git": {"subcommand": "commit", "message_regex": r"^wip"}}

    def test_every_form_of_the_first_message_is_read(self):
        for command in ("git commit -m wip", "git commit --message wip",
                        "git commit --message=wip", "git commit -mwip", "git commit -am wip",
                        "git commit -sm wip", "git commit -asm wip",
                        "git commit -m wip -m 'feat: x'"):
            with self.subTest(command=command):
                self.assertEqual(count(self.WHEN, command), 1)

    def test_every_valueless_flag_may_lead_the_m_and_text_may_follow_it(self):
        for flag in "aeinopqsvz":
            with self.subTest(flag=flag):
                self.assertEqual(count(self.WHEN, "git commit -%sm wip" % flag), 1)
        self.assertEqual(count(self.WHEN, "git commit -amwip"), 1)
        self.assertEqual(count(self.WHEN, "git commit -amfeat"), 0)
        self.assertEqual(count(self.WHEN, "git commit -Fm wip"), 0)

    def test_a_heredoc_marker_inside_a_message_is_unreadable(self):
        command = "git commit -m \"wip $(cat <<'EOF'\nbody\nEOF\n)\""
        self.assertEqual(count(self.WHEN, command), 0)

    def test_a_single_quoted_dollar_is_an_unread_message(self):
        # A stated under-count: the parse keeps no quoting, so `$` is unreadable anywhere.
        self.assertEqual(count(self.WHEN, "git commit -m 'wip costs $5'"), 0)

    def test_a_later_message_or_a_quoted_flag_is_not_the_subject(self):
        for command in ("git commit -m 'feat: x' -m wip", "git commit --author='A -m wip'",
                        "git commit --author='A' -m 'feat: -m wip'",
                        "git commit -- -m wip", "git commit -F msg.txt",
                        "git commit -Cm wip", "git commit -m"):
            with self.subTest(command=command):
                self.assertEqual(count(self.WHEN, command), 0)

    def test_an_unreadable_message_is_undecided_so_a_negation_never_counts_it(self):
        negated = {"git": {"subcommand": "commit"},
                   "not": {"git": {"subcommand": "commit", "message_regex": r"^feat"}}}
        self.assertEqual(count(negated, "git commit -m 'fix: x'"), 1)
        for command in ('git commit -m "$MSG"', 'git commit -m "$(cat msg)"',
                        "git commit -m \"$(cat <<'EOF'\nfeat: x\nEOF\n)\""):
            with self.subTest(command=command):
                self.assertEqual(count(negated, command), 0)
                self.assertEqual(count({"git": {"subcommand": "commit",
                                                "message_regex": ""}}, command), 0)

    def test_a_readable_call_beside_an_unreadable_one_still_decides(self):
        self.assertEqual(count(self.WHEN, 'git commit -m "$MSG" && git commit -m wip'), 1)


if __name__ == "__main__":
    unittest.main()
