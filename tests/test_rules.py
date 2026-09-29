# SPDX-License-Identifier: MIT
"""Detector files, rule-file binding, and what happens when one of them is wrong.

Every path here is a temporary directory: nothing in this suite reads a real machine's
configuration, and `XDG_CONFIG_HOME` is redirected for the discovery tests so they mean the
same thing on a machine that has a user detector file and one that does not.

Run: python3 -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

from corpus import bash, tool_use
from ruleprobe import DEFAULT, Registry, iter_sessions, run
from ruleprobe.events import Session
from ruleprobe.cli import main
from ruleprobe.rules import (IMPORT_DEPTH, discover, find_rule_files, load_bundle, load_file,
                             load_rules_dir, read_rule_file)
from test_readers import FIXTURES

SUDO = {"detectors": [{"id": "house-style/sudo-install", "rule": "house-style",
                       "event": "tool_use",
                       "when": {"command": {"starts_with": ["sudo", "pip"]}}}]}

MEASURED = """---
rule: house-style
detector:
  id: house-style/npm-install
  event: tool_use
  when:
    command: {starts_with: [npm, install]}
---

# House style

Use uv, never npm.
"""

DARK = """---
rule: secrets
opt_out: a transcript shows no secret that never reached a file
---

Never commit a secret.
"""

UNMEASURED = """# Working style

Honesty over polish.
"""

MALFORMED = """---
rule: broken
detector:
  event: tool_use
  when:
    comand: {starts_with: git}
---
"""


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, relative, text):
        path = os.path.join(self.dir, relative)
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class DetectorFileTests(Temp):
    def test_a_detectors_mapping_and_a_bare_list_both_load(self):
        mapping = self.write(".ruleprobe/detectors.yaml",
                             "detectors:\n  - id: a/b\n    when: {tool: Write}\n")
        listed = self.write("list.yaml", "- id: a/b\n  when: {tool: Write}\n")
        for path in (mapping, listed):
            detectors, findings = load_file(path)
            self.assertEqual([d.id for d in detectors], ["a/b"])
            self.assertEqual(findings, [])

    def test_a_json_file_loads_the_same_detectors(self):
        detectors, findings = load_file(self.write("d.json", json.dumps(SUDO)))
        self.assertEqual([d.id for d in detectors], ["house-style/sudo-install"])
        self.assertEqual(findings, [])

    def test_a_loaded_detector_fires_on_the_shape_it_names(self):
        detectors, _ = load_file(self.write("d.json", json.dumps(SUDO)))
        registry = Registry(detectors)
        self.assertIn("house-style/sudo-install",
                      run([bash("sudo pip install ruff")], registry=registry))
        self.assertEqual(run([bash("uv pip install ruff")], registry=registry), {})

    def test_a_file_that_is_not_a_list_of_detectors_is_one_finding(self):
        detectors, findings = load_file(self.write("d.yaml", "detectors: nope\n"))
        self.assertEqual(detectors, [])
        self.assertIn("expected a list of detectors", findings[0].reason)

    def test_one_bad_entry_is_skipped_and_the_rest_of_the_file_still_loads(self):
        path = self.write("d.yaml",
                          "- id: a/good\n"
                          "  when: {tool: Write}\n"
                          "- id: a/bad\n"
                          "  when: {comand: cat}\n"
                          "- id: a/also-good\n"
                          "  when: {tool: Edit}\n")
        detectors, findings = load_file(path)
        self.assertEqual([d.id for d in detectors], ["a/good", "a/also-good"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 4)
        self.assertIn("unknown matcher", findings[0].reason)

    def test_a_file_that_does_not_parse_is_a_finding_and_never_an_exception(self):
        detectors, findings = load_file(self.write("d.yaml", "a: 1\n  b: 2\n"))
        self.assertEqual(detectors, [])
        self.assertEqual((findings[0].line, findings[0].path.endswith("d.yaml")), (2, True))

    def test_a_missing_file_is_a_finding_too(self):
        detectors, findings = load_file(os.path.join(self.dir, "absent.yaml"))
        self.assertEqual(detectors, [])
        self.assertEqual(len(findings), 1)


class DiscoveryTests(Temp):
    def setUp(self):
        Temp.setUp(self)
        self.config = os.path.join(self.dir, "config")
        os.makedirs(os.path.join(self.config, "ruleprobe"))
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.config
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old

    def test_the_repository_file_is_found_from_a_subdirectory(self):
        self.write(".ruleprobe/detectors.yaml", "- id: a/b\n  when: {tool: Write}\n")
        os.makedirs(os.path.join(self.dir, "src", "deep"))
        found = discover(cwd=os.path.join(self.dir, "src", "deep"), user=False)
        self.assertEqual([os.path.relpath(p, self.dir) for p in found],
                         [os.path.join(".ruleprobe", "detectors.yaml")])

    def test_the_user_file_is_read_before_the_repository_s_so_the_repository_wins(self):
        user = self.write("config/ruleprobe/detectors.yaml",
                          "- id: a/b\n  when: {tool: Write}\n")
        repo = self.write(".ruleprobe/detectors.yaml",
                          "- id: a/b\n  when: {tool: Edit}\n")
        self.assertEqual(discover(cwd=self.dir), [user, repo])
        bundle = load_bundle(cwd=self.dir)
        registry = bundle.registry(base=Registry())
        self.assertEqual(registry.ids(), ["a/b"])
        self.assertIn("a/b", run([tool_use("Edit", {})], registry=registry))
        self.assertEqual(run([tool_use("Write", {})], registry=registry), {})

    def test_nothing_is_discovered_when_there_is_nothing_to_discover(self):
        self.assertEqual(discover(cwd=self.dir), [])

    def test_config_false_reads_neither(self):
        self.write(".ruleprobe/detectors.yaml", "- id: a/b\n  when: {tool: Write}\n")
        self.assertEqual(load_bundle(cwd=self.dir, config=False).detectors, [])


class RuleBindingTests(Temp):
    def bundle(self):
        self.write("rules/house-style.md", MEASURED)
        self.write("rules/secrets.md", DARK)
        self.write("rules/working-style.md", UNMEASURED)
        return load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)

    def test_a_rule_with_a_detector_is_measured_and_its_detector_runs(self):
        bundle = self.bundle()
        entry = [r for r in bundle.rules if r.rule == "house-style"][0]
        self.assertEqual((entry.state, entry.detectors),
                         ("measured", ["house-style/npm-install"]))
        registry = bundle.registry(base=Registry())
        self.assertIn("house-style/npm-install",
                      run([bash("npm install left-pad")], registry=registry))

    def test_a_rule_with_an_opt_out_is_dark_and_carries_its_reason(self):
        entry = [r for r in self.bundle().rules if r.rule == "secrets"][0]
        self.assertEqual(entry.state, "dark")
        self.assertIn("no secret that never reached a file", entry.reason)

    def test_a_rule_with_neither_is_unmeasured_so_the_gap_is_visible(self):
        entry = [r for r in self.bundle().rules if r.rule == "working-style.md#working-style"][0]
        self.assertEqual((entry.state, entry.detectors, entry.reason), ("unmeasured", [], ""))

    def test_the_counts_are_what_the_summary_prints(self):
        bundle = self.bundle()
        self.assertEqual(bundle.counts(), {"measured": 1, "dark": 1, "unmeasured": 1})
        summary = bundle.summary(relative_to=self.dir)
        self.assertIn("rules: 1 measured, 1 dark, 1 unmeasured", summary)
        self.assertIn("unmeasured working-style.md#working-style ", summary)
        self.assertNotIn(self.dir, summary)

    def test_the_rule_name_defaults_to_the_file_name(self):
        path = self.write("rules/cache-hygiene.md", "---\nopt_out: no\n---\n")
        self.assertEqual(read_rule_file(path)[1][0].rule, "cache-hygiene")

    def test_an_id_defaults_to_the_rule_and_the_entry_s_place_in_the_file(self):
        path = self.write("rules/x.md", "---\nrule: house-style\ndetector:\n"
                                        "  when: {tool: Write}\n---\n")
        detectors, [entry], findings = read_rule_file(path)
        self.assertEqual(([d.id for d in detectors], entry.state, findings),
                         (["house-style/1"], "measured", []))

    def test_several_detectors_may_measure_one_rule(self):
        path = self.write("rules/x.md", "---\nrule: r\ndetector:\n"
                                        "  - {id: r/a, when: {tool: Write}}\n"
                                        "  - {id: r/b, when: {tool: Edit}}\n---\n")
        detectors, [entry], _ = read_rule_file(path)
        self.assertEqual([d.id for d in detectors], ["r/a", "r/b"])
        self.assertEqual(entry.detectors, ["r/a", "r/b"])

    def test_a_detector_takes_its_rule_from_the_file_it_sits_in(self):
        path = self.write("rules/x.md", "---\nrule: house-style\ndetector:\n"
                                        "  id: house-style/npm\n  when: {tool: Write}\n---\n")
        self.assertEqual(read_rule_file(path)[0][0].rule, "house-style")

    def test_a_directory_that_is_not_one_is_a_finding(self):
        _detectors, rules, findings = load_rules_dir(os.path.join(self.dir, "absent"))
        self.assertEqual((rules, len(findings)), ([], 1))

    def test_the_walk_is_sorted_so_a_report_is_the_same_everywhere(self):
        self.write("rules/b.md", UNMEASURED)
        self.write("rules/a.md", UNMEASURED)
        self.write("rules/nested/c.md", UNMEASURED)
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([r.rule for r in bundle.rules],
                         ["a.md#working-style", "b.md#working-style",
                          "nested/c.md#working-style"])


class MalformedRuleTests(Temp):
    def test_a_malformed_detector_is_reported_with_its_line_and_skipped(self):
        self.write("rules/broken.md", MALFORMED)
        self.write("rules/house-style.md", MEASURED)
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([d.id for d in bundle.detectors], ["house-style/npm-install"])
        self.assertEqual(len(bundle.findings), 1)
        finding = bundle.findings[0]
        self.assertEqual(finding.line, 6)
        self.assertTrue(finding.path.endswith("broken.md"))
        self.assertIn("unknown matcher", finding.reason)
        self.assertIn("findings: 1 (everything else still loaded)", bundle.summary(relative_to=self.dir))

    def test_a_rule_whose_detector_did_not_compile_is_unmeasured_not_measured(self):
        self.write("rules/broken.md", MALFORMED)
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([(r.rule, r.state) for r in bundle.rules],
                         [("broken", "unmeasured")])

    def test_front_matter_that_does_not_parse_is_a_finding_and_an_unmeasured_rule(self):
        self.write("rules/x.md", "---\nrule: a\n  bad: indent\n---\n")
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual(bundle.rules[0].state, "unmeasured")
        self.assertEqual(len(bundle.findings), 1)

    def test_a_rule_name_with_a_slash_in_it_is_a_finding_not_a_crash(self):
        self.write("rules/x.md", '---\nrule: a/b\nopt_out: "no"\n---\n')
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual(bundle.rules[0].state, "dark")
        self.assertIn("slash-free", bundle.findings[0].reason)


class ExampleTests(unittest.TestCase):
    """The worked example the README prints. If this drifts, the README is wrong, which is
    the failure mode a documented sixty-second test has."""

    DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")

    def test_the_example_rules_load_with_no_findings(self):
        bundle = load_bundle(rules_dir=os.path.join(self.DOCS, "rules"), config=False)
        self.assertEqual(bundle.findings, [])
        self.assertEqual([(r.rule, r.state) for r in bundle.rules],
                         [("house-style", "measured"), ("secrets", "dark"),
                          ("verification", "measured"),
                          ("working-style.md#working-style", "unmeasured")])

    def test_the_example_transcript_fires_the_example_rule(self):
        bundle = load_bundle(rules_dir=os.path.join(self.DOCS, "rules"), config=False)
        registry = bundle.registry()
        sessions = list(iter_sessions(root=self.DOCS))
        self.assertEqual([s.id for s in sessions], ["example-1"])
        hits = run(sessions[0].events, registry=registry, strict=True)
        self.assertEqual(len(hits["house-style/sudo-install"]), 2)
        self.assertEqual(len(hits["verification/no-test-run"]), 1)


class CliTests(Temp):
    def run_cli(self, *argv):
        out = io.StringIO()
        code = main(list(argv), out=out)
        return code, out.getvalue()

    def test_report_runs_a_rule_s_own_detector_and_lists_what_is_unmeasured(self):
        self.write("rules/transcript-hygiene.md",
                   "---\nrule: transcript-hygiene\ndetector:\n"
                   "  id: transcript-hygiene/sed-range\n  event: tool_use\n"
                   "  when: {command: {name: sed}}\n---\n")
        self.write("rules/working-style.md", UNMEASURED)
        code, text = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                  "--rules", os.path.join(self.dir, "rules"))
        self.assertEqual(code, 0)
        self.assertIn("transcript-hygiene/sed-range", text)
        self.assertIn("rules: 1 measured, 0 dark, 1 unmeasured", text)
        self.assertIn("unmeasured working-style.md#working-style ", text)

    def test_a_detector_file_named_on_the_command_line_is_loaded(self):
        path = self.write("d.json", json.dumps(SUDO))
        code, text = self.run_cli("detectors", "--no-config", "--detectors", path)
        self.assertEqual(code, 0)
        self.assertIn("house-style/sudo-install", text)

    def test_a_malformed_file_is_printed_as_a_finding_and_the_report_still_runs(self):
        path = self.write("d.yaml", "- id: a/b\n  when: {comand: cat}\n")
        code, text = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                  "--detectors", path)
        self.assertEqual(code, 0)
        self.assertIn("findings: 1 (everything else still loaded)", text)
        self.assertIn("unknown matcher", text)
        self.assertIn("transcript-hygiene/whole-file-cat", text)

    def test_a_section_several_detectors_measure_lists_them_all_on_its_line(self):
        self.write("rules/CLAUDE.md", MULTI)
        rules_dir = os.path.join(self.dir, "rules")
        code, text = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                  "--rules", rules_dir)
        self.assertEqual(code, 0)
        self.assertIn("rules: 1 measured, 0 dark, 0 unmeasured (100% measured)", text)
        self.assertRegex(text, r"measured +CLAUDE\.md#git .*: catalog-bound, "
                               r"verification/no-verify, git-safety/force-push-default, "
                               r"commits/non-conventional-subject\n")
        for did in MULTI_IDS:
            self.assertIn(did, text.split("rules:")[0])
        out = io.StringIO()
        with mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(main(["report", "--root", FIXTURES, "--no-config", "--rules",
                                   rules_dir, "--json"], out=out), 0)
        coverage = json.loads(out.getvalue())["coverage"]
        self.assertEqual((coverage["measured"], coverage["unmeasured"], coverage["catalog"]),
                         (1, 0, 1))

    def test_a_default_shape_is_reported_by_the_one_shipped_detector(self):
        self.write("rules/CLAUDE.md", DEFAULTS)
        rules_dir = os.path.join(self.dir, "rules")
        code, text = self.run_cli("report", "--root", FIXTURES, "--no-config",
                                  "--rules", rules_dir)
        self.assertEqual(code, 0)
        self.assertIn("rules: 1 measured, 0 dark, 0 unmeasured (100% measured)", text)
        self.assertRegex(text, r"measured +CLAUDE\.md#sessions .*: catalog-bound, "
                               r"cache-hygiene/compact, cache-hygiene/model-switch, "
                               r"secrets/secret-in-write, "
                               r"transcript-hygiene/unfiltered-find\n")
        table = text.split("rules:")[0]
        for did in DEFAULTS_IDS:
            self.assertEqual(table.count(did), 1, did)


#: One section of three rules, each sentence binding a different catalog entry.
MULTI = ("# Git\n\n- Use Conventional Commits.\n- Never force-push to main.\n"
         "- Never skip pre-commit hooks.\n")
#: What `MULTI` binds, in catalog order, whatever order its sentences come in.
MULTI_IDS = ["verification/no-verify", "git-safety/force-push-default",
             "commits/non-conventional-subject"]

#: One section stating the four default shapes the 0.2 catalog left unbound.
DEFAULTS = ("# Sessions\n\nFilter every `find`. Never write API keys to a file.\n"
            "Do not switch models mid-session. Never compact the conversation.\n")
#: What `DEFAULTS` binds, in catalog order.
DEFAULTS_IDS = ["cache-hygiene/compact", "cache-hygiene/model-switch",
                "secrets/secret-in-write", "transcript-hygiene/unfiltered-find"]


class SentenceBindingTests(Temp):
    """A section binds one catalog entry per sentence, under its own section id."""

    def load(self, text):
        self.write("rules/CLAUDE.md", text)
        return load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)

    def test_a_section_binds_every_entry_its_sentences_bind_in_catalog_order(self):
        [entry] = self.load(MULTI).rules
        self.assertEqual((entry.rule, entry.state, entry.detectors, entry.source),
                         ("CLAUDE.md#git", "measured", MULTI_IDS, "catalog"))
        [again] = self.load("# Git\n\nNever skip pre-commit hooks. Use Conventional Commits. "
                            "Never force-push to main.\n").rules
        self.assertEqual(again.detectors, MULTI_IDS)

    def test_one_entry_two_sentences_bind_is_listed_once(self):
        [entry] = self.load("# Git\n\nNever force-push to main.\n\n"
                            "Do not force-push the default branch either.\n").rules
        self.assertEqual(entry.detectors, ["git-safety/force-push-default"])

    def test_every_bound_detector_joins_the_registry(self):
        registry = self.load(MULTI).registry()
        for did in MULTI_IDS:
            self.assertIn(did, registry)

    def test_a_user_detector_replacing_one_bound_id_makes_the_rule_its_own(self):
        self.write("rules/CLAUDE.md", MULTI)
        path = self.write("d.json", json.dumps({"detectors": [
            {"id": "git-safety/force-push-default", "rule": "git", "event": "tool_use",
             "when": {"git": {"subcommand": "push"}}}]}))
        bundle = load_bundle(paths=[path], rules_dir=os.path.join(self.dir, "rules"),
                             config=False)
        [entry] = bundle.rules
        self.assertEqual((entry.state, entry.detectors, entry.source),
                         ("measured", MULTI_IDS, "own"))

    def test_a_heading_less_file_binds_per_sentence_too(self):
        self.write("rules/git.md", "Use uv, not pip. Keep it short.\n\n"
                                   "Never force-push to main when others share it.\n")
        [entry] = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False).rules
        self.assertEqual((entry.rule, entry.state, entry.detectors),
                         ("git", "measured", ["package-manager/pip-install"]))

    def test_the_four_default_shapes_bind_in_catalog_order_to_the_shipped_detectors(self):
        bundle = self.load(DEFAULTS)
        [entry] = bundle.rules
        self.assertEqual((entry.rule, entry.state, entry.detectors, entry.source),
                         ("CLAUDE.md#sessions", "measured", DEFAULTS_IDS, "catalog"))
        registry = bundle.registry()
        self.assertEqual(registry.ids(), DEFAULT.ids())
        for did in DEFAULTS_IDS:
            self.assertIs(registry.get(did), DEFAULT.get(did))

    def test_a_default_shape_beside_a_0_2_shape_binds_both(self):
        [entry] = self.load("# Git\n\nNever force-push to main. Never write a secret into "
                            "a file.\n").rules
        self.assertEqual(entry.detectors, ["git-safety/force-push-default",
                                           "secrets/secret-in-write"])

    def test_a_user_detector_replacing_a_default_s_id_makes_the_rule_its_own(self):
        self.write("rules/CLAUDE.md", "# Sessions\n\nNever compact the conversation.\n")
        path = self.write("d.json", json.dumps({"detectors": [
            {"id": "cache-hygiene/compact", "rule": "cache-hygiene", "event": "session",
             "when": {"kind": "compact"}}]}))
        bundle = load_bundle(paths=[path], rules_dir=os.path.join(self.dir, "rules"),
                             config=False)
        bundle.registry()
        [entry] = bundle.rules
        self.assertEqual((entry.state, entry.detectors, entry.source),
                         ("measured", ["cache-hygiene/compact"], "own"))

    def test_binding_is_the_same_on_every_load(self):
        first = [tuple(e) for e in self.load(MULTI).rules]
        second = [tuple(e) for e in self.load(MULTI).rules]
        self.assertEqual(first, second)


class RuleFileDiscoveryTests(Temp):
    """With no `--rules`, the rule files are found: the three global ones under a synthetic
    home, and each runtime's project files at the working directories sessions recorded."""

    def setUp(self):
        Temp.setUp(self)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)
        patched = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.project = os.path.join(self.home, "work", "project")
        os.makedirs(self.project)

    def at(self, *parts):
        """A found file's path, as found: under the home as given, never resolved."""
        return os.path.join(self.dir, *parts)

    def found(self, workdirs=()):
        return find_rule_files(workdirs, home=self.home)

    def test_the_three_global_files_and_each_runtime_s_project_files_are_read(self):
        for name in ("home/.claude/CLAUDE.md", "home/.codex/AGENTS.md",
                     "home/.gemini/GEMINI.md", "home/work/project/CLAUDE.md",
                     "home/work/project/.claude/rules/testing.md",
                     "home/work/project/AGENTS.md", "home/work/project/GEMINI.md",
                     "home/work/project/README.md"):
            self.write(name, "# %s\n\nSome rule text for %s.\n" % (name, name))
        globals_only = [self.at("home/.claude/CLAUDE.md"), self.at("home/.codex/AGENTS.md"),
                        self.at("home/.gemini/GEMINI.md")]
        self.assertEqual(self.found(), sorted(globals_only))
        claude = self.found([("claude-code", self.project)])
        self.assertEqual(claude, sorted(globals_only + [
            self.at("home/work/project/CLAUDE.md"),
            self.at("home/work/project/.claude/rules/testing.md")]))
        every = self.found([("codex", self.project), ("gemini", self.project),
                            ("claude-code", self.project)])
        self.assertEqual(every, sorted(claude + [self.at("home/work/project/AGENTS.md"),
                                                 self.at("home/work/project/GEMINI.md")]))
        self.assertNotIn(self.at("home/work/project/README.md"), every)

    def test_a_working_directory_that_is_gone_or_blank_reads_nothing(self):
        self.assertEqual(self.found([("claude-code", os.path.join(self.dir, "gone")),
                                     ("codex", ""), ("claude-code", None)]), [])

    def test_the_list_is_the_same_whatever_order_the_sessions_came_in(self):
        other = os.path.join(self.home, "work", "other")
        for name in ("home/work/project/CLAUDE.md", "home/work/other/CLAUDE.md"):
            self.write(name, "# Rules\n\nText of %s.\n" % name)
        workdirs = [("claude-code", other), ("claude-code", self.project)]
        self.assertEqual(self.found(workdirs), self.found(list(reversed(workdirs))))
        self.assertEqual(len(self.found(workdirs)), 2)

    def test_a_file_reached_twice_or_copied_into_a_worktree_is_read_once(self):
        self.write("home/work/project/AGENTS.md", "# Rules\n\nNever force-push to main.\n")
        link = os.path.join(self.project, "CLAUDE.md")
        try:
            os.symlink("AGENTS.md", link)
        except (OSError, NotImplementedError):  # pragma: no cover - no symlinks here
            self.skipTest("symlinks are not available")
        self.write("home/work/project/.claude/worktrees/one/AGENTS.md",
                   "# Rules\n\nNever force-push to main.\n")
        found = self.found([("claude-code", self.project), ("codex", self.project),
                            ("codex", os.path.join(self.project, ".claude", "worktrees",
                                                   "one"))])
        self.assertEqual(found, [self.at("home/work/project/AGENTS.md")])

    def test_each_directory_and_candidate_file_is_checked_once(self):
        self.write("home/work/project/CLAUDE.md", "# Git\n\nNever force-push to main.\n")
        spelled = [self.project, self.project + os.sep, os.path.join(self.project, ".")]
        workdirs = [("claude-code", d) for d in spelled for _ in range(50)]
        workdirs += [("codex", self.project)] * 50
        real_isdir, real_isfile = os.path.isdir, os.path.isfile
        with mock.patch("os.path.isdir", side_effect=real_isdir) as isdir, \
                mock.patch("os.path.isfile", side_effect=real_isfile) as isfile:
            found = self.found(workdirs)
        self.assertEqual(found, [self.at("home/work/project/CLAUDE.md")])
        dirs = [c[0][0] for c in isdir.call_args_list]
        files = [c[0][0] for c in isfile.call_args_list]
        self.assertEqual(dirs.count(self.project), 1)
        self.assertEqual(len(files), len(set(files)))

    def test_codex_reads_its_override_in_place_of_agents_md(self):
        self.write("home/work/project/AGENTS.md", "# Rules\n\nOne.\n")
        self.write("home/work/project/AGENTS.override.md", "# Rules\n\nTwo.\n")
        self.assertEqual(self.found([("codex", self.project)]),
                         [self.at("home/work/project/AGENTS.override.md")])

    def test_local_markdown_imports_are_followed_and_nothing_else_is(self):
        self.write("home/.claude/CLAUDE.md",
                   "# Global\n\n@~/.claude/personal.md\nSee @docs/house.md, too.\n\n"
                   "```\n@docs/fenced.md\n```\n\nNot `@docs/spanned.md` and not "
                   "@docs/data.json or someone@docs/mail.md or @docs/missing.md.\n")
        for name in ("personal.md", "docs/house.md", "docs/fenced.md", "docs/spanned.md",
                     "docs/data.json", "docs/mail.md"):
            self.write("home/.claude/" + name, "# Imported\n\nText.\n" + name)
        self.assertEqual(self.found(), sorted([self.at("home/.claude/CLAUDE.md"),
                                               self.at("home/.claude/personal.md"),
                                               self.at("home/.claude/docs/house.md")]))

    def test_imports_stop_after_the_depth_limit_and_a_cycle_ends(self):
        chain = IMPORT_DEPTH + 2
        self.write("home/.gemini/GEMINI.md", "# Top\n\n@hop1.md\n")
        for hop in range(1, chain + 1):
            self.write("home/.gemini/hop%d.md" % hop,
                       "# Hop %d\n\n@hop%d.md @GEMINI.md\n" % (hop, hop + 1))
        found = self.found()
        self.assertIn(self.at("home/.gemini/hop%d.md" % IMPORT_DEPTH), found)
        self.assertNotIn(self.at("home/.gemini/hop%d.md" % (IMPORT_DEPTH + 1)), found)
        self.assertEqual(len(found), IMPORT_DEPTH + 1)

    def test_a_codex_file_s_imports_are_not_followed(self):
        self.write("home/.codex/AGENTS.md", "# Global\n\n@extra.md\n")
        self.write("home/.codex/extra.md", "# Extra\n\nText.\n")
        self.assertEqual(self.found(), [self.at("home/.codex/AGENTS.md")])

    def test_a_found_file_is_named_by_where_it_is_so_two_projects_never_share_an_id(self):
        other = os.path.join(self.home, "work", "other")
        self.write("home/work/project/AGENTS.md", "# Git\n\nNever force-push to main.\n")
        self.write("home/work/other/AGENTS.md", "# Git\n\nUse uv, not pip.\n")
        self.write("home/.codex/AGENTS.md", "Never force-push to main.\n")
        files = self.found([("codex", self.project), ("codex", other)])
        bundle = load_bundle(config=False, rule_files=files)
        self.assertEqual([(e.rule, e.state, e.detectors) for e in bundle.rules], [
            ("~/.codex/AGENTS.md", "measured", ["git-safety/force-push-default"]),
            ("~/work/other/AGENTS.md#git", "measured", ["package-manager/pip-install"]),
            ("~/work/project/AGENTS.md#git", "measured", ["git-safety/force-push-default"])])

    def test_a_found_file_binds_the_four_default_detector_shapes_too(self):
        self.write("home/.claude/CLAUDE.md",
                   "# Sessions\n\nNever compact the context.\n\n"
                   "# Models\n\nDo not switch models in the middle of a session.\n\n"
                   "# Credentials\n\nNever write an API key to a file.\n\n"
                   "# Searching\n\nFilter every `find` by name or type.\n")
        bundle = load_bundle(config=False, rule_files=self.found())
        bundle.registry()
        self.assertEqual([(e.rule, e.state, e.detectors) for e in bundle.rules], [
            ("~/.claude/CLAUDE.md#sessions", "measured", ["cache-hygiene/compact"]),
            ("~/.claude/CLAUDE.md#models", "measured", ["cache-hygiene/model-switch"]),
            ("~/.claude/CLAUDE.md#credentials", "measured", ["secrets/secret-in-write"]),
            ("~/.claude/CLAUDE.md#searching", "measured",
             ["transcript-hygiene/unfiltered-find"])])

    def test_a_path_outside_the_working_directory_prints_under_the_home_as_a_tilde(self):
        from ruleprobe.rules import _short
        path = os.path.join(self.home, "work", "project", "CLAUDE.md")
        self.assertEqual(_short(path, relative_to=self.project), "CLAUDE.md")
        self.assertEqual(_short(path, relative_to=os.path.join(self.dir, "elsewhere")),
                         "~/work/project/CLAUDE.md")
        outside = os.path.join(self.dir, "other", "rules.md")
        self.assertEqual(_short(outside, relative_to=self.home), outside)

    def test_a_blocked_section_names_its_nearest_entry_and_the_blocking_word(self):
        self.write("home/.claude/CLAUDE.md",
                   "# Git\n\nNever force-push to main unless the release lead says so.\n\n"
                   "# Style\n\nKeep functions short.\n")
        bundle = load_bundle(config=False, rule_files=self.found())
        bundle.registry()
        blocked, plain = bundle.rules
        self.assertEqual(blocked.state, "unmeasured")
        self.assertIn("(unless)", blocked.reason)
        self.assertIn("nearest git-safety/force-push-default", blocked.reason)
        self.assertEqual(plain.reason, "")
        text = bundle.summary()
        line = [x for x in text.split("\n") if "#git" in x][0]
        self.assertIn("(unless), nearest git-safety/force-push-default", line)

    def test_the_coverage_block_says_once_that_found_rule_text_is_today_s(self):
        self.write("home/.claude/CLAUDE.md", "# Git\n\nNever force-push to main.\n")
        self.write("home/.gemini/GEMINI.md", "# Style\n\nKeep functions short.\n")
        text = load_bundle(config=False, rule_files=self.found()).summary()
        self.assertEqual(text.count("the rule text is today's"), 1)
        self.assertTrue(text.startswith("rules found with no --rules in 2 files; the rule text "
                                        "is today's, not the text in force when an older "
                                        "session ran\n"))
        self.write("rules/git.md", "# Git\n\nNever force-push to main.\n")
        named = load_bundle(config=False, rules_dir=os.path.join(self.dir, "rules"))
        self.assertNotIn("today's", named.summary())
        self.assertEqual(load_bundle(config=False, rule_files=[]).summary(), "")


class UntrustedRuleFileTests(Temp):
    """A found rule file is untrusted text: it may be a clone of somebody else's repository."""

    def setUp(self):
        Temp.setUp(self)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)
        patched = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.project = os.path.join(self.home, "clone")
        os.makedirs(self.project)
        self.outside = self.write("outside/private.md", "# Private heading\n\nSecret text.\n")

    def found(self, workdirs=(), refused=None):
        return find_rule_files(workdirs or [("claude-code", self.project)], home=self.home,
                               refused=refused)

    def symlink(self, target, link):
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):  # pragma: no cover - no symlinks here
            self.skipTest("symlinks are not available")

    def test_a_found_file_s_front_matter_detector_is_never_compiled(self):
        self.write("home/clone/AGENTS.md",
                   "---\ndetectors:\n"
                   "  - id: git-safety/force-push-default\n    rule: git\n"
                   "    event: tool_use\n    when: {command: {starts_with: [ls]}}\n"
                   "  - id: clone/slow\n    rule: git\n    event: tool_use\n"
                   "    when: {command: {regex: '^(a+)+$'}}\n---\n\n"
                   "# Git\n\nNever force-push to main.\n")
        files = self.found([("codex", self.project)])
        bundle = load_bundle(config=False, rule_files=files)
        registry = bundle.registry()
        self.assertEqual(bundle.detectors[0].id, "git-safety/force-push-default")
        self.assertEqual(len(bundle.detectors), 1)
        self.assertIs(registry.get("git-safety/force-push-default"), bundle.detectors[0])
        self.assertNotIn("clone/slow", registry)
        [entry] = bundle.rules
        self.assertEqual((entry.rule, entry.state, entry.source),
                         ("~/clone/AGENTS.md#git", "measured", "catalog"))
        self.assertIn("read only under --rules", bundle.findings[0].reason)
        # A command the pathological pattern would take far too long over, run in memory.
        events = [bash("a" * 40 + "!"), bash("ls")]
        self.assertEqual(sorted(run(events, registry=registry)), [])
        # The same file named with --rules is trusted, as before.
        shutil.copy(files[0], self.write("rules/AGENTS.md", ""))
        named = load_bundle(config=False, rules_dir=os.path.join(self.dir, "rules"))
        self.assertEqual(sorted(d.id for d in named.detectors),
                         ["clone/slow", "git-safety/force-push-default"])

    def test_an_import_outside_its_root_is_refused_and_only_counted(self):
        other = self.write("outside/other.md", "# Other private heading\n\nText.\n")
        relative = os.path.relpath(other, self.project).replace(os.sep, "/")
        self.write("home/clone/docs/ok.md", "# Inside\n\nText.\n")
        self.write("home/clone/CLAUDE.md",
                   "# Rules\n\n@%s @%s @link.md @docs/ok.md @docs/../../clone/docs/ok.md\n"
                   % (self.outside.replace(os.sep, "/"), relative))
        self.symlink(self.outside, os.path.join(self.project, "link.md"))
        refused = []
        files = self.found(refused=refused)
        self.assertEqual(files, [os.path.join(self.project, "CLAUDE.md"),
                                 os.path.join(self.project, "docs", "ok.md")])
        self.assertEqual(len(refused), 3)
        text = load_bundle(config=False, rule_files=files, refused=len(refused)).summary()
        self.assertIn("imports refused: 3 outside their rule file's project or global folder, "
                      "not read", text)
        self.assertNotIn("private", text.lower())
        self.assertNotIn("outside", text.split("imports refused")[0])

    def test_a_global_file_s_imports_stay_in_its_global_folder(self):
        self.write("home/.claude/CLAUDE.md", "# G\n\n@~/.claude/mine.md @~/elsewhere.md\n")
        self.write("home/.claude/mine.md", "# Mine\n\nText.\n")
        self.write("home/elsewhere.md", "# Elsewhere\n\nText.\n")
        refused = []
        self.assertEqual(find_rule_files((), home=self.home, refused=refused),
                         [os.path.join(self.home, ".claude", "CLAUDE.md"),
                          os.path.join(self.home, ".claude", "mine.md")])
        self.assertEqual(refused, [os.path.join(self.home, "elsewhere.md")])

    def test_an_unreadable_file_s_finding_names_the_reason_and_not_the_path(self):
        path = self.write("home/clone/CLAUDE.md", "# Rules\n\nText.\n")
        with mock.patch("ruleprobe.rules._read_regular",
                        side_effect=PermissionError(13, "Permission denied", path)):
            _detectors, [entry], [finding] = read_rule_file(path, label="~/clone/CLAUDE.md",
                                                            trusted=False)
        self.assertEqual(finding.reason, "cannot read: Permission denied")
        self.assertEqual(entry.reason, "unreadable")

    def test_a_fifo_named_like_a_rule_file_never_blocks_or_loads(self):
        if not hasattr(os, "mkfifo"):  # pragma: no cover - Windows
            self.skipTest("no FIFOs here")
        os.makedirs(os.path.join(self.project, ".claude", "rules"))
        fifo = os.path.join(self.project, ".claude", "rules", "pipe.md")
        os.mkfifo(fifo)
        result = {}

        def read():
            result["files"] = self.found()
            result["direct"] = read_rule_file(fifo)[2]

        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        worker.join(10)
        self.assertFalse(worker.is_alive(), "reading a FIFO blocked")
        self.assertEqual(result["files"], [])
        self.assertEqual([f.reason for f in result["direct"]],
                         ["cannot read: not a regular file"])

    def test_identical_files_are_compared_by_digest(self):
        for name in ("home/clone/CLAUDE.md", "home/clone/.claude/CLAUDE.md"):
            self.write(name, "# Rules\n\nNever force-push to main.\n")
        import hashlib
        with mock.patch("ruleprobe.rules.hashlib.sha256", wraps=hashlib.sha256) as digest:
            self.assertEqual(self.found(), [os.path.join(self.project, "CLAUDE.md")])
        self.assertEqual(digest.call_count, 2)

    def test_a_relative_import_resolves_from_the_file_as_named_not_its_real_path(self):
        dotfiles = os.path.join(self.home, "dotfiles")
        self.write("home/dotfiles/CLAUDE.md", "# Global\n\n@rules/git.md\n")
        self.write("home/dotfiles/rules/git.md", "# Decoy\n\nWrong file.\n")
        self.write("home/.claude/rules/git.md", "# Git\n\nNever force-push to main.\n")
        self.symlink(os.path.join(dotfiles, "CLAUDE.md"),
                     os.path.join(self.home, ".claude", "CLAUDE.md"))
        refused = []
        self.assertEqual(find_rule_files((), home=self.home, refused=refused),
                         [os.path.join(self.home, ".claude", "CLAUDE.md"),
                          os.path.join(self.home, ".claude", "rules", "git.md")])
        self.assertEqual(refused, [])

    def test_a_relative_recorded_working_directory_is_ignored(self):
        self.write("rel/app/CLAUDE.md", "# Rules\n\nNever force-push to main.\n")
        self.write("CLAUDE.md", "# Rules\n\nUse uv, not pip.\n")
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.dir)
        self.assertEqual(find_rule_files([("claude-code", "rel/app"), ("claude-code", "."),
                                          ("claude-code", "rel/../rel/app")],
                                         home=self.home), [])

    def test_a_session_keeps_its_seven_fields_and_carries_cwd_beside_them(self):
        [session] = [s for s in iter_sessions(root=FIXTURES) if s.runtime == "claude-code"]
        self.assertEqual(len(session), 7)
        _id, _repo, _runtime, _events, _path, _started, _ended = session
        self.assertEqual(session.cwd, "/tmp/demo-repo")
        self.assertEqual(Session("x", "", "codex", []).cwd, "")


if __name__ == "__main__":
    unittest.main()
