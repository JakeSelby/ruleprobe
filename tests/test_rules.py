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
import unittest
from unittest import mock

from corpus import bash, tool_use
from ruleprobe import Registry, iter_sessions, run
from ruleprobe.cli import main
from ruleprobe.rules import discover, load_bundle, load_file, load_rules_dir, read_rule_file
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


#: One section of three rules, each sentence binding a different catalog entry.
MULTI = ("# Git\n\n- Use Conventional Commits.\n- Never force-push to main.\n"
         "- Never skip pre-commit hooks.\n")
#: What `MULTI` binds, in catalog order, whatever order its sentences come in.
MULTI_IDS = ["verification/no-verify", "git-safety/force-push-default",
             "commits/non-conventional-subject"]


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
                                   "Never force-push to main. Tags are fine.\n")
        [entry] = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False).rules
        self.assertEqual((entry.rule, entry.state, entry.detectors),
                         ("git", "measured", ["package-manager/pip-install"]))

    def test_binding_is_the_same_on_every_load(self):
        first = [tuple(e) for e in self.load(MULTI).rules]
        second = [tuple(e) for e in self.load(MULTI).rules]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
