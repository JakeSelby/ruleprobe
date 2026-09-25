# SPDX-License-Identifier: MIT
"""The declared public API, held by test.

`DECLARED` is the list: every name a downstream tool may import, at the path it imports it
from. The README's public API section renders it, and a test below holds the two equal. Each
other test exercises one declared call shape, attribute or non-name dependency, and the
comment above it names the item it covers, so removing a name or changing a declared call
shape fails here. A name joins `DECLARED` only with a test in this module.

The list, the call shapes and the non-name dependencies were last re-derived from
agent-harness `main` at `40cc0b7`; the tests pin ruleprobe's side and never import the harness.

The wheel checks read a built wheel from `$RULEPROBE_WHEEL` when it is set, as CI's package
job does; set but empty or naming no file is an error. That the built wheel is the one file
`dist/ruleprobe-<version>-py3-none-any.whl` is checked by the package job's shell step, which
builds it, not here. Unset, they
assemble the same archive from the source tree, so the zip import and the corpus in the
archive are still exercised on every run.
"""
import ast
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

try:
    from collections.abc import Mapping
except ImportError:  # pragma: no cover
    from collections import Mapping

from corpus import FAKE_KEY, bash, compact, prompt, say, tool_result, tool_use

import ruleprobe
from ruleprobe import (Registry, analyse, compile_detector, counts, is_undecided,
                       iter_sessions, load_bundle, report, report_data, run, validity)
from ruleprobe import declarative
from ruleprobe.detectors import common
from ruleprobe.events import hit, input_of, text_of
from ruleprobe.registry import Detector
from ruleprobe.shell import (Context, MARKER_RE, MAX_COMMAND, Parsed, SUB_PLACEHOLDER,
                             git_calls, has_redirect, normalise, operands, pipelines,
                             strip_heredocs)
from ruleprobe.validity import (CorpusError, DEFAULT_FLOOR, Score, below_floor,
                                score_corpus, scores_as_dict, validity_table)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
WHEEL_ENV = "RULEPROBE_WHEEL"

DECLARED = {
    "ruleprobe": (
        "Registry", "analyse", "compile_detector", "counts", "is_undecided", "iter_sessions",
        "load_bundle", "report", "report_data", "run", "validity",
    ),
    "ruleprobe.declarative": ("load",),
    "ruleprobe.detectors.common": ("DETECTORS", "SECRET_PATTERNS"),
    "ruleprobe.events": ("hit", "input_of", "text_of"),
    "ruleprobe.registry": ("Detector", "Registry"),
    "ruleprobe.shell": (
        "Context", "MARKER_RE", "MAX_COMMAND", "Parsed", "SUB_PLACEHOLDER", "git_calls",
        "has_redirect", "normalise", "operands", "pipelines", "strip_heredocs",
    ),
    "ruleprobe.validity": (
        "CorpusError", "DEFAULT_FLOOR", "Score", "below_floor", "score_corpus",
        "scores_as_dict", "validity_table",
    ),
}

#: The names the README declared in 0.1.0. Every one stays declared.
DECLARED_IN_0_1 = ("iter_sessions", "run", "Registry", "report", "report_data", "validity",
                   "load_bundle", "compile_detector")

#: The detectors `ruleprobe.detectors.common` ships. A consumer re-registers exactly these and
#: counts them, so adding, removing or renaming one changes the declared surface.
GENERIC = ("cache-hygiene/compact", "cache-hygiene/model-switch", "secrets/secret-in-write",
           "transcript-hygiene/unfiltered-find", "transcript-hygiene/whole-file-cat",
           "verification/no-verify")

#: The `event` values a consumer registers its own detectors under.
CONSUMER_EVENTS = ("agent-brief", "assistant-final", "bash", "session", "write")

#: Every `event` value `Registry.add` accepts: the five above and the two raw event kinds.
EVENT_VALUES = CONSUMER_EVENTS + ("assistant_text", "tool_use")


def _session():
    """One session touching every event kind, a heredoc and a git call."""
    return [
        prompt(turn=1),
        say("Committing.", turn=1, final=False),
        bash("git commit -F - <<'EOF'\nfix: the thing\nEOF", turn=1, id="tu1"),
        tool_result("done", tool_name="Bash", tool_use_id="tu1", turn=1),
        compact(turn=1),
        say("Done.", turn=1, final=True),
    ]


class DeclaredNamesTests(unittest.TestCase):
    # Covers: the eight names the README declared in 0.1.0, and every name the harness imports,
    # each at its declared import path.
    def test_every_declared_name_imports_from_its_path(self):
        for module_name, names in sorted(DECLARED.items()):
            module = importlib.import_module(module_name)
            for name in names:
                with self.subTest(name="%s.%s" % (module_name, name)):
                    self.assertTrue(hasattr(module, name))

    # Covers: the eight names the README declared in 0.1.0 stay declared.
    def test_the_names_declared_in_0_1_stay_declared_at_the_root(self):
        for name in DECLARED_IN_0_1:
            with self.subTest(name=name):
                self.assertIn(name, DECLARED["ruleprobe"])
                self.assertIn(name, ruleprobe.__all__)

    # Covers: every declared root name, `is_undecided` included, is exported from the root.
    def test_every_declared_root_name_is_in_all(self):
        self.assertEqual(set(DECLARED["ruleprobe"]) - set(ruleprobe.__all__), set())

    # Covers: each declared root name is the object its home module defines.
    def test_root_names_are_the_module_names(self):
        homes = {"Registry": "registry", "analyse": "shell", "compile_detector": "matchers",
                 "counts": "events", "is_undecided": "matchers", "iter_sessions": "readers",
                 "load_bundle": "rules", "report": "report", "report_data": "report",
                 "run": "registry", "validity": "validity"}
        self.assertEqual(set(homes), set(DECLARED["ruleprobe"]))
        for name, home in sorted(homes.items()):
            with self.subTest(name=name):
                module = importlib.import_module("ruleprobe." + home)
                self.assertIs(getattr(ruleprobe, name), getattr(module, name))


class ReadmeTests(unittest.TestCase):
    """The README's public API section is `DECLARED`, rendered."""

    def section(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
            text = handle.read()
        start = text.index("\n## The public API\n")
        end = text.index("\n## ", start + 1)
        return text, text[start:end]

    # Covers: the README declares the public API, and it is this list.
    def test_the_readme_lists_exactly_the_declared_names(self):
        _, section = self.section()
        listed = {}
        for item in re.findall(r"^- `(ruleprobe[\w.]*)`: (.+?)(?=^- |^$)", section,
                               re.M | re.S):
            module_name, body = item
            self.assertNotIn(module_name, listed, "listed twice: %s" % module_name)
            listed[module_name] = tuple(re.findall(r"`(\w+)`", body))
        self.assertEqual(listed, DECLARED)

    # Covers: the README no longer gives the 0.1.0 count of six names.
    def test_the_six_names_count_is_gone(self):
        text, _ = self.section()
        self.assertNotIn("six names", text)

    # Covers: both routes past an undecided predicate are named where a Python caller reads.
    def test_the_readme_names_both_routes_past_undecided(self):
        _, section = self.section()
        self.assertIn("is_undecided(value)", section)
        self.assertIn("`not`, `any` and `all`", section)


class DetectorFunctionTests(unittest.TestCase):
    # Covers: the detector function `fn(events, ctx)` returning `(turn, tool_use_id)` pairs;
    # `ctx` a `Context` with `.events`, `.bash` (each a `Parsed`) and `.finals`; `Parsed` with
    # `.event`, `.command` and `.heredocs`; `run(events, stances, registry=, strict=, errors=)`.
    def test_run_calls_fn_with_events_and_ctx(self):
        seen = {}

        # `run(strict=False)` catches whatever `fn` raises, so `fn` only records what it saw
        # and every assertion runs after `run` returns.
        def fn(events, ctx):
            seen["events"], seen["ctx"] = events, ctx
            seen["bash"] = [(type(p), p.event, p.command, p.heredocs) for p in ctx.bash]
            out = [(p.event.get("turn"), p.event.get("id")) for p in ctx.bash]
            return out + [hit(final) for final in ctx.finals]

        errors = []
        hits = run(_session(), {"commits": "conventional"},
                   registry=Registry([Detector("contract/fn", "contract", "bash", fn, None)]),
                   strict=False, errors=errors)
        self.assertEqual(errors, [])
        self.assertEqual(len(seen["bash"]), 1)
        cls, event, command, heredocs = seen["bash"][0]
        self.assertTrue(issubclass(cls, Parsed))
        self.assertEqual(event["kind"], "tool_use")
        self.assertIn("git commit", command)
        self.assertEqual(heredocs, ["fix: the thing"])
        ctx = seen["ctx"]
        self.assertIsInstance(ctx, Context)
        self.assertIs(seen["events"], ctx.events)
        self.assertEqual(len(ctx.events), 6)
        self.assertEqual([e["text"] for e in ctx.finals], ["Done."])
        self.assertEqual([(h.turn, h.tool_use_id) for h in hits["contract/fn"]],
                         [(1, "tu1"), (1, None)])

    # Covers: `run(..., strict=, errors=)`, the two keywords that decide what a raise does.
    def test_errors_collects_a_raising_detector_and_strict_raises_it(self):
        def boom(events, ctx):
            raise KeyError("x")

        registry = Registry([Detector("contract/boom", "contract", "session", boom, None)])
        errors = []
        self.assertEqual(run(_session(), None, registry=registry, strict=False,
                             errors=errors), {})
        self.assertEqual(errors, [{"detector": "contract/boom", "error": "KeyError"}])
        with self.assertRaises(KeyError):
            run(_session(), None, registry=registry, strict=True, errors=None)

    # Covers: `analyse(events)` from the root, the parsed view `run` hands a detector; one
    # `Parsed` per Bash call, in order, each holding the very event object it was parsed
    # from, so a caller can key parses by `id(p.event)`.
    def test_analyse_returns_the_context_run_uses(self):
        ctx = analyse(_session())
        self.assertIsInstance(ctx, Context)
        self.assertEqual(len(ctx.bash), 1)
        self.assertEqual(len(ctx.finals), 1)
        events = [bash("git status", id="tu1"), bash("cat a.md", id="tu2")]
        parsed = analyse(events).bash
        self.assertEqual(len(parsed), len(events))
        for one, event in zip(parsed, events):
            self.assertIs(one.event, event)

    # Covers: `run` returning `{detector_id: [hit, ...]}` with the detectors that found
    # nothing omitted, each hit a 3-sequence `(id, turn, tool_use_id)` with those attributes;
    # a detector `fn` may return plain tuples.
    def test_run_returns_three_field_hits_keyed_by_id_and_omits_the_empty(self):
        registry = Registry([
            Detector("contract/one", "contract", "bash", lambda e, c: [(2, "tu2"), (3, None)]),
            Detector("contract/none", "contract", "session", lambda e, c: []),
        ])
        hits = run([], None, registry=registry, strict=True)
        self.assertIsInstance(hits, dict)
        self.assertEqual(list(hits), ["contract/one"])
        self.assertEqual([tuple(h) for h in hits["contract/one"]],
                         [("contract/one", 2, "tu2"), ("contract/one", 3, None)])
        for one in hits["contract/one"]:
            self.assertEqual(len(one), 3)
            self.assertEqual((one.id, one.turn, one.tool_use_id), tuple(one))

    # Covers: the shipped detectors over a session built by the caller rather than a reader,
    # with no `stances`: the hits the harness pins in its own golden for the generic half.
    def test_the_shipped_detectors_over_a_caller_built_session(self):
        session = [
            {"kind": "user_prompt", "turn": 1, "text": "go"},
            {"kind": "assistant_text", "turn": 1, "text": "Looking.", "final": False,
             "model": "model-a"},
            bash("cat notes.txt", turn=1, id="tu1"),
            tool_result("x", tool_name="Bash", tool_use_id="tu1", turn=1),
            {"kind": "user_prompt", "turn": 2},
            compact(turn=2),
            bash("find .", turn=2, id="tu2"),
            bash("git push --no-verify", turn=2, id="tu3"),
            tool_use("Write", {"file_path": "a.py", "content": "KEY = '%s'\n" % FAKE_KEY},
                     turn=2, id="tu4"),
            bash("cat > .env <<EOF\nAWS_ACCESS_KEY_ID=%s\nEOF" % FAKE_KEY, turn=2, id="tu5"),
            {"kind": "assistant_text", "turn": 2, "text": "Done.", "final": True,
             "model": "model-b"},
        ]
        hits = run(session, None, registry=Registry(common.DETECTORS), strict=True)
        self.assertEqual(dict((k, [tuple(h)[1:] for h in v]) for k, v in hits.items()), {
            "cache-hygiene/compact": [(2, None)],
            "cache-hygiene/model-switch": [(2, None)],
            "secrets/secret-in-write": [(2, "tu4"), (2, "tu5")],
            "transcript-hygiene/unfiltered-find": [(2, "tu2")],
            "transcript-hygiene/whole-file-cat": [(1, "tu1")],
            "verification/no-verify": [(2, "tu3")],
        })


class DetectorTypeTests(unittest.TestCase):
    # Covers: `Detector` built positionally as `(id, rule, event, fn, gate)`, subclassable with
    # `__slots__ = ()`; `.id`, `.rule`, `.event`, `.fn` and `.gate` on it and on each item of
    # `common.DETECTORS`; `Registry(<list>)` positionally.
    def test_positional_detector_and_a_slots_subclass(self):
        class HarnessDetector(Detector):
            __slots__ = ()

            # A subclass renames two fields with read-only properties, so the base class
            # defines neither name.
            @property
            def kind(self):
                return self.event

            @property
            def stance(self):
                return self.gate

        self.assertFalse(hasattr(Detector, "kind"))
        self.assertFalse(hasattr(Detector, "stance"))

        def fn(events, ctx):
            return [(1, None)]

        for cls in (Detector, HarnessDetector):
            with self.subTest(cls=cls.__name__):
                detector = cls("contract/pos", "contract", "session", fn, ("commits", None))
                self.assertEqual((detector.id, detector.rule, detector.event, detector.fn,
                                  detector.gate),
                                 ("contract/pos", "contract", "session", fn,
                                  ("commits", None)))
                registry = Registry([detector])
                self.assertEqual(list(run([], {"commits": "on"}, registry=registry)),
                                 ["contract/pos"])
                if cls is HarnessDetector:
                    self.assertEqual((detector.kind, detector.stance),
                                     ("session", ("commits", None)))

    # Covers: `Detector(id, rule, event, fn)` with the gate left out, which is always on, and
    # each shipped detector re-registered positionally, ungated, under a subclass.
    def test_four_positional_arguments_and_a_re_registered_shipped_detector(self):
        class HarnessDetector(Detector):
            __slots__ = ()

        detector = HarnessDetector("contract/four", "contract", "session",
                                   lambda e, c: [(1, None)])
        self.assertIsNone(detector.gate)
        self.assertEqual(list(run([], None, registry=Registry([detector]))),
                         ["contract/four"])
        copies = [HarnessDetector(d.id, d.rule, d.event, d.fn, None) for d in common.DETECTORS]
        registry = Registry(copies)
        self.assertEqual(sorted(d.id for d in copies), sorted(GENERIC))
        self.assertEqual(sorted(run([bash("cat a.md")], None, registry=registry)),
                         ["transcript-hygiene/whole-file-cat"])

    # Covers: all seven declared `event` values are accepted, the five a consumer registers
    # under among them, and any other is refused.
    def test_the_event_kinds_a_consumer_registers_under(self):
        self.assertTrue(set(CONSUMER_EVENTS) <= set(EVENT_VALUES))
        with self.assertRaises(ValueError):
            Registry([Detector("contract/ev", "contract", "tool-use", lambda e, c: [])])
        for event in EVENT_VALUES:
            with self.subTest(event=event):
                registry = Registry([Detector("contract/ev", "contract", event,
                                              lambda e, c: [])])
                self.assertEqual(run([], None, registry=registry, strict=True), {})

    # Covers: `common.DETECTORS` is exactly the six generic detectors, by id.
    def test_the_shipped_detectors_are_the_six_generic_ones(self):
        self.assertEqual(sorted(d.id for d in common.DETECTORS), list(GENERIC))

    # Covers: `opportunities`, set by keyword only, a callable over `(events, ctx)` returning
    # `(turn, tool_use_id, followed)` triples; `None` when not given; never called by `run()`;
    # filled by `compile_detector` for `order` and turn-scoped `absent`, `None` for
    # session-scoped `absent`.
    def test_opportunities_is_keyword_only_and_returns_triples(self):
        def fn(events, ctx):
            return [(1, None)]

        def boom(events, ctx):
            raise AssertionError("run() called opportunities")

        detector = Detector("contract/opp", "contract", "session", fn, None,
                            opportunities=boom)
        self.assertIs(detector.opportunities, boom)
        self.assertIsNone(Detector("contract/opp", "contract", "session", fn,
                                   None).opportunities)
        with self.assertRaises(TypeError):
            Detector("contract/opp", "contract", "session", fn, None, None, boom)
        self.assertEqual(list(run([], registry=Registry([detector]), strict=True)),
                         ["contract/opp"])
        events = [{"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash",
                   "input": {"command": "ls"}},
                  {"kind": "tool_use", "turn": 2, "id": "tu2", "name": "Read",
                   "input": {"file_path": "a"}}]
        ctx = analyse(events)
        read = {"tool": "Read"}
        cases = [({"order": {"first": {"tool": "Bash"}, "then": read}}, [(1, "tu1", True)]),
                 ({"absent": {"of": read, "scope": "turn"}}, [(1, None, False),
                                                               (2, None, True)]),
                 ({"absent": {"of": read, "scope": "session"}}, None)]
        for when, expected in cases:
            with self.subTest(when=when):
                compiled = compile_detector({"id": "contract/agg", "event": "session",
                                             "when": when})
                if expected is None:
                    self.assertIsNone(compiled.opportunities)
                else:
                    self.assertEqual(compiled.opportunities(ctx.events, ctx), expected)

    # Covers: `.id`, `.rule`, `.event`, `.fn` and `.gate` on each item of `common.DETECTORS`.
    def test_the_shipped_detectors_carry_the_declared_attributes(self):
        self.assertTrue(common.DETECTORS)
        for detector in common.DETECTORS:
            with self.subTest(detector=detector.id):
                self.assertIsInstance(detector, Detector)
                for attr in ("id", "rule", "event", "fn", "gate"):
                    self.assertTrue(hasattr(detector, attr), attr)
                self.assertTrue(callable(detector.fn))

    # Covers: `gate` as `None` or a `(dimension, allowed_variants_or_None)` pair.
    def test_gate_is_none_or_a_dimension_pair(self):
        def fn(events, ctx):
            return [(1, None)]

        cases = [
            (None, None, True),
            (("commits", None), None, False),
            (("commits", None), {"commits": "conventional"}, True),
            (("commits", ("attributed",)), {"commits": "conventional"}, False),
            (("commits", ("attributed",)), {"commits": "attributed"}, True),
        ]
        for gate, stances, fires in cases:
            with self.subTest(gate=gate, stances=stances):
                registry = Registry([Detector("contract/gate", "contract", "session", fn,
                                              gate)])
                self.assertEqual(bool(run([], stances, registry=registry)), fires)


class EventTests(unittest.TestCase):
    # Covers: the event fields the harness reads, each on the kinds `ruleprobe/events.py`
    # documents it for, read through `.get` from events a reader emitted.
    FIELDS = {
        "assistant_text": ("kind", "turn", "text", "final"),
        "tool_use": ("kind", "turn", "id", "name", "input"),
        "tool_result": ("kind", "turn", "tool_use_id", "tool_name", "text"),
        "user_prompt": ("kind", "turn", "text"),
        "compact": ("kind", "turn"),
    }

    #: The kinds each fixture's transcript holds.
    KINDS = {"claude-code": set(FIELDS), "codex": {"assistant_text", "tool_use", "tool_result"}}

    def check_type(self, field, value):
        if field == "turn":
            self.assertIs(type(value), int)
        elif field == "final":
            self.assertIs(type(value), bool)
        elif field == "input":
            self.assertIsInstance(value, Mapping)
        else:
            self.assertIsInstance(value, str)

    def test_each_kind_carries_its_documented_fields(self):
        for runtime, kinds in sorted(self.KINDS.items()):
            with self.subTest(runtime=runtime):
                events = [e for s in iter_sessions(root=FIXTURES, runtime=runtime)
                          for e in s.events]
                self.assertEqual(set(e.get("kind") for e in events), kinds)
                for index, event in enumerate(events):
                    for field in self.FIELDS[event.get("kind")]:
                        with self.subTest(runtime=runtime, event=index, field=field):
                            self.assertIsNotNone(event.get(field))
                            self.check_type(field, event.get(field))

    def test_a_gemini_session_carries_the_documented_fields(self):
        # Built in a temporary tree: a Gemini file under `FIXTURES` would change the
        # mixed-root counts other suites read there.
        from test_reader_gemini import Tree, call, gemini_record, meta, response, user
        tree = Tree()
        self.addCleanup(tree.close)
        path = tree.write("session-2026-09-20T10-00-contract.jsonl", [
            meta(), user("u1", "go"),
            gemini_record("g1", "Working.", [
                call("c1", "run_shell_command", {"command": "ls"}),
                dict(call("c2", "read_file", {}), args="not an object")]),
            response("r1", "c1", "run_shell_command", "ok")])
        events = [e for s in iter_sessions(root=tree.base, runtime="gemini")
                  for e in s.events]
        self.assertEqual(set(e.get("kind") for e in events),
                         {"user_prompt", "assistant_text", "tool_use", "tool_result"})
        self.assertTrue(os.path.exists(path))
        for index, event in enumerate(events):
            fields = self.FIELDS[event.get("kind")]
            if event.get("kind") == "assistant_text":
                fields = fields + ("model",)
            for field in fields:
                with self.subTest(event=index, field=field):
                    self.assertIsNotNone(event.get(field))
                    self.check_type(field, event.get(field))

    # Covers: `hit(event)` and `hit(event, tool_use_id=False)`, returning `(turn, id or None)`.
    def test_hit_shapes(self):
        event = tool_use("Bash", {"command": "ls"}, turn=3, id="tu9")
        self.assertEqual(hit(event), (3, "tu9"))
        self.assertEqual(hit(event, tool_use_id=False), (3, None))

    # Covers: `input_of(event)` and `text_of(value)`.
    def test_input_of_and_text_of(self):
        self.assertEqual(input_of({"input": {"a": 1}}), {"a": 1})
        self.assertEqual(input_of({"input": "not a dict"}), {})
        self.assertEqual(text_of("x"), "x")
        self.assertEqual(text_of(None), "")

    # Covers: `counts(events)` from the root.
    def test_counts_is_a_dict_of_ints(self):
        out = counts([tool_use("Agent", {}), tool_use("WebSearch", {})])
        self.assertEqual(out, {"web_search": 1, "agent": 1, "ask_user": 0})


class ShellTests(unittest.TestCase):
    # Covers: `git_calls(parsed, subcommands)` yielding `(segment, subcommand, args)` 3-tuples.
    def test_git_calls_yields_three_tuples(self):
        parsed = Parsed(bash("git -C repo commit -m msg && git push origin main"))
        calls = list(git_calls(parsed, ("commit",)))
        self.assertEqual(len(calls), 1)
        segment, subcommand, args = calls[0]
        self.assertIsInstance(segment, list)
        self.assertEqual(subcommand, "commit")
        self.assertEqual(args, ["-m", "msg"])

    # Covers: `MARKER_RE.match(value)` with group 1 an index into `Parsed.heredocs`.
    def test_marker_group_one_indexes_heredocs(self):
        parsed = Parsed(bash("cat > a.txt <<'A'\none\nA\ncat > b.txt <<'B'\ntwo\nB"))
        markers = [m for pipe in pipelines(parsed.command) for seg in pipe for t in seg
                   for m in [MARKER_RE.match(t)] if m]
        self.assertEqual(len(markers), 2)
        self.assertEqual([parsed.heredocs[int(m.group(1))] for m in markers],
                         ["one", "two"])

    # Covers: `normalise(command)`, and the other shell names the harness imports.
    def test_shell_helpers_return_their_documented_types(self):
        self.assertEqual(normalise("cd repo &&   git   status"), "git status")
        text, bodies = strip_heredocs("cat <<EOF\nbody\nEOF")
        self.assertIsInstance(text, str)
        self.assertEqual(bodies, ["body"])
        pipes = pipelines("ls -la > out.txt | wc -l")
        self.assertIsInstance(pipes, list)
        segment = pipes[0][0]
        self.assertEqual(operands(segment), [])
        self.assertTrue(has_redirect(segment))
        self.assertIsInstance(MAX_COMMAND, int)
        self.assertIsInstance(SUB_PLACEHOLDER, str)
        self.assertIn(SUB_PLACEHOLDER, [t for p in pipelines("echo $(date)") for s in p
                                        for t in s])

    # Covers: `pipelines(command)` as a list of pipelines, each a list of segments, each a
    # list of tokens, `[]` for an unterminated quote; `operands(segment)` dropping flags
    # and a redirect target; `strip_heredocs(command)` returning `(text, bodies)`.
    def test_the_shell_helpers_return_the_nested_shapes(self):
        self.assertEqual(pipelines("cat a | head -20"), [[["cat", "a"], ["head", "-20"]]])
        self.assertEqual(pipelines("cd x && git status"), [[["cd", "x"]], [["git", "status"]]])
        self.assertEqual(pipelines("git status\ngit diff"),
                         [[["git", "status"]], [["git", "diff"]]])
        self.assertEqual(pipelines("echo 'unterminated"), [])
        self.assertEqual(operands(["cat", "-n", "a.txt", ">", "b.txt"]), ["a.txt"])
        text, bodies = strip_heredocs("cat > a <<EOF\nline one\nline two\nEOF\nls")
        self.assertEqual(bodies, ["line one\nline two"])
        self.assertNotIn("line one", text)

    # Covers: `Parsed.skipped` and `Parsed.pipelines`; a command over `MAX_COMMAND` is
    # skipped, never tokenized, and still carries its event.
    def test_parsed_skipped_and_pipelines(self):
        parsed = analyse([bash("cat a | head -20")]).bash[0]
        self.assertIs(parsed.skipped, False)
        self.assertEqual(parsed.pipelines, [[["cat", "a"], ["head", "-20"]]])
        event = bash("cat " + "x" * MAX_COMMAND)
        parsed = analyse([event]).bash[0]
        self.assertIs(parsed.skipped, True)
        self.assertEqual(parsed.pipelines, [])
        self.assertIs(parsed.event, event)


class DeclarativeTests(unittest.TestCase):
    # Covers: `declarative.load(path)` returning `(document, lines)`.
    def test_load_returns_document_and_lines(self):
        document, lines = declarative.load(os.path.join(FIXTURES, "gated-detector.yaml"))
        self.assertIsInstance(document, dict)
        self.assertTrue(hasattr(lines, "line_of"))

    # Covers: the 0.1.0 declarative names `load_bundle(...)` and `compile_detector(...)`.
    def test_load_bundle_and_compile_detector(self):
        bundle = load_bundle(paths=[os.path.join(FIXTURES, "gated-detector.yaml")],
                             rules_dir=None, cwd=ROOT, config=False)
        for attr in ("detectors", "rules", "findings"):
            self.assertTrue(hasattr(bundle, attr), attr)
        self.assertEqual([d.id for d in bundle.detectors], ["gated/commit-message"])
        self.assertEqual(list(bundle.findings), [])
        detector = compile_detector({"id": "contract/sudo", "rule": "contract",
                                     "event": "tool_use",
                                     "when": {"command": {"starts_with": ["sudo"]}}},
                                    path="<contract>", lines=None)
        self.assertIsInstance(detector, Detector)
        self.assertEqual(list(run([bash("sudo ls")], registry=Registry([detector]))),
                         ["contract/sudo"])

    # Covers: `is_undecided(value)`, which tells a predicate's undecided result from false.
    def test_is_undecided(self):
        # No declared function yet produces an undecided value: `compile_matcher` needs the
        # private `_Where` and `_Env`, so this test reaches them to get a real one.
        from ruleprobe import matchers

        predicate = ruleprobe.compile_matcher({"command": {"name": ["git"]}},
                                              matchers._Where())
        events = [bash('echo "unterminated', id="tu1"), bash("git status", id="tu2"),
                  bash("ls", id="tu3")]
        env = matchers._Env(analyse(events))
        results = [predicate(event, env) for event in events]
        self.assertFalse(results[0])
        self.assertEqual([is_undecided(r) for r in results], [True, False, False])
        for value in (True, False, None, 0, "", [], "UNDECIDED"):
            with self.subTest(value=value):
                self.assertIs(is_undecided(value), False)


class ValidityTests(unittest.TestCase):
    def setUp(self):
        # These read the corpus inside the package, so a caller's override must not leak in.
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("RULEPROBE_CORPUS", None)

    # Covers: `score_corpus(registry=, directory=)`; `Score(detector_id)` with `.add`,
    # `.scored`, `.precision`, `.recall` and `.detector`; `DEFAULT_FLOOR`.
    def test_score_corpus_and_score(self):
        scores = score_corpus(registry=Registry(common.DETECTORS), directory=None)
        self.assertEqual(set(scores), set(d.id for d in common.DETECTORS))
        for detector_id, score in scores.items():
            self.assertIsInstance(score, Score)
            self.assertEqual(score.detector, detector_id)
        scored = [s for _, s in sorted(scores.items()) if s.scored]
        self.assertTrue(scored)
        score = Score("contract/x")
        self.assertEqual(score.detector, "contract/x")
        self.assertFalse(score.scored)
        self.assertIs(score.add(scored[0]), score)
        self.assertTrue(score.scored)
        self.assertEqual((score.precision, score.recall),
                         (scored[0].precision, scored[0].recall))
        self.assertIsInstance(DEFAULT_FLOOR, float)

    # Covers: `score_corpus` raising `CorpusError` on a broken corpus.
    def test_score_corpus_raises_corpus_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CorpusError):
                score_corpus(registry=Registry(common.DETECTORS), directory=directory)

    # Covers: `below_floor(scores, floor)`, `scores_as_dict(scores, floor)` and
    # `validity_table(scores, floor)`, positional.
    def test_the_floor_helpers_take_scores_and_floor_positionally(self):
        scores = score_corpus(registry=Registry(common.DETECTORS), directory=None)
        scored = sorted(did for did, s in scores.items() if s.scored)
        self.assertTrue(scored)
        # No rate exceeds 1.0, so every scored detector is under a floor above it.
        self.assertEqual(below_floor(scores, 1.01), scored)
        self.assertEqual(below_floor(scores, 0.0), [])
        data = scores_as_dict(scores, 1.01)
        self.assertEqual(data["below_floor"], scored)
        self.assertEqual(data["floor"], 1.01)
        self.assertIn("below floor", validity_table(scores, 1.01))
        self.assertNotIn("below floor", validity_table(scores, 0.0))

    # Covers: `score_corpus` over a consumer's own corpus directory: `labels.yaml` with a
    # top-level `version` and a key the scorer does not read, session and label `note`s,
    # `fire` and `near` flow lists, and a file beside it that is not a session; the result
    # passes through `scores_as_dict`, extended by the caller, into JSON.
    def test_score_corpus_over_a_consumer_corpus(self):
        from test_validity import cc_lines

        labels = ("version: 1\n"
                  "known_below_floor:\n"
                  "  - detector: contract/none\n"
                  "    floor: 0.9\n"
                  "sessions:\n"
                  "  - session: consumer.jsonl\n"
                  "    note: one whole-file read and one ranged read\n"
                  "    labels:\n"
                  "      - at: \"1:tu-a\"\n"
                  "        fire: [transcript-hygiene/whole-file-cat]\n"
                  "        note: a lone cat\n"
                  "      - at: \"1:tu-b\"\n"
                  "        near: [transcript-hygiene/whole-file-cat]\n")
        with tempfile.TemporaryDirectory() as directory:
            os.mkdir(os.path.join(directory, "sessions"))
            with open(os.path.join(directory, "labels.yaml"), "w", encoding="utf-8") as handle:
                handle.write(labels)
            with open(os.path.join(directory, "build_sessions.py"), "w",
                      encoding="utf-8") as handle:
                handle.write("# writes the sessions\n")
            with open(os.path.join(directory, "sessions", "consumer.jsonl"), "w",
                      encoding="utf-8") as handle:
                handle.write("\n".join(cc_lines([("prompt", None),
                                                  ("bash", ("tu-a", "cat a.txt")),
                                                  ("bash", ("tu-b", "sed -n 1,5p b.txt"))]))
                             + "\n")
            ungated = [Detector(d.id, d.rule, d.event, d.fn, None) for d in common.DETECTORS]
            scores = score_corpus(registry=Registry(ungated), directory=directory)
        score = scores["transcript-hygiene/whole-file-cat"]
        self.assertTrue(score.scored)
        self.assertEqual((score.precision, score.recall), (1.0, 1.0))
        data = scores_as_dict(scores, DEFAULT_FLOOR)
        self.assertIsInstance(data, dict)
        data.update({"failed": [], "stale": []})
        self.assertEqual(json.loads(json.dumps(data))["below_floor"], [])

    # Covers: the 0.1.0 names `validity`, `report` and `report_data`.
    def test_validity_report_and_report_data(self):
        scores = validity(registry=Registry(common.DETECTORS), directory=None)
        self.assertTrue(all(isinstance(s, Score) for s in scores.values()))
        self.assertIsInstance(report([], by="rule", min_sessions=20, frequent_share=0.30), str)
        self.assertIsInstance(report_data([], by="rule"), dict)

    # Covers: the 0.2.0 `min_opportunities` keyword of `report` and `report_data`.
    def test_report_and_report_data_take_min_opportunities(self):
        self.assertIsInstance(report([], by="rule", min_sessions=20, frequent_share=0.30,
                                     min_opportunities=20), str)
        self.assertEqual(report_data([], by="rule", min_opportunities=5)["min_opportunities"],
                         5)

    # Covers: the 0.1.0 names `iter_sessions`, `Registry.add` and `Registry.from_entry_points`.
    def test_iter_sessions_and_registry_methods(self):
        errors = []
        sessions = list(iter_sessions(root=FIXTURES, runtime="auto", since=None,
                                      errors=errors))
        self.assertTrue(sessions)
        for attr in ("id", "repo", "events"):
            self.assertTrue(hasattr(sessions[0], attr), attr)
        registry = Registry()
        detector = Detector("contract/add", "contract", "session", lambda e, c: [], gate=None)
        self.assertIs(registry.add(detector), detector)
        self.assertIsInstance(Registry.from_entry_points("ruleprobe.detectors"), Registry)


class SecretPatternsTests(unittest.TestCase):
    # Covers: `SECRET_PATTERNS` a plain module-level `ast.Assign` of a literal list in
    # `ruleprobe/detectors/common.py`, read by syntax tree without importing.
    def test_secret_patterns_is_a_plain_assign_of_a_literal_list(self):
        path = os.path.join(ROOT, "ruleprobe", "detectors", "common.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), path)
        found = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "SECRET_PATTERNS"
                         for t in node.targets)]
        self.assertEqual(len(found), 1)
        self.assertIsInstance(found[0].value, ast.List)
        value = ast.literal_eval(found[0].value)
        self.assertEqual(value, common.SECRET_PATTERNS)
        self.assertTrue(value and all(isinstance(p, str) for p in value))

    # Covers: every pattern in `SECRET_PATTERNS` compiles with `re.compile` as it stands.
    def test_every_secret_pattern_compiles(self):
        for pattern in common.SECRET_PATTERNS:
            with self.subTest(pattern=pattern):
                re.compile(pattern)


def _flow_labelled(text):
    """Every detector id in a `fire:` or `near:` flow list, read by pattern, not by YAML."""
    found = set()
    for match in re.finditer(r"\b(?:fire|near):\s*\[([^\]]*)\]", text):
        found.update(part.strip() for part in match.group(1).split(",") if part.strip())
    return found


class ShippedLabelsTests(unittest.TestCase):
    # Covers: the shipped `labels.yaml` writes every `fire` and `near` as a flow list, so a
    # caller reading it by pattern, without a YAML parser, sees every labelled id.
    def test_every_fire_and_near_is_a_flow_list(self):
        path = os.path.join(ROOT, "ruleprobe", "corpus", "labels.yaml")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        block = re.compile(r"^[ \t]*(?:-[ \t]+)?(?:fire|near):\s*(?!\[)\S", re.M)
        self.assertEqual(block.findall(text), [])
        for bad in ("  - at: x\n    fire:\n      - a/b\n", "  - fire:\n      - a/b\n"):
            with self.subTest(bad=bad):
                self.assertTrue(block.findall(bad))
        self.assertEqual(_flow_labelled("misfire: [a/b]\nnear: [c/d]\n"), {"c/d"})
        document, _lines = declarative.load(path)
        loaded = set()
        for session in document["sessions"]:
            for label in session.get("labels") or []:
                for key in ("fire", "near"):
                    loaded.update(label.get(key) or [])
        self.assertEqual(_flow_labelled(text), loaded)
        self.assertTrue(set(GENERIC) <= loaded)


_PROBE = r"""
import importlib, json, os, sys
sys.path.insert(0, sys.argv[1])
import ruleprobe
for module_name, names in json.loads(sys.argv[2]).items():
    module = importlib.import_module(module_name)
    assert module.__file__.startswith(sys.argv[1] + os.sep), module.__file__
    for name in names:
        getattr(module, name)
from ruleprobe import Registry, run
from ruleprobe.detectors import common
from ruleprobe.validity import score_corpus
hits = run([{"kind": "tool_use", "turn": 1, "id": "tu1", "name": "Bash",
             "input": {"command": "cat README.md"}}])
scores = score_corpus(registry=Registry(common.DETECTORS))
print(json.dumps({"file": ruleprobe.__file__, "version": ruleprobe.__version__,
                  "dir": os.path.dirname(ruleprobe.__file__), "hits": sorted(hits),
                  "scored": sorted(k for k, s in scores.items() if s.scored)}))
"""


def _package_data_globs():
    """The `package-data` globs `pyproject.toml` gives setuptools."""
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        text = handle.read()
    section = text.split("[tool.setuptools.package-data]", 1)[-1]
    match = re.search(r"^ruleprobe = (\[.*\])$", section, re.M)
    if match is None:
        raise AssertionError("pyproject.toml has no [tool.setuptools.package-data] "
                             "ruleprobe = [...] line")
    return ast.literal_eval(match.group(1))


def _source_wheel(directory):
    """The source tree packed the way the wheel packs it: every module, plus package data,
    each pattern globbed as setuptools globs it, so `*` stops at a `/` and `**` crosses it."""
    import glob

    package = os.path.join(ROOT, "ruleprobe")
    files = set()
    for dirpath, dirnames, filenames in os.walk(package):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        files.update(os.path.join(dirpath, f) for f in filenames if f.endswith(".py"))
    for pattern in _package_data_globs():
        matched = glob.glob(os.path.join(package, pattern), recursive=True)
        if not matched:
            raise AssertionError("package-data pattern %r matches no file" % pattern)
        files.update(matched)
    path = os.path.join(directory, "ruleprobe-%s-py3-none-any.whl" % ruleprobe.__version__)
    with zipfile.ZipFile(path, "w") as archive:
        for full in sorted(files):
            archive.write(full, "ruleprobe/" + os.path.relpath(full, package).replace(os.sep, "/"))
    return path


class WheelTests(unittest.TestCase):
    # Covers: the pure-Python wheel named `ruleprobe-<version>-py3-none-any.whl`, checked on
    # the built wheel CI passes in; the package importing and running from it on `sys.path` as
    # a zip, uninstalled; the corpus inside it at `ruleprobe/corpus/`. A zip import cannot read
    # the corpus in place, so it needs `RULEPROBE_CORPUS` or an unpacked copy, as here.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        if WHEEL_ENV not in os.environ:
            self.wheel = _source_wheel(self.tmp.name)
            return
        built = os.environ[WHEEL_ENV]
        if not built or not os.path.isfile(built):
            raise AssertionError("%s=%r names no wheel file" % (WHEEL_ENV, built))
        self.wheel = os.path.abspath(built)
        self.assertEqual(os.path.basename(self.wheel),
                         "ruleprobe-%s-py3-none-any.whl" % ruleprobe.__version__)

    def probe(self, env=None):
        # -I and -S keep the checkout, PYTHONPATH and any installed copy off sys.path.
        result = subprocess.run([sys.executable, "-I", "-S", "-c", _PROBE, self.wheel,
                                 json.dumps(DECLARED)],
                                cwd=self.tmp.name, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    # Covers: the package imports and runs from the wheel on `sys.path` as a zip, uninstalled.
    def test_the_package_imports_and_runs_from_the_zip(self):
        corpus = self.unpack_corpus()
        env = dict(os.environ, RULEPROBE_CORPUS=corpus)
        out = self.probe(env)
        self.assertTrue(out["file"].startswith(self.wheel + os.sep), out["file"])
        self.assertEqual(out["version"], ruleprobe.__version__)
        self.assertEqual(out["hits"], ["transcript-hygiene/whole-file-cat"])
        self.assertTrue(out["scored"])

    # Covers: the corpus ships inside the wheel at `ruleprobe/corpus/`, beside `__file__`; read
    # from the zip, it is found through `RULEPROBE_CORPUS` pointed at an unpacked copy.
    def test_the_corpus_is_in_the_wheel_beside_file(self):
        out = self.probe(dict(os.environ, RULEPROBE_CORPUS=self.unpack_corpus()))
        self.assertEqual(out["dir"], os.path.join(self.wheel, "ruleprobe"))
        with zipfile.ZipFile(self.wheel) as archive:
            names = set(archive.namelist())
        self.assertIn("ruleprobe/corpus/labels.yaml", names)
        self.assertIn("ruleprobe/corpus/rules-zoo.json", names)
        self.assertTrue(any(n.startswith("ruleprobe/corpus/sessions/") for n in names))
        self.assertFalse([n for n in names if n.endswith((".so", ".pyd"))])

    # Covers: the wheel carries `ruleprobe/detectors/common.py` as source, and
    # `SECRET_PATTERNS` read out of that member by syntax tree, without importing, is the list.
    def test_secret_patterns_read_from_the_wheel_member(self):
        with zipfile.ZipFile(self.wheel) as archive:
            source = archive.read("ruleprobe/detectors/common.py").decode("utf-8")
        found = [ast.literal_eval(node.value) for node in ast.parse(source).body
                 if isinstance(node, ast.Assign)
                 and any(getattr(t, "id", "") == "SECRET_PATTERNS" for t in node.targets)]
        self.assertEqual(found, [common.SECRET_PATTERNS])

    def unpack_corpus(self):
        target = os.path.join(self.tmp.name, "unpacked")
        with zipfile.ZipFile(self.wheel) as archive:
            members = [n for n in archive.namelist() if n.startswith("ruleprobe/corpus/")]
            archive.extractall(target, members)
        return os.path.join(target, "ruleprobe", "corpus")


if __name__ == "__main__":
    unittest.main()
