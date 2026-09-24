# SPDX-License-Identifier: MIT
"""Transcript readers, and `iter_sessions` over them.

A reader is a module with `ROOT`, `transcripts(root)`, `read(path, empty=False)` and
`session_key(path)`. `read` returns None for a transcript that yields no event; with
`empty=True` it returns one that names a session with no events instead, so the `since`
cut-off applies before the no-event note does. `session_key` is the id `read` would give,
read from as few lines as decide it. Adding a runtime is adding one of those and a line in
`RUNTIMES`.
"""
import datetime
import json
import os

from . import claude_code, codex, gemini

RUNTIMES = {"claude-code": claude_code, "codex": codex, "gemini": gemini}

__all__ = ["iter_sessions", "RUNTIMES", "claude_code", "codex", "gemini"]

#: The `error` of an `errors` entry for a transcript set aside because another file carries
#: the same session: a copy, not a failure. The entry's `kept` names the file that was read.
COPY = "copy of a session read from another file"


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
    """Every session under `root`, one per runtime and session id, in path order.

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
      A copy set aside is recorded too, with `error` set to `COPY` and `kept` naming the
      file read in its place.

    Yields `Session` objects. A file that cannot be read, or holds no session, is skipped:
    a report over a hundred transcripts is not worth losing to one bad file. It is counted
    rather than swallowed, though - a hundred transcripts quietly becoming sixty is a
    number nobody can see is missing, so `errors` collects each one and
    `ruleprobe report` says how many there were.

    One session can sit in several files - a project directory copied or renamed, a
    worktree's folder - and each would count its hits again. So the files carrying one
    runtime's session id are read as one group: the one with the most events is kept, the
    first in path order on a tie, and the rest are set aside as copies. A file older than
    `since`, or with no event, is dropped or noted as it would be alone and is no candidate.
    Each group is yielded where its first file falls in path order, so the result does not
    depend on the order a directory lists its files in.

    A cheap pass reads each file's session id first, through its reader's `session_key`, and
    only then are sessions read, one group at a time. Holding every session until the last
    file had been read would hold the whole history in memory; this holds two at most.
    """
    return _sessions(root, runtime, since, errors, by_id=True)


def iter_file_sessions(root=None, runtime="auto", since=None, errors=None):
    """`iter_sessions`, but one session per transcript file, copies included.

    A labelled corpus names each session by its file, and a near-miss is often made by
    copying a positive and editing it, so two of its files may carry one session id and both
    are meant. Everything else counts a session once, through `iter_sessions`.
    """
    return _sessions(root, runtime, since, errors, by_id=False)


def _sessions(root, runtime, since, errors, by_id):
    """`iter_sessions` when `by_id`, else `iter_file_sessions`: each file its own group."""
    if runtime != "auto" and runtime not in RUNTIMES:
        raise ValueError("unknown runtime %r; one of auto, %s"
                         % (runtime, ", ".join(sorted(RUNTIMES))))
    stamp = _since_stamp(since)
    groups = {}
    order = []
    for path, reader in _paths(root, runtime):
        key = _group_key(path, reader) if by_id else path
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((path, reader))
    # Each address yielded, to its file. A file written between the two passes could carry
    # an id its key did not predict; its session is still yielded once.
    yielded = {}
    for key in order:
        kept, copies = _pick(groups.pop(key), stamp, errors)
        if kept is None:
            continue
        address = (kept.runtime, kept.id) if by_id else kept.path
        if address in yielded:
            copies.append(kept.path)
        if errors is not None:
            for path in copies:
                errors.append({"path": path, "error": COPY,
                               "kept": yielded.get(address, kept.path)})
        if address not in yielded:
            yielded[address] = kept.path
            yield kept


def _group_key(path, reader):
    """What groups `path` with the other files carrying its session: its reader and its
    session key, or the path itself when the key cannot be read, so the read reports it."""
    try:
        key = reader.session_key(path)
    except Exception:
        key = None
    return (reader.__name__, key) if key is not None else ("", path)


def _pick(members, stamp, errors):
    """The session to keep from `members`, the `(path, reader)` pairs of one group in path
    order, and the paths of the copies set aside for it. Every other file is noted in `errors`
    or dropped by `stamp` as `iter_sessions` describes. Two sessions are held at most."""
    kept = None
    copies = []
    for path, reader in members:
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
        if kept is None or len(session.events) > len(kept.events):
            session, kept = kept, session
        if session is not None:
            copies.append(session.path)
    return kept, copies


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
