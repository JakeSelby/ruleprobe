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

A transcript that yields no event is not a measured session: `read` returns None for it, as
for a file that holds no session at all, so it never enters a share's denominator.
`read(path, empty=True)` returns it with no events instead, which `iter_sessions` uses to drop
an old one by `since` before reporting the rest.
"""
import json
import os

from ..events import Session, result_text, text_of

#: Where Claude Code keeps its transcripts.
ROOT = os.path.join("~", ".claude", "projects")


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
    agent_id = _own_agent(entries)
    events = []
    session_id = ""
    cwd = ""
    started = ended = ""
    tool_names = {}
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
        session_id = session_id or entry.get("sessionId") or ""
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
    if not events and not (empty and session_id):
        return None
    if agent_id:
        session_id = "%s/%s" % (session_id, agent_id) if session_id else agent_id
    return Session(id=session_id or os.path.basename(path)[:-6],
                   repo=os.path.basename(cwd.rstrip("/")) if cwd else "",
                   runtime="claude-code", events=events, path=path,
                   started=started, ended=ended)


def _entries(path):
    """Every JSON object line of `path`, in order, or None when it cannot be opened."""
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    entries = []
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _own_agent(entries):
    """The agent id when `entries` are a subagent's own transcript, else "".

    They are when every `user` and `assistant` line is `isSidechain` and all of them name the
    same non-empty `agentId`. Those lines carry the work; a `system`, `attachment` or
    `summary` line does not, so one written without the markers cannot turn the file back
    into an empty session. A parent's file holds its own non-sidechain lines, so its sidechain
    lines stay another agent's work; a file mixing agent ids is read as a parent, which
    counts less rather than more.
    """
    agent = ""
    for entry in entries:
        if entry.get("type") not in ("user", "assistant"):
            continue
        named = entry.get("agentId")
        if not entry.get("isSidechain") or not isinstance(named, str) or not named \
                or (agent and named != agent):
            return ""
        agent = named
    return agent


def _prompt_text(content):
    """A user prompt's text, whether the line wrote a string or a list of blocks. A
    `message: {role: user}` detector reads this, and a Codex rollout carries the same."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text_of(b.get("text")) for b in content
                          if isinstance(b, dict) and b.get("type") == "text")
    return ""
