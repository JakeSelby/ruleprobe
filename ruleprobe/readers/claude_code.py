# SPDX-License-Identifier: MIT
"""Claude Code transcripts: `~/.claude/projects/<slug>/<session-id>.jsonl`.

One JSON object per line. The lines that matter here are `user`, `assistant` and the
`system` line that marks a compaction boundary; everything else is skipped. Token accounting
is not this package's business and is not read.

Two shapes cost more care than they look:

- One API response is written as several lines repeating the same message id, each carrying
  one content block, and the early lines of a response carry partial text. A block seen
  twice is one block, not two events.
- A subagent's turns may appear in the parent's file as `isSidechain` lines (older Claude
  Code) or in a file of their own (newer). Sidechain lines are that agent's work, not this
  session's, so they make no event here and the subagent's own file is read as its own
  session.
"""
import json
import os

from ..events import Session, result_text

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


def read(path):
    """One `Session` from one transcript, or None when the file holds no session.

    A line that is not JSON, or not an object, is skipped rather than fatal: a transcript is
    written by a live process and its tail may be half a line.
    """
    events = []
    session_id = ""
    cwd = ""
    started = ended = ""
    tool_names = {}
    blocks_seen = set()
    turn = 0
    pending_final = None
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            sidechain = bool(entry.get("isSidechain"))
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
                events.append({"kind": "user_prompt", "turn": turn})
                continue
            if kind != "assistant" or sidechain:
                continue
            model = message.get("model")
            for index, block in enumerate(content or []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text") or ""
                    key = ("text", mid, block.get("apiBlockIndex", index), text)
                    if key in blocks_seen:
                        continue
                    blocks_seen.add(key)
                    pending_final = {"kind": "assistant_text", "turn": turn, "text": text,
                                     "final": False, "model": model or ""}
                    events.append(pending_final)
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
    if not session_id and not events:
        return None
    return Session(id=session_id or os.path.basename(path)[:-6],
                   repo=os.path.basename(cwd.rstrip("/")) if cwd else "",
                   runtime="claude-code", events=events, path=path,
                   started=started, ended=ended)
