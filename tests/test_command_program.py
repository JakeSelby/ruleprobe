# SPDX-License-Identifier: MIT
"""The `command` matcher's `program` and `first_operand`: the first word by basename, past
leading assignments, and the first operand past flags, each matched whole.

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


class ProgramTests(unittest.TestCase):
    def test_the_basename_past_assignments_is_matched_whole(self):
        when = {"command": {"program": r"pytest"}}
        for command in ("pytest", "/usr/local/bin/pytest -x", "CI=1 A=b pytest",
                        "cd a && .venv/bin/pytest"):
            with self.subTest(command=command):
                self.assertEqual(count(when, command), 1)
        for command in ("pytest-watch", "echo pytest", "CI=1", "cat bin/pytest"):
            with self.subTest(command=command):
                self.assertEqual(count(when, command), 0)

    def test_the_first_operand_skips_flags_and_is_matched_whole(self):
        when = {"command": {"program": r"pip[0-9.]*", "first_operand": r"install"}}
        for command in ("pip install x", "pip3.12 -q install x", "pip --user install x"):
            with self.subTest(command=command):
                self.assertEqual(count(when, command), 1)
        for command in ("pip uninstall x", "pip", "pip -q", "pip show install"):
            with self.subTest(command=command):
                self.assertEqual(count(when, command), 0)

    def test_both_hold_of_one_segment(self):
        when = {"command": {"program": r"pip", "first_operand": r"install"}}
        self.assertEqual(count(when, "pip list; npm install"), 0)

    def test_over_a_command_the_parse_skipped_it_is_undecided(self):
        negated = {"tool": "Bash", "not": {"command": {"program": r"pytest"}}}
        self.assertEqual(count(negated, "echo 'unterminated"), 0)
        self.assertEqual(count(negated, "ls"), 1)

    def test_a_bad_pattern_is_a_spec_error(self):
        for key in ("program", "first_operand"):
            with self.subTest(key=key), self.assertRaises(DeclarativeError):
                compile_detector({"id": "t/x", "rule": "t", "event": "tool_use",
                                  "when": {"command": {key: "("}}})


if __name__ == "__main__":
    unittest.main()
