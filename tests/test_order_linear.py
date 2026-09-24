# SPDX-License-Identifier: MIT
"""`order` against a naive reference: the linear evaluation gives the same hits and the same
opportunity triples as walking the window after every opened event.

Run: python3 -m unittest discover -s tests
"""
import random
import time
import unittest

from corpus import bash, tool_result
from ruleprobe import analyse
from ruleprobe.matchers import compile_detector

#: One event per label: `first` true, `then` true, both true (one segment each), both
#: undecided (a command the parse skips), neither, and a tool result, which `within` does
#: not count and which `first` opens when the detector is built with `results_open`.
COMMANDS = {"F": "touch a.py", "T": "pytest -q", "B": "touch a.py && pytest -q",
            "U": "echo 'unterminated", "N": "ls"}


def events_for(labels):
    out = []
    for index, label in enumerate(labels):
        if label == "R":
            out.append(tool_result("ok", tool_use_id="r%d" % index, turn=1 + index // 7))
        else:
            out.append(bash(COMMANDS[label], turn=1 + index // 7, id="e%d" % index))
    return out


def detector(within, results_open=False):
    first = {"command": {"name": "touch"}}
    if results_open:
        first = {"any": [first, {"kind": "tool_result"}]}
    return compile_detector({"id": "t/order", "rule": "t", "event": "session", "when": {
        "order": {"first": first, "then": {"command": {"name": "pytest"}},
                  "within": within}}}, "<test>")


def reference(labels, events, within, results_open=False):
    """The walk `order` made before it was linear, over the labels."""
    opens = "FBR" if results_open else "FB"
    out = []
    for i, label in enumerate(labels):
        if label == "U":
            out.append((events[i]["turn"], events[i].get("id"), None))
            continue
        if label not in opens:
            continue
        followed, distance = False, 0
        for j in range(i + 1, len(labels)):
            if labels[j] == "U":
                followed = None
            elif labels[j] in "TB":
                followed = True
                break
            if labels[j] == "R":
                continue
            distance += 1
            if distance >= within:
                break
        out.append((events[i]["turn"], events[i].get("id"), followed))
    return out


class OrderDifferentialTests(unittest.TestCase):
    def test_the_linear_evaluation_matches_the_naive_walk(self):
        rng = random.Random(49)
        for case in range(400):
            labels = [rng.choice("FFTBUNNRR") for _ in range(rng.randint(0, 40))]
            within = rng.choice([1, 2, 3, 5, 8, 100000])
            results_open = case % 2 == 1
            events = events_for(labels)
            found = detector(within, results_open)
            ctx = analyse(events)
            expected = reference(labels, events, within, results_open)
            with self.subTest(case=case, labels="".join(labels), within=within,
                              results_open=results_open):
                self.assertEqual(found.opportunities(events, ctx), expected)
                self.assertEqual([tuple(hit) for hit in found.fn(events, ctx)],
                                 [(t, i) for t, i, f in expected if f is True])

    def test_many_opened_events_in_a_long_session_stay_linear(self):
        # 10,000 opened events among 40,000: the old walk was about 4 x 10^8 steps.
        labels = (["F"] * 10000) + (["N", "R"] * 15000)
        events = events_for(labels)
        ctx = analyse(events)
        found = detector(100000)
        started = time.perf_counter()
        triples = found.opportunities(events, ctx)
        self.assertLess(time.perf_counter() - started, 5.0)
        self.assertEqual(len(triples), 10000)
        self.assertTrue(all(f is False for _t, _i, f in triples))


if __name__ == "__main__":
    unittest.main()
