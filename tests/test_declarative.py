# SPDX-License-Identifier: MIT
"""The YAML subset, and the front matter a rule file carries.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import tempfile
import unittest

from ruleprobe.declarative import (DeclarativeError, load, parse, parse_with_lines,
                                   split_front_matter)


class ScalarTests(unittest.TestCase):
    def test_the_scalar_types_the_subset_has(self):
        self.assertEqual(parse("a: 1\nb: -2\nc: 1.5\nd: true\ne: false\nf: null\ng: ~\n"),
                         {"a": 1, "b": -2, "c": 1.5, "d": True, "e": False,
                          "f": None, "g": None})

    def test_a_plain_scalar_is_a_string_and_keeps_its_punctuation(self):
        self.assertEqual(parse("a: sk-[A-Za-z0-9]{20,}\n"), {"a": "sk-[A-Za-z0-9]{20,}"})
        self.assertEqual(parse("a: --no-verify\n"), {"a": "--no-verify"})

    def test_a_single_quoted_string_is_literal_and_doubles_its_quote(self):
        self.assertEqual(parse("a: 'x: y'\nb: 'it''s'\nc: '\\n'\n"),
                         {"a": "x: y", "b": "it's", "c": "\\n"})

    def test_a_double_quoted_string_takes_the_json_escapes(self):
        self.assertEqual(parse('a: "x\\ny"\nb: "a\\\\d+"\nc: "say \\"hi\\""\n'),
                         {"a": "x\ny", "b": "a\\d+", "c": 'say "hi"'})

    def test_a_case_insensitive_constant_is_still_a_constant(self):
        self.assertEqual(parse("a: TRUE\nb: Null\n"), {"a": True, "b": None})

    def test_a_quoted_constant_stays_a_string(self):
        self.assertEqual(parse("a: 'true'\nb: \"1\"\n"), {"a": "true", "b": "1"})


class BlockTests(unittest.TestCase):
    def test_a_nested_mapping_and_sequence(self):
        text = ("detectors:\n"
                "  - id: a/b\n"
                "    when:\n"
                "      command:\n"
                "        starts_with:\n"
                "          - sudo\n"
                "          - pip\n")
        self.assertEqual(parse(text), {"detectors": [
            {"id": "a/b", "when": {"command": {"starts_with": ["sudo", "pip"]}}}]})

    def test_a_sequence_may_sit_at_its_key_s_own_indentation(self):
        self.assertEqual(parse("a:\n- 1\n- 2\nb: 3\n"), {"a": [1, 2], "b": 3})

    def test_a_key_with_nothing_under_it_is_null(self):
        self.assertEqual(parse("a:\nb: 1\n"), {"a": None, "b": 1})

    def test_a_sequence_of_sequences(self):
        self.assertEqual(parse("- - 1\n  - 2\n- - 3\n"), [[1, 2], [3]])

    def test_comments_and_blank_lines_are_not_content(self):
        self.assertEqual(parse("# lead\n\na: 1  # trailing\n\n# tail\n"), {"a": 1})

    def test_a_hash_inside_a_quote_or_a_word_is_data(self):
        self.assertEqual(parse("a: '# 1'\nb: --exclude=#tmp\n"),
                         {"a": "# 1", "b": "--exclude=#tmp"})

    def test_an_empty_document_is_none(self):
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("# only a comment\n"))


class FlowTests(unittest.TestCase):
    def test_a_flow_mapping_and_a_flow_sequence_on_one_line(self):
        self.assertEqual(parse("when: {command: {starts_with: [sudo, pip]}}\n"),
                         {"when": {"command": {"starts_with": ["sudo", "pip"]}}})

    def test_a_flow_sequence_of_mappings(self):
        self.assertEqual(parse("any: [{tool: Write}, {tool: Edit}]\n"),
                         {"any": [{"tool": "Write"}, {"tool": "Edit"}]})

    def test_a_quoted_string_in_flow_keeps_its_commas_and_colons(self):
        self.assertEqual(parse('a: ["x,y", "p: q"]\n'), {"a": ["x,y", "p: q"]})

    def test_a_plain_flow_scalar_may_hold_a_space_as_yaml_has_it(self):
        self.assertEqual(parse("a: [git commit, ls]\n"), {"a": ["git commit", "ls"]})

    def test_an_empty_flow_collection(self):
        self.assertEqual(parse("a: []\nb: {}\n"), {"a": [], "b": {}})


class RefusalTests(unittest.TestCase):
    """Every unsupported YAML feature is refused by name. A wrong parse is worse than no
    parse: a detector that silently means something else never fires and never says so."""

    CASES = [
        ("a: &x 1\n", 1, "anchors"),
        ("a: *x\n", 1, "aliases"),
        ("a: !!str 1\n", 1, "tags"),
        ("a: |\n  text\n", 1, "block scalars"),
        ("a: >\n  text\n", 1, "folded"),
        ("%YAML 1.2\na: 1\n", 1, "directives"),
        ("a: 1\n---\nb: 2\n", 2, "more than one document"),
        ("a: 1\n  b: 2\n", 2, "unexpected indentation"),
        ("\ta: 1\n", 1, "tab"),
        ("a: 1\na: 2\n", 2, "duplicate key"),
        ("a: 'unterminated\n", 1, "unterminated quoted string"),
        ("a: [1, 2\n", 1, "unterminated flow collection"),
        ("plain text\n", 1, "expected 'key: value'"),
        ("a: [1] junk\n", 1, "trailing text"),
    ]

    def test_each_refusal_names_its_line_and_its_reason(self):
        for text, line, reason in self.CASES:
            with self.subTest(text=text.strip()[:24]):
                with self.assertRaises(DeclarativeError) as caught:
                    parse(text, "detectors.yaml")
                self.assertEqual(caught.exception.line, line)
                self.assertIn(reason, caught.exception.reason)
                self.assertIn("detectors.yaml:%d" % line, str(caught.exception))

    def test_nesting_deeper_than_the_cap_is_refused_rather_than_recursed(self):
        text = "".join("%sa:\n" % ("  " * i) for i in range(64))
        with self.assertRaises(DeclarativeError):
            parse(text)

    def test_text_that_is_not_text_is_a_finding_and_not_a_type_error(self):
        with self.assertRaises(DeclarativeError):
            parse(b"a: 1")


class LineTests(unittest.TestCase):
    def test_every_mapping_key_carries_the_line_it_was_written_on(self):
        value, lines = parse_with_lines("a: 1\nb:\n  - id: x\n    when: y\n")
        self.assertEqual(lines.line_of(value, "a"), 1)
        self.assertEqual(lines.line_of(value, "b"), 2)
        self.assertEqual(lines.line_of(value["b"][0], "when"), 4)

    def test_front_matter_lines_are_the_lines_of_the_file_it_came_from(self):
        front, first, _body = split_front_matter("---\nrule: a\ndetector: x\n---\nbody\n")
        value, lines = parse_with_lines(front, "rule.md", first)
        self.assertEqual(lines.line_of(value, "detector"), 3)


class FrontMatterTests(unittest.TestCase):
    def test_front_matter_is_split_from_the_body(self):
        front, first, body = split_front_matter("---\nrule: a\n---\n# Heading\n")
        self.assertEqual((front, first, body), ("rule: a", 2, "# Heading\n"))

    def test_a_file_with_no_front_matter_is_all_body(self):
        front, _first, body = split_front_matter("# Heading\n---\nnot front matter\n")
        self.assertIsNone(front)
        self.assertTrue(body.startswith("# Heading"))

    def test_an_unterminated_block_is_not_front_matter(self):
        self.assertIsNone(split_front_matter("---\nrule: a\n")[0])

    def test_a_dotted_terminator_ends_it_too(self):
        self.assertEqual(split_front_matter("---\nrule: a\n...\nbody\n")[0], "rule: a")


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ruleprobe-")

    def tearDown(self):
        for name in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, name))
        os.rmdir(self.dir)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_json_and_the_yaml_subset_load_to_the_same_objects(self):
        document = {"detectors": [{"id": "a/b", "when": {"tool": {"name": "Bash"}}}]}
        as_json, _ = load(self.write("d.json", json.dumps(document)))
        as_yaml, _ = load(self.write("d.yaml", "detectors:\n  - id: a/b\n"
                                               "    when: {tool: {name: Bash}}\n"))
        self.assertEqual(as_json, document)
        self.assertEqual(as_yaml, document)

    def test_invalid_json_is_a_finding_with_a_line(self):
        with self.assertRaises(DeclarativeError) as caught:
            load(self.write("d.json", '{"detectors": [}'))
        self.assertIn("invalid JSON", caught.exception.reason)

    def test_a_missing_file_is_the_same_kind_of_error_as_a_bad_one(self):
        with self.assertRaises(DeclarativeError):
            load(os.path.join(self.dir, "absent.yaml"))


if __name__ == "__main__":
    unittest.main()
