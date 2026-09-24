# SPDX-License-Identifier: MIT
"""A rule file that nothing in its front matter binds is split at its headings, one rule per
section; a file bound in its front matter stays one rule.

Run: python3 -m unittest discover -s tests
"""
import os
import shutil
import tempfile
import unittest

from ruleprobe.rules import (Bundle, RuleEntry, load_bundle, read_rule_file, sections,
                             slug)

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "rules")


def fixture(name):
    return os.path.join(RULES, name)


def text(name):
    with open(fixture(name), encoding="utf-8") as handle:
        return handle.read()


class SplitTests(unittest.TestCase):
    def test_three_rule_sections_and_a_fenced_example_are_three_rules(self):
        detectors, entries, findings = read_rule_file(fixture("sectioned.md"), root=RULES)
        self.assertEqual((detectors, findings), ([], []))
        self.assertEqual([e.rule for e in entries],
                         ["sectioned.md#testing", "sectioned.md#dependencies",
                          "sectioned.md#pinning"])
        self.assertEqual(set(e.state for e in entries), {"unmeasured"})
        bundle = Bundle(rules=entries)
        self.assertEqual(bundle.counts(), {"measured": 0, "dark": 0, "unmeasured": 3})
        self.assertIn("rules: 0 measured, 0 dark, 3 unmeasured", bundle.summary())

    def test_a_hash_line_inside_a_fence_does_not_start_a_section(self):
        headings = [h for h, _index, _rule in sections(text("sectioned.md"))]
        self.assertNotIn("Not a heading: this line sits inside a fenced block.", headings)
        self.assertEqual(len(headings), 5)

    def test_a_heading_fence_table_or_blockquote_alone_is_not_a_rule(self):
        _detectors, entries, findings = read_rule_file(fixture("non-rules.md"), root=RULES)
        self.assertEqual(([e.rule for e in entries], findings), (["non-rules.md#a-rule"], []))
        units = sections(text("non-rules.md"))
        self.assertEqual([(h, rule) for h, _index, rule in units],
                         [("Only a heading", False), ("Only a fence", False),
                          ("Only a table", False), ("Only a table without edge pipes", False),
                          ("Only a blockquote", False), ("Only a thematic break", False),
                          ("A rule", True)])

    def test_a_non_rule_unit_is_in_no_state(self):
        bundle = Bundle(rules=read_rule_file(fixture("non-rules.md"), root=RULES)[1])
        self.assertEqual(sum(bundle.counts().values()), 1)

    def test_text_above_the_first_heading_belongs_to_no_section(self):
        self.assertEqual(sections("A line with no heading above it.\n"), [])

    def test_the_directory_walk_lists_every_section_rule(self):
        bundle = load_bundle(rules_dir=RULES, config=False)
        self.assertIn("sectioned.md#pinning", [r.rule for r in bundle.rules])
        self.assertEqual(bundle.rules, load_bundle(rules_dir=RULES, config=False).rules)


class IdTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, relative, text):
        path = os.path.join(self.dir, relative)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def ids(self, path):
        return [e.rule for e in read_rule_file(path, root=self.dir)[1]]

    def test_an_id_is_the_path_under_the_rules_directory_and_the_heading_slug(self):
        path = self.write("team/AGENTS.md", "## Use `uv`, not pip!\n\nInstall with uv.\n")
        self.assertEqual(self.ids(path), ["team/AGENTS.md#use-uv-not-pip"])

    def test_without_a_root_an_id_is_relative_to_the_file_s_own_directory(self):
        path = self.write("team/AGENTS.md", "## Testing\n\nRun the suite.\n")
        self.assertEqual([e.rule for e in read_rule_file(path)[1]], ["AGENTS.md#testing"])

    def test_an_id_is_unchanged_after_a_section_above_it_is_edited(self):
        path = self.write("CLAUDE.md", "## Style\n\nShort lines.\n\n## Testing\n\nRun it.\n")
        before = self.ids(path)[-1]
        self.write("CLAUDE.md", "## Layout\n\nShorter lines,\nand fewer of them.\n\n"
                                "## New section\n\nAdded above.\n\n## Testing\n\nRun it.\n")
        self.assertEqual((before, self.ids(path)[-1]), ("CLAUDE.md#testing",) * 2)

    def test_a_repeated_slug_takes_an_ordinal_and_a_remaining_collision_is_a_finding(self):
        _detectors, entries, findings = read_rule_file(fixture("duplicates.md"), root=RULES)
        self.assertEqual([e.rule for e in entries],
                         ["duplicates.md#testing", "duplicates.md#testing-2",
                          "duplicates.md#testing-2"])
        self.assertEqual([(f.line, f.reason) for f in findings],
                         [(9, "the section id duplicates.md#testing-2 is already taken "
                              "in this file")])

    def test_a_collision_line_counts_the_front_matter_above_the_body(self):
        path = self.write("x.md", "---\nowner: docs\n---\n# A\n\nOne.\n\n# A 2\n\nTwo.\n"
                                  "\n# A\n\nThree.\n")
        _detectors, entries, findings = read_rule_file(path, root=self.dir)
        self.assertEqual([e.rule for e in entries], ["x.md#a", "x.md#a-2", "x.md#a-2"])
        self.assertEqual([f.line for f in findings], [12])

    def test_an_ordinal_counts_headings_that_are_not_rules(self):
        path = self.write("x.md", "# Example\n\n```\nx\n```\n\n# Example\n\nA rule.\n")
        self.assertEqual(self.ids(path), ["x.md#example-2"])

    def test_slug(self):
        self.assertEqual([slug(h) for h in ("Testing", "  Pull requests ", "C++ & you",
                                            "snake_case-ok")],
                         ["testing", "pull-requests", "c--you", "snake_case-ok"])

    def test_a_heading_less_file_is_one_rule_named_for_the_file(self):
        path = self.write("rules/working-style.md", "Say when something did not work.\n")
        self.assertEqual(read_rule_file(path, root=self.dir)[1],
                         [RuleEntry("working-style", path, "unmeasured", "", [])])

    def test_a_heading_less_file_keeps_its_front_matter_name(self):
        path = self.write("x.md", "---\nrule: house-style\n---\nUse uv.\n")
        self.assertEqual([(e.rule, e.state) for e in read_rule_file(path)[1]],
                         [("house-style", "unmeasured")])

    def test_a_heading_inside_a_fence_does_not_make_a_file_headed(self):
        path = self.write("x.md", "Run it.\n\n```sh\n# a comment\n```\n")
        self.assertEqual(self.ids(path), ["x"])

    def test_text_above_the_first_heading_of_a_headed_file_is_no_rule(self):
        path = self.write("x.md", "Preamble text.\n\n# Testing\n\nRun it.\n")
        self.assertEqual(self.ids(path), ["x.md#testing"])

    def test_a_closing_hash_sequence_is_not_part_of_the_heading(self):
        path = self.write("x.md", "## Testing ##\n\nRun it.\n")
        self.assertEqual(self.ids(path), ["x.md#testing"])


class BoundFileTests(unittest.TestCase):
    def test_a_file_bound_in_front_matter_keeps_one_rule_with_its_old_id_and_state(self):
        detectors, entries, findings = read_rule_file(fixture("bound.md"), root=RULES)
        self.assertEqual((detectors, findings), ([], []))
        self.assertEqual([(e.rule, e.state, e.reason) for e in entries],
                         [("bound-example", "dark", "nothing in a transcript shows this")])

    def test_a_detector_bound_file_with_sections_stays_one_measured_rule(self):
        directory = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "style.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("---\ndetector:\n  id: style/write\n  when: {tool: Write}\n---\n"
                         "# One\n\nFirst.\n\n# Two\n\nSecond.\n")
        detectors, entries, findings = read_rule_file(path, root=directory)
        self.assertEqual(([d.id for d in detectors], findings), (["style/write"], []))
        self.assertEqual([(e.rule, e.state, e.detectors) for e in entries],
                         [("style", "measured", ["style/write"])])


if __name__ == "__main__":
    unittest.main()
