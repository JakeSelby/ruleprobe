# SPDX-License-Identifier: MIT
"""The reference-volume generator: the same arguments write the same bytes, and the real
reader reads what it writes."""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import reference_volume  # noqa: E402

from ruleprobe import iter_sessions  # noqa: E402

ANCHOR = datetime.date(2026, 9, 20)


def _tree(root):
    """`{relative path: bytes}` for every file under `root`."""
    out = {}
    for directory, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(directory, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, root)] = handle.read()
    return out


class ReferenceVolumeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _make(self, name, seed=7, sessions=20):
        out = os.path.join(self.tmp, name)
        files, total = reference_volume.generate(out, sessions=sessions, megabytes=0.3,
                                                 seed=seed, anchor=ANCHOR, subagent_share=0.2)
        return out, files, total

    def test_same_seed_writes_the_same_bytes(self):
        first, _, _ = self._make("a")
        second, _, _ = self._make("b")
        self.assertEqual(_tree(first), _tree(second))

    def test_another_seed_writes_other_bytes(self):
        first, _, _ = self._make("a", seed=7)
        second, _, _ = self._make("b", seed=8)
        self.assertNotEqual(_tree(first), _tree(second))

    def test_counts_and_size_are_as_asked(self):
        out, files, total = self._make("a")
        tree = _tree(out)
        self.assertEqual(files, 20)
        self.assertEqual(len(tree), 20)
        self.assertEqual(total, sum(len(data) for data in tree.values()))
        self.assertGreaterEqual(total, 0.3 * 1024 * 1024)
        self.assertLess(total, 3 * 0.3 * 1024 * 1024)
        subagents = [path for path in tree if os.sep + "subagents" + os.sep in path]
        self.assertEqual(len(subagents), 4)

    def test_every_line_is_a_json_object(self):
        out, _, _ = self._make("a")
        for path, data in _tree(out).items():
            for line in data.decode("utf-8").splitlines():
                self.assertIsInstance(json.loads(line), dict, path)

    def test_the_reader_reads_every_transcript_as_a_session(self):
        out, _, _ = self._make("a")
        errors = []
        sessions = list(iter_sessions(root=out, runtime="auto", errors=errors))
        self.assertEqual(errors, [])
        self.assertEqual(len(sessions), 20)
        self.assertTrue(all(session.runtime == "claude-code" for session in sessions))
        self.assertTrue(all(session.events for session in sessions))
        self.assertEqual(sum("/" in session.id for session in sessions), 4)
        kinds = {event["kind"] for session in sessions for event in session.events}
        self.assertLessEqual({"user_prompt", "assistant_text", "tool_use", "tool_result"}, kinds)

    def test_a_since_window_keeps_some_and_drops_others(self):
        out, _, _ = self._make("a", sessions=40)
        kept = list(iter_sessions(root=out, since=(ANCHOR - datetime.timedelta(days=30))))
        self.assertTrue(0 < len(kept) < 40)

    def test_the_command_refuses_a_directory_that_is_not_empty(self):
        out = os.path.join(self.tmp, "full")
        os.makedirs(out)
        open(os.path.join(out, "keep"), "w").close()
        with self.assertRaises(SystemExit):
            with open(os.devnull, "w") as sink:
                stderr, sys.stderr = sys.stderr, sink
                try:
                    reference_volume.main([out])
                finally:
                    sys.stderr = stderr


if __name__ == "__main__":
    unittest.main()
