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
import unittest
import zipfile
from unittest import mock

from corpus import bash, say
from ruleprobe import DEFAULT, Registry, contract_data, run
from ruleprobe.cli import main
from ruleprobe.declarative import load
from ruleprobe.detectors import catalog
from ruleprobe.rules import Bundle, RuleEntry, _CATALOG, _catalog_matches, load_bundle
from ruleprobe.validity import DEFAULT_FLOOR, score_examples
from test_contract_data import non_literal
from test_readers import FIXTURES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_RULES = os.path.join(FIXTURES, "catalog")
IDS = [entry["detector"]["id"] for entry in catalog.ENTRIES]
#: The fixture's sections, in catalog order: section id and the entry it states.
FIXTURE = [("team/CLAUDE.md#testing", "testing/no-test-run"),
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

    def test_a_session_with_no_events_is_no_missing_test_run(self):
        self.assertEqual(self.hits("testing/no-test-run", []), [])
        self.assertTrue(self.hits("testing/no-test-run", [say("Done.")]))


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
                         ["testing/no-test-run"])

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


class LiteralTests(unittest.TestCase):
    def test_the_catalog_module_holds_only_literals(self):
        with open(inspect.getsourcefile(catalog), encoding="utf-8") as handle:
            self.assertEqual(non_literal(handle.read()), [])

    def test_the_entries_compile_with_compile_detector(self):
        self.assertEqual([d.id for _pattern, d in _CATALOG], IDS)


_ZIP_PROBE = r"""
import builtins, io, json, sys
zip_path, rules = sys.argv[1], sys.argv[2]
sys.path.insert(0, zip_path)
opened = []
real = builtins.open
def guarded(file, *args, **kwargs):
    opened.append(str(file))
    return real(file, *args, **kwargs)
builtins.open = io.open = guarded
from ruleprobe.detectors import catalog
from ruleprobe.rules import load_bundle
bundle = load_bundle(rules_dir=rules, config=False)
registry = bundle.registry()
print(json.dumps({"file": catalog.__file__, "opened": opened,
                  "bound": [d for r in bundle.rules for d in r.detectors],
                  "registered": [d for d in registry.ids()]}))
"""


class ZipTests(unittest.TestCase):
    def test_the_catalog_loads_from_a_zip_with_no_file_read_beside_it(self):
        tmp = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, tmp, True)
        archive = os.path.join(tmp, "ruleprobe.zip")
        package = os.path.join(ROOT, "ruleprobe")
        with zipfile.ZipFile(archive, "w") as handle:
            for base, dirs, files in os.walk(package):
                dirs[:] = sorted(d for d in dirs if d != "__pycache__")
                for name in sorted(files):
                    if name.endswith(".py"):
                        full = os.path.join(base, name)
                        handle.write(full, os.path.join(
                            "ruleprobe", os.path.relpath(full, package)).replace(os.sep, "/"))
        # -I and -S keep the checkout, PYTHONPATH and any installed copy off sys.path.
        result = subprocess.run([sys.executable, "-I", "-S", "-c", _ZIP_PROBE, archive,
                                 CATALOG_RULES], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertTrue(out["file"].startswith(archive + os.sep), out["file"])
        self.assertEqual(out["bound"], [did for _rule, did in FIXTURE])
        self.assertTrue(set(out["bound"]) <= set(out["registered"]))
        self.assertEqual(out["opened"], [os.path.join(CATALOG_RULES, "team", "CLAUDE.md")])


if __name__ == "__main__":
    unittest.main()
