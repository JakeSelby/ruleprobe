# SPDX-License-Identifier: MIT
"""`verification/no-verify` counts a `core.hooksPath` override only when it turns hooks off.

Pointing the hooks path at a tracked directory such as `.githooks` is how a repository turns
its own hooks on, so those commits ran every hook. Each case runs through the shipped Python
detector, its declarative twin and the catalog entry that restates it, which have to agree.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import bash
from ruleprobe import DEFAULT, Registry, pipelines, run
from ruleprobe.declarative import DeclarativeError
from ruleprobe.detectors import catalog
from ruleprobe.matchers import compile_detector
from ruleprobe.shell import git_config
from test_equivalence import declarative_registry
from test_matchers import count

DID = "verification/no-verify"

FIRES = [
    "git -c core.hooksPath=/dev/null commit -m 'feat(x): y'",
    "git -c core.hooksPath= commit -m 'feat(x): y'",
    "git -c 'core.hooksPath=/dev/null' commit -m 'feat(x): y'",
    'git -c "core.hooksPath=" commit -m x',
    "git -c core.hookspath=/dev/null commit -m x",
    "git -c CORE.HOOKSPATH= push origin feature",
    "git -C repo -c user.name=a -c core.hooksPath=/dev/null commit -m x",
    "git -c core.hooksPath=/dev/null push origin feature",
    "git --git-dir .git --work-tree . -c core.hooksPath=/dev/null commit -m x",
    "git -c core.hooksPath=.githooks -c core.hooksPath= commit -m x",
]

SKIPS = [
    # The regression: the repository's own hooks turned on, not off.
    "git -c core.hooksPath=.githooks commit -m 'feat(x): y'",
    "git -c core.hooksPath=.githooks push origin feature",
    "git -c 'core.hooksPath=tools/hooks' commit -m x",
    "git -c core.hooksPath=/dev/null/hooks commit -m x",
    "git -c core.hooksPathX= commit -m x",
    # Git keeps the last value of a key, and the value is matched exactly.
    "git -c core.hooksPath=/dev/null -c core.hooksPath=.githooks commit -m x",
    "git -c core.hooksPath=/dev/null -c CORE.HOOKSPATH=.githooks commit -m x",
    "git -c core.hooksPath=/DEV/NULL commit -m x",
    # Settings the parse does not read: stated under-counts.
    "git --config-env=core.hooksPath=EMPTY commit -m x",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0= git commit -m x",
    # The override on a subcommand that runs no commit hooks, and one named in a message.
    "git -c core.hooksPath=/dev/null status",
    "git commit -m 'core.hooksPath=/dev/null'",
    "rg 'core.hooksPath=' docs/",
]


class HooksPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.declarative = declarative_registry()
        entry = next(e for e in catalog.ENTRIES if e["detector"]["id"] == DID)
        cls.catalog = Registry([compile_detector(entry["detector"], "<catalog>")])

    def check(self, command, expected):
        events = [bash(command)]
        python = run(events, registry=DEFAULT, strict=True).get(DID, [])
        self.assertEqual(len(python), expected)
        for registry in (self.declarative, self.catalog):
            self.assertEqual(list(run(events, registry=registry, strict=True).get(DID, [])),
                             list(python))

    def test_an_override_that_turns_hooks_off_fires(self):
        for command in FIRES:
            with self.subTest(command=command):
                self.check(command, 1)

    def test_an_override_that_points_hooks_elsewhere_does_not(self):
        for command in SKIPS:
            with self.subTest(command=command):
                self.check(command, 0)

    def test_the_flag_and_the_assignment_still_fire_beside_a_tracked_hooks_path(self):
        self.check("git -c core.hooksPath=.githooks commit --no-verify -m x", 1)
        self.check("SKIP=ruff git -c core.hooksPath=.githooks commit -m x", 1)
        self.check("git -c core.hooksPath=.githooks commit -n -m x", 1)
        self.check("PRE_COMMIT_ALLOW_NO_CONFIG=1 git -c core.hooksPath=.githooks commit -m x",
                   1)


class GitConfigTests(unittest.TestCase):
    def values(self, command):
        return git_config(pipelines(command)[0][0])

    def test_every_config_value_before_the_subcommand(self):
        self.assertEqual(self.values("git -C repo -c a.b=1 -c c.d= commit -m x"),
                         ["a.b=1", "c.d="])

    def test_the_last_value_of_a_key_wins_and_keys_ignore_case(self):
        self.assertEqual(self.values("git -c a.b=1 -c c.d=2 -c A.B=3 commit"),
                         ["c.d=2", "A.B=3"])

    def test_the_global_options_are_stepped_over_with_their_values(self):
        self.assertEqual(self.values("git --git-dir .git --work-tree . --namespace n "
                                     "--no-pager -c a.b=1 commit"), ["a.b=1"])

    def test_nothing_after_the_subcommand_or_without_a_value(self):
        self.assertEqual(self.values("git commit -c a.b=1"), [])
        self.assertEqual(self.values("git -c"), [])
        self.assertEqual(self.values("FOO=1 git -c a.b=1 log"), ["a.b=1"])

    def test_a_segment_that_is_not_git_gives_nothing(self):
        self.assertEqual(self.values("echo -c a.b=1"), [])
        self.assertEqual(self.values("FOO=1"), [])


class ConfigRegexKeyTests(unittest.TestCase):
    def matches(self, when, command):
        return count(when, [bash(command)]) == 1

    def test_config_regex_reads_each_value_before_the_subcommand(self):
        when = {"git": {"subcommand": ["commit"], "config_regex": "^core\\.hooksPath=$"}}
        self.assertTrue(self.matches(when, "git -c core.hooksPath= commit -m x"))
        self.assertFalse(self.matches(when, "git -c core.hooksPath=.githooks commit -m x"))
        self.assertFalse(self.matches(when, "git commit -m core.hooksPath="))
        self.assertFalse(self.matches(when, "git -c core.hooksPath= log"))

    def test_config_regex_and_args_any_must_both_hold(self):
        when = {"git": {"subcommand": ["commit"], "config_regex": "^a\\.b=",
                        "args_any": ["--amend"]}}
        self.assertTrue(self.matches(when, "git -c a.b=1 commit --amend"))
        self.assertFalse(self.matches(when, "git -c a.b=1 commit -m x"))
        self.assertFalse(self.matches(when, "git commit --amend"))

    def test_an_unreadable_value_is_undecided(self):
        negated = {"tool": "Bash", "not": {"git": {"subcommand": ["commit"],
                                                   "config_regex": "^core\\.hooksPath=$"}}}
        self.assertEqual(count(negated, [bash('git -c core.hooksPath="$X" commit -m x')]), 0)
        self.assertEqual(count(negated, [bash("git -c core.hooksPath=$(pwd) commit -m x")]), 0)
        self.assertEqual(count(negated, [bash("git -c core.hooksPath=.githooks commit -m x")]),
                         1)

    def test_a_bad_pattern_is_a_spec_error(self):
        with self.assertRaises(DeclarativeError):
            compile_detector({"id": "t/x", "rule": "t", "event": "tool_use",
                              "when": {"git": {"subcommand": ["commit"], "config_regex": "("}}},
                             "<test>")


if __name__ == "__main__":
    unittest.main()
