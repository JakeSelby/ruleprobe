# SPDX-License-Identifier: MIT
"""Codex rollouts: `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl`.

One JSON object per line, each with a `type` and a `payload`. A rollout opens with a
`session_meta` line; `turn_context` starts a turn; `response_item` carries the tool calls,
their output and the assistant's messages.

Two names are translated so a detector sees one vocabulary across runtimes: Codex's
`exec_command` is `Bash` and its `spawn_agent` is `Agent`, and a call whose arguments carry
`cmd` gains a `command` key beside it.

A thread spawned as a subagent inherits its parent's history and carries the parent's
`session_meta` further down the file. Only the first one is this rollout's own.
"""
import json
import os

from ..events import Session, result_text

#: Where Codex keeps its rollouts.
ROOT = os.path.join("~", ".codex", "sessions")

_TOOL_NAMES = {"exec_command": "Bash", "spawn_agent": "Agent"}


def transcripts(root=None):
    """Every Codex rollout under `root`."""
    base = os.path.expanduser(root or ROOT)
    found = []
    for directory, _dirs, files in os.walk(base, followlinks=True):
        for name in files:
            if name.endswith(".jsonl"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def read(path):
    """One `Session` from one rollout, or None when the file names no session."""
    events = []
    meta = {}
    session_id = cwd = model_now = ""
    started = ended = ""
    tool_names = {}
    turn = 0
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            try:
                item = json.loads(line)
                payload = item.get("payload") or {}
                if not isinstance(payload, dict):
                    raise ValueError("invalid payload")
            except (ValueError, AttributeError):
                continue
            timestamp = item.get("timestamp") or ""
            started = started or timestamp
            ended = timestamp or ended
            kind = item.get("type")
            if kind == "session_meta":
                if meta:
                    continue
                meta = payload
                session_id = session_id or meta.get("id", "")
                cwd = cwd or meta.get("cwd", "")
            elif kind == "turn_context":
                turn += 1
                # Codex names the model per turn and it changes mid-thread, which is exactly
                # what `cache-hygiene/model-switch` is counting.
                if isinstance(payload.get("model"), str) and payload["model"]:
                    model_now = payload["model"]
            elif kind == "response_item":
                what = payload.get("type")
                call_id = payload.get("call_id", "")
                if what in ("function_call", "custom_tool_call"):
                    name = payload.get("name", "")
                    name = _TOOL_NAMES.get(name, name)
                    arguments = payload.get("arguments", payload.get("input", {}))
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except ValueError:
                            arguments = {"command": arguments}
                    if isinstance(arguments, dict) and "cmd" in arguments:
                        arguments = dict(arguments, command=arguments["cmd"])
                    tool_names[call_id] = name
                    events.append({"kind": "tool_use", "turn": turn, "id": call_id,
                                   "name": name, "input": arguments})
                elif what in ("function_call_output", "custom_tool_call_output"):
                    name = tool_names.get(call_id, "")
                    events.append({"kind": "tool_result", "turn": turn,
                                   "tool_use_id": call_id, "tool_name": name,
                                   "text": result_text(payload.get("output"), name)})
                elif what == "message" and payload.get("role") == "assistant":
                    text = "\n".join(x.get("text", "") for x in payload.get("content", [])
                                     if isinstance(x, dict))
                    events.append({"kind": "assistant_text", "turn": turn, "text": text,
                                   "final": payload.get("phase") == "final_answer",
                                   "model": model_now or _model(meta)})
    if not session_id and not events:
        return None
    return Session(id=session_id or os.path.basename(path)[:-6],
                   repo=os.path.basename(cwd.rstrip("/")) if cwd else "",
                   runtime="codex", events=events, path=path,
                   started=started, ended=ended)


def _model(meta):
    """The model the rollout names, when it names one. Codex records the model per turn in
    `turn_context`; the meta's is the one the thread opened with."""
    value = meta.get("model") if isinstance(meta, dict) else ""
    return value if isinstance(value, str) else ""
