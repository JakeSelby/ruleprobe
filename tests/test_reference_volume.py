# SPDX-License-Identifier: MIT
"""The reference-volume generator: the same arguments write the same bytes, and the real
reader reads what it writes."""
import contextlib
import datetime
import io
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

    def test_the_reader_meets_compaction_and_streamed_partials(self):
        out, _, _ = self._make("a", sessions=40)
        sessions = {s.path: s for s in iter_sessions(root=out)}
        compacts = sum(e["kind"] == "compact" for s in sessions.values() for e in s.events)
        self.assertGreater(compacts, 0)
        streamed = 0
        for path, data in _tree(out).items():
            texts = {}
            for line in data.decode("utf-8").splitlines():
                entry = json.loads(line)
                message = entry.get("message") or {}
                if entry["type"] == "assistant" and message["content"][0]["type"] == "text":
                    texts.setdefault(message["id"], []).append(message["content"][0]["text"])
            said = [e["text"] for e in sessions[os.path.join(out, path)].events
                    if e["kind"] == "assistant_text"]
            self.assertEqual(len(said), len(texts))
            for partial, full in (t for t in texts.values() if len(t) == 2):
                streamed += 1
                self.assertIn(full, said)
                self.assertNotIn(partial, said)
        self.assertGreater(streamed, 0)

    def test_no_timestamp_runs_past_the_anchor(self):
        out, _, _ = self._make("a", sessions=40)
        last = ""
        for data in _tree(out).values():
            for line in data.decode("utf-8").splitlines():
                last = max(last, json.loads(line)["timestamp"])
        self.assertTrue(last.startswith(ANCHOR.isoformat()), last)

    def test_short_outputs_write_more_lines_in_the_same_bytes(self):
        out = os.path.join(self.tmp, "base")
        dense = os.path.join(self.tmp, "dense")
        _, base_total = reference_volume.generate(out, sessions=10, megabytes=1.0, seed=3,
                                                  anchor=ANCHOR)
        _, dense_total = reference_volume.generate(dense, sessions=10, megabytes=1.0, seed=3,
                                                   anchor=ANCHOR, short_outputs=True)
        again = os.path.join(self.tmp, "dense-again")
        reference_volume.generate(again, sessions=10, megabytes=1.0, seed=3, anchor=ANCHOR,
                                  short_outputs=True)
        self.assertEqual(_tree(dense), _tree(again))

        def lines(root):
            return sum(data.count(b"\n") for data in _tree(root).values())

        self.assertGreater(lines(dense) / dense_total, 1.5 * lines(out) / base_total)
        errors = []
        self.assertEqual(len(list(iter_sessions(root=dense, errors=errors))), 10)
        self.assertEqual(errors, [])

    def _main(self, argv):
        """`main(argv)` as `(exit code, stdout, stderr)`."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = reference_volume.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def test_the_command_writes_a_volume(self):
        out = os.path.join(self.tmp, "cli")
        code, stdout, _ = self._main([out, "--sessions", "5", "--megabytes", "0.05",
                                      "--anchor", "2026-09-20", "--short-outputs"])
        self.assertEqual(code, 0)
        self.assertIn("reference volume: 5 transcript(s)", stdout)
        self.assertEqual(len(_tree(out)), 5)

    def test_the_command_refuses_a_malformed_anchor(self):
        out = os.path.join(self.tmp, "cli")
        code, _, stderr = self._main([out, "--anchor", "2026-13-40"])
        self.assertEqual(code, 2)
        self.assertIn("expected YYYY-MM-DD", stderr)
        self.assertFalse(os.path.exists(out))

    def test_the_command_refuses_a_bad_subagent_share(self):
        for share in ("-0.1", "1", "1.5"):
            out = os.path.join(self.tmp, "cli")
            code, _, stderr = self._main([out, "--sessions", "4", "--subagent-share", share])
            self.assertEqual(code, 2, share)
            self.assertIn("--subagent-share", stderr)
            self.assertFalse(os.path.exists(out), share)

    def test_the_command_refuses_a_directory_that_is_not_empty(self):
        out = os.path.join(self.tmp, "full")
        os.makedirs(out)
        open(os.path.join(out, "keep"), "w").close()
        code, _, stderr = self._main([out, "--sessions", "2", "--megabytes", "0.01"])
        self.assertEqual(code, 2)
        self.assertIn("not empty", stderr)
        self.assertEqual(os.listdir(out), ["keep"])

    def test_the_command_refuses_a_file(self):
        out = os.path.join(self.tmp, "file")
        with open(out, "w") as handle:
            handle.write("kept")
        code, _, stderr = self._main([out, "--sessions", "2", "--megabytes", "0.01"])
        self.assertEqual(code, 2)
        self.assertIn("not a directory", stderr)
        with open(out) as handle:
            self.assertEqual(handle.read(), "kept")

if __name__ == "__main__":
    unittest.main()
