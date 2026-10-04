# SPDX-License-Identifier: MIT
"""Codex rollouts: `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl`.

One JSON object per line, each with a `type` and a `payload`. A rollout opens with a
`session_meta` line; `turn_context` starts a turn; `response_item` carries the tool calls,
their output and the assistant's messages.

Two names are translated so a detector sees one vocabulary across runtimes: Codex's
`exec_command` is `Bash` and its `spawn_agent` is `Agent`, and a call whose arguments carry
`cmd` gains a `command` key beside it.

A thread spawned as a subagent inherits its parent's history and carries the parent's
`session_meta` further down the file. Only the first one is this rollout's own, and its id
is the session's; `session_key(path)` reads it without reading the rest.

A call that never ran makes no event, and neither does its output. Codex answers such a call
with a fixed output: `exec command rejected by user` or `patch rejected by user` when the user
declined it, `patch rejected: ...` when the approval settings refused a patch,
`apply_patch verification failed: ...` when a patch did not match the files and was never
applied, and `aborted`
when the turn was interrupted before the call returned. An interrupted call may have started, but
the rollout does not say, so it is left out: a measure that under-counts. Any other output is a
call that ran, a command that exited non-zero included. A refusal Codex words otherwise, such as
an exec policy's own reason, is not recognised and still counts.

A user message is a `user_prompt`, and the last assistant message before one - or before the
end - is the final one. Both are derived the way the Claude Code reader derives them, rather
than read from `payload.phase`, so a detector means the same thing on either runtime.
"""
import json
import os

from ..events import Session, result_text, text_of

#: Where Codex keeps its rollouts.
ROOT = os.path.join("~", ".codex", "sessions")

_TOOL_NAMES = {"exec_command": "Bash", "spawn_agent": "Agent"}
#: The outputs Codex writes for a call that never ran, whole, and the prefixes of others.
_NOT_RUN = frozenset(("exec command rejected by user", "patch rejected by user", "aborted"))
_NOT_RUN_PREFIXES = ("patch rejected:", "apply_patch verification failed:")


def transcripts(root=None):
    """Every Codex rollout under `root`."""
    base = os.path.expanduser(root or ROOT)
    found = []
    for directory, _dirs, files in os.walk(base, followlinks=True):
        for name in files:
            if name.endswith(".jsonl"):
                found.append(os.path.join(directory, name))
    return sorted(found)


def read(path, empty=False):
    """One `Session` from one rollout, or None when the file yields no event: a rollout
    with nothing to measure is not a session, as in the Claude Code reader. With `empty`,
    one that names a session is returned with no events, so `iter_sessions` can drop it by
    date before it reports the rest."""
    events = []
    meta = {}
    cwd = model_now = ""
    started = ended = ""
    tool_names = {}
    not_run = set()
    turn = 0
    pending_final = None
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for item, payload in _items(handle):
            timestamp = item.get("timestamp") or ""
            started = started or timestamp
            ended = timestamp or ended
            kind = item.get("type")
            if kind == "session_meta":
                if meta:
                    continue
                meta = payload
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
                    if isinstance(call_id, str) and call_id \
                            and _never_ran(payload.get("output")):
                        not_run.add(call_id)
                        continue
                    name = tool_names.get(call_id, "")
                    events.append({"kind": "tool_result", "turn": turn,
                                   "tool_use_id": call_id, "tool_name": name,
                                   "text": result_text(payload.get("output"), name)})
                elif what == "message" and payload.get("role") == "assistant":
                    pending_final = {"kind": "assistant_text", "turn": turn,
                                     "text": _text(payload), "final": False,
                                     "model": model_now or _model(meta)}
                    events.append(pending_final)
                elif what == "message" and payload.get("role") == "user":
                    # Parity with the Claude Code reader, both ways: a user message is a
                    # `user_prompt` event, so `message: {role: user}` can fire on a rollout
                    # at all, and the assistant text before it is the final one, derived
                    # rather than taken from `phase`, which only one runtime writes.
                    if pending_final is not None:
                        pending_final["final"] = True
                        pending_final = None
                    events.append({"kind": "user_prompt", "turn": turn,
                                   "text": _text(payload)})
    if pending_final is not None:
        pending_final["final"] = True
    if not_run:
        events = [e for e in events
                  if not (e["kind"] == "tool_use" and isinstance(e["id"], str)
                          and e["id"] in not_run)]
    session_id = meta.get("id", "")
    if not events and not (empty and session_id):
        return None
    return Session(id=_key(meta, path),
                   repo=os.path.basename(cwd.rstrip("/")) if cwd else "",
                   runtime="codex", events=events, path=path,
                   started=started, ended=ended, cwd=cwd)


def session_key(path):
    """The id `read(path)` gives its session, from the rollout's own `session_meta`, or None
    when the file cannot be opened or that line names no id. It stops at that line, a
    rollout's first."""
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for item, payload in _items(handle):
            if item.get("type") == "session_meta" and payload:
                return _key(payload, path) if payload.get("id", "") else None
    return None


def _key(meta, path):
    """A rollout's session id: its own `session_meta`'s id, as a string, else the file's
    stem."""
    value = meta.get("id", "")
    if value and not isinstance(value, str):
        value = str(value)
    return value or os.path.basename(path)[:-6]


def _items(lines):
    """`(item, payload)` for each line of `lines` that parses to an object with an object
    payload, in order; any other line is skipped."""
    for line in lines:
        try:
            item = json.loads(line)
            payload = item.get("payload") or {}
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
        except (ValueError, AttributeError):
            continue
        yield item, payload


def _never_ran(output):
    """Whether a call's output is one Codex writes for a call that never ran."""
    if isinstance(output, list):
        output = "".join(text_of(x.get("text")) for x in output if isinstance(x, dict))
    if not isinstance(output, str):
        return False
    output = output.strip()
    return output in _NOT_RUN or output.startswith(_NOT_RUN_PREFIXES)


def _text(payload):
    """A message's text, from the content blocks Codex writes it in."""
    content = payload.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(text_of(x.get("text")) for x in content or []
                      if isinstance(x, dict))


def _model(meta):
    """The model the rollout names, when it names one. Codex records the model per turn in
    `turn_context`; the meta's is the one the thread opened with."""
    value = meta.get("model") if isinstance(meta, dict) else ""
    return value if isinstance(value, str) else ""
