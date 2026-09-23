# SPDX-License-Identifier: MIT
"""`schema_version` on a detector entry, and a file's top-level `version` as its default.

An entry names the schema it was written under, a file names one for the entries that do
not, and absent both it is 1. A value the package does not know is a finding with a line,
and only the entries that would be read under it are skipped.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import tempfile
import unittest

from ruleprobe.declarative import DeclarativeError, load, parse_with_lines
from ruleprobe import matchers
from ruleprobe.matchers import ENTRY_KEYS, compile_detector
from ruleprobe.registry import KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION
from ruleprobe.rules import load_bundle, load_file, read_rule_file

WHEN = {"tool": "Write"}

#: Every shape of value that is not a known schema version, by name, as YAML text.
BAD = (
    ("above the highest known", str(SCHEMA_VERSION + 1), "newer than this ruleprobe"),
    ("zero", "0", "they start at 1"),
    ("negative", "-1", "they start at 1"),
    ("string", '"2"', "must be an integer"),
    ("float", "2.0", "must be an integer"),
    ("boolean", "true", "must be an integer"),
)


def _value(text):
    document, _ = parse_with_lines("v: %s\n" % text, "<test>")
    return document["v"]


class EntryTests(unittest.TestCase):
    def test_the_key_is_part_of_the_format(self):
        self.assertIn("schema_version", ENTRY_KEYS)
        self.assertEqual((SCHEMA_VERSION, KNOWN_SCHEMA_VERSIONS), (2, (1, 2)))

    def test_entry_validation_reads_the_one_registry_constant(self):
        self.assertIs(matchers.KNOWN_SCHEMA_VERSIONS, KNOWN_SCHEMA_VERSIONS)

    def test_an_entry_with_no_key_compiles(self):
        detector = compile_detector({"id": "t/x", "when": WHEN}, "<test>")
        self.assertEqual(detector.id, "t/x")

    def test_every_known_version_loads(self):
        for version in range(1, SCHEMA_VERSION + 1):
            with self.subTest(version=version):
                spec = {"id": "t/x", "when": WHEN, "schema_version": version}
                self.assertEqual(compile_detector(spec, "<test>").id, "t/x")

    def test_each_unknown_value_shape_is_an_error_on_the_key_s_line(self):
        for name, text, reason in BAD:
            with self.subTest(shape=name):
                source = ("detectors:\n"
                          "  - id: t/x\n"
                          "    when: {tool: Write}\n"
                          "    schema_version: %s\n" % text)
                document, lines = parse_with_lines(source, "detectors.yaml")
                with self.assertRaises(DeclarativeError) as caught:
                    compile_detector(document["detectors"][0], "detectors.yaml", lines)
                self.assertIn(reason, caught.exception.reason)
                self.assertEqual(caught.exception.line, 4)

    def test_the_bad_values_parse_to_the_shapes_they_name(self):
        shapes = dict((name, _value(text)) for name, text, _ in BAD)
        self.assertIs(type(shapes["string"]), str)
        self.assertIs(type(shapes["float"]), float)
        self.assertIs(shapes["boolean"], True)
        self.assertEqual((shapes["zero"], shapes["negative"]), (0, -1))


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class FileVersionTests(Temp):
    def load(self, text):
        detectors, findings = load_file(self.write("detectors.yaml", text))
        return [d.id for d in detectors], findings

    def test_a_file_with_no_version_loads_its_entries(self):
        ids, findings = self.load("detectors:\n"
                                  "  - id: a/one\n"
                                  "    when: {tool: Write}\n")
        self.assertEqual((ids, findings), (["a/one"], []))

    def test_a_known_file_version_loads_its_entries(self):
        for version in range(1, SCHEMA_VERSION + 1):
            with self.subTest(version=version):
                ids, findings = self.load("version: %d\n"
                                          "detectors:\n"
                                          "  - id: a/one\n"
                                          "    when: {tool: Write}\n" % version)
                self.assertEqual((ids, findings), (["a/one"], []))

    def test_each_unknown_file_version_skips_only_the_entries_that_take_it(self):
        for name, text, reason in BAD:
            with self.subTest(shape=name):
                ids, findings = self.load("# a comment first\n"
                                          "version: %s\n"
                                          "detectors:\n"
                                          "  - id: a/defaulted\n"
                                          "    when: {tool: Write}\n"
                                          "  - id: a/own\n"
                                          "    schema_version: 2\n"
                                          "    when: {tool: Edit}\n" % text)
                self.assertEqual(ids, ["a/own"])
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].line, 2)
                self.assertTrue(findings[0].path.endswith("detectors.yaml"))
                self.assertIn(reason, findings[0].reason)
                self.assertIn("version", findings[0].reason)

    def test_each_unknown_entry_version_skips_that_entry_and_the_rest_still_load(self):
        for name, text, reason in BAD:
            with self.subTest(shape=name):
                ids, findings = self.load("detectors:\n"
                                          "  - id: a/first\n"
                                          "    when: {tool: Write}\n"
                                          "  - id: a/bad\n"
                                          "    schema_version: %s\n"
                                          "    when: {tool: Edit}\n"
                                          "  - id: a/last\n"
                                          "    when: {tool: Read}\n" % text)
                self.assertEqual(ids, ["a/first", "a/last"])
                self.assertEqual([f.line for f in findings], [5])
                self.assertIn(reason, findings[0].reason)

    def test_a_bad_entry_under_a_bad_file_version_is_its_own_finding(self):
        ids, findings = self.load("version: 9\n"
                                  "detectors:\n"
                                  "  - id: a/bad\n"
                                  "    schema_version: 0\n"
                                  "    when: {tool: Edit}\n")
        self.assertEqual(ids, [])
        self.assertEqual([f.line for f in findings], [1, 4])

    def test_a_json_file_reads_the_same_way(self):
        document = {"version": 3, "detectors": [
            {"id": "a/defaulted", "when": WHEN},
            {"id": "a/own", "schema_version": 1, "when": WHEN}]}
        detectors, findings = load_file(self.write("detectors.json", json.dumps(document)))
        self.assertEqual([d.id for d in detectors], ["a/own"])
        self.assertEqual(len(findings), 1)
        self.assertIn("newer than this ruleprobe", findings[0].reason)

    def test_the_shipped_file_s_version_is_read_and_known(self):
        common = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "ruleprobe", "detectors", "common.yaml")
        detectors, findings = load_file(common)
        self.assertTrue(detectors)
        self.assertEqual(findings, [])
        document, _ = load(common)
        document["version"] = 9
        detectors, findings = load_file(self.write("common.json", json.dumps(document)))
        self.assertEqual(detectors, [])
        self.assertEqual(len(findings), 1)
        self.assertIn("version 9 is newer", findings[0].reason)

    def test_a_top_level_schema_version_is_a_finding_not_a_silent_schema_one(self):
        ids, findings = self.load("schema_version: 2\n"
                                  "detectors:\n"
                                  "  - id: a/defaulted\n"
                                  "    when: {tool: Write}\n"
                                  "  - id: a/own\n"
                                  "    schema_version: 2\n"
                                  "    when: {tool: Edit}\n")
        self.assertEqual(ids, ["a/own"])
        self.assertEqual([f.line for f in findings], [1])
        self.assertIn("the file-level key is `version`", findings[0].reason)

    def test_the_finding_counts_and_names_the_entries_it_skipped(self):
        ids, findings = self.load("version: 9\n"
                                  "detectors:\n"
                                  "  - id: a/one\n"
                                  "    when: {tool: Write}\n"
                                  "  - when: {tool: Read}\n"
                                  "  - id: a/own\n"
                                  "    schema_version: 2\n"
                                  "    when: {tool: Edit}\n"
                                  "  - id: a/two\n"
                                  "    when: {tool: Grep}\n")
        self.assertEqual(ids, ["a/own"])
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].reason.endswith(
            "; skipped 3 entries without their own schema_version: a/one, a/two"),
            findings[0].reason)

    def test_a_top_level_schema_version_and_a_bad_version_are_both_reported(self):
        ids, findings = self.load("schema_version: 2\n"
                                  "version: 9\n"
                                  "detectors:\n"
                                  "  - id: a/one\n"
                                  "    when: {tool: Write}\n")
        self.assertEqual(ids, [])
        self.assertEqual([f.line for f in findings], [1, 2])
        self.assertIn("the file-level key is `version`", findings[0].reason)
        self.assertIn("version 9 is newer", findings[1].reason)
        for finding in findings:
            self.assertIn("skipped 1 entry without their own schema_version: a/one",
                          finding.reason)

    def test_a_non_mapping_entry_under_a_bad_file_version_keeps_its_own_finding(self):
        ids, findings = self.load("version: 9\n"
                                  "detectors:\n"
                                  "  - just a string\n"
                                  "  - id: a/own\n"
                                  "    schema_version: 1\n"
                                  "    when: {tool: Edit}\n")
        self.assertEqual(ids, ["a/own"])
        self.assertEqual(len(findings), 2)
        self.assertIn("a detector entry is a mapping", findings[1].reason)

    def test_discovery_reports_the_finding_and_keeps_the_rest(self):
        repo = os.path.join(self.dir, "repo")
        os.makedirs(os.path.join(repo, ".ruleprobe"))
        with open(os.path.join(repo, ".ruleprobe", "detectors.yaml"), "w",
                  encoding="utf-8") as handle:
            handle.write("version: 3\n"
                         "detectors:\n"
                         "  - id: a/defaulted\n"
                         "    when: {tool: Write}\n"
                         "  - id: a/own\n"
                         "    schema_version: 2\n"
                         "    when: {tool: Edit}\n")
        bundle = load_bundle(cwd=repo, user=False)
        self.assertEqual([d.id for d in bundle.detectors], ["a/own"])
        self.assertEqual([(f.line, f.reason.split(" ")[0]) for f in bundle.findings],
                         [(1, "version")])


class FrontMatterTests(Temp):
    def test_a_bad_schema_version_on_a_front_matter_entry_is_a_finding(self):
        path = self.write("house-style.md", "---\n"
                                            "rule: house-style\n"
                                            "detector:\n"
                                            "  id: house-style/npm\n"
                                            "  schema_version: 3\n"
                                            "  when: {tool: Write}\n"
                                            "---\n"
                                            "\n"
                                            "Use uv.\n")
        detectors, entry, findings = read_rule_file(path)
        self.assertEqual((detectors, entry.state), ([], "unmeasured"))
        self.assertEqual([f.line for f in findings], [5])
        self.assertIn("newer than this ruleprobe", findings[0].reason)

    def test_front_matter_version_is_not_a_file_level_default(self):
        path = self.write("house-style.md", "---\n"
                                            "version: 9\n"
                                            "detector:\n"
                                            "  id: house-style/npm\n"
                                            "  when: {tool: Write}\n"
                                            "---\n")
        detectors, entry, findings = read_rule_file(path)
        self.assertEqual(([d.id for d in detectors], findings), (["house-style/npm"], []))


if __name__ == "__main__":
    unittest.main()
