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

`measure(session)` counts what a detector found; `validity()` is its counterpart over the
labelled corpus that ships in `ruleprobe/corpus/`, and says how much that count is worth.

A detector may be written as data instead of as Python: `ruleprobe.matchers` compiles one
entry into the same `Detector`, and `ruleprobe.rules` finds the files they live in.
"""
from .declarative import DeclarativeError
from .events import Hit, Session, counts
from .matchers import compile_detector, compile_matcher, is_undecided
from .readers import iter_sessions
from .registry import DEFAULT, Detector, Registry, from_spec, register_compiler, run
from .report import (RULE_MIN_SESSIONS, RULE_PROMOTE_SHARE, measure, report,
                     report_data)
from .rules import Bundle, Finding, RuleEntry, load_bundle
from .shell import analyse, pipelines
from .validity import (CorpusError, DEFAULT_FLOOR, Score, load_corpus,
                       score_corpus, score_examples, validity,
                       validity_table)

__version__ = "0.1.0"

__all__ = [
    "Bundle", "CorpusError", "DeclarativeError", "Detector", "Finding", "Hit", "Registry",
    "RuleEntry", "Score", "Session", "DEFAULT", "DEFAULT_FLOOR",
    "analyse", "compile_detector", "compile_matcher", "counts", "from_spec",
    "is_undecided", "iter_sessions", "load_bundle", "load_corpus", "measure", "pipelines",
    "register_compiler", "report", "report_data", "run", "score_corpus", "score_examples", "validity",
    "validity_table", "RULE_MIN_SESSIONS", "RULE_PROMOTE_SHARE", "__version__",
]
