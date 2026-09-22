# SPDX-License-Identifier: MIT
"""ruleprobe: which of your agent rules actually fire.

Deterministic detectors over a coding agent's own transcripts. Nothing is sent anywhere, no
model is asked anything, and the same transcript gives the same answer every time.

    from ruleprobe import iter_sessions, measure, report

    rows = [measure(s) for s in iter_sessions(since=30)]
    print(report(rows, by="rule"))

The engine is `run(events, ...)` over the event schema in `ruleprobe.events`; a reader turns
one runtime's transcript into that schema and nothing else in the package knows which
runtime wrote what.

A detector may be written as data instead of as Python: `ruleprobe.matchers` compiles one
entry into the same `Detector`, and `ruleprobe.rules` finds the files they live in.
"""
from .declarative import DeclarativeError
from .events import Hit, Session, counts
from .matchers import compile_detector, compile_matcher
from .readers import iter_sessions
from .registry import DEFAULT, Detector, Registry, from_spec, register_compiler, run
from .report import RULE_MIN_SESSIONS, RULE_PROMOTE_SHARE, measure, report
from .rules import Bundle, Finding, RuleEntry, load_bundle
from .shell import analyse, pipelines

__version__ = "0.1.0.dev0"

__all__ = [
    "Bundle", "DeclarativeError", "Detector", "Finding", "Hit", "Registry", "RuleEntry",
    "Session", "DEFAULT",
    "analyse", "compile_detector", "compile_matcher", "counts", "from_spec",
    "iter_sessions", "load_bundle", "measure", "pipelines", "register_compiler", "report",
    "run", "RULE_MIN_SESSIONS", "RULE_PROMOTE_SHARE", "__version__",
]
