# SPDX-License-Identifier: MIT
"""The shell tokenizer: compounds, substitutions and heredocs.

These are the cases that decide whether a detector reads the right words. They are ported
from the engine's original home and are the reason the parser is worth having at all: a
regular expression over the command text gets every one of them wrong.
"""
import time
import unittest

from corpus import bash
from ruleprobe import pipelines, run
from ruleprobe.shell import (SUB_PLACEHOLDER, group_output, has_redirect, normalise, operands,
                             strip_comment, strip_heredocs, strip_subs, tokenize)

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


def outputs(command):
    """`(first word, group_output)` for every segment of `command`."""
    return [(seg[0], group_output(seg)) for pipe in pipelines(command) for seg in pipe]


class GroupTests(unittest.TestCase):
    def test_a_redirect_after_a_brace_group_reaches_every_command_in_it(self):
        self.assertEqual(outputs("{ cat a.txt; echo; } > out.txt"),
                         [("cat", ("redirect",)), ("echo", ("redirect",)), (">", ())])
        segment = pipelines("{ cat a.txt; } > out.txt")[0][0]
        self.assertTrue(has_redirect(segment))
        self.assertEqual(operands(segment), ["a.txt"])

    def test_a_redirect_after_a_subshell_reaches_every_command_in_it(self):
        self.assertEqual(outputs("( cat a.txt; echo ) >> out.txt")[:2],
                         [("cat", ("redirect",)), ("echo", ("redirect",))])

    def test_a_nested_group_takes_on_the_redirect_of_the_group_around_it(self):
        self.assertEqual(outputs("{ { cat a.txt; }; echo; } > out.txt")[0],
                         ("cat", ("redirect",)))
        self.assertEqual(outputs("( { cat a.txt; } | head ) > out.txt")[0],
                         ("cat", ("pipe", "redirect")))

    def test_a_pipe_after_a_group_is_recorded_and_is_not_a_redirect(self):
        segment = pipelines("{ cat a.txt; echo; } | head -20")[0][0]
        self.assertEqual(group_output(segment), ("pipe",))
        self.assertFalse(has_redirect(segment))
        self.assertEqual(outputs("{ cat a.txt; } 2>&1 | head")[0], ("cat", ("pipe", "redirect")))

    def test_a_command_outside_the_group_keeps_its_own_output(self):
        self.assertEqual(outputs("{ echo x; } > out.txt; cat a.txt")[-1], ("cat", ()))
        self.assertEqual(outputs("cat a.txt; ( echo x ) > out.txt")[0], ("cat", ()))
        self.assertEqual(outputs("{ cat a.txt; }"), [("cat", ())])
        self.assertEqual(outputs("{ cat a.txt; } && echo done")[0], ("cat", ()))

    def test_a_group_the_parse_cannot_follow_is_unknown(self):
        # Never closed, a word after the close, and a `)` the tokenizer joined to `>`.
        self.assertEqual(outputs("{ cat a.txt; echo done")[0], ("cat", ("unknown",)))
        self.assertEqual(outputs("{ cat a.txt; } extra")[0], ("cat", ("unknown",)))
        self.assertEqual(outputs("( cat a.txt )>out.txt")[0], ("cat", ("unknown",)))

    def test_a_brace_is_a_group_only_where_a_command_starts_and_unquoted(self):
        self.assertEqual(outputs("echo { cat a.txt; } > out.txt")[0], ("echo", ()))
        self.assertEqual(outputs("'{' cat a.txt; } > out.txt")[0], ("{", ()))

    def test_a_close_with_no_open_closes_nothing(self):
        self.assertEqual(outputs("case x in a) cat a.txt;; esac > out.txt")[1], ("cat", ()))

    def test_a_plain_list_has_no_group_output(self):
        self.assertEqual(group_output(["cat", "a.txt"]), ())
        self.assertFalse(has_redirect(["cat", "a.txt"]))

    def test_hostile_groups_parse_in_linear_time(self):
        # Deep nesting with a segment at every level, and closes each followed by words: a
        # walk per close over the segments inside, or over the rest of the command, is
        # quadratic here.
        deep = "{ cat a; " * 20000 + "} " * 20000 + "> out"
        words = "( cat a ) x x x x " * 20000
        for command in (deep, words):
            started = time.perf_counter()
            pipelines(command)
            self.assertLess(time.perf_counter() - started, 2.0)


class WordTests(unittest.TestCase):
    def test_normalise_collapses_whitespace_and_drops_a_leading_cd(self):
        self.assertEqual(normalise("cd /repo &&  pytest   -q  tests/"), "pytest -q tests/")
        self.assertEqual(normalise("  ls  -la "), "ls -la")

    def test_operands_skip_flags_and_redirect_targets(self):
        self.assertEqual(operands(["cat", "-n", "a.txt", ">", "b.txt"]), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
