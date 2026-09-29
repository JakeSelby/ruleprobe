# SPDX-License-Identifier: MIT
"""The command line, over the fixture transcripts.

The home directory is an empty temporary one for the whole module, so a run with no `--rules`
finds no rule file of the machine's own, and the discovery tests build a synthetic home.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from ruleprobe import contract_data
from ruleprobe.cli import main
from test_envelope import no_network_no_writes
from test_readers import FIXTURES

_HOME = mock.patch.dict(os.environ)


def setUpModule():
    home = tempfile.mkdtemp(prefix="ruleprobe-home-")
    _HOME.start()
    os.environ.update({"HOME": home, "USERPROFILE": home,
                       "XDG_CONFIG_HOME": os.path.join(home, ".config")})


def tearDownModule():
    home = os.environ["HOME"]
    _HOME.stop()
    shutil.rmtree(home, True)


def run_cli(*argv):
    out = io.StringIO()
    code = main(list(argv), out=out)
    return code, out.getvalue()


class ReportCommandTests(unittest.TestCase):
    def test_the_default_grouping_is_by_detector(self):
        code, text = run_cli("report", "--root", FIXTURES, "--no-config")
        self.assertEqual(code, 0)
        self.assertIn("detector", text.split("\n")[0])
        self.assertIn("verification/no-verify", text)
        self.assertIn("transcript-hygiene/unfiltered-find", text)

    def test_by_repo_names_both_repositories(self):
        code, text = run_cli("report", "--root", FIXTURES, "--no-config", "--by", "repo")
        self.assertEqual(code, 0)
        self.assertIn("demo-repo", text)
        self.assertIn("other-repo", text)

    def test_since_narrows_the_window(self):
        _, text = run_cli("report", "--root", FIXTURES, "--since", "2026-09-21", "--by", "repo")
        self.assertIn("other-repo", text)
        self.assertNotIn("demo-repo", text)

    def test_json_prints_the_same_report_as_data_and_the_rows_with_it(self):
        code, text = run_cli("report", "--root", FIXTURES, "--json")
        data = json.loads(text)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(r["repo"] for r in data["rows"]),
                         ["demo-repo", "other-repo"])
        self.assertEqual(data["measured"], 2)
        self.assertEqual([d["of"] for d in data["detectors"]], [2] * len(data["detectors"]))

    def test_json_carries_the_schema_version_on_the_result_and_every_row(self):
        _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--json")
        data = json.loads(text)
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual([r["schema_version"] for r in data["rows"]], [2, 2])

    def test_json_carries_the_effective_fold_map_beside_the_rows(self):
        retired = {"verification/old-no-verify": "verification/no-verify"}
        with mock.patch.dict(contract_data.RENAMED, retired):
            _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--json")
        data = json.loads(text)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["renamed"], retired)

    def test_json_is_byte_identical_across_two_runs(self):
        # Separate processes under different hash seeds, so an order that depends on set or
        # dict hashing shows up as a difference rather than a repeat. It guards hash order
        # only: two runs over one directory walk it the same way.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outputs = []
        for seed in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            done = subprocess.run(
                [sys.executable, "-m", "ruleprobe", "report", "--root", FIXTURES,
                 "--no-config", "--json", "--validity"],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.strip())
            outputs.append(done.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_an_empty_root_says_what_to_do_and_exits_non_zero(self):
        code, text = run_cli("report", "--root", FIXTURES + "/nothing-here")
        self.assertEqual(code, 1)
        self.assertIn("--root", text)

    def test_the_notes_are_tunable_from_the_command_line(self):
        _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--min-sessions", "1",
                          "--frequent-share", "0.1")
        self.assertEqual(note_of(text, "cache-hygiene/compact"), "frequent")

    def test_a_share_under_frequent_share_earns_no_frequent_note(self):
        _, text = run_cli("report", "--root", FIXTURES, "--no-config", "--min-sessions", "1",
                          "--frequent-share", "0.9")
        self.assertEqual(note_of(text, "cache-hygiene/compact"), "")
        self.assertNotIn("frequent", text)


def note_of(text, detector_id):
    """What sits in the note column of `detector_id`'s line, read from the header."""
    lines = text.split("\n")
    start = lines[0].index("note")
    got = [x for x in lines if x.split() and x.split()[0] == detector_id][0]
    return got[start:].split("  ")[0].strip()


ORDER_DETECTOR = """version: 1

detectors:
  - id: fixture/commit-then-push
    rule: fixture
    event: session
    when:
      order:
        first: {git: {subcommand: commit}}
        then: {git: {subcommand: push}}
        within: 3
"""


class ComplianceCommandTests(unittest.TestCase):
    """Over the fixtures, one commit and no push: one opportunity, not followed."""

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        self.detectors = os.path.join(tmp, "detectors.yaml")
        with open(self.detectors, "w") as fh:
            fh.write(ORDER_DETECTOR)
        self.args = ["report", "--root", FIXTURES, "--no-config", "--detectors",
                     self.detectors]

    def test_below_min_opportunities_the_counts_print_and_the_rate_does_not(self):
        _, text = run_cli(*self.args)
        got = [x for x in text.split("\n") if x.startswith("fixture/commit-then-push")][0]
        self.assertEqual(got.split()[5:9], ["1", "0", "0", "-"])
        _, text = run_cli(*(self.args + ["--json"]))
        entry = [d for d in json.loads(text)["detectors"]
                 if d["detector"] == "fixture/commit-then-push"][0]
        self.assertEqual((entry["opportunities"], entry["followed"]), (1, 0))
        self.assertIsNone(entry["compliance_rate"])

    def test_min_opportunities_lowers_the_minimum(self):
        _, text = run_cli(*(self.args + ["--min-opportunities", "1", "--json"]))
        data = json.loads(text)
        self.assertEqual(data["min_opportunities"], 1)
        entry = [d for d in data["detectors"]
                 if d["detector"] == "fixture/commit-then-push"][0]
        self.assertEqual(entry["compliance_rate"], 0.0)

    def test_by_stance_json_is_byte_identical_across_two_runs(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outputs = []
        for seed in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            done = subprocess.run(
                [sys.executable, "-m", "ruleprobe"] + self.args
                + ["--stance", "commits=on", "--by", "stance", "--json"],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            outputs.append(done.stdout)
        self.assertEqual(outputs[0], outputs[1])
        group = json.loads(outputs[0])["groups"][0]
        self.assertEqual(group["key"], "commits=on")
        self.assertEqual(group["compliance"]["fixture/commit-then-push"]["undecided"], 0)


def transcript_line(cwd, stamp, message, kind="assistant"):
    return json.dumps({"type": kind, "timestamp": stamp, "sessionId": "sess-found",
                       "cwd": cwd, "message": message}) + "\n"


class NoRulesFlagTests(unittest.TestCase):
    """`report` with no flags finds the rule files in a synthetic home: a global file, and
    the project file at the working directory the one transcript recorded."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, self.base, True)
        self.home = os.path.join(self.base, "home")
        project = os.path.join(self.home, "work", "project")
        self.write(os.path.join(project, "CLAUDE.md"),
                   "# Git\n\nNever force-push to main.\n")
        self.write(os.path.join(project, "AGENTS.md"), "# Codex only\n\nUse uv, not pip.\n")
        self.write(os.path.join(self.home, ".claude", "CLAUDE.md"),
                   "# Style\n\nKeep functions short.\n\n"
                   "# Tests\n\nRun the tests before finishing unless it is late.\n")
        push = {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                "input": {"command": "git push --force origin main"}}
        self.write(os.path.join(self.home, ".claude", "projects", "-work-project",
                                "sess-found.jsonl"),
                   transcript_line(project, "2026-09-20T10:00:00.000Z",
                                   {"role": "user", "content": "ship it"}, kind="user")
                   + transcript_line(project, "2026-09-20T10:00:05.000Z",
                                     {"id": "msg_1", "model": "claude-opus-5",
                                      "content": [push]}))
        patched = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home,
                                               "XDG_CONFIG_HOME": os.path.join(self.home,
                                                                               ".config")})
        patched.start()
        self.addCleanup(patched.stop)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.base)

    def write(self, path, text):
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def snapshot(self):
        out = []
        for base, dirs, files in os.walk(self.base):
            dirs.sort()
            for name in sorted(dirs + files):
                path = os.path.join(base, name)
                out.append((path, os.stat(path).st_mtime_ns))
        return out

    def test_with_no_flags_the_project_and_global_rules_are_read(self):
        _code, text = run_cli("report")
        self.assertIn("~/work/project/CLAUDE.md#git", text)
        self.assertIn("~/.claude/CLAUDE.md#style", text)
        self.assertNotIn("AGENTS.md", text)

    def test_a_blocked_section_names_its_nearest_entry_and_the_word(self):
        _code, text = run_cli("report")
        line = [x for x in text.split("\n") if "#tests" in x][0]
        self.assertIn("unmeasured", line)
        self.assertIn("(unless), nearest testing/test-after-change", line)

    def test_a_found_run_says_once_that_the_rule_text_is_today_s(self):
        _code, text = run_cli("report")
        self.assertEqual(text.count("the rule text is today's, not the text in force when an "
                                    "older session ran"), 1)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _code, data = run_cli("report", "--json")
        self.assertEqual(err.getvalue().count("the rule text is today's"), 1)
        self.assertEqual(json.loads(data)["coverage"]["measured"], 1)

    def test_the_bindable_rule_is_measured_inside_sixty_seconds(self):
        started = time.monotonic()
        code, text = run_cli("report")
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0)
        self.assertLess(elapsed, 60)
        line = [x for x in text.split("\n") if "#git" in x][0]
        self.assertEqual(line.split()[:2], ["measured", "~/work/project/CLAUDE.md#git"])
        self.assertIn("catalog-bound, git-safety/force-push-default", line)
        row = [x for x in text.split("\n") if x.startswith("git-safety/force-push-default")]
        self.assertEqual(row[0].split()[1:3], ["1", "1"])

    def test_a_found_run_writes_nothing(self):
        before = self.snapshot()
        with no_network_no_writes() as attempts, \
                contextlib.redirect_stderr(io.StringIO()):
            code, _text = run_cli("report")
            json_code, _data = run_cli("report", "--json")
        self.assertEqual((code, json_code, attempts), (0, 0, []))
        self.assertEqual(self.snapshot(), before)

    def test_rules_or_no_config_turns_finding_off(self):
        rules = os.path.join(self.base, "rules")
        self.write(os.path.join(rules, "git.md"), "# Git\n\nUse uv, not pip.\n")
        _code, named = run_cli("report", "--rules", rules)
        self.assertIn("git.md#git", named)
        self.assertNotIn("today's", named)
        self.assertNotIn("~/work/project", named)
        _code, bare = run_cli("report", "--no-config")
        self.assertNotIn("CLAUDE.md", bare)
        self.assertNotIn("today's", bare)


class OtherCommandTests(unittest.TestCase):
    def test_detectors_lists_the_shipped_six_and_the_catalog(self):
        code, text = run_cli("detectors", "--no-config")
        self.assertEqual(code, 0)
        self.assertEqual(len([x for x in text.strip().split("\n") if x]), 11)
        self.assertIn("secrets/secret-in-write", text)

    def test_no_command_prints_the_help_and_exits_non_zero(self):
        code, text = run_cli()
        self.assertEqual(code, 1)
        self.assertIn("usage: ruleprobe", text)


if __name__ == "__main__":
    unittest.main()
