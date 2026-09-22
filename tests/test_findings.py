# SPDX-License-Identifier: MIT
"""One regression test per finding of the pre-release review (issue #2).

Each test is the reviewer's own input, kept verbatim where it was concrete, so a fix that
is later undone fails here under the number it was reported as.
"""
import unittest

from corpus import bash
from ruleprobe import run
from ruleprobe.shell import Parsed, pipelines, strip_heredocs


def parsed(command):
    return Parsed(bash(command))


class ShellFindingTests(unittest.TestCase):
    def test_finding_03_escaped_heredoc_delimiter(self):
        command = "cat <<\\EOF > n.md\nfind /\nEOF"
        self.assertEqual(strip_heredocs(command)[1], ["find /"])
        self.assertEqual(pipelines(command)[0][0][0], "cat")
        self.assertEqual(run([bash(command)]), {})

    def test_finding_04_an_indented_terminator_does_not_close_a_plain_heredoc(self):
        command = "cat <<EOF > n.md\n  EOF\nfind /\nEOF"
        self.assertEqual(strip_heredocs(command)[1], ["  EOF\nfind /"])
        self.assertEqual(run([bash(command)]), {})

    def test_finding_04_a_dash_heredoc_still_closes_on_a_tabbed_terminator(self):
        self.assertEqual(strip_heredocs("cat <<-EOF\n\tbody\n\tEOF\nls")[1], ["\tbody"])

    def test_finding_05_an_unbalanced_quote_is_unparsed_not_invisible(self):
        p = parsed('echo "unclosed')
        self.assertTrue(p.skipped)
        self.assertEqual(p.pipelines, [])


if __name__ == "__main__":
    unittest.main()
