# SPDX-License-Identifier: MIT
"""`ruleprobe explain`: every hit with the event behind it, redacted, and nothing written.

Every secret here is fake and assembled at run time, so a scanner reading this file finds
concatenations rather than key shapes.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from corpus import FAKE_KEY, bash, compact, prompt, say, tool_use
from ruleprobe import (DEFAULT, Bundle, Detector, Registry, Session, iter_sessions, measure,
                       report_data)
from ruleprobe.cli import main
from ruleprobe.detectors.common import REDACTED, SECRET_PATTERNS, redact
from ruleprobe.report import (MAX_EXPLAINED, explain, explain_row, explain_text,
                              session_address)
from ruleprobe.validity import event_key
from test_readers import FIXTURES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: One fake instance of every `SECRET_PATTERNS` shape, in the list's order.
FAKE_SECRETS = [
    FAKE_KEY,
    "AWS_SECRET" + "_ACCESS_KEY=" + "Z" * 12,
    "Bearer " + "b" * 24,
    "client_secret" + ": " + "c" * 12,
    ("-----BEGIN RSA " + "PRIVATE KEY-----\n" + "k" * 40
     + "\n-----END RSA " + "PRIVATE KEY-----"),
    "xox" + "b-" + "1234-abcd",
    "ghp" + "_" + "g" * 24,
    "sk" + "-" + "s" * 24,
]

#: Secrets assigned to a key name, as a credentials file, YAML, a CLI call, a quoted
#: string and a value on the next line write them: `(text, the value that must not print)`.
ASSIGNED = [
    ("aws_secret" + "_access_key = " + "wJalr" + "V" * 20, "wJalr" + "V" * 20),
    ("AWS_SECRET" + "_ACCESS_KEY: " + "abc" + "Y" * 20, "abc" + "Y" * 20),
    ("aws configure set aws_secret" + "_access_key " + "Xq" * 10, "Xq" * 10),
    ("client_secret" + ' = "two words"', "two words"),
    ("client_secret" + ":\n  " + "nextline" + "N" * 8, "nextline" + "N" * 8),
]


def run_cli(*argv):
    out = io.StringIO()
    code = main(list(argv), out=out)
    return code, out.getvalue()


def run_cli_err(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        code = main(list(argv), out=out)
    return code, out.getvalue(), err.getvalue()


def blocks(text):
    return [b for b in text.strip().split("\n\n") if b]


def claude_transcript(session_id, tool_uses):
    """A synthetic Claude Code transcript: one prompt, then each `(id, name, input)`."""
    base = {"sessionId": session_id, "cwd": "/tmp/demo-repo", "gitBranch": "main"}
    lines = [dict(base, type="user", timestamp="2026-09-20T10:00:00.000Z",
                  message={"role": "user", "content": "do the thing"})]
    for n, (tool_id, name, data) in enumerate(tool_uses):
        stamp = "2026-09-20T10:00:%02d.000Z" % (n + 1)
        lines.append(dict(base, type="assistant", timestamp=stamp,
                          message={"id": "msg_%d" % n, "model": "claude-opus-5",
                                   "content": [{"type": "tool_use", "id": tool_id,
                                                "name": name, "input": data}]}))
    return "\n".join(json.dumps(line) for line in lines) + "\n"


class RedactTests(unittest.TestCase):
    def test_every_shape_is_covered_by_a_fake(self):
        self.assertEqual(len(FAKE_SECRETS), len(SECRET_PATTERNS))
        for pattern, secret in zip(SECRET_PATTERNS, FAKE_SECRETS):
            with self.subTest(pattern=pattern):
                self.assertTrue(re.search(pattern, secret))

    def test_no_known_shape_survives_redact(self):
        for secret in FAKE_SECRETS:
            with self.subTest(secret=secret[:12]):
                text = redact("before %s after" % secret)
                self.assertIn(REDACTED, text)
                self.assertFalse(any(re.search(p, text) for p in SECRET_PATTERNS))
                self.assertTrue(text.startswith("before "))

    def test_the_secret_after_a_prefix_or_an_assignment_goes_too(self):
        self.assertNotIn("1234-abcd", redact("token " + FAKE_SECRETS[5] + " end"))
        self.assertNotIn("c" * 12, redact(FAKE_SECRETS[3]))
        self.assertNotIn("Z" * 12, redact(FAKE_SECRETS[1]))

    def test_an_assigned_value_goes_in_every_form(self):
        for text, value in ASSIGNED:
            with self.subTest(text=text[:16]):
                redacted = redact("before\n" + text + "\nafter")
                self.assertNotIn(value, redacted)
                self.assertTrue(redacted.startswith("before\n"))
                self.assertTrue(redacted.endswith("\nafter"))

    def test_a_quoted_value_ends_at_its_quote(self):
        self.assertEqual(redact("client_secret" + "='a b' tail"), REDACTED + " tail")

    def test_a_private_key_body_goes_to_its_footer_or_to_the_end(self):
        text = redact("head\n" + FAKE_SECRETS[4] + "\ntail")
        self.assertEqual(text, "head\n" + REDACTED + "\ntail")
        unterminated = FAKE_SECRETS[4].split("\n-----END")[0]
        self.assertEqual(redact("head\n" + unterminated + "\ntail"), "head\n" + REDACTED)

    def test_near_misses_and_plain_text_pass_unchanged(self):
        for text in ("git commit -m wip", "AKIA" + "Q" * 15, "Bearer short",
                     "sk-short", "task-" + "a" * 10, ""):
            with self.subTest(text=text):
                self.assertEqual(redact(text), text)

    def test_redact_is_idempotent_and_takes_only_strings(self):
        once = redact(" ".join(FAKE_SECRETS))
        self.assertEqual(redact(once), once)
        self.assertEqual(redact(None), "")
        self.assertEqual(redact(42), "")


class ExplainTests(unittest.TestCase):
    def sessions(self):
        return list(iter_sessions(root=FIXTURES))

    def test_every_hit_measure_counts_is_explained_once(self):
        sessions = self.sessions()
        rows = [measure(s) for s in sessions]
        items = list(explain(sessions))
        for session, row in zip(sessions, rows):
            address = session_address(session.runtime, session.id)
            counted = {}
            for item in items:
                if item["session"] == address:
                    counted[item["detector"]] = counted.get(item["detector"], 0) + 1
            self.assertEqual(counted, row["rules"])

    def test_explain_changes_no_report_number(self):
        sessions = self.sessions()
        before = report_data([measure(s) for s in sessions])
        list(explain(sessions))
        self.assertEqual(report_data([measure(s) for s in sessions]), before)

    def test_keys_come_from_hit_key_and_name_the_event(self):
        sessions = self.sessions()
        items = list(explain(sessions))
        self.assertTrue(items)
        by_address = dict((session_address(s.runtime, s.id), s) for s in sessions)
        for item in items:
            self.assertEqual(item["key"], "%s:%s" % (item["turn"], item["tool_use_id"] or "-"))
            if item["tool_use_id"]:
                events = by_address[item["session"]].events
                keys = [event_key(e) for e in events]
                self.assertIn(item["key"], keys)
                self.assertEqual(item["tool"], "Bash")
                self.assertEqual(item["field"], "command")
            else:
                self.assertIsNone(item["field"])

    def test_a_session_hit_and_a_tool_use_hit_in_one_session(self):
        events = [prompt(), say("hi", model="m1"), compact(), bash("git push --no-verify"),
                  say("again", model="m2")]
        session = Session("s-1", "/tmp/demo-repo", "codex", events, "")
        items = list(explain([session]))
        self.assertEqual([(i["key"], i["detector"]) for i in items],
                         [("1:-", "cache-hygiene/compact"),
                          ("1:-", "cache-hygiene/model-switch"),
                          ("1:tu1", "verification/no-verify")])
        self.assertEqual(items[2]["session"], "codex:s-1")
        self.assertEqual(items[2]["value"], "git push --no-verify")
        text = explain_text(items[0])
        self.assertIn("session   codex:s-1", text)
        self.assertIn("a hit on the session", text)

    def test_a_secret_in_the_event_never_reaches_the_item_or_the_text(self):
        for secret in FAKE_SECRETS:
            with self.subTest(secret=secret[:12]):
                events = [prompt(), tool_use("Write", {"file_path": "/tmp/demo-repo/.env",
                                                       "content": "KEY=" + secret})]
                items = list(explain([Session("s", "", "claude-code", events, "")]))
                self.assertEqual([i["detector"] for i in items], ["secrets/secret-in-write"])
                self.assertEqual(items[0]["field"], "input")
                for text in (items[0]["value"], explain_text(items[0])):
                    self.assertIn(REDACTED, text)
                    self.assertNotIn(secret, text)
                    self.assertFalse(any(re.search(p, text) for p in SECRET_PATTERNS))

    def test_a_raising_detector_is_collected_with_its_session(self):
        def boom(events, ctx):
            raise KeyError("x")

        registry = Registry([Detector("x/boom", "x", "session", boom)])
        errors = []
        items = list(explain([Session("s", "", "codex", [prompt()], "")], registry=registry,
                             errors=errors))
        self.assertEqual(items, [])
        self.assertEqual(errors, [{"detector": "x/boom", "error": "KeyError",
                                   "session": "codex:s"}])

    def test_a_hit_on_a_missing_tool_use_says_so(self):
        registry = Registry([Detector("x/ghost", "x", "session", lambda e, c: [(1, "nope")])])
        items = list(explain([Session("s", "", "codex", [prompt()], "")], registry=registry))
        self.assertEqual(items[0]["key"], "1:nope")
        self.assertIn("not an event in this session", explain_text(items[0]))


    def test_two_hits_in_one_turn_are_in_transcript_order(self):
        events = [prompt(), bash("git commit --no-verify -m x", id="tu1"),
                  bash("cat notes.txt", id="tu2")]
        items = list(explain([Session("s", "", "codex", events, "")]))
        self.assertEqual([(i["key"], i["detector"]) for i in items],
                         [("1:tu1", "verification/no-verify"),
                          ("1:tu2", "transcript-hygiene/whole-file-cat")])

    def test_the_event_is_found_by_turn_and_id(self):
        events = [prompt(1), bash("echo hi", turn=1, id="tu1"), prompt(2),
                  bash("find .", turn=2, id="tu1")]
        items = list(explain([Session("s", "", "codex", events, "")]))
        self.assertEqual([(i["key"], i["value"]) for i in items], [("2:tu1", "find .")])

    def test_a_malformed_session_counts_as_measure_counts_it(self):
        events = [prompt(), "not an event", None, bash("find ."), {"kind": "tool_use"}]
        session = Session("s", "", "codex", events, "")
        items = list(explain([session]))
        counted = {}
        for item in items:
            counted[item["detector"]] = counted.get(item["detector"], 0) + 1
        self.assertEqual(counted, measure(session)["rules"])

    def test_control_characters_are_escaped(self):
        events = [prompt(), bash("cat \x1b[2J\rnotes\x07.txt")]
        items = list(explain([Session("s\x1b]0;x", "", "codex", events, "")]))
        text = explain_text(items[0])
        for raw in ("\x1b", "\r", "\x07"):
            self.assertNotIn(raw, text)
            self.assertNotIn(raw, items[0]["value"])
        self.assertIn("cat \\x1b[2J\\x0dnotes\\x07.txt", text)
        self.assertIn("session   codex:s\\x1b]0;x", text)

    def test_a_long_value_is_cut_and_the_cut_counted(self):
        content = "x" * (MAX_EXPLAINED * 2) + FAKE_KEY
        events = [prompt(), tool_use("Write", {"file_path": "a.env", "content": content})]
        items = list(explain([Session("s", "", "codex", events, "")]))
        value = items[0]["value"]
        head, note = value.rsplit("\n", 1)
        self.assertEqual(len(head), MAX_EXPLAINED)
        cut = int(re.match(r"\[(\d+) more character\(s\) cut\]$", note).group(1))
        whole = len(redact(json.dumps({"content": content, "file_path": "a.env"},
                                      sort_keys=True)))
        self.assertEqual(cut, whole - MAX_EXPLAINED)
        self.assertNotIn(FAKE_KEY, value)


class StoredRowTests(unittest.TestCase):
    def test_a_row_says_counts_only_and_names_the_rerun(self):
        row = {"session_id": "sess-9", "runtime": "codex",
               "rules": {"a/one": 2, "a/two": 1}}
        text = explain_row(row)
        self.assertIn("counts only", text)
        self.assertIn("3 hit(s)", text)
        self.assertIn("ruleprobe explain --runtime codex --session codex:sess-9", text)

    def test_a_row_missing_its_identity_still_answers(self):
        text = explain_row({"rules": {"a/one": 1}})
        self.assertIn("counts only", text)
        self.assertIn("`ruleprobe explain`", text)
        self.assertIn("carries no rule counts", explain_row(None))

    def test_no_runtime_uses_the_bare_id(self):
        text = explain_row({"session_id": "sess-9", "rules": {"a/one": 1}})
        self.assertIn("`ruleprobe explain --session sess-9`", text)
        self.assertNotIn(":sess-9", text)

    def test_an_unknown_runtime_drops_runtime_but_keeps_the_address(self):
        text = explain_row({"session_id": "sess-9", "runtime": "other", "rules": {}})
        self.assertIn("`ruleprobe explain --session other:sess-9`", text)
        self.assertNotIn("--runtime", text)

    def test_values_are_shell_quoted(self):
        text = explain_row({"session_id": "s 1; rm x", "runtime": "codex", "rules": {}})
        self.assertIn("--runtime codex --session 'codex:s 1; rm x'", text)

    def test_a_row_without_a_rules_map_carries_no_counts(self):
        for rules in ([1, 2], None, "3"):
            row = {"session_id": "s", "runtime": "codex"}
            if rules is not None:
                row["rules"] = rules
            with self.subTest(rules=rules):
                text = explain_row(row)
                self.assertIn("carries no rule counts", text)
                self.assertNotIn("hit(s)", text)

    def test_a_secret_shaped_session_id_is_redacted(self):
        text = explain_row({"session_id": FAKE_KEY, "runtime": "codex", "rules": {}})
        self.assertNotIn(FAKE_KEY, text)


class ExplainCommandTests(unittest.TestCase):
    def test_no_filter_prints_every_hit_report_counts(self):
        code, text = run_cli("explain", "--root", FIXTURES, "--no-config")
        self.assertEqual(code, 0)
        rows = [measure(s) for s in iter_sessions(root=FIXTURES)]
        self.assertEqual(len(blocks(text)), sum(sum(r["rules"].values()) for r in rows))
        for block in blocks(text):
            lines = block.split("\n")
            self.assertEqual([line.split()[0] for line in lines[:5]],
                             ["session", "key", "detector", "turn", "tool"])

    def test_the_printed_address_is_runtime_session_and_key(self):
        _, text = run_cli("explain", "--root", FIXTURES, "--no-config",
                          "--detector", "verification/no-verify")
        self.assertEqual(len(blocks(text)), 1)
        self.assertIn("session   claude-code:sess-1\nkey       1:toolu_2\n", text)
        self.assertIn("command   git commit --no-verify", text)

    def test_each_filter_narrows(self):
        _, every = run_cli("explain", "--root", FIXTURES, "--no-config")
        total = len(blocks(every))
        for argv, expected in (
                (("--session", "codex:rollout-1"), 1),
                (("--session", "rollout-1"), 1),
                (("--session", "claude-code:sess-1"), total - 1),
                (("--detector", "cache-hygiene/compact"), 1),
                (("--key", "1:-"), 2),
                (("--session", "claude-code:sess-1", "--key", "1:toolu_1"), 1)):
            with self.subTest(argv=argv):
                code, text = run_cli("explain", "--root", FIXTURES, "--no-config", *argv)
                self.assertEqual(code, 0)
                self.assertEqual(len(blocks(text)), expected)

    def test_a_filter_matching_nothing_prints_nothing_and_exits_zero(self):
        for argv in (("--session", "codex:nobody"), ("--detector", "no/such"),
                     ("--key", "99:-")):
            with self.subTest(argv=argv):
                self.assertEqual(run_cli("explain", "--root", FIXTURES, "--no-config", *argv),
                                 (0, ""))

    def test_no_transcripts_says_what_to_do_and_exits_non_zero(self):
        code, text = run_cli("explain", "--root", os.path.join(FIXTURES, "nothing-here"))
        self.assertEqual(code, 1)
        self.assertIn("--root", text)

    def test_a_secret_in_a_transcript_never_prints(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        uses = [("toolu_%d" % n, "Write", {"file_path": "/tmp/demo-repo/.env",
                                           "content": "KEY=%s\n" % secret})
                for n, secret in enumerate(FAKE_SECRETS)]
        uses.append(("toolu_bash", "Bash",
                     {"command": "cat > .env <<EOF\n%s\nEOF" % FAKE_SECRETS[6]}))
        for n, (assigned, _value) in enumerate(ASSIGNED):
            uses.append(("toolu_a%d" % n, "Write", {"file_path": "/tmp/demo-repo/creds",
                                                    "content": assigned + "\n"}))
            uses.append(("toolu_h%d" % n, "Bash",
                         {"command": "cat > creds <<EOF\n%s\nEOF" % assigned}))
        with open(os.path.join(scratch.name, "secret.jsonl"), "w") as handle:
            handle.write(claude_transcript("sess-secret", uses))
        code, text = run_cli("explain", "--root", scratch.name, "--no-config")
        self.assertEqual(code, 0)
        self.assertEqual(len(blocks(text)), len(uses))
        for secret in FAKE_SECRETS:
            self.assertNotIn(secret, text)
        for _assigned, value in ASSIGNED:
            self.assertNotIn(value, text)
        self.assertFalse(any(re.search(p, text) for p in SECRET_PATTERNS))
        self.assertIn(REDACTED, text)

    def test_since_and_runtime_narrow_the_transcripts_read(self):
        for argv in (("--since", "2026-09-21"), ("--runtime", "codex")):
            with self.subTest(argv=argv):
                code, text, _err = run_cli_err("explain", "--root", FIXTURES,
                                               "--no-config", *argv)
                self.assertEqual(code, 0)
                self.assertEqual([b.split("\n")[0] for b in blocks(text)],
                                 ["session   codex:rollout-1"])

    def test_rules_prints_the_coverage_block_to_stderr(self):
        code, text, err = run_cli_err("explain", "--root", FIXTURES, "--no-config",
                                      "--rules", os.path.join(ROOT, "docs", "rules"))
        self.assertEqual(code, 0)
        self.assertTrue(blocks(text))
        self.assertIn("rules:", err)

    def test_detectors_loads_a_file_and_a_skipped_entry_is_not_silent(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        path = os.path.join(scratch.name, "detectors.yaml")
        with open(path, "w") as handle:
            handle.write("version: 1\ndetectors:\n"
                         "  - id: mine/find\n    rule: mine\n    event: tool_use\n"
                         "    when:\n      command: {name: [find]}\n"
                         "  - id: mine/broken\n    rule: mine\n    event: tool_use\n")
        code, text, err = run_cli_err("explain", "--root", FIXTURES, "--no-config",
                                      "--detectors", path, "--detector", "mine/find")
        self.assertEqual(code, 0)
        self.assertEqual(len(blocks(text)), 1)
        self.assertIn("detector  mine/find", text)
        self.assertIn("detector findings: 1", err)

    def test_stance_runs_a_gated_detector_and_plugins_is_accepted(self):
        gated = os.path.join(FIXTURES, "gated-detector.yaml")
        base = ("explain", "--root", FIXTURES, "--no-config", "--detectors", gated,
                "--detector", "gated/commit-message")
        self.assertEqual(run_cli(*base), (0, ""))
        code, text = run_cli(*(base + ("--stance", "commits=conventional")))
        self.assertEqual(code, 0)
        self.assertEqual(len(blocks(text)), 1)
        code, text = run_cli("explain", "--root", FIXTURES, "--no-config", "--plugins")
        self.assertEqual(code, 0)
        self.assertEqual(text, run_cli("explain", "--root", FIXTURES, "--no-config")[1])

    def test_a_renamed_detector_id_is_folded(self):
        registry = DEFAULT.copy().rename("old/find", "transcript-hygiene/unfiltered-find")
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            code, text = run_cli("explain", "--root", FIXTURES, "--detector", "old/find")
        self.assertEqual(code, 0)
        self.assertEqual(len(blocks(text)), 1)
        self.assertIn("detector  transcript-hygiene/unfiltered-find", text)

    def test_a_raising_detector_is_named_on_stderr_redacted_and_exits_zero(self):
        def boom(events, ctx):
            raise KeyError("x")

        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        with open(os.path.join(scratch.name, "s.jsonl"), "w") as handle:
            handle.write(claude_transcript(FAKE_KEY, [("toolu_1", "Bash", {"command": "ls"})]))
        registry = Registry([Detector("x/boom", "x", "session", boom)])
        with mock.patch("ruleprobe.cli._bundle_and_registry",
                        return_value=(Bundle(), registry)):
            code, text, err = run_cli_err("explain", "--root", scratch.name)
        self.assertEqual((code, text), (0, ""))
        self.assertIn("1 detector error(s): x/boom (KeyError) in claude-code:" + REDACTED, err)
        self.assertNotIn(FAKE_KEY, err)

    def test_the_output_is_byte_identical_across_hash_seeds(self):
        outputs = []
        for seed in ("1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            done = subprocess.run(
                [sys.executable, "-m", "ruleprobe", "explain", "--root", FIXTURES,
                 "--no-config"],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.strip())
            outputs.append(done.stdout)
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
