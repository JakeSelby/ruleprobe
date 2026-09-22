# SPDX-License-Identifier: MIT
"""The event schema every reader emits and every detector consumes.

A session is a list of dicts in transcript order. Every event carries `kind` and `turn`
(an int, incremented on every `user_prompt`):

- `assistant_text` - `text` (str), `final` (bool: the last assistant text before the next
  user prompt or the end of the transcript), `model` (str).
- `tool_use` - `id` (str), `name` (str), `input` (dict).
- `tool_result` - `tool_use_id` (str), `tool_name` (str, the name of the `tool_use` it
  answers, resolved by the reader), `text` (str).
- `user_prompt` - no extra fields.
- `compact` - no extra fields; one per context-compaction boundary.

A transcript is machine-written but it is not schema-checked, so every field is treated as
untrusted shape: `input_of` and `text_of` are how a detector reads one safely.
"""
from collections import namedtuple

# Only the tools a detector reads keep their result text, and only the first 64 KB of it:
# the event list is held whole in memory, and a `Read` of a large file would otherwise be
# carried through the entire scan for nothing.
TEXT_KEPT_FOR = frozenset(("Bash", "Agent", "Task"))
MAX_RESULT_TEXT = 64 * 1024

#: One transcript: its id, the repository directory it ran in, the runtime that wrote it,
#: the events, and where they were read from.
Session = namedtuple("Session", "id repo runtime events path started ended")
Session.__new__.__defaults__ = ("", "", "")

#: What a detector returns, one per observation: the detector id, the turn it happened on,
#: and the tool use it happened in, when there was one. Never a snippet of the transcript:
#: the transcript is the evidence and a report is a count.
Hit = namedtuple("Hit", "id turn tool_use_id")


def input_of(event):
    """A tool use's input, always a dict."""
    data = event.get("input")
    return data if isinstance(data, dict) else {}


def text_of(value):
    """`value` when it is a string, and the empty string when it is any other shape."""
    return value if isinstance(value, str) else ""


def result_text(content, tool_name):
    """A tool result's text, whether the transcript wrote a string or a block list."""
    if tool_name not in TEXT_KEPT_FOR:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(b.get("text") or "" for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    else:
        return ""
    return text[:MAX_RESULT_TEXT]


def hit(event, tool_use_id=True):
    """The `(turn, tool_use_id)` half of a hit; `run()` adds the detector id."""
    return (event.get("turn", 0), event.get("id") if tool_use_id else None)


def counts(events):
    """Per-session tool counts a report records whether or not a detector fires."""
    out = {"web_search": 0, "agent": 0, "ask_user": 0}
    keys = {"WebSearch": "web_search", "Agent": "agent", "AskUserQuestion": "ask_user"}
    for event in events or []:
        if isinstance(event, dict) and event.get("kind") == "tool_use":
            key = keys.get(event.get("name"))
            if key:
                out[key] += 1
    return out
