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
"""
from .events import Hit, Session, counts
from .readers import iter_sessions
from .registry import DEFAULT, Detector, Registry, from_spec, register_compiler, run
from .report import RULE_MIN_SESSIONS, RULE_PROMOTE_SHARE, measure, report
from .shell import analyse, pipelines

__version__ = "0.1.0.dev0"

__all__ = [
    "Detector", "Hit", "Registry", "Session", "DEFAULT",
    "analyse", "counts", "from_spec", "iter_sessions", "measure", "pipelines",
    "register_compiler", "report", "run",
    "RULE_MIN_SESSIONS", "RULE_PROMOTE_SHARE", "__version__",
]
