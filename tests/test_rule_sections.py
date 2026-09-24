# SPDX-License-Identifier: MIT
"""A rule file that nothing in its front matter binds is split at its headings, one rule per
section; a file bound in its front matter stays one rule.

Run: python3 -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

from ruleprobe.rules import (Bundle, RuleEntry, load_bundle, read_rule_file, _sections,
                             _slug)
from ruleprobe.cli import main
from test_readers import FIXTURES

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
        # "Install with uv, never with sudo pip" is a catalog shape; the other two are not.
        self.assertEqual([(e.state, e.source) for e in entries],
                         [("unmeasured", None), ("measured", "catalog"), ("unmeasured", None)])
        bundle = Bundle(rules=entries)
        self.assertEqual(bundle.counts(), {"measured": 1, "dark": 0, "unmeasured": 2})
        self.assertIn("rules: 1 measured, 0 dark, 2 unmeasured", bundle.summary())

    def test_a_hash_line_inside_a_fence_does_not_start_a_section(self):
        headings = [h for h, _index, _rule in _sections(text("sectioned.md"))]
        self.assertNotIn("Not a heading: this line sits inside a fenced block.", headings)
        self.assertEqual(len(headings), 5)

    def test_a_heading_fence_table_or_blockquote_alone_is_not_a_rule(self):
        _detectors, entries, findings = read_rule_file(fixture("non-rules.md"), root=RULES)
        self.assertEqual(([e.rule for e in entries], findings), (["non-rules.md#a-rule"], []))
        units = _sections(text("non-rules.md"))
        self.assertEqual([(h, rule) for h, _index, rule in units],
                         [("Only a heading", False), ("Only a fence", False),
                          ("Only a table", False), ("Only a table without edge pipes", False),
                          ("Only a blockquote", False), ("Only a thematic break", False),
                          ("Only an underscore break", False), ("Only a spaced break", False),
                          ("A rule", True)])

    def test_an_html_comment_is_never_text_and_never_a_heading(self):
        units = _sections("# A\n\n<!-- a note -->\n\n# B\n\n<!--\n# x\nhidden\n-->\n\n"
                         "# B\n\nReal text.\n")
        self.assertEqual(units, [("A", 0, False), ("B", 4, False), ("B", 11, True)])

    def test_an_indented_code_block_after_a_blank_line_is_code(self):
        self.assertEqual(_sections("# A\n\n    make test\n\n    make lint\n"),
                         [("A", 0, False)])
        self.assertEqual(_sections("# A\n\nText,\n    continued.\n"), [("A", 0, True)])

    def test_a_bullet_after_a_quote_is_not_part_of_the_quote(self):
        self.assertEqual(_sections("# A\n\n> Quoted.\n- Pin tools.\n"), [("A", 0, True)])

    def test_text_after_a_comment_closes_is_text(self):
        self.assertEqual(_sections("# A\n\n<!--\nnote\n--> Pin tools.\n"), [("A", 0, True)])
        self.assertEqual(_sections("# A\n\n<!-- note --> Pin tools.\n"), [("A", 0, True)])

    def test_a_comment_opened_mid_line_hides_the_heading_inside_it(self):
        self.assertEqual(_sections("# A\n\nPin tools. <!--\n# x\n-->\n"), [("A", 0, True)])

    def test_indented_code_right_after_a_fence_or_a_comment_is_code(self):
        self.assertEqual(_sections("# A\n\n```\nx\n```\n    make\n"), [("A", 0, False)])
        self.assertEqual(_sections("# A\n\n<!-- x -->\n    make\n"), [("A", 0, False)])

    def test_indented_code_under_a_heading_and_over_several_lines_is_code(self):
        self.assertEqual(_sections("# A\n    make test\n    make lint\n        nested\n"),
                         [("A", 0, False)])

    def test_an_image_or_a_link_reference_alone_is_not_text(self):
        self.assertEqual(_sections("# A\n\n![Build](https://example.test/b.svg) "
                                   "[![Docs](d.svg)](https://example.test)\n\n"
                                   "[docs]: https://example.test \"Docs\"\n"),
                         [("A", 0, False)])
        self.assertEqual(_sections("# A\n\nSee ![a diagram](d.svg) first.\n"),
                         [("A", 0, True)])

    def test_the_fence_branches(self):
        self.assertEqual(_sections("# A\n\n~~~\n```\n# x\n~~~\n"), [("A", 0, False)])
        self.assertEqual(_sections("# A\n\n````\n```\n# x\n````\n"), [("A", 0, False)])
        self.assertEqual(_sections("# A\n\n```x``` is inline code.\n"), [("A", 0, True)])

    def test_a_table_without_edge_pipes_takes_every_body_row(self):
        self.assertEqual(_sections("# A\n\nTool | Use\n--- | ---\nuv | yes\npip | no\n"
                                   "tox | no\n"), [("A", 0, False)])
        self.assertEqual(_sections("# A\n\na | b\n--- | ---\nc | d\n\nPin tools.\n"),
                         [("A", 0, True)])

    def test_crlf_input_finds_its_headings_and_its_collision_lines(self):
        directory = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "x.md")
        with open(path, "wb") as handle:
            handle.write(b"# A\r\n\r\nOne.\r\n\r\n# A 2\r\n\r\nTwo.\r\n\r\n"
                         b"# A\r\n\r\nThree.\r\n")
        _detectors, entries, findings = read_rule_file(path, root=directory)
        self.assertEqual([e.rule for e in entries], ["x.md#a", "x.md#a-2", "x.md#a-2"])
        self.assertEqual([f.line for f in findings], [9])

    def test_an_undecodable_file_is_one_unreadable_rule_and_one_finding(self):
        directory = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, directory, True)
        with open(os.path.join(directory, "bad.md"), "wb") as handle:
            handle.write(b"# A\n\n\xff\xfe not utf-8\n")
        bundle = load_bundle(rules_dir=directory, config=False)
        self.assertEqual([(r.rule, r.state, r.reason) for r in bundle.rules],
                         [("bad", "unmeasured", "unreadable")])
        self.assertEqual(len(bundle.findings), 1)
        self.assertIn("unreadable", bundle.summary(relative_to=directory))

    def test_report_counts_the_sectioned_fixture_as_three_rules(self):
        directory = tempfile.mkdtemp(prefix="ruleprobe-")
        self.addCleanup(shutil.rmtree, directory, True)
        shutil.copy(fixture("sectioned.md"), directory)
        out, err = io.StringIO(), io.StringIO()
        saved, sys.stderr = sys.stderr, err
        try:
            code = main(["report", "--root", FIXTURES, "--no-config", "--rules", directory,
                         "--json"], out=out)
        finally:
            sys.stderr = saved
        self.assertEqual(code, 0)
        coverage = json.loads(out.getvalue())["coverage"]
        self.assertEqual((coverage["measured"], coverage["dark"], coverage["unmeasured"]),
                         (1, 0, 2))
        self.assertIn("rules: 1 measured, 0 dark, 2 unmeasured", err.getvalue())

    def test_a_non_rule_unit_is_in_no_state(self):
        bundle = Bundle(rules=read_rule_file(fixture("non-rules.md"), root=RULES)[1])
        self.assertEqual(sum(bundle.counts().values()), 1)

    def test_text_above_the_first_heading_belongs_to_no_section(self):
        self.assertEqual(_sections("A line with no heading above it.\n"), [])

    def test_the_directory_walk_lists_every_section_rule(self):
        bundle = load_bundle(rules_dir=RULES, config=False)
        self.assertIn("sectioned.md#pinning", [r.rule for r in bundle.rules])
        self.assertEqual(bundle.rules, load_bundle(rules_dir=RULES, config=False).rules)


class TempDir(unittest.TestCase):
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


class IdTests(TempDir):
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

    def test_a_heading_with_nothing_to_slug_is_a_section(self):
        path = self.write("x.md", "# !!!\n\nOne.\n\n# \U0001F680\n\nTwo.\n")
        self.assertEqual(self.ids(path), ["x.md#section", "x.md#section-2"])

    def test_a_byte_order_mark_does_not_hide_the_first_heading(self):
        path = self.write("x.md", "\ufeff# Testing\n\nRun it.\n")
        self.assertEqual(self.ids(path), ["x.md#testing"])

    def test_empty_front_matter_is_an_empty_mapping_and_the_file_splits(self):
        path = self.write("x.md", "---\n---\n# Testing\n\nRun it.\n")
        self.assertEqual(read_rule_file(path, root=self.dir)[1:],
                         ([RuleEntry("x.md#testing", path, "unmeasured", "", [])], []))

    def test_a_rule_name_on_a_split_file_is_a_finding(self):
        path = self.write("x.md", "---\nrule: a/b\n---\n# Testing\n\nRun it.\n")
        _detectors, entries, findings = read_rule_file(path, root=self.dir)
        self.assertEqual([e.rule for e in entries], ["x.md#testing"])
        self.assertEqual([(f.line, f.reason) for f in findings],
                         [(2, "rule: does not apply to a file split at its headings; its "
                              "rules are named by path and heading")])

    def test_a_collision_reaches_the_bundle_s_findings(self):
        self.write("rules/x.md", "# A\n\nOne.\n\n# A 2\n\nTwo.\n\n# A\n\nThree.\n")
        bundle = load_bundle(rules_dir=os.path.join(self.dir, "rules"), config=False)
        self.assertEqual([(f.line, f.reason) for f in bundle.findings],
                         [(9, "the section id x.md#a-2 is already taken in this file")])
        self.assertIn("findings: 1 (everything else still loaded)",
                      bundle.summary(relative_to=self.dir))

    def test_a_link_target_and_emphasis_stay_out_of_a_slug(self):
        self.assertEqual([_slug(h) for h in ("See [the docs](https://x.y)", "*Always* _test_",
                                             "**Bold** and [ref][1]", "snake_case stays")],
                         ["see-the-docs", "always-test", "bold-and-ref", "snake_case-stays"])

    def test_slug(self):
        self.assertEqual([_slug(h) for h in ("Testing", "  Pull requests ", "C++ & you",
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


class SingleRulePathTests(TempDir):
    """A headed file that takes a one-rule path stays one rule, whatever its sections."""

    TWO = "# One\n\nFirst.\n\n# Two\n\nSecond.\n"

    def entries(self, front):
        path = self.write("x.md", "---\n%s---\n%s" % (front, self.TWO))
        return [(e.rule, e.state, e.reason) for e in read_rule_file(path, root=self.dir)[1]]

    def test_front_matter_that_does_not_parse(self):
        self.assertEqual(self.entries("rule: a\n  bad: x\n"),
                         [("x", "unmeasured", "front matter did not parse")])

    def test_front_matter_that_is_a_list(self):
        self.assertEqual(self.entries("- a\n"),
                         [("x", "unmeasured", "front matter is not a mapping")])

    def test_a_detector_that_does_not_compile(self):
        self.assertEqual(self.entries("detector:\n  when: {comand: cat}\n"),
                         [("x", "unmeasured", "its detector did not compile")])

    def bare(self, key):
        path = self.write("x.md", "---\nowner: docs\n%s:\n---\n%s" % (key, self.TWO))
        _detectors, entries, findings = read_rule_file(path, root=self.dir)
        return [e.rule for e in entries], [(f.line, f.reason) for f in findings]

    def test_a_bare_opt_out_key_binds_nothing_and_is_a_finding(self):
        self.assertEqual(self.bare("opt_out"),
                         (["x.md#one", "x.md#two"],
                          [(3, "opt_out: has no value, so it binds nothing")]))

    def test_a_bare_detector_key_binds_nothing_and_is_a_finding(self):
        self.assertEqual(self.bare("detector"),
                         (["x.md#one", "x.md#two"],
                          [(3, "detector: has no value, so it binds nothing")]))

    def test_a_bare_detectors_key_binds_nothing_and_is_a_finding(self):
        self.assertEqual(self.bare("detectors"),
                         (["x.md#one", "x.md#two"],
                          [(3, "detectors: has no value, so it binds nothing")]))

    def test_a_bare_opt_out_on_a_heading_less_file_stays_unmeasured(self):
        path = self.write("x.md", "---\nopt_out:\n---\nOne rule.\n")
        self.assertEqual([(e.rule, e.state) for e in read_rule_file(path)[1]],
                         [("x", "unmeasured")])

    def test_comment_only_front_matter_is_an_empty_mapping(self):
        path = self.write("x.md", "---\n# owned by docs\n---\n%s" % self.TWO)
        self.assertEqual(read_rule_file(path, root=self.dir)[1:],
                         ([RuleEntry("x.md#one", path, "unmeasured", "", []),
                           RuleEntry("x.md#two", path, "unmeasured", "", [])], []))

    def test_a_headed_file_with_no_rule_section_stays_one_rule(self):
        path = self.write("tools.md", "---\nrule: tools\n---\n# Tools\n\n```sh\nmake\n```\n")
        self.assertEqual(read_rule_file(path, root=self.dir)[1:],
                         ([RuleEntry("tools", path, "unmeasured", "no section is a rule", [])],
                          []))


class CoverageBlockTests(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_a_long_section_id_prints_whole_and_the_column_widens_to_it(self):
        long_id = "team/CLAUDE.md#read-credentials-from-the-environment-never-inline"
        bundle = Bundle(rules=[RuleEntry("short", "a.md", "unmeasured", "", []),
                               RuleEntry(long_id, "b.md", "unmeasured", "", [])])
        rows = bundle.summary(relative_to=os.getcwd()).split("\n")[1:]
        self.assertIn("  unmeasured %s b.md" % long_id, rows)
        self.assertEqual(rows[0].index("a.md"), rows[1].index("b.md"))

    def test_short_ids_keep_the_old_column(self):
        bundle = Bundle(rules=[RuleEntry("short", "a.md", "dark", "", [])])
        self.assertEqual(bundle.summary(relative_to=os.getcwd()).split("\n")[1],
                         "  dark       short                       a.md")

    def test_the_readme_quotes_every_line_of_the_example_coverage_block(self):
        bundle = load_bundle(rules_dir=os.path.join(self.ROOT, "docs", "rules"), config=False)
        printed = bundle.summary(relative_to=self.ROOT).split("\n")
        with open(os.path.join(self.ROOT, "README.md"), encoding="utf-8") as handle:
            readme = handle.read().split("\n")
        start = readme.index(printed[0])
        self.assertEqual(readme[start:start + len(printed)], printed)


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
