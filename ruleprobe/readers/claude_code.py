# SPDX-License-Identifier: MIT
"""Claude Code transcripts: `~/.claude/projects/<slug>/<session-id>.jsonl`.

One JSON object per line. The lines that matter here are `user`, `assistant` and the
`system` line that marks a compaction boundary; everything else is skipped. Token accounting
is not this package's business and is not read.

Two shapes cost more care than they look:

- One API response is written as several lines repeating the same message id, each carrying
  one content block, and the early lines of a response carry partial text. A block seen
  twice is one block, not two events: the later, longer text replaces the partial in the
  event already emitted.
- A subagent's turns may appear in the parent's file as `isSidechain` lines (older Claude
  Code) or in a file of their own (newer, `<session>/subagents/agent-<id>.jsonl`). In a
  parent's file, sidechain lines are that agent's work, not this session's, so they make no
  event. The subagent's own file marks every line `isSidechain` too, so the file is told by
  its content rather than its path: when every `user` and `assistant` line in it is a
  sidechain line naming one and the same `agentId`, the lines are this file's own work, and
  the file is read as its own session, `<parent session id>/<agent id>`.

A call that never ran makes no event, and neither does its result. Claude Code answers such
a call with an error result: since 2.1 the line carries `toolDenialKind` (`user-rejected`,
`cancelled`, `permission-rule`, `interrupted`), and before it the result text is one of the
fixed refusals - the user rejecting or cancelling the call, a `Permission to use ...` denial,
a `PreToolUse:<tool> hook error: ...` block, an interrupt marker - or a `<tool_use_error>` from a
check made before the tool ran, such as input validation or a cancelled sibling call. The
line's own markers, `toolDenialKind` and `toolUseResult`, are read only on a line holding one
result: on a line holding several, each result is decided by its own text, so a refusal never
drops the sibling that ran. A hook's own deny reason, free text, is recognised only by
`toolDenialKind`. An interrupted call may have started, but the
line does not say, so it is left out: a measure that under-counts. An error the tool itself
raised while running (`<tool_use_error>Error calling tool ...`) and a command that exits
non-zero (`Exit code 1`) are calls that ran, and count.

A transcript that yields no event is not a measured session: `read` returns None for it, as
for a file that holds no session at all, so it never enters a share's denominator.
`session_key(path)` gives the id `read` would, from as few lines as decide it, so
`iter_sessions` can find two files carrying one session before reading either.
`read(path, empty=True)` returns it with no events instead, which `iter_sessions` uses to drop
an old one by `since` before reporting the rest.
"""
import json
import os
import re

from ..events import Session, result_text, text_of

#: Where Claude Code keeps its transcripts.
ROOT = os.path.join("~", ".claude", "projects")

#: How an error result for a call that never ran begins, before `toolDenialKind` was written.
_NOT_RUN_PREFIXES = (
    "The user doesn't want to proceed with this tool use",
    "The user doesn't want to take this action right now",
    "[Request interrupted by user",
    "[Tool call not completed",
    "[Tool call did not complete",
    "[Tool call interrupted",
    "Permission to use ",
)
#: A PreToolUse hook's blocking error, as Claude Code words it: `PreToolUse:<tool> hook error: `.
_HOOK_BLOCKED = re.compile(r"PreToolUse:\S+ hook error: ")
_TOOL_USE_ERROR = "<tool_use_error>"
#: How a `<tool_use_error>` raised by the running tool itself begins.
_RAN_AND_FAILED = "Error calling tool"


def transcripts(root=None):
    """Every Claude Code transcript under `root`, oldest modification first."""
    base = os.path.expanduser(root or ROOT)
    found = []
    for directory, _dirs, files in os.walk(base, followlinks=True):
        for name in files:
            if name.endswith(".jsonl"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def read(path, empty=False):
    """One `Session` from one transcript, or None when the file yields no event - or, with
    `empty`, when it holds no session id either.

    A line that is not JSON, or not an object, is skipped rather than fatal: a transcript is
    written by a live process and its tail may be half a line. The file is read once, so the
    lines that decide whose work it is are the lines read.
    """
    entries = _entries(path)
    if entries is None:
        return None
    session_id, agent_id = _identity(entries)
    events = []
    cwd = ""
    started = ended = ""
    tool_names = {}
    not_run = set()
    blocks_seen = set()
    text_blocks = {}
    turn = 0
    pending_final = None
    for entry in entries:
        sidechain = bool(entry.get("isSidechain")) and not agent_id
        stamp = entry.get("timestamp") or ""
        if stamp:
            started = stamp if not started or stamp < started else started
            ended = stamp if stamp > ended else ended
        cwd = cwd or entry.get("cwd") or ""
        kind = entry.get("type")
        message = entry.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        mid = message.get("id") if isinstance(message, dict) else None
        if kind == "system":
            if entry.get("subtype") == "compact_boundary" and not sidechain:
                events.append({"kind": "compact", "turn": turn})
            continue
        if kind == "user":
            if sidechain:
                continue
            blocks = content if isinstance(content, list) else []
            results = [b for b in blocks
                       if isinstance(b, dict) and b.get("type") == "tool_result"]
            for block in results:
                tool_use_id = block.get("tool_use_id") or ""
                if isinstance(tool_use_id, str) and tool_use_id \
                        and _never_ran(entry if len(results) == 1 else {}, block):
                    not_run.add(tool_use_id)
                    continue
                name = tool_names.get(tool_use_id, "")
                events.append({"kind": "tool_result", "turn": turn,
                               "tool_use_id": tool_use_id, "tool_name": name,
                               "text": result_text(block.get("content"), name)})
            if results or entry.get("isMeta") or entry.get("isCompactSummary"):
                continue
            turn += 1
            if pending_final is not None:
                pending_final["final"] = True
                pending_final = None
            events.append({"kind": "user_prompt", "turn": turn,
                           "text": _prompt_text(content)})
            continue
        if kind != "assistant" or sidechain:
            continue
        model = message.get("model")
        for index, block in enumerate(content or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text") or ""
                key = ("text", mid, block.get("apiBlockIndex", index))
                # The early lines of a response carry a partial of the same block, so
                # the key holds no text: a block seen twice is one event that grows,
                # and not two messages for a `message` detector to count.
                if mid and key in text_blocks:
                    seen_block = text_blocks[key]
                    if len(text) > len(seen_block["text"]):
                        seen_block["text"] = text
                    continue
                pending_final = {"kind": "assistant_text", "turn": turn, "text": text,
                                 "final": False, "model": model or ""}
                events.append(pending_final)
                if mid:
                    text_blocks[key] = pending_final
            elif block.get("type") == "tool_use":
                use_id = block.get("id") or ""
                key = ("tool_use", mid, block.get("apiBlockIndex", index), use_id)
                if key in blocks_seen:
                    continue
                blocks_seen.add(key)
                tool_names[use_id] = block.get("name") or ""
                events.append({"kind": "tool_use", "turn": turn, "id": use_id,
                               "name": block.get("name") or "",
                               "input": block.get("input")})
    if pending_final is not None:
        pending_final["final"] = True
    if not_run:
        events = [e for e in events
                  if not (e["kind"] == "tool_use" and isinstance(e["id"], str)
                          and e["id"] in not_run)]
    if not events and not (empty and session_id):
        return None
    return Session(id=_key(session_id, agent_id, path),
                   repo=os.path.basename(cwd.rstrip("/")) if cwd else "",
                   runtime="claude-code", events=events, path=path,
                   started=started, ended=ended, cwd=cwd)


def session_key(path):
    """The id `read(path)` gives its session, or None when the file cannot be opened or names
    neither a `sessionId` nor an agent id, since a file known only by its stem is not known
    to be another file's copy.

    It reads only as far as decides the id: to the first `sessionId` and the first line that
    shows the file is not a subagent's own, which in a parent's file is its opening lines. A
    subagent's own file is read to the end, since only its last line can rule that out. A
    file that `read` finds no session in may still have a key; it is simply never kept.
    """
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        session_id, agent_id = _identity(_parsed(handle))
    if not session_id and not agent_id:
        return None
    return _key(session_id, agent_id, path)


def _key(session_id, agent_id, path):
    """A session's id: `<parent session id>/<agent id>` for a subagent's own file, the
    `sessionId` otherwise, and the file's stem when the file names neither. A `sessionId`
    that is not a string, a list say, is its `str()`, so the id is always a string."""
    if session_id and not isinstance(session_id, str):
        session_id = str(session_id)
    if agent_id:
        session_id = "%s/%s" % (session_id, agent_id) if session_id else agent_id
    return session_id or os.path.basename(path)[:-6]


def _entries(path):
    """Every JSON object line of `path`, in order, or None when it cannot be opened."""
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        return list(_parsed(handle))


def _parsed(lines):
    """Each line of `lines` that is a JSON object, parsed, in order."""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            yield entry


def _identity(entries):
    """`(session id, agent id)` for `entries`: the first `sessionId` in them, and the agent id
    when they are a subagent's own transcript, else "". It stops once both are decided, so
    `session_key` can hand it a lazy iterator and `read` its list.

    They are a subagent's own when every `user` and `assistant` line is `isSidechain` and all
    of them name the same non-empty `agentId`. Those lines carry the work; a `system`,
    `attachment` or `summary` line does not, so one written without the markers cannot turn
    the file back into an empty session. A parent's file holds its own non-sidechain lines,
    so its sidechain lines stay another agent's work; a file mixing agent ids is read as a
    parent, which counts less rather than more.
    """
    session_id = agent = ""
    parent = False
    for entry in entries:
        session_id = session_id or entry.get("sessionId") or ""
        if parent:
            if session_id:
                break
            continue
        if entry.get("type") not in ("user", "assistant"):
            continue
        named = entry.get("agentId")
        if not entry.get("isSidechain") or not isinstance(named, str) or not named \
                or (agent and named != agent):
            parent = True
            agent = ""
            if session_id:
                break
            continue
        agent = named
    return session_id, agent


def _never_ran(entry, block):
    """Whether an error result answers a call that never ran: see the module docstring.
    `entry` is the line, for its markers, or `{}` when the line holds other results too."""
    if block.get("is_error") is not True:
        return False
    kind = entry.get("toolDenialKind")
    if (isinstance(kind, str) and kind) or entry.get("toolUseResult") == "User rejected tool use":
        return True
    content = block.get("content")
    if isinstance(content, list):
        content = "\n".join(text_of(b.get("text")) for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
    text = text_of(content).lstrip()
    if text.startswith(_TOOL_USE_ERROR):
        return not text[len(_TOOL_USE_ERROR):].lstrip().startswith(_RAN_AND_FAILED)
    return text.startswith(_NOT_RUN_PREFIXES) or bool(_HOOK_BLOCKED.match(text))


def _prompt_text(content):
    """A user prompt's text, whether the line wrote a string or a list of blocks. A
    `message: {role: user}` detector reads this, and a Codex rollout carries the same."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text_of(b.get("text")) for b in content
                          if isinstance(b, dict) and b.get("type") == "text")
    return ""
