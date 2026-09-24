# SPDX-License-Identifier: MIT
"""A repeated opportunity point with no tool use id, `None` or `""`, is several opportunities,
not a malformed result; a repeated point with one is still refused. The rule is `_tally`'s
docstring.

Run: python3 -m unittest discover -s tests
"""
import unittest

from corpus import bash, prompt, say, tool_result
from ruleprobe import Detector, Registry, analyse, compile_detector, measure
from ruleprobe.events import Session


def session(events):
    return Session("s1", "repo", "claude_code", events, "s1.jsonl")


def fixed(*triples):
    return lambda events, ctx: list(triples)


def order(first):
    return compile_detector({"id": "o/then-bash", "rule": "o", "event": "session",
                             "when": {"order": {"first": first,
                                                "then": {"tool": "Bash"}}}}, "<test>")


class RepeatedPointTests(unittest.TestCase):
    def test_an_order_opening_on_two_results_in_one_turn_keeps_its_compliance(self):
        # The two tool results carry `tool_use_id`s, but an opportunity point names a tool
        # use id only for a `tool_use` event, so the compiled `order` gives (1, None) twice.
        detector = order({"kind": "tool_result"})
        events = [tool_result("a", tool_use_id="x1"), tool_result("b", tool_use_id="x2"),
                  bash("ls", id="tu3")]
        ctx = analyse(events)
        self.assertEqual(detector.opportunities(ctx.events, ctx),
                         [(1, None, True), (1, None, True)])
        row = measure(session(events), registry=Registry([detector]))
        self.assertNotIn("rules_errors", row)
        self.assertEqual(row["rules"], {"o/then-bash": 2})
        self.assertEqual(row["compliance"], {"o/then-bash": {"opportunities": 2, "followed": 2,
                                                             "undecided": 0}})

    def test_an_order_opening_on_text_and_prompts_counts_each_event(self):
        for label, first, events, followed in (
                ("assistant_text", {"kind": "assistant_text"},
                 [say("one", final=False), say("two"), bash("ls", turn=2, id="tu2")], 2),
                ("user_prompt", {"kind": "user_prompt"},
                 [prompt(), prompt(), say("done")], 0)):
            with self.subTest(label):
                row = measure(session(events), registry=Registry([order(first)]))
                self.assertNotIn("rules_errors", row)
                self.assertEqual(row["compliance"], {"o/then-bash": {
                    "opportunities": 2, "followed": followed, "undecided": 0}})

    def test_an_order_opening_on_two_tool_uses_with_empty_ids_keeps_its_compliance(self):
        # A reader gives a tool use its transcript left without an id the id "".
        detector = compile_detector({"id": "o/ls-then-cat", "rule": "o", "event": "session",
                                     "when": {"order": {"first": {"command": {"name": "ls"}},
                                                        "then": {"command": {"name": "cat"}}}}},
                                    "<test>")
        events = [bash("ls a", id=""), bash("ls b", id=""), bash("cat c", id="")]
        ctx = analyse(events)
        self.assertEqual(detector.opportunities(ctx.events, ctx),
                         [(1, "", True), (1, "", True)])
        row = measure(session(events), registry=Registry([detector]))
        self.assertNotIn("rules_errors", row)
        self.assertEqual(row["compliance"], {"o/ls-then-cat": {"opportunities": 2,
                                                               "followed": 2,
                                                               "undecided": 0}})

    def test_a_hand_written_repeat_with_no_id_counts_each_triple(self):
        registry = Registry([Detector("a/opp", "a", "session", lambda e, c: [],
                                      opportunities=fixed((1, None, True), (1, None, False),
                                                          (1, None, None)))])
        row = measure(session([bash("ls")]), registry=registry)
        self.assertNotIn("rules_errors", row)
        self.assertEqual(row["compliance"], {"a/opp": {"opportunities": 2, "followed": 1,
                                                       "undecided": 1}})

    def test_a_hand_written_repeat_with_an_id_is_still_refused(self):
        for label, triples in (
                ("both decided", [(1, "t1", True), (1, "t1", False)]),
                ("one undecided", [(1, "t1", None), (1, "t1", True)]),
                ("beside id-less repeats", [(1, None, True), (1, None, True),
                                            (2, "t2", True), (2, "t2", True)])):
            with self.subTest(label):
                registry = Registry([Detector("a/bad", "a", "session", lambda e, c: [],
                                              opportunities=fixed(*triples))])
                row = measure(session([bash("ls")]), registry=registry)
                self.assertEqual(row["rules_errors"], [
                    {"detector": "a/bad", "error": "MalformedOpportunities",
                     "hook": "opportunities"}])
                self.assertEqual(row["compliance"], {})

    def test_the_same_id_in_two_turns_is_two_points(self):
        registry = Registry([Detector("a/opp", "a", "session", lambda e, c: [],
                                      opportunities=fixed((1, "t1", True), (2, "t1", True)))])
        row = measure(session([bash("ls")]), registry=registry)
        self.assertEqual(row["compliance"]["a/opp"]["opportunities"], 2)


if __name__ == "__main__":
    unittest.main()
