# SPDX-License-Identifier: MIT
"""Transcript readers, and `iter_sessions` over them.

A reader is a module with `ROOT`, `transcripts(root)` and `read(path, empty=False)`. `read`
returns None for a transcript that yields no event; with `empty=True` it returns one that
names a session with no events instead, so the `since` cut-off applies before the no-event
note does. Adding a runtime is adding one of those and a line in `RUNTIMES`.
"""
import datetime
import json
import os

from . import claude_code, codex, gemini

RUNTIMES = {"claude-code": claude_code, "codex": codex, "gemini": gemini}

__all__ = ["iter_sessions", "RUNTIMES", "claude_code", "codex", "gemini"]


def _since_stamp(since):
    """`since` as a `YYYY-MM-DD` string, from a date, a datetime, a string, or an int number
    of days back. `None` means no filtering."""
    if since is None:
        return None
    if isinstance(since, bool):
        raise TypeError("since must be a date, a YYYY-MM-DD string, or a number of days")
    if isinstance(since, int):
        day = datetime.date.today() - datetime.timedelta(days=since)
        return day.isoformat()
    if isinstance(since, datetime.datetime):
        return since.date().isoformat()
    if isinstance(since, datetime.date):
        return since.isoformat()
    return str(since)[:10]


def _detect(path):
    """The reader for `path`, from its first line.

    A Codex rollout opens with a line whose `type` is `session_meta`, and a Gemini CLI
    session with a line `gemini.recognises`, which no Claude Code line matches; anything else
    is Claude Code. The line is parsed rather than searched,
    because a user prompt that quotes `"session_meta"` - a transcript of somebody working on
    this package, say - would otherwise be handed to the Codex reader and silently read as
    nothing.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    try:
        entry = json.loads(first)
    except ValueError:
        entry = None
    if isinstance(entry, dict) and entry.get("type") == "session_meta":
        return codex
    if gemini.recognises(entry):
        return gemini
    return claude_code


def iter_sessions(root=None, runtime="auto", since=None, errors=None):
    """Every session under `root`, in path order.

    - `root` - a directory to walk. `None` reads each selected runtime's own default
      location: `~/.claude/projects`, `~/.codex/sessions` and `~/.gemini/tmp`.
    - `runtime` - `"auto"`, `"claude-code"`, `"codex"` or `"gemini"`. `"auto"` reads every
      default location and decides each file by its first line, so a directory holding
      several kinds is read correctly.
    - `since` - a date, a `YYYY-MM-DD` string, or a number of days back. A transcript whose
      last timestamp is older is skipped; one that carries no timestamp at all is kept,
      because an absent date is not an old one.
    - `errors` - a list, when you pass one, collecting `{"path": ..., "error": ...}` for
      every transcript a reader could not read and every one that held no session or no
      event. One with no event that `since` would have dropped is dropped, not recorded.

    Yields `Session` objects. A file that cannot be read, or holds no session, is skipped:
    a report over a hundred transcripts is not worth losing to one bad file. It is counted
    rather than swallowed, though - a hundred transcripts quietly becoming sixty is a
    number nobody can see is missing, so `errors` collects each one and
    `ruleprobe report` says how many there were.
    """
    if runtime != "auto" and runtime not in RUNTIMES:
        raise ValueError("unknown runtime %r; one of auto, %s"
                         % (runtime, ", ".join(sorted(RUNTIMES))))
    stamp = _since_stamp(since)
    for path, reader in _paths(root, runtime):
        try:
            session = reader.read(path, empty=True)
        except Exception as exc:
            if errors is not None:
                errors.append({"path": path, "error": type(exc).__name__})
            continue
        if session is None:
            if errors is not None:
                errors.append({"path": path, "error": "no session in it"})
            continue
        if stamp and session.ended and session.ended[:10] < stamp:
            continue
        if not session.events:
            if errors is not None:
                errors.append({"path": path, "error": "no session in it"})
            continue
        yield session


def _walk(base):
    """Every `.jsonl` file under `base`, in path order."""
    found = []
    for directory, _dirs, files in os.walk(base, followlinks=True):
        for name in files:
            if name.endswith(".jsonl"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def _paths(root, runtime):
    """`(path, reader)` for every transcript to read, deduplicated and ordered."""
    seen = set()
    out = []
    if root is not None:
        base = os.path.expanduser(root)
        if runtime == "gemini":
            return [(path, gemini) for path in gemini.transcripts(base)]
        for path in _walk(base):
            reader = _detect(path) if runtime == "auto" else RUNTIMES[runtime]
            if reader is not None and path not in seen:
                seen.add(path)
                out.append((path, reader))
        if runtime == "auto":
            # A legacy Gemini `session-*.json` ends in no `.jsonl`, so `_walk` never sees it.
            out.extend((path, gemini) for path in gemini.transcripts(base)
                       if path.endswith(".json"))
            out.sort(key=lambda pair: pair[0])
        return out
    names = [runtime] if runtime != "auto" else sorted(RUNTIMES)
    for name in names:
        reader = RUNTIMES[name]
        for path in reader.transcripts():
            if path not in seen:
                seen.add(path)
                out.append((path, reader))
    return out
