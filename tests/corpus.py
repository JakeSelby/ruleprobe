# SPDX-License-Identifier: MIT
"""Event builders the corpus is written in. Hand-written, not captured: an event is five
keys, and a synthetic one is easier to read than a redacted transcript."""

# Assembled at run time so a secret scanner reading this file finds a concatenation rather
# than a key shape.
FAKE_KEY = "AKIA" + "Q" * 16


def bash(command, turn=1, id="tu1"):
    return {"kind": "tool_use", "turn": turn, "id": id, "name": "Bash",
            "input": {"command": command}}


def tool_use(name, data, turn=1, id="tu1"):
    return {"kind": "tool_use", "turn": turn, "id": id, "name": name, "input": data}


def tool_result(text, tool_name="Agent", tool_use_id="tu1", turn=1):
    return {"kind": "tool_result", "turn": turn, "tool_use_id": tool_use_id,
            "tool_name": tool_name, "text": text}


def say(text, turn=1, final=True, model="claude-opus-5"):
    return {"kind": "assistant_text", "turn": turn, "text": text, "final": final,
            "model": model}


def prompt(turn=1):
    return {"kind": "user_prompt", "turn": turn}


def compact(turn=1):
    return {"kind": "compact", "turn": turn}
