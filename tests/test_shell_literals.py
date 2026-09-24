# SPDX-License-Identifier: MIT
"""An operator character that was quoted or escaped is a word, not an operator.

`find . \\( -name x \\)` is one command whose arguments include `(` and `)`; `(cd a && ls)` is
a subshell. The tokenizer hands back `(` for both, so the parse has to remember which was
which, in the segment split and in every helper that reads a segment. The same holds for a
quoted reserved word: `'done' x` runs a command named `done`.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import bash
from ruleprobe import DEFAULT, analyse, pipelines
from ruleprobe.rules import catalog_detectors
from ruleprobe.shell import Literal, _free_mark, has_redirect, normalise, operands, strip_comment, tokenize

GROUPED = "find App \\( -name '*.bak' \\)"
GROUPED_PIPED = "find App AppTests \\( -name '*.bak' -o -name '*.tmp' \\) | head"

#: `(shape, reference)`: the reference spells each quoted or escaped operator as a plain word,
#: so every detector has to treat the two alike.
EQUIVALENT = [
    (GROUPED, "find App LP -name '*.bak' RP"),
    (GROUPED_PIPED, "find App AppTests LP -name '*.bak' -o -name '*.tmp' RP | head"),
    ("find . \\( -name '*.bak' -o -name '*.tmp' \\) | head",
     "find . LP -name '*.bak' -o -name '*.tmp' RP | head"),
    ("find . '(' -type f ')'", "find . LP -type f RP"),
    ("find . -exec cat {} \\;", "find . -exec cat {} SEMI"),
    ("find . \\> out", "find . GT out"),
    ("echo a \\&\\& find .", "echo a AND find ."),
    ("echo \\; cat a.txt", "echo SEMI cat a.txt"),
    ("echo \\| cat a.txt", "echo BAR cat a.txt"),
    ("echo '|' cat a.txt", "echo BAR cat a.txt"),
    ("cat \\< a.txt", "cat LT a.txt"),
    ("git commit -m '(' --no-verify", "git commit -m LP --no-verify"),
    ("git commit -m \\) --no-verify", "git commit -m RP --no-verify"),
    ("git push --force origin main \"&\"", "git push --force origin main AMP"),
    ("pip install \"(\" requests", "pip install LP requests"),
    ("echo '&&' find .", "echo AND find ."),
    ("echo \\& find .", "echo AMP find ."),
    ("echo a \\& cat a.txt", "echo a AMP cat a.txt"),
]

#: `(command, the detector ids expected to hit)`: real operators still split.
REAL = [
    ("(cd a && find .)", {"transcript-hygiene/unfiltered-find"}),
    ("{ find .; }", {"transcript-hygiene/unfiltered-find"}),
    ("echo a && find .", {"transcript-hygiene/unfiltered-find"}),
    ("echo a; cat a.txt", {"transcript-hygiene/whole-file-cat"}),
    ("find . | head", set()),
    ("cat a.txt > b.txt", set()),
    ('echo "say \\"hi\\"" && find .', {"transcript-hygiene/unfiltered-find"}),
    ('echo "a\\\\" && cat a.txt', {"transcript-hygiene/whole-file-cat"}),
]


def every_detector():
    """The shipped detectors and the catalog's, ungated: a stance is not what is tested."""
    return list(DEFAULT) + catalog_detectors()


def hits(command):
    """The ids of every detector that hits a session of one Bash call to `command`."""
    ctx = analyse([bash(command)])
    return set(d.id for d in every_detector() if d.fn(ctx.events, ctx))


class LiteralParseTests(unittest.TestCase):
    def test_escaped_parentheses_stay_in_an_unpiped_find(self):
        self.assertEqual(pipelines(GROUPED),
                         [[["find", "App", "(", "-name", "*.bak", ")"]]])

    def test_escaped_parentheses_stay_in_a_piped_find(self):
        self.assertEqual(pipelines(GROUPED_PIPED),
                         [[["find", "App", "AppTests", "(", "-name", "*.bak", "-o", "-name",
                            "*.tmp", ")"], ["head"]]])

    def test_quoted_parentheses_are_words(self):
        self.assertEqual(pipelines("echo '(' \")\" x"), [[["echo", "(", ")", "x"]]])

    def test_escaped_operators_are_words(self):
        self.assertEqual(pipelines("echo \\| \\& \\< \\> \\; \\&\\& '||' \";;\" x"),
                         [[["echo", "|", "&", "<", ">", ";", "&&", "||", ";;", "x"]]])

    def test_an_escaped_semicolon_ends_no_command(self):
        self.assertEqual(pipelines("find . -exec cat {} \\; -print"),
                         [[["find", ".", "-exec", "cat", "{}", ";", "-print"]]])

    def test_a_literal_word_is_marked_and_still_a_string(self):
        word = tokenize("find . \\(")[2]
        self.assertIsInstance(word, Literal)
        self.assertEqual(word, "(")
        self.assertNotIsInstance(tokenize("(ls)")[0], Literal)

    def test_a_backslash_inside_double_quotes_is_kept(self):
        self.assertEqual(pipelines('echo "a\\(" b'), [[["echo", "a\\(", "b"]]])

    def test_an_escaped_backslash_leaves_the_pipe_real(self):
        self.assertEqual(pipelines("ls \\\\ | wc"), [[["ls", "\\"], ["wc"]]])

    def test_a_subshell_and_a_group_still_split(self):
        self.assertEqual(pipelines("(cd a && ls)"), [[["cd", "a"]], [["ls"]]])
        self.assertEqual(pipelines("{ ls; } | head"), [[["ls"]], [["head"]]])
        self.assertEqual(pipelines("echo \\(hi\\)"), [[["echo", "(hi)"]]])

    def test_a_literal_redirect_is_an_operand(self):
        segment = pipelines("cat \\> a.txt")[0][0]
        self.assertFalse(has_redirect(segment))
        self.assertEqual(operands(segment), [">", "a.txt"])
        self.assertTrue(has_redirect(pipelines("cat > a.txt")[0][0]))

    def test_every_quoted_or_escaped_operator_is_an_operand(self):
        for command, word in (("cat '(' a.txt", "("), ('cat "(" a.txt', "("),
                              ("cat \\< a.txt", "<"), ("cat \\| a.txt", "|")):
            with self.subTest(command=command):
                segment = pipelines(command)[0][0]
                self.assertFalse(has_redirect(segment))
                self.assertEqual(operands(segment), [word, "a.txt"])

    def test_an_escape_inside_double_quotes_keeps_the_quote_open(self):
        self.assertEqual(pipelines('echo "\\"" "(" x'), [[["echo", '"', "(", "x"]]])
        self.assertEqual(pipelines('echo "\\\\" "|" x'), [[["echo", "\\", "|", "x"]]])
        self.assertEqual(pipelines('echo "say \\"hi\\"" && find .'),
                         [[["echo", 'say "hi"']], [["find", "."]]])

    def test_a_quoted_or_escaped_reserved_word_is_the_command(self):
        for command, words in (("'done' x", ["done", "x"]), ("\\! x", ["!", "x"]),
                               ("'{' a", ["{", "a"]), ('"}" b', ["}", "b"])):
            with self.subTest(command=command):
                self.assertEqual(pipelines(command), [[words]])
        self.assertEqual(pipelines("! done; { ls; }"), [[["ls"]]])

    def test_every_quoted_or_escaped_word_is_marked(self):
        words = tokenize("a 'b' \\c d\"e\" ''")
        self.assertEqual(words, ["a", "b", "c", "de", ""])
        self.assertEqual([isinstance(w, Literal) for w in words],
                         [False, True, True, True, True])

    def test_an_escaped_parenthesis_opens_no_comment(self):
        self.assertEqual(strip_comment("echo \\(#x"), "echo \\(#x")
        self.assertEqual(strip_comment("(#x"), "(")
        self.assertEqual(strip_comment("echo a\\;#x"), "echo a\\;#x")
        self.assertEqual(strip_comment("echo a;#x"), "echo a;")

    def test_an_escaped_space_continues_the_word_so_a_hash_opens_no_comment(self):
        # bash: `echo a\ #b` prints `a #b`.
        self.assertEqual(strip_comment("echo a\\ #b"), "echo a\\ #b")

    def test_a_space_after_an_escaped_backslash_ends_the_word(self):
        # bash: `cat a\\ #x b.txt` reads the file `a\`; `#x b.txt` is a comment.
        self.assertEqual(strip_comment("cat a\\\\ #x b.txt"), "cat a\\\\ ")
        self.assertEqual(pipelines("cat a\\\\ #x b.txt"), [[["cat", "a\\"]]])

    def test_an_escaped_ampersand_keeps_the_cd(self):
        self.assertEqual(normalise("cd a\\&& ls"), "cd a\\&& ls")
        self.assertEqual(normalise("cd my\\ dir && ls"), "ls")

    def test_a_private_use_glyph_in_the_command_leaves_the_marking_on(self):
        self.assertEqual(pipelines("echo \ue000 \\( x | head"),
                         [[["echo", "\ue000", "(", "x"], ["head"]]])
        self.assertEqual(pipelines("echo \U000F0000 \\( x"),
                         [[["echo", "\U000F0000", "(", "x"]]])

    def test_a_command_cannot_forge_a_literal_by_holding_the_mark(self):
        tokens = tokenize("echo \U000F0000 ( x")
        self.assertEqual(tokens[2], "(")
        self.assertNotIsInstance(tokens[2], Literal)
        self.assertEqual(_free_mark("a \U000F0000 \U000F0001"), "\U000F0002")

    def test_a_command_holding_every_mark_is_read_unmarked(self):
        every = "".join(chr(p) for p in range(0xF0000, 0xFFFFE))
        self.assertIsNone(_free_mark(every))

    def test_an_unterminated_quote_is_still_skipped(self):
        self.assertTrue(analyse([bash("find . \\( -name 'x")]).bash[0].skipped)

    def test_a_command_that_does_not_tokenize_is_skipped_with_an_escaped_operator(self):
        for command in ("find . \\( -name x \\", "echo \\| $(date", "echo \\; `date"):
            with self.subTest(command=command):
                parsed = analyse([bash(command)]).bash[0]
                self.assertTrue(parsed.skipped)
                self.assertEqual(parsed.pipelines, [])
                self.assertIsNone(tokenize(command, strict=True))


class DetectorTests(unittest.TestCase):
    def test_a_literal_operator_reads_like_any_other_word_to_every_detector(self):
        for shape, reference in EQUIVALENT:
            with self.subTest(shape=shape):
                self.assertEqual(hits(shape), hits(reference))

    def test_the_grouped_finds_are_not_unfiltered(self):
        for command in (GROUPED, GROUPED_PIPED):
            with self.subTest(command=command):
                self.assertEqual(hits(command), set())

    def test_a_literal_operator_hides_no_command_and_invents_none(self):
        self.assertIn("verification/no-verify", hits("git commit -m '(' --no-verify"))
        self.assertEqual(hits("echo a \\&\\& find ."), set())
        self.assertEqual(hits("echo \\; cat a.txt"), set())

    def test_real_operators_still_split_for_every_detector(self):
        for command, expected in REAL:
            with self.subTest(command=command):
                self.assertEqual(hits(command), expected)


if __name__ == "__main__":
    unittest.main()
