# SPDX-License-Identifier: MIT
"""The shipped catalog: its entries, how a section rule binds one, and how it loads.

A section rule that no front matter binds is matched against every catalog entry's anchored
pattern and binds the one that matches; none or several leave it unmeasured. The catalog's
detectors join a bundle's registry after the shipped ones and before a user's, and never
`DEFAULT`. The module is literals only, so it loads from a zip with no file read.

Run: python3 -m unittest discover -s tests
"""
import inspect
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

from corpus import bash, say, tool_result, tool_use
from ruleprobe import DEFAULT, Registry, analyse, contract_data, run
from ruleprobe.cli import main
from ruleprobe.declarative import load
from ruleprobe.detectors import catalog
from ruleprobe.matchers import Examples
from ruleprobe.rules import (Bundle, RuleEntry, _CATALOG, _catalog_matches,
                             catalog_detectors, load_bundle)
from ruleprobe.registry import Detector
from ruleprobe.validity import DEFAULT_FLOOR, score_corpus, score_examples
from test_contract_data import non_literal
from test_readers import FIXTURES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_RULES = os.path.join(FIXTURES, "catalog")
IDS = [entry["detector"]["id"] for entry in catalog.ENTRIES]
#: The fixture's sections, in catalog order: section id and the entry it states.
FIXTURE = [("team/CLAUDE.md#testing", "testing/test-after-change"),
           ("team/CLAUDE.md#hooks", "verification/no-verify"),
           ("team/CLAUDE.md#pushing", "git-safety/force-push-default"),
           ("team/CLAUDE.md#dependencies", "package-manager/pip-install"),
           ("team/CLAUDE.md#reading-files", "transcript-hygiene/whole-file-cat"),
           ("team/CLAUDE.md#commits", "commits/non-conventional-subject"),
           ("team/CLAUDE.md#secrets", "secrets/secret-file-add")]


def matched(text):
    """The catalog ids a one-paragraph rule under a plain heading matches."""
    return [d.id for d in _catalog_matches("Rule", [text])]


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, relative, text):
        path = os.path.join(self.dir, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def rules(self, text):
        self.write("rules/CLAUDE.md", text)
        return load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)


class EntryTests(unittest.TestCase):
    def test_the_catalog_holds_six_to_eight_shapes_each_with_three_keys(self):
        self.assertTrue(6 <= len(catalog.ENTRIES) <= 8)
        for entry in catalog.ENTRIES:
            self.assertEqual(sorted(entry), ["detector", "pattern", "shape"])

    def test_every_pattern_is_anchored(self):
        for entry in catalog.ENTRIES:
            with self.subTest(entry=entry["shape"]):
                self.assertTrue(entry["pattern"].startswith("^"))

    def test_every_id_is_unique_and_every_rule_is_slash_free(self):
        self.assertEqual(len(set(IDS)), len(IDS))
        for _pattern, detector in _CATALOG:
            self.assertNotIn("/", detector.rule)

    def test_every_entry_carries_examples_with_a_near_miss_and_clears_the_floor(self):
        scores = score_examples([detector for _pattern, detector in _CATALOG])
        for did in IDS:
            with self.subTest(detector=did):
                score = scores[did]
                self.assertTrue(score.positives and score.negatives)
                self.assertGreaterEqual(score.precision, DEFAULT_FLOOR)
                self.assertGreaterEqual(score.recall, DEFAULT_FLOOR)

    def test_every_catalog_id_is_on_the_shipped_id_list(self):
        self.assertEqual([did for did in IDS if did not in contract_data.SHIPPED_IDS], [])

    def test_an_entry_restating_a_shipped_detector_is_its_declarative_twin(self):
        doc, _lines = load(os.path.join(ROOT, "ruleprobe", "detectors", "common.yaml"))
        twins = dict((d["id"], d["when"]) for d in doc["detectors"])
        restated = [e["detector"] for e in catalog.ENTRIES if e["detector"]["id"] in DEFAULT]
        self.assertEqual(sorted(d["id"] for d in restated),
                         ["transcript-hygiene/whole-file-cat", "verification/no-verify"])
        for spec in restated:
            with self.subTest(detector=spec["id"]):
                self.assertEqual(spec["when"], twins[spec["id"]])


class DetectorTests(unittest.TestCase):
    """Cases beyond each entry's own examples, one near-miss beside each."""

    def hits(self, did, events):
        return run(events, registry=Registry([dict((d.id, d) for _p, d in _CATALOG)[did]]),
                   strict=True).get(did, [])

    def test_a_commit_message_from_a_heredoc_is_not_read(self):
        heredoc = "git commit -m \"$(cat <<'EOF'\nupdate things\nEOF\n)\""
        self.assertEqual(self.hits("commits/non-conventional-subject", [bash(heredoc)]), [])
        self.assertTrue(self.hits("commits/non-conventional-subject",
                                  [bash("git commit -m 'update things'")]))

    def test_a_merge_subject_is_passed_over(self):
        self.assertEqual(self.hits("commits/non-conventional-subject",
                                   [bash("git commit -m \"Merge branch 'feature'\"")]), [])

    def test_a_force_with_lease_to_main_is_a_force_push(self):
        self.assertTrue(self.hits("git-safety/force-push-default",
                                  [bash("git push --force-with-lease origin main")]))
        self.assertEqual(self.hits("git-safety/force-push-default",
                                   [bash("git push --force-with-lease origin maintenance")]), [])

    def test_a_local_env_file_is_secret_shaped_and_envrc_is_not(self):
        self.assertTrue(self.hits("secrets/secret-file-add", [bash("git add .env.local")]))
        self.assertEqual(self.hits("secrets/secret-file-add", [bash("git add .envrc")]), [])

    def test_a_change_opens_an_opportunity_that_a_later_test_run_follows(self):
        detector = dict((d.id, d) for _p, d in _CATALOG)["testing/test-after-change"]
        edit = tool_use("Edit", {"file_path": "src/app.py"}, turn=1, id="e1")
        events = [edit, bash("python3 -m pytest", turn=2, id="t1"),
                  tool_use("Write", {"file_path": "src/b.py"}, turn=3, id="e2")]
        self.assertEqual(detector.opportunities(events, analyse(events)),
                         [(1, "e1", True), (3, "e2", False)])
        self.assertEqual(self.hits("testing/test-after-change", [say("Done.")]), [])

    def test_the_common_runners_and_wrappers_are_test_runs(self):
        edit = tool_use("Edit", {"file_path": "src/app.py"}, id="e1")
        for command in ("poetry run pytest", "pipenv run pytest -x", "npx jest",
                        "npm test", "yarn run test", "bun test", "python -m pytest",
                        "mvn test", "./gradlew test", "bundle exec rspec", "go test ./...",
                        "cargo test", "make check", "cd api; make test",
                        "npm test && echo 'a; b' | tee log", "mvn -q test", "CI=1 pytest",
                        "/usr/local/bin/pytest -x", "~/.local/bin/tox -e py39",
                        "node_modules/.bin/vitest run", "python3.12 -m pytest"):
            with self.subTest(command=command):
                self.assertTrue(self.hits("testing/test-after-change",
                                          [edit, bash(command, turn=2, id="t1")]))
        # The last two are stated under-counts: a runner behind `env`, and a build tool
        # option taking a value before the target.
        for command in ("pytest-watch --help", "npm install", "go build ./...",
                        "make lint", "echo pytest", "echo 'x; pytest'", "cat bin/pytest",
                        "python3 pytest_plugin.py", "env CI=1 pytest", "make -C api test"):
            with self.subTest(command=command):
                self.assertEqual(self.hits("testing/test-after-change",
                                           [edit, bash(command, turn=2, id="t1")]), [])

    def test_a_subject_from_a_variable_or_substitution_is_unreadable(self):
        for command in ('git commit -m "$MSG"', 'git commit -m "${msg}"',
                        "git commit -m `cat msg.txt`", 'git commit -m"$MSG"'):
            with self.subTest(command=command):
                self.assertEqual(self.hits("commits/non-conventional-subject",
                                           [bash(command)]), [])
        self.assertTrue(self.hits("commits/non-conventional-subject",
                                  [bash('git commit -m"tidy up"')]))
        self.assertEqual(self.hits("commits/non-conventional-subject",
                                   [bash('git commit -m"fix: tidy up"')]), [])

    def test_each_git_entry_needs_the_call_and_the_shape_in_one_segment(self):
        cases = [("commits/non-conventional-subject",
                  "git commit -m 'feat: x' && echo \"git commit -m wip\"",
                  "git status && git commit -m wip"),
                 ("secrets/secret-file-add", "git add src; echo \"git add .env\"",
                  "echo ok; git add .env"),
                 ("git-safety/force-push-default",
                  "git push origin main && echo \"git push -f origin main\"",
                  "echo ok && git push -f origin main")]
        for did, near, positive in cases:
            with self.subTest(detector=did):
                self.assertEqual(self.hits(did, [bash(near)]), [])
                self.assertTrue(self.hits(did, [bash(positive)]))

    def test_a_push_through_a_global_option_or_a_flag_cluster_is_read(self):
        self.assertTrue(self.hits("git-safety/force-push-default",
                                  [bash("git -C app push -fu origin main")]))
        self.assertEqual(self.hits("git-safety/force-push-default",
                                   [bash("git -C app push -u origin main")]), [])

    def test_certificates_and_test_env_files_are_not_secret_shaped(self):
        for path in (".env.test", ".env.example", "certs/ca.pem", "certs/fullchain.pem"):
            with self.subTest(path=path):
                self.assertEqual(self.hits("secrets/secret-file-add",
                                           [bash("git add " + path)]), [])
        for path in (".env", ".env.production", "certs/privkey.pem", "tls/server-key.pem",
                     "id_rsa"):
            with self.subTest(path=path):
                self.assertTrue(self.hits("secrets/secret-file-add",
                                          [bash("git add " + path)]))

    def test_every_forced_form_of_the_default_branch_is_a_force_push(self):
        for command in ("git push -f origin refs/heads/main",
                        "git push --force origin HEAD:refs/heads/master",
                        "git push origin +refs/heads/main", "git push origin +HEAD:master",
                        "git push -f origin main:main", "git push origin +master:master",
                        "git push --force origin master:refs/heads/master"):
            with self.subTest(command=command):
                self.assertTrue(self.hits("git-safety/force-push-default", [bash(command)]))
        for command in ("git push -f origin feature:main-backup",
                        "git push origin refs/heads/main", "git push origin main:main",
                        "git push -f origin refs/heads/maintenance",
                        "git push origin +feature"):
            with self.subTest(command=command):
                self.assertEqual(self.hits("git-safety/force-push-default",
                                           [bash(command)]), [])

    def test_force_if_includes_alone_is_not_a_force_push(self):
        did = "git-safety/force-push-default"
        self.assertEqual(self.hits(did, [bash("git push --force-if-includes origin main")]), [])
        self.assertTrue(self.hits(did, [bash(
            "git push --force-with-lease --force-if-includes origin main")]))
        self.assertTrue(self.hits(did, [bash("git push --force origin main")]))

    def test_pip_is_read_by_basename_version_and_past_leading_flags(self):
        did = "package-manager/pip-install"
        for command in (".venv/bin/pip install ruff", "pip3.12 install ruff",
                        "pip -q install ruff", "PIP_INDEX_URL=x pip install ruff",
                        "/usr/bin/pip3 install --user ruff"):
            with self.subTest(command=command):
                self.assertTrue(self.hits(did, [bash(command)]))
        for command in ("pip uninstall ruff", "pipx install ruff", "pip download ruff",
                        "uv pip install ruff", "pip-compile requirements.in"):
            with self.subTest(command=command):
                self.assertEqual(self.hits(did, [bash(command)]), [])

    def test_a_codex_apply_patch_opens_an_opportunity(self):
        rollout = os.path.join(tempfile.mkdtemp(prefix="ruleprobe-"), "rollout-x.jsonl")
        self.addCleanup(shutil.rmtree, os.path.dirname(rollout), True)
        lines = [
            {"type": "session_meta", "payload": {"id": "rollout-x", "cwd": "/tmp/r"}},
            {"type": "turn_context", "payload": {"model": "gpt-5-codex"}},
            {"type": "response_item", "payload": {
                "type": "custom_tool_call", "call_id": "c1", "name": "apply_patch",
                "input": "*** Begin Patch\n*** Update File: a.py\n*** End Patch\n"}},
            {"type": "response_item", "payload": {
                "type": "custom_tool_call_output", "call_id": "c1", "output": "Done"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "c2", "name": "exec_command",
                "arguments": json.dumps({"cmd": "pytest -q"})}},
            {"type": "response_item", "payload": {
                "type": "custom_tool_call", "call_id": "c3", "name": "apply_patch",
                "input": "*** Begin Patch\n*** Update File: b.py\n*** End Patch\n"}}]
        with open(rollout, "w") as handle:
            handle.write("\n".join(json.dumps(line) for line in lines) + "\n")
        from ruleprobe.readers import codex
        events = codex.read(rollout).events
        detector = dict((d.id, d) for _p, d in _CATALOG)["testing/test-after-change"]
        self.assertEqual(detector.opportunities(events, analyse(events)),
                         [(1, "c1", True), (1, "c3", False)])

    def test_a_public_key_pem_is_not_secret_shaped(self):
        for path in ("certs/public-key.pem", "keys/pubkey.pem", "tls/key.pub.pem"):
            with self.subTest(path=path):
                self.assertEqual(self.hits("secrets/secret-file-add",
                                           [bash("git add " + path)]), [])
        self.assertTrue(self.hits("secrets/secret-file-add",
                                  [bash("git add certs/private-key.pem")]))

    def test_the_subject_is_read_from_the_parsed_arguments(self):
        did = "commits/non-conventional-subject"
        self.assertEqual(self.hits(did, [bash("git commit --author=\"A -m B\" -m 'feat: x'")]),
                         [])
        self.assertTrue(self.hits(did, [bash("git commit --author=\"A -m B\" -m 'fixed'")]))
        self.assertTrue(self.hits(did, [bash("git commit -sm 'fixed it'")]))
        self.assertTrue(self.hits(did, [bash("git commit -asm 'fixed it'")]))
        self.assertEqual(self.hits(did, [bash("git commit -sm 'fix: it'")]), [])
        for subject in ("fixup! feat: x", "squash! fix: y", "amend! docs: z"):
            with self.subTest(subject=subject):
                self.assertEqual(self.hits(did, [bash("git commit -m '%s'" % subject)]), [])
        self.assertTrue(self.hits(did, [bash("git commit -m 'fixup the parser'")]))
        self.assertTrue(self.hits(did, [bash("git commit -pm 'fixed it'")]))
        self.assertTrue(self.hits(did, [bash("git commit -amfixed")]))
        # A stated under-count: any word before the colon reads as a type.
        self.assertEqual(self.hits(did, [bash("git commit -m 'WIP: stuff'")]), [])


#: Inputs built to make a backtracking pattern blow up: many separators, long runs of
#: quotes, backslashes, comment and background markers, and near-miss paths and flags.
HOSTILE = ("cd a && " * 2000 + "echo done",
           "cd a && " * 2000 + "git push origin feature",
           "'" * 8000, '"' * 8000, "\\" * 8000, "#" * 8000, "&" * 8000, "; " * 4000,
           "git commit " + "-m " * 4000, "git commit -m " + "a -m " * 3000,
           "git add " + "a/" * 7000 + "key" * 300, "git add " + "key" * 5000 + ".pe",
           "git push " + "-f " * 4000 + "mainx", "git push " + "+HEAD:" * 2500,
           "run the tests " + "a " * 7000, "never force-push " + "x " * 7000,
           "use uv " + "not " * 3500, "use uv" + " -" * 7000,
           "never commit " + "a " * 7000, "echo \"" + "\\\"" * 4000)


class HostileInputTests(unittest.TestCase):
    """Every catalog pattern and detector stays linear on inputs built to defeat it.

    The limit is generous so a slow shared runner never fails it; the inputs are sized so
    exponential or quadratic behaviour would take far longer - 2,000 segments where 12
    took 9 s on the old prefix, and 10,000 edits among 40,000 events, where the walk per
    edit took 4.3 s at a quarter of that size."""

    LIMIT = 5.0

    def regexes(self, value, found):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("pattern", "regex", "arg_regex", "message_regex"):
                    found.extend([item] if isinstance(item, str) else item)
                else:
                    self.regexes(item, found)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.regexes(item, found)
        return found

    def test_every_catalog_regex_is_fast_on_hostile_text(self):
        patterns = self.regexes(list(catalog.ENTRIES), [])
        self.assertGreaterEqual(len(patterns), len(catalog.ENTRIES) + 2)
        for pattern in patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            for text in HOSTILE:
                started = time.perf_counter()
                compiled.search(text)
                compiled.match(text)
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, self.LIMIT, "%r on %r" % (pattern[:60], text[:40]))

    def test_every_catalog_detector_is_fast_on_hostile_commands(self):
        edits = [tool_use("Edit", {"file_path": "src/app.py"}, turn=1, id="e%d" % i)
                 for i in range(100)]
        self.assertEqual([detector.id for _pattern, detector in _CATALOG], IDS)
        for _pattern, detector in _CATALOG:
            for text in HOSTILE:
                events = edits + [bash(text, turn=2, id="t1")]
                ctx = analyse(events)
                started = time.perf_counter()
                detector.fn(events, ctx)
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, self.LIMIT, "%s on %r" % (detector.id, text[:40]))

    def test_every_catalog_detector_is_linear_in_a_long_session(self):
        events = [tool_use("Edit", {"file_path": "src/app.py"}, turn=1, id="e%d" % i)
                  for i in range(10000)]
        for i in range(15000):
            events.append(bash("cd a && ls -la src", turn=2, id="b%d" % i))
            events.append(tool_result("ok", tool_use_id="b%d" % i, turn=2))
        ctx = analyse(events)
        for _pattern, detector in _CATALOG:
            with self.subTest(detector=detector.id):
                started = time.perf_counter()
                detector.fn(events, ctx)
                if detector.opportunities is not None:
                    detector.opportunities(events, ctx)
                self.assertLess(time.perf_counter() - started, self.LIMIT)

    def test_every_pattern_is_covered_by_the_regex_check(self):
        patterns = self.regexes(list(catalog.ENTRIES), [])
        for entry in catalog.ENTRIES:
            with self.subTest(shape=entry["shape"]):
                self.assertIn(entry["pattern"], patterns)

    def test_no_pattern_spans_a_clause_with_a_wildcard(self):
        for entry in catalog.ENTRIES:
            with self.subTest(shape=entry["shape"]):
                self.assertNotIn(".*", entry["pattern"])
                self.assertNotIn(".+", entry["pattern"])


class BindingTests(Temp):
    def test_each_fixture_section_binds_its_entry_and_is_catalog_bound(self):
        bundle = load_bundle(rules_dir=CATALOG_RULES, config=False)
        self.assertEqual(bundle.findings, [])
        self.assertEqual([(r.rule, r.state, r.detectors, r.source) for r in bundle.rules],
                         [(rule, "measured", [did], "catalog") for rule, did in FIXTURE])

    def test_report_prints_each_fixture_section_measured_and_catalog_bound(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            code = main(["report", "--root", FIXTURES, "--no-config", "--rules",
                         CATALOG_RULES, "--json"], out=out)
        self.assertEqual(code, 0)
        coverage = json.loads(out.getvalue())["coverage"]
        self.assertEqual((coverage["measured"], coverage["unmeasured"]), (7, 0))
        for rule, did in FIXTURE:
            self.assertRegex(err.getvalue(), r"measured +%s .*: catalog-bound, %s\n"
                             % (re.escape(rule), re.escape(did)))

    def test_a_section_id_with_a_slash_binds_a_detector_whose_rule_has_none(self):
        bundle = load_bundle(rules_dir=CATALOG_RULES, config=False)
        registry = bundle.registry()
        for entry in bundle.rules:
            self.assertIn("/", entry.rule)
            self.assertNotIn("/", registry.get(entry.detectors[0]).rule)

    def test_a_rule_that_matches_no_entry_stays_unmeasured(self):
        bundle = self.rules("# Working style\n\nHonesty over polish.\n")
        self.assertEqual([(r.state, r.detectors, r.reason, r.source) for r in bundle.rules],
                         [("unmeasured", [], "", None)])

    def test_a_rule_that_matches_two_entries_stays_unmeasured_and_names_them(self):
        bundle = self.rules("# Git\n\nNever force-push to main. Use uv, not pip.\n")
        [entry] = bundle.rules
        self.assertEqual((entry.state, entry.detectors, entry.source),
                         ("unmeasured", [], None))
        self.assertEqual(entry.reason, "matches 2 catalog entries: "
                                       "git-safety/force-push-default, "
                                       "package-manager/pip-install")
        self.assertEqual(bundle.registry().ids(), DEFAULT.ids())

    def test_a_pattern_matches_at_the_start_of_a_sentence_only(self):
        self.assertEqual(matched("We run the tests before lunch."), [])
        self.assertEqual(matched("Lunch is late. Run the tests before you push."),
                         ["testing/test-after-change"])

    def test_the_heading_is_read_as_a_sentence(self):
        self.assertEqual([d.id for d in _catalog_matches("Never force-push main", [])],
                         ["git-safety/force-push-default"])

    def test_markup_list_markers_and_a_typographic_apostrophe_are_read_through(self):
        self.assertEqual(matched("- **Don’t** `cat` an *entire* file."),
                         ["transcript-hygiene/whole-file-cat"])
        self.assertEqual(matched("1. Use [uv](https://example.test/uv), never pip."),
                         ["package-manager/pip-install"])

    def test_a_near_miss_of_each_shape_binds_nothing(self):
        for text in ("Run the tests.", "Never skip lunch.", "Never push to main.",
                     "Use uv for scripts.", "Do not read a file twice.",
                     "Write short commit subjects.", "Never commit to main directly."):
            with self.subTest(text=text):
                self.assertEqual(matched(text), [])

    def test_a_file_bound_in_its_front_matter_is_its_own_and_never_catalog_bound(self):
        bundle = self.rules("---\nrule: git\ndetector:\n  id: git/push\n"
                            "  when: {git: {subcommand: push}}\n---\n\n"
                            "# Git\n\nNever force-push to main.\n")
        self.assertEqual([(r.rule, r.state, r.detectors, r.source) for r in bundle.rules],
                         [("git", "measured", ["git/push"], "own")])

    def test_binding_reads_text_and_opens_no_connection(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")):
            bundle = load_bundle(rules_dir=CATALOG_RULES, config=False)
        self.assertEqual(bundle.counts()["measured"], len(FIXTURE))

    def test_a_load_into_memory_or_an_add_to_a_prompt_binds_nothing(self):
        self.assertEqual(matched("Never load an entire file into memory; stream it."), [])
        self.assertEqual(matched("Never add credentials to a prompt."), [])
        self.assertEqual(matched("Never read a whole file into your context."),
                         ["transcript-hygiene/whole-file-cat"])
        self.assertEqual(matched("Never git add credentials."), ["secrets/secret-file-add"])

    def test_a_file_with_no_heading_binds_as_one_rule(self):
        self.write("rules/testing.md", "Run the tests before finishing.\n")
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([(r.rule, r.state, r.detectors, r.source) for r in bundle.rules],
                         [("testing", "measured", ["testing/test-after-change"], "catalog")])

    def test_a_headed_file_with_no_rule_section_binds_by_its_text(self):
        self.write("rules/x.md", "Never force-push to main.\n\n# Notes\n")
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([(r.rule, r.state, r.source) for r in bundle.rules],
                         [("x", "measured", "catalog")])

    def test_a_task_list_marker_is_read_through(self):
        bundle = self.rules("# Git\n\n- [ ] Never force-push to main\n- [x] Keep it small\n")
        self.assertEqual(bundle.rules[0].detectors, ["git-safety/force-push-default"])

    def test_a_catalog_id_the_fold_map_retires_binds_nothing(self):
        with mock.patch.dict(contract_data.RENAMED,
                             {"git-safety/force-push-default": "git-safety/renamed"}):
            bundle = self.rules("# Git\n\nNever force-push to main.\n")
            self.assertEqual((bundle.rules[0].state, bundle.rules[0].detectors),
                             ("unmeasured", []))
            self.assertNotIn("git-safety/force-push-default",
                             Bundle().registry(whole_catalog=True))

    def test_a_sentence_wrapped_across_lines_binds(self):
        bundle = self.rules("# Git\n\nNever force-push\nto main, whatever the reason.\n")
        self.assertEqual(bundle.rules[0].detectors, ["git-safety/force-push-default"])

    def test_unpunctuated_list_items_are_sentences_of_their_own(self):
        listed = self.rules("# Git\n\n- Keep commits small\n- Never force-push to main\n")
        self.assertEqual(listed.rules[0].detectors, ["git-safety/force-push-default"])
        joined = self.rules("# Git\n\nKeep commits small\nNever force-push to main\n")
        self.assertEqual(joined.rules[0].detectors, [])

    def test_a_rule_inside_a_fence_quote_table_or_comment_binds_nothing(self):
        for block in ("```\nNever force-push to main.\n```\n",
                      "> Never force-push to main.\n",
                      "| Rule |\n| ---- |\n| Never force-push to main. |\n",
                      "<!-- Never force-push to main. -->\n"):
            with self.subTest(block=block):
                bundle = self.rules("# Git\n\nSee below.\n\n" + block)
                self.assertEqual((bundle.rules[0].state, bundle.rules[0].detectors),
                                 ("unmeasured", []))

    def test_a_sentence_with_an_exception_or_a_permission_binds_nothing(self):
        for text in ("Never force-push except to main.",
                     "Use uv for scripts, not poetry; pip is fine.",
                     "Never force-push to main unless the release lead asks.",
                     "Use uv, not pip, but pip is okay in CI.",
                     "Run the tests before you finish, however small the change."):
            with self.subTest(text=text):
                self.assertEqual(matched(text), [])

    def test_an_exception_in_any_sentence_or_the_heading_unbinds_the_rule(self):
        for text in ("# Pushing\n\nNever force-push to main.\n\n"
                     "Except for release branches, rebase freely.\n",
                     "# Except for release branches\n\nNever force-push to main.\n",
                     "# Pushing\n\nNever force-push to main. Hotfixes excepted.\n",
                     "# Pushing\n\nNever force-push to main without approval.\n",
                     "# Pushing\n\nNever force-push to main when others share it.\n",
                     "# Pushing\n\nNever force-push to main, apart from the first push.\n",
                     "# Pushing\n\nNever force-push to main if CI is red.\n",
                     "# Pushing\n\nNever force-push anything excluding drafts to main.\n"):
            with self.subTest(text=text):
                [entry] = self.rules(text).rules
                self.assertEqual((entry.state, entry.detectors, entry.source),
                                 ("unmeasured", [], None))
                self.assertIn("exception or condition", entry.reason)
        [entry] = self.rules("# Pushing\n\nNever force-push to main. Rebase instead.\n").rules
        self.assertEqual(entry.detectors, ["git-safety/force-push-default"])

    def test_a_double_dash_is_a_clause_break(self):
        self.assertEqual(matched("Never force-push feature branches -- main is protected."), [])
        self.assertEqual(matched("Use uv for scripts -- not pip."), [])

    def test_a_pattern_never_spans_a_clause_break(self):
        for text in ("Never force-push feature branches; main is protected.",
                     "Never force-push feature branches: main is protected.",
                     "Never force-push feature branches - main is protected.",
                     "Never force-push feature branches \u2014 main is protected.",
                     "Run the tests, and commit before lunch.",
                     "Use uv for scripts, and poetry - never pip."):
            with self.subTest(text=text):
                self.assertEqual(matched(text), [])
        for text in ("Never force-push to main.", "Use uv, not pip, for installs.",
                     "Install with uv, never with sudo pip.",
                     "Use uv for scripts, never pip.",
                     "Run the tests before you finish."):
            with self.subTest(text=text):
                self.assertEqual(len(matched(text)), 1)


class RegistryTests(Temp):
    def test_order_is_shipped_then_catalog_then_the_user_s(self):
        path = self.write("detectors.yaml", "- id: house/write\n  when: {tool: Write}\n")
        self.write("rules/CLAUDE.md", "# Pushing\n\nNever force-push to main.\n")
        bundle = load_bundle(paths=[path], rules_dir=os.path.join(self.dir, "rules"),
                             config=False)
        self.assertEqual(bundle.registry().ids(),
                         DEFAULT.ids() + ["git-safety/force-push-default", "house/write"])

    def test_a_user_detector_with_a_catalog_id_wins_and_the_rule_is_its_own(self):
        before = DEFAULT.ids()
        path = self.write("detectors.yaml", "- id: git-safety/force-push-default\n"
                                            "  when: {git: {subcommand: push}}\n")
        self.write("rules/CLAUDE.md", "# Pushing\n\nNever force-push to main.\n")
        bundle = load_bundle(paths=[path], rules_dir=os.path.join(self.dir, "rules"),
                             config=False)
        [entry] = bundle.rules
        self.assertEqual((entry.state, entry.detectors, entry.source),
                         ("measured", ["git-safety/force-push-default"], "own"))
        registry = bundle.registry()
        self.assertIs(registry.get("git-safety/force-push-default"), bundle.detectors[0])
        self.assertTrue(run([bash("git push origin feature")], registry=registry))
        self.assertNotIn(": catalog-bound", bundle.summary(relative_to=self.dir))
        self.assertEqual(DEFAULT.ids(), before)
        self.assertNotIn("git-safety/force-push-default", DEFAULT)

    def test_a_restated_shipped_detector_stays_the_shipped_one(self):
        bundle = self.rules("# Reading\n\nNever cat a whole file.\n")
        self.assertEqual(bundle.rules[0].detectors, ["transcript-hygiene/whole-file-cat"])
        registry = bundle.registry()
        self.assertEqual(registry.ids(), DEFAULT.ids())
        self.assertIs(registry.get("transcript-hygiene/whole-file-cat"),
                      DEFAULT.get("transcript-hygiene/whole-file-cat"))

    def test_nothing_bound_adds_no_catalog_detector_and_default_is_untouched(self):
        before = DEFAULT.ids()
        self.assertEqual(Bundle().registry().ids(), before)
        whole = Bundle().registry(whole_catalog=True)
        self.assertEqual(whole.ids(), before + [did for did in IDS if did not in before])
        self.assertEqual(DEFAULT.ids(), before)

    def test_the_corpus_command_scores_every_catalog_entry(self):
        out = io.StringIO()
        self.assertEqual(main(["corpus", "--no-config", "--json"], out=out), 0)
        scores = json.loads(out.getvalue())["detectors"]
        for did in IDS:
            with self.subTest(detector=did):
                self.assertIn(did, scores)
                self.assertTrue(scores[did]["scored"])

    def test_a_rule_entry_takes_five_fields_and_defaults_its_source(self):
        self.assertIsNone(RuleEntry("r", "r.md", "unmeasured", "", []).source)

    def test_bound_catalog_detectors_lead_the_bundle_s_own(self):
        path = self.write("detectors.yaml", "- id: house/write\n  when: {tool: Write}\n")
        self.write("rules/CLAUDE.md", "# Pushing\n\nNever force-push to main.\n\n"
                                      "# Reading\n\nNever cat a whole file.\n")
        bundle = load_bundle(paths=[path], rules_dir=os.path.join(self.dir, "rules"),
                             config=False)
        self.assertEqual([d.id for d in bundle.detectors],
                         ["git-safety/force-push-default", "house/write"])
        registry = DEFAULT.copy().extend(bundle.detectors)
        self.assertIn("git-safety/force-push-default",
                      run([bash("git push -f origin main")], registry=registry))
        self.assertEqual(bundle.coverage()["catalog"], 2)

    def test_a_base_detector_holding_a_catalog_id_makes_the_rule_own(self):
        base = DEFAULT.copy()
        mine = Detector("git-safety/force-push-default", "git-safety", "bash",
                        lambda events, ctx: [])
        base.add(mine)
        bundle = self.rules("# Git\n\nNever force-push to main.\n")
        registry = bundle.registry(base)
        self.assertIs(registry.get("git-safety/force-push-default"), mine)
        self.assertEqual(bundle.rules[0].source, "own")
        self.assertEqual(bundle.coverage()["catalog"], 0)
        self.assertNotIn("catalog-bound", bundle.summary(relative_to=self.dir))

    def test_detectors_lists_every_catalog_entry_marked_catalog(self):
        out = io.StringIO()
        self.assertEqual(main(["detectors", "--no-config"], out=out), 0)
        lines = dict((line.split()[0], line) for line in out.getvalue().splitlines())
        for did in IDS:
            with self.subTest(detector=did):
                self.assertTrue(lines[did].endswith("catalog"))
        self.assertFalse(lines["secrets/secret-in-write"].endswith("catalog"))

    def test_corpus_scores_a_restating_entry_s_examples_on_the_shipped_row(self):
        out = io.StringIO()
        main(["corpus", "--no-config", "--json"], out=out)
        scores = json.loads(out.getvalue())["detectors"]
        corpus_only = score_corpus(DEFAULT)
        for entry in catalog.ENTRIES:
            did = entry["detector"]["id"]
            if did not in DEFAULT:
                continue
            examples = entry["detector"]["examples"]
            with self.subTest(detector=did):
                self.assertEqual(scores[did]["positives"],
                                 corpus_only[did].positives + len(examples["fire"]))
                self.assertEqual(scores[did]["negatives"],
                                 corpus_only[did].negatives + len(examples["skip"]))

    def test_a_catalog_id_the_base_registry_retires_is_neither_added_nor_bound(self):
        did = "git-safety/force-push-default"
        base = Registry(DEFAULT, renamed={did: "git-safety/push-main"})
        base.add(Detector("git-safety/push-main", "git-safety", "tool_use",
                          lambda events, ctx: []))
        bundle = self.rules("# Git\n\nNever force-push to main.\n")
        self.assertIn(did, [d.id for d in bundle.detectors])
        registry = bundle.registry(base)
        self.assertNotIn(did, registry)
        self.assertNotIn(did, bundle.registry(base, whole_catalog=True))
        self.assertNotIn(did, [d.id for d in catalog_detectors(base.fold_map())])
        [entry] = bundle.rules
        self.assertEqual((entry.state, entry.source, entry.detectors),
                         ("unmeasured", None, []))
        self.assertIn("retired", entry.reason)
        self.assertEqual(bundle.coverage()["catalog"], 0)

    def test_registry_relabels_from_the_loaded_binding_on_every_call(self):
        did = "git-safety/force-push-default"
        plugin = DEFAULT.copy()
        plugin.add(Detector(did, "git-safety", "tool_use", lambda events, ctx: []))
        bundle = self.rules("# Git\n\nNever force-push to main.\n")
        loaded = list(bundle.rules)
        self.assertEqual(loaded[0].source, "catalog")
        self.assertEqual(bundle.coverage()["catalog"], 1)
        self.assertIn("catalog-bound", bundle.summary(relative_to=self.dir))
        bundle.registry(plugin)
        self.assertEqual(bundle.rules[0].source, "own")
        self.assertEqual(bundle.coverage()["catalog"], 0)
        self.assertEqual(loaded[0].source, "catalog")
        bundle.registry()
        self.assertEqual(bundle.rules, loaded)
        self.assertEqual(bundle.coverage()["catalog"], 1)
        bundle.registry(plugin)
        self.assertEqual(bundle.rules[0].source, "own")

    def test_a_catalog_bound_rule_the_registry_does_not_hold_is_unmeasured(self):
        entry = RuleEntry("r", "r.md", "measured", "", ["house/nowhere"], "catalog")
        bundle = Bundle(rules=[entry])
        bundle.registry()
        [after] = bundle.rules
        self.assertEqual((after.state, after.source, after.detectors),
                         ("unmeasured", None, []))
        self.assertIn("not registered", after.reason)
        self.assertEqual(bundle.coverage()["measured"], 0)
        self.assertEqual(bundle.coverage()["catalog"], 0)

    def test_the_rules_line_counts_a_catalog_bound_rule_as_measured(self):
        bundle = self.rules("# Git\n\nNever force-push to main.\n\n# Style\n\nKeep it tidy.\n")
        self.assertEqual(bundle.summary(relative_to=self.dir).splitlines()[0],
                         "rules: 1 measured, 0 dark, 1 unmeasured (50% measured)")
        bundle.registry()
        self.assertEqual(bundle.summary(relative_to=self.dir).splitlines()[0],
                         "rules: 1 measured, 0 dark, 1 unmeasured (50% measured)")

    def test_one_matching_sentence_marks_a_heading_less_file_measured(self):
        # The stated over-count of whole-text binding: the rest of the file rides along.
        bundle = self.rules("Never force-push to main.\n\nKeep functions short. Name "
                            "things well. Write docs.\n")
        self.assertEqual(bundle.summary(relative_to=self.dir).splitlines()[0],
                         "rules: 1 measured, 0 dark, 0 unmeasured (100% measured)")

    def test_an_entry_appended_after_a_call_keeps_the_earlier_rules_relabellable(self):
        did = "git-safety/force-push-default"
        plugin = DEFAULT.copy()
        plugin.add(Detector(did, "git-safety", "tool_use", lambda events, ctx: []))
        bundle = self.rules("# Git\n\nNever force-push to main.\n")
        bundle.registry(plugin)
        self.assertEqual(bundle.rules[0].source, "own")
        bundle.rules.append(RuleEntry("extra", "extra.md", "unmeasured", "", []))
        bundle.registry()
        self.assertEqual([e.source for e in bundle.rules], ["catalog", None])
        self.assertEqual(bundle.rules[1].rule, "extra")
        self.assertEqual(bundle.coverage()["catalog"], 1)

    def test_a_catalog_detector_no_rule_binds_any_more_does_not_join(self):
        did = "git-safety/force-push-default"
        bundle = self.rules("# Git\n\nNever force-push to main.\n")
        self.assertIn(did, bundle.registry())
        del bundle.rules[0]
        self.assertNotIn(did, bundle.registry())
        bundle.rules = []
        self.assertNotIn(did, bundle.registry())
        self.assertIn(did, bundle.registry(whole_catalog=True))

    def test_catalog_detectors_is_exported_but_not_in_the_readme_api(self):
        import ruleprobe.rules as rules_module
        self.assertIn("catalog_detectors", rules_module.__all__)
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        api = readme[readme.index("## The public API"):readme.index("## Development")]
        self.assertNotIn("catalog_detectors", api)

    def run_cli(self, *argv):
        out = io.StringIO()
        code = main(list(argv), out=out)
        return code, out.getvalue()

    def test_report_validity_and_corpus_give_a_restated_detector_one_score(self):
        did = "verification/no-verify"
        detector = dict((d.id, d) for d in catalog_detectors())[did]
        failing = [("a push past the hooks it cannot see",
                    [bash("git status", id="tu1")])]
        weaker = Examples(list(detector.examples.fire) + failing, detector.examples.skip)
        with mock.patch.object(detector, "examples", weaker):
            _code, corpus_text = self.run_cli("corpus", "--no-config", "--json")
            _code, report_text = self.run_cli("report", "--root", os.path.join(ROOT, "docs"),
                                              "--no-config", "--validity", "--json")
        row = json.loads(corpus_text)["detectors"][did]
        self.assertLess(row["recall"], 1.0)
        notes = dict((d["detector"], d["validity"])
                     for d in json.loads(report_text)["detectors"])
        self.assertEqual(notes[did], "p=%.2f r=%.2f" % (row["precision"], row["recall"]))

    def test_a_restated_row_no_corpus_label_scores_says_it_came_from_examples(self):
        base = os.path.join(self.dir, "corpus")
        os.makedirs(os.path.join(base, "sessions"))
        with open(os.path.join(base, "labels.yaml"), "w") as handle:
            handle.write("sessions: []\n")
        _code, text = self.run_cli("corpus", "--no-config", "--json", "--corpus", base)
        rows = json.loads(text)["detectors"]
        for did in ("verification/no-verify", "transcript-hygiene/whole-file-cat"):
            with self.subTest(detector=did):
                self.assertTrue(rows[did]["scored"])
                self.assertEqual(rows[did]["source"], "examples")
        self.assertEqual(rows["verification/no-verify"]["positives"],
                         len(dict((d.id, d) for d in catalog_detectors())[
                             "verification/no-verify"].examples.fire))

    def test_an_override_of_a_catalog_id_is_not_marked_catalog(self):
        path = self.write("detectors.yaml",
                          "- id: git-safety/force-push-default\n"
                          "  when: {git: {subcommand: push}}\n"
                          "- id: verification/no-verify\n"
                          "  when: {git: {subcommand: commit, args_any: [--no-verify]}}\n")
        _code, text = self.run_cli("detectors", "--no-config", "--detectors", path)
        lines = dict((line.split()[0], line) for line in text.splitlines() if line.strip())
        for did in ("git-safety/force-push-default", "verification/no-verify"):
            with self.subTest(detector=did):
                self.assertNotIn("catalog", lines[did])
        self.assertTrue(lines["package-manager/pip-install"].endswith("catalog"))

    def test_corpus_adds_no_catalog_examples_to_an_overridden_restated_id(self):
        did = "verification/no-verify"
        path = self.write("detectors.yaml",
                          "- id: verification/no-verify\n"
                          "  when: {git: {subcommand: commit, args_any: [--no-verify]}}\n")
        _code, text = self.run_cli("corpus", "--no-config", "--json", "--detectors", path)
        row = json.loads(text)["detectors"][did]
        corpus_only = score_corpus(DEFAULT)[did]
        self.assertEqual((row["positives"], row["negatives"]),
                         (corpus_only.positives, corpus_only.negatives))


class LiteralTests(unittest.TestCase):
    def test_the_catalog_module_holds_only_literals(self):
        with open(inspect.getsourcefile(catalog), encoding="utf-8") as handle:
            self.assertEqual(non_literal(handle.read()), [])

    def test_the_entries_compile_with_compile_detector(self):
        self.assertEqual([d.id for _pattern, d in _CATALOG], IDS)


_ZIP_PROBE = r"""
import json, sys, zipimport
zip_path, rules = sys.argv[1], sys.argv[2]
opened, loader_reads = [], []

def audit(event, args):
    if event == "open" and args and isinstance(args[0], str):
        opened.append(args[0])

# A read through the loader - `pkgutil.get_data`, `importlib.resources` - opens the archive
# itself, so the audit hook sees only the archive's path; these two record it instead.
# Importing a module goes through neither.
def recording(name):
    original = getattr(zipimport.zipimporter, name, None)
    if original is None:
        return
    def wrapper(self, *args, **kwargs):
        loader_reads.append([name] + [str(a) for a in args])
        return original(self, *args, **kwargs)
    setattr(zipimport.zipimporter, name, wrapper)

recording("get_data")
recording("get_resource_reader")
sys.path.insert(0, zip_path)
sys.addaudithook(audit)
from ruleprobe.detectors import catalog
from ruleprobe.rules import load_bundle
bundle = load_bundle(rules_dir=rules, config=False)
registry = bundle.registry()
print(json.dumps({"file": catalog.__file__, "opened": opened, "loader_reads": loader_reads,
                  "bound": [d for r in bundle.rules for d in r.detectors],
                  "registered": [d for d in registry.ids()]}))
"""


class ZipTests(unittest.TestCase):
    def test_the_catalog_loads_from_a_zip_with_no_file_read_beside_it(self):
        tmp = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, tmp, True)
        archive = os.path.join(tmp, "ruleprobe.zip")
        package = os.path.join(ROOT, "ruleprobe")
        # Every file of the package, data included, so a read beside a module would find
        # its file and succeed - and be seen - rather than fail quietly.
        with zipfile.ZipFile(archive, "w") as handle:
            for base, dirs, files in os.walk(package):
                dirs[:] = sorted(d for d in dirs if d != "__pycache__")
                for name in sorted(files):
                    if not name.endswith(".pyc"):
                        full = os.path.join(base, name)
                        handle.write(full, os.path.join(
                            "ruleprobe", os.path.relpath(full, package)).replace(os.sep, "/"))
        with zipfile.ZipFile(archive) as handle:
            self.assertIn("ruleprobe/detectors/common.yaml", handle.namelist())
        # -I and -S keep the checkout, PYTHONPATH and any installed copy off sys.path.
        result = subprocess.run([sys.executable, "-I", "-S", "-c", _ZIP_PROBE, archive,
                                 CATALOG_RULES], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertTrue(out["file"].startswith(archive + os.sep), out["file"])
        self.assertEqual(out["bound"], [did for _rule, did in FIXTURE])
        self.assertTrue(set(out["bound"]) <= set(out["registered"]))
        # The hook sees a plain open: the rule file read, and none of a path in the archive.
        self.assertIn(os.path.join(CATALOG_RULES, "team", "CLAUDE.md"), out["opened"])
        self.assertEqual([p for p in out["opened"] if p.startswith(archive + os.sep)], [])
        # And no read through the loader, which a path check cannot see.
        self.assertEqual(out["loader_reads"], [])


if __name__ == "__main__":
    unittest.main()
