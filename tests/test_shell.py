# SPDX-License-Identifier: MIT
"""The shell tokenizer: compounds, substitutions and heredocs.

These are the cases that decide whether a detector reads the right words. They are ported
from the engine's original home and are the reason the parser is worth having at all: a
regular expression over the command text gets every one of them wrong.
"""
import unittest

from corpus import bash
from ruleprobe import pipelines, run
from ruleprobe.shell import (SUB_PLACEHOLDER, has_redirect, normalise, operands, strip_comment,
                             strip_heredocs, strip_subs, tokenize)

TRAILER = "Co-Authored-By: A Model"
# The form a coding agent writes for nearly every commit: the message is a heredoc inside a
# command substitution bound to -m.
CC_FORM = "git commit -m \"$(cat <<'EOF'\n%s\n\nCloses #1\n%s\nEOF\n)\""
CC_OK = CC_FORM % ("feat(cli): add a flag", TRAILER)
CONTINUED = "git commit \\\n  -m \"feat(cli): add a flag\" \\\n  -m \"%s\"" % TRAILER
MULTILINE_MESSAGE = 'git commit -m "feat(cli): add a flag\n\n%s"' % TRAILER


class PipelineTests(unittest.TestCase):
    def test_a_pipeline_keeps_its_segments_together(self):
        self.assertEqual(pipelines("cat a | head -20"), [[["cat", "a"], ["head", "-20"]]])

    def test_a_break_starts_a_new_pipeline(self):
        self.assertEqual(pipelines("cd x && git status"), [[["cd", "x"]], [["git", "status"]]])

    def test_a_loop_keyword_is_not_a_command(self):
        self.assertEqual(pipelines("for f in a b; do cat $f; done"),
                         [[["f", "in", "a", "b"]], [["cat", "$f"]]])

    def test_a_continuation_is_one_command_not_two(self):
        self.assertEqual(pipelines("git commit \\\n  -m 'feat(x): y'"),
                         [["git commit -m".split() + ["feat(x): y"]]])

    def test_a_newline_inside_quotes_stays_in_the_argument(self):
        segment = pipelines(MULTILINE_MESSAGE)[0][0]
        self.assertEqual(segment[:3], ["git", "commit", "-m"])
        self.assertIn("\n\n" + TRAILER, segment[3])

    def test_a_newline_outside_quotes_still_separates_commands(self):
        self.assertEqual(pipelines("git status\ngit diff"),
                         [["git status".split()], ["git diff".split()]])

    def test_an_unparseable_command_yields_no_pipelines_and_no_crash(self):
        self.assertEqual(pipelines("echo 'unterminated"), [])
        self.assertEqual(run([bash("echo 'unterminated")]), {})

    def test_a_continued_commit_is_one_pipeline(self):
        self.assertEqual(len(pipelines(CONTINUED)), 1)


class SubstitutionTests(unittest.TestCase):
    def test_a_substitution_becomes_a_placeholder(self):
        self.assertEqual(strip_subs("echo $(date)"), "echo " + SUB_PLACEHOLDER)
        self.assertEqual(strip_subs("echo `date`"), "echo " + SUB_PLACEHOLDER)
        self.assertEqual(strip_subs("echo $((1 + 2))"), "echo " + SUB_PLACEHOLDER)

    def test_a_substitution_inside_quotes_is_still_lifted_out(self):
        self.assertEqual(strip_subs('echo "the time is $(date)"'),
                         'echo "the time is %s"' % SUB_PLACEHOLDER)

    def test_unbalanced_text_does_not_parse(self):
        self.assertIsNone(strip_subs("echo $(date"))
        self.assertIsNone(strip_subs("echo 'unterminated"))
        self.assertIsNone(strip_subs("echo `date"))

    def test_unparseable_text_is_tokenized_raw_rather_than_half_rewritten(self):
        self.assertEqual(tokenize("echo $(date"), ["echo", "$", "(", "date"])

    def test_a_comment_is_not_part_of_the_command(self):
        self.assertEqual(strip_comment("git status  # look first"), "git status  ")
        self.assertEqual(strip_comment("echo 'a # b'"), "echo 'a # b'")
        self.assertEqual(tokenize("git status # look\ngit diff"),
                         ["git", "status", ";", "git", "diff"])


class HeredocTests(unittest.TestCase):
    def test_a_heredoc_body_is_separated_from_the_command(self):
        text, bodies = strip_heredocs("cat > a <<EOF\nline one\nline two\nEOF\nls")
        self.assertEqual(bodies, ["line one\nline two"])
        self.assertNotIn("line one", text)
        self.assertIn("ls", text)

    def test_every_heredoc_operator_spelling_is_recognised(self):
        for command in ("cat <<-EOF\nbody\nEOF", 'cat <<"EOF"\nbody\nEOF',
                        "cat <<'MSG-END'\nbody\nMSG-END", "cat << EOF\nbody\nEOF"):
            with self.subTest(command=command.split("\n")[0]):
                self.assertEqual(strip_heredocs(command)[1], ["body"])

    def test_a_quoted_operator_is_data_and_opens_no_heredoc(self):
        text, bodies = strip_heredocs("grep -n '<<EOF' hooks.py\ncat big.md")
        self.assertEqual(bodies, [])
        self.assertIn("cat big.md", text)

    def test_a_herestring_is_not_a_heredoc(self):
        text, bodies = strip_heredocs('grep x <<<"$var"')
        self.assertEqual(bodies, [])
        self.assertIn("grep", text)

    def test_a_heredoc_inside_a_substitution_is_bound_to_the_flag_that_carries_it(self):
        text, bodies = strip_heredocs(CC_OK)
        self.assertEqual(len(bodies), 1)
        self.assertIn("feat(cli): add a flag", bodies[0])
        self.assertEqual(pipelines(CC_OK)[0][0][:3], ["git", "commit", "-m"])

    def test_two_heredocs_on_one_line_keep_their_own_bodies(self):
        _, bodies = strip_heredocs("diff <(cat <<A\none\nA\n) <(cat <<B\ntwo\nB\n)")
        self.assertEqual(bodies, ["one", "two"])

    def test_a_heredoc_leaves_its_command_visibly_redirected(self):
        segment = pipelines("cat > out.txt <<EOF\nbody\nEOF")[0][0]
        self.assertTrue(has_redirect(segment))


class WordTests(unittest.TestCase):
    def test_normalise_collapses_whitespace_and_drops_a_leading_cd(self):
        self.assertEqual(normalise("cd /repo &&  pytest   -q  tests/"), "pytest -q tests/")
        self.assertEqual(normalise("  ls  -la "), "ls -la")

    def test_operands_skip_flags_and_redirect_targets(self):
        self.assertEqual(operands(["cat", "-n", "a.txt", ">", "b.txt"]), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
