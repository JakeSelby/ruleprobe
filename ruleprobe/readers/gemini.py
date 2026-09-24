# SPDX-License-Identifier: MIT
"""Gemini CLI sessions: `~/.gemini/tmp/<project>/chats/session-<stamp>-<id>.jsonl`.

One JSON object per line, append-only, in four shapes: a metadata line (`sessionId`,
`projectHash`, `startTime`), a message record (`id`, `timestamp`, `type`, `content`, and on a
`gemini` record `toolCalls`, `thoughts` and `model`), a `{"$set": ...}` update and a
`{"$rewindTo": id}`. A message that changes is appended again whole, so messages are keyed by
`id`: the last line wins and the first appearance fixes the order. Gemini CLI 0.38 and earlier
wrote one `session-*.json` object instead; it is read too, and a `.jsonl` of the same name
beside it, which is what resuming one leaves, is the one read.

A tool call and its result both live on the `gemini` record that made the call. Gemini also
writes the results back as `user` records made only of `functionResponse` parts; those are
not prompts, start no turn and make no event. `info`, `error` and `warning` records are UI
notices and make none either.

What is read differently from the transcript, and why:

- `$rewindTo` is ignored. Gemini's own loader drops the rewound messages, but their tool calls
  ran, so they are kept.
- `$set.messages` is ignored. Compaction writes it, but so do truncation, tool-output masking
  and rollback, with no marker telling them apart, so this reader emits no `compact` event.
- `run_shell_command` is `Bash` only when `.project_root`, in the project directory above
  `chats/`, holds a POSIX path. On Windows its `command` is PowerShell, which can tokenise as
  Bash, and with no root the platform is not known; every root that is not POSIX - a drive
  letter, a UNC path, none - keeps the native name, measured by no `Bash` detector.
- No event carries a `model`: Gemini's router and quota fallback change it without anyone
  choosing to, so `model` is the empty string and `cache-hygiene/model-switch` counts nothing.
- `write_file` is `Write` and `replace` is `Edit`: their keys are Claude Code's. A relative
  `file_path` is resolved against a POSIX `.project_root` unless it climbs out of it. `invoke_agent` stays native until its
  arguments are checked against `Agent`'s, and every other tool keeps its native name.

A subagent writes its own file under `chats/<parent session id>/`, read as its own session
with the id `<parent session id>/<its own session id>`, so it stays unique even when the file
repeats its parent's id.
"""
import json
import ntpath
import os
import posixpath
import re

from ..events import Session, result_text

#: Where Gemini CLI keeps its sessions.
ROOT = os.path.join("~", ".gemini", "tmp")

_TOOL_NAMES = {"write_file": "Write", "replace": "Edit"}
_SHELL = "run_shell_command"
_WINDOWS = re.compile(r"[A-Za-z]:|\\\\")
_MESSAGE_TYPES = frozenset(("user", "gemini", "info", "error", "warning"))


def transcripts(root=None):
    """Every Gemini CLI session under `root`: the files below a `chats` directory at or under
    `root` - one above it does not count - with a legacy `session-*.json` left out when its
    `.jsonl` is beside it."""
    base = os.path.expanduser(root or ROOT)
    top = os.path.basename(os.path.normpath(base))
    found = []
    for directory, _dirs, files in os.walk(base, followlinks=True):
        relative = os.path.relpath(directory, base)
        parts = [top] + ([] if relative == os.curdir else relative.split(os.sep))
        if "chats" not in parts:
            continue
        names = set(files)
        for name in files:
            if name.endswith(".jsonl") or (name.startswith("session-") and name.endswith(".json")
                                           and name + "l" not in names):
                found.append(os.path.join(directory, name))
    return sorted(found)


def recognises(entry):
    """Whether a parsed first line is Gemini's: the metadata line, a message record, or an
    update or rewind record. No Claude Code or Codex line has any of these shapes."""
    if not isinstance(entry, dict) or "message" in entry or "payload" in entry:
        return False
    if isinstance(entry.get("sessionId"), str) and isinstance(entry.get("projectHash"), str):
        return True
    if (isinstance(entry.get("id"), str) and entry.get("type") in _MESSAGE_TYPES
            and "content" in entry):
        return True
    return isinstance(entry.get("$set"), dict) or isinstance(entry.get("$rewindTo"), str)


def read(path):
    """One `Session` from one session file, or None when the file holds no session.

    A line that is not JSON, or not an object, is skipped: a session is written by a live
    process and its tail may be half a line.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            body = handle.read()
    except OSError:
        return None
    records = None
    if path.endswith(".json"):
        try:
            records = [json.loads(body)]
        except ValueError:
            records = None
    if records is None:
        records = []
        for line in body.splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    session_id = ""
    stamps = []
    messages = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if "$rewindTo" in record:
            continue
        if "$set" in record:
            update = record.get("$set")
            if isinstance(update, dict) and isinstance(update.get("lastUpdated"), str):
                stamps.append(update["lastUpdated"])
            continue
        if isinstance(record.get("id"), str):
            _keep(messages, record)
            continue
        if isinstance(record.get("sessionId"), str):
            session_id = session_id or record["sessionId"]
            for key in ("startTime", "lastUpdated"):
                if isinstance(record.get(key), str):
                    stamps.append(record[key])
            # A legacy file is the metadata and every message in one object.
            listed = record.get("messages")
            for message in listed if isinstance(listed, list) else []:
                if isinstance(message, dict) and isinstance(message.get("id"), str):
                    _keep(messages, message)
    chats, nested = _chats(path)
    project_root = _project_root(chats)
    events = _events(list(messages.values()), project_root)
    stamps.extend(m["timestamp"] for m in messages.values()
                  if isinstance(m.get("timestamp"), str) and m["timestamp"])
    if not session_id and not events:
        return None
    own = session_id or os.path.splitext(os.path.basename(path))[0]
    return Session(id="/".join(nested + [own]),
                   repo=_basename(project_root),
                   runtime="gemini", events=events, path=path,
                   started=min(stamps) if stamps else "",
                   ended=max(stamps) if stamps else "")


def _keep(messages, record):
    """Keep `record` under its id: a later copy replaces the earlier one in its place."""
    messages[record["id"]] = record


def _events(messages, project_root):
    """The event list from the messages, in the order they first appeared."""
    events = []
    turn = 0
    pending_final = None
    posix = project_root.startswith("/")
    for message in messages:
        kind = message.get("type")
        if kind == "user":
            parts = _parts(message.get("content"))
            if parts and all(isinstance(p, dict) and "functionResponse" in p for p in parts):
                continue
            turn += 1
            if pending_final is not None:
                pending_final["final"] = True
                pending_final = None
            text = _text(message.get("displayContent")) or _text(message.get("content"))
            events.append({"kind": "user_prompt", "turn": turn, "text": text})
        elif kind == "gemini":
            text = _text(message.get("content"))
            if text.strip():
                # The model is left out on purpose: see the module docstring.
                pending_final = {"kind": "assistant_text", "turn": turn, "text": text,
                                 "final": False, "model": ""}
                events.append(pending_final)
            calls = message.get("toolCalls")
            for call in calls if isinstance(calls, list) else []:
                if isinstance(call, dict):
                    events.extend(_call(call, turn, posix, project_root))
    if pending_final is not None:
        pending_final["final"] = True
    return events


def _call(call, turn, posix, project_root):
    """The `tool_use` for one recorded call, and its `tool_result` when it has one."""
    native = call.get("name") if isinstance(call.get("name"), str) else ""
    use_id = call.get("id") if isinstance(call.get("id"), str) else ""
    arguments = call.get("args")
    arguments = arguments if isinstance(arguments, dict) else {}
    if native == _SHELL and posix:
        name = "Bash"
    else:
        name = _TOOL_NAMES.get(native, native)
    if name in ("Write", "Edit") and posix:
        file_path = arguments.get("file_path")
        if isinstance(file_path, str) and file_path and not file_path.startswith("/"):
            arguments = dict(arguments, file_path=_resolve(project_root, file_path))
    out = [{"kind": "tool_use", "turn": turn, "id": use_id, "name": name,
            "input": arguments}]
    # An empty result, `[]` or `{}`, answers nothing, so it makes no event.
    if call.get("result"):
        out.append({"kind": "tool_result", "turn": turn, "tool_use_id": use_id,
                    "tool_name": name, "text": result_text(_result(call["result"]), name)})
    return out


def _parts(content):
    """A `PartListUnion` as a list: a string, one part, or a list of either."""
    if content is None:
        return []
    return content if isinstance(content, list) else [content]


def _text(content):
    """The text of a message's parts, leaving out thought parts."""
    out = []
    for part in _parts(content):
        if isinstance(part, str):
            out.append(part)
        elif (isinstance(part, dict) and isinstance(part.get("text"), str)
              and not part.get("thought")):
            out.append(part["text"])
    return "".join(out)


def _result(content):
    """A tool result's text: its text parts, and each `functionResponse`'s `output`, or its
    `error` when the call failed."""
    out = []
    for part in _parts(content):
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, dict):
            if isinstance(part.get("text"), str):
                out.append(part["text"])
            response = part.get("functionResponse")
            response = response.get("response") if isinstance(response, dict) else None
            if isinstance(response, dict):
                for key in ("output", "error"):
                    if isinstance(response.get(key), str):
                        out.append(response[key])
    return "\n".join(out)


def _resolve(project_root, file_path):
    """`file_path` joined to the POSIX `project_root`, or as written when `..` climbs out."""
    root = project_root.rstrip("/") or "/"
    joined = posixpath.normpath(posixpath.join(root, file_path))
    inside = joined == root or joined.startswith(root.rstrip("/") + "/")
    return joined if inside else file_path


def _chats(path):
    """The `chats` directory `path` sits under, at any depth, and the directory names between
    it and the file - a subagent's parent session id - or `("", [])` when there is none."""
    directory = os.path.dirname(os.path.abspath(path))
    nested = []
    while True:
        if os.path.basename(directory) == "chats":
            return directory, nested
        parent = os.path.dirname(directory)
        if parent == directory:
            return "", []
        nested.insert(0, os.path.basename(directory))
        directory = parent


def _project_root(chats):
    """The absolute project root from `.project_root` in the project directory holding
    `chats`, or the empty string."""
    if not chats:
        return ""
    try:
        with open(os.path.join(os.path.dirname(chats), ".project_root"),
                  encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _basename(root):
    """The last component of a POSIX or a Windows project root."""
    if not root:
        return ""
    if _WINDOWS.match(root):
        return ntpath.basename(root.rstrip("\\/"))
    return posixpath.basename(root.rstrip("/"))
