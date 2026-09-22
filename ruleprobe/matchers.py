# SPDX-License-Identifier: MIT
"""Matchers: a detector written as data, compiled to the same function a Python one is.

An entry is five keys - `id`, `rule`, `event`, `when`, and an optional `gate` - and `when`
is a matcher. A matcher is a mapping; every key in it must hold, so a mapping of two keys is
an implicit `all`. `any`, `all` and `not` compose them.

    id: house-style/sudo-install
    rule: house-style
    event: tool_use
    when:
      command: {starts_with: [sudo, pip]}

The matchers, by the shape they read:

- `tool` - `name`, `glob`: which tool was called.
- `arg` - `field`, and `regex`, `path_glob`, `contains`, `equals`, `exists`: one field of
  the tool's input. `field` may be dotted, and may be a list, in which case any of them
  satisfying every constraint is a match.
- `command` - `name`, `starts_with`, `contains`, `none_of`, `arg_count`, `sole_segment`,
  `redirect`, `unparsed`, `regex`: a Bash command, through the shared parse in
  `ruleprobe.shell`. Every key but `regex` and `unparsed` is read against one pipeline
  segment, and they must hold of the *same* segment - which is why two constraints on one
  command belong in one `command` block and not in an `all` of two.
- `git` - `subcommand`, `args_any`, `args_none`, `token_prefix`: a `git` call, with its
  flags and `-C`/`-c` options already stepped over.
- `env` - `name`, `command`: a `NAME=value` assignment in front of a named command.
- `text` - `source` (`command`, `heredocs`, `payload`, `assistant`), `regex`, `contains`.
- `message` - `role`, `final`, `regex`, `contains`: an assistant message.
- `kind` - the raw event kind, for `compact` and the other schema events.

Three read the session rather than one event, and may only be the whole of a `session`
detector's `when`, because a hit they produce is not a hit on the event in hand:

- `order` - `first`, `then`, `within`: one event followed by another within N events.
- `absent` - `of`, `scope` (`session` or `turn`): nothing matched, which is the only way to
  measure a rule that asks for something to happen.
- `change` - `kind`, `field`, `ignore_prefix`, `ignore_empty`: a field that differs from the
  previous event of that kind.

An entry may also carry `examples`, which is how a detector states its own precision and
recall rather than being taken on trust. `fire` is a list of minimal cases it should fire
on, `skip` a list it should not; each case is `bash: <command>`, or `event: <one event>`,
or `events: [<event>, ...]` for a session detector, with an optional `note`. Nothing runs
them at report time; `ruleprobe corpus` scores them.

    examples:
      fire:
        - bash: sudo pip install ruff
      skip:
        - bash: uv pip install ruff
          note: the tool the rule asks for

Every spec error is a `DeclarativeError` with a line number. Nothing here compiles a
half-valid detector: a typo in a key name is a finding, never a detector that quietly never
fires.
"""
import fnmatch
import re
from collections import namedtuple

from .declarative import DeclarativeError
from .events import hit, input_of, text_of
from .registry import Detector, register_compiler
from .shell import git_calls, has_redirect, operands, split_assignments

__all__ = ["SPEC_KIND", "Examples", "compile_detector", "compile_examples",
           "compile_matcher"]

#: The cases a detector states about itself: `fire` and `skip`, each a list of
#: `(note, events)`. Scored by `ruleprobe.validity`, never at report time.
Examples = namedtuple("Examples", "fire skip")

EXAMPLE_KEYS = ("fire", "skip")
CASE_KEYS = ("bash", "event", "events", "note")
#: The keys one event snippet may carry: the event schema in `ruleprobe.events`, and
#: nothing else, so a typo is a finding rather than a case that silently tests nothing.
SNIPPET_KEYS = ("kind", "turn", "id", "name", "input", "text", "final", "model",
                "tool_name", "tool_use_id")

#: The `kind` a declarative spec carries when it arrives through `registry.from_spec`.
SPEC_KIND = "declarative"

ENTRY_KEYS = ("id", "rule", "event", "when", "gate", "kind", "description", "examples")
EVENTS = ("tool_use", "assistant_text", "session")
_TEXT_SOURCES = ("command", "heredocs", "payload", "assistant")


class _Where(object):
    """Where a spec came from, so every error carries a file and a line."""

    __slots__ = ("path", "lines", "line")

    def __init__(self, path="<spec>", lines=None, line=0):
        self.path = path or "<spec>"
        self.lines = lines
        self.line = line

    def at(self, container=None, key=None):
        if self.lines is None or container is None:
            return self.line
        return self.lines.line_of(container, key, self.line)

    def fail(self, reason, container=None, key=None):
        raise DeclarativeError(reason, self.at(container, key), self.path)


class _Env(object):
    """One session's parsed view, plus the Bash parse looked up by event identity."""

    __slots__ = ("ctx", "_parsed")

    def __init__(self, ctx):
        self.ctx = ctx
        self._parsed = dict((id(p.event), p) for p in ctx.bash)

    def parsed(self, event):
        return self._parsed.get(id(event))


class _Aggregate(object):
    """A matcher that reads the whole session and returns hits itself."""

    __slots__ = ("run",)

    def __init__(self, run):
        self.run = run


# --- reading a spec safely -------------------------------------------------------------


def _mapping(value, where, container, key, what):
    if not isinstance(value, dict):
        where.fail("%s must be a mapping" % what, container, key)
    return value


def _allowed(value, keys, where, container, key, what):
    for name in value:
        if name not in keys:
            where.fail("unknown %s key %r; one of %s" % (what, name, ", ".join(keys)),
                       value, name)
    return value


def _strings(value, where, container, key, what):
    """A string or a list of strings, always returned as a tuple."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return tuple(value)
    where.fail("%s must be a string or a list of strings" % what, container, key)


def _regexes(value, where, container, key):
    out = []
    for pattern in _strings(value, where, container, key, "regex"):
        try:
            out.append(re.compile(pattern))
        except re.error as exc:
            where.fail("bad regular expression %r: %s" % (pattern, exc), container, key)
    return out


def _flag(value, where, container, key):
    if value is None or isinstance(value, bool):
        return value
    where.fail("%r must be true or false" % key, container, key)


def _count(value, where, container, key):
    """`arg_count`: an integer, or a mapping of `eq`, `min` and `max`."""
    if value is None:
        return None
    if isinstance(value, bool):
        where.fail("arg_count must be a number", container, key)
    if isinstance(value, int):
        return lambda n: n == value
    spec = _allowed(_mapping(value, where, container, key, "arg_count"),
                    ("eq", "min", "max"), where, container, key, "arg_count")
    for name, bound in spec.items():
        if not isinstance(bound, int) or isinstance(bound, bool):
            where.fail("arg_count %s must be a number" % name, spec, name)

    def ok(n):
        if "eq" in spec and n != spec["eq"]:
            return False
        if "min" in spec and n < spec["min"]:
            return False
        if "max" in spec and n > spec["max"]:
            return False
        return True
    return ok


def _dotted(data, field):
    """`data["a"]["b"]` for `a.b`, and None the moment the path stops being a mapping."""
    value = data
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _hit(event):
    return hit(event, tool_use_id=(event.get("kind") == "tool_use"))


# --- the matchers ----------------------------------------------------------------------


def _m_tool(value, where, owner, key):
    if isinstance(value, (str, list)):
        value = {"name": value}
    value = _allowed(_mapping(value, where, owner, key, "tool"), ("name", "glob"),
                     where, owner, key, "tool")
    names = frozenset(_strings(value.get("name"), where, value, "name", "tool name"))
    globs = _strings(value.get("glob"), where, value, "glob", "tool glob")

    def match(event, env):
        if event.get("kind") != "tool_use":
            return False
        name = text_of(event.get("name"))
        if names and name not in names:
            return False
        if globs and not any(fnmatch.fnmatchcase(name, g) for g in globs):
            return False
        return True
    return match


def _m_kind(value, where, owner, key):
    kinds = frozenset(_strings(value, where, owner, key, "kind"))
    if not kinds:
        where.fail("kind needs an event kind", owner, key)
    return lambda event, env: event.get("kind") in kinds


def _m_arg(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "arg"),
                     ("field", "regex", "path_glob", "contains", "equals", "exists"),
                     where, owner, key, "arg")
    fields = _strings(value.get("field"), where, value, "field", "arg field")
    if not fields:
        where.fail("arg needs a field", value, "field")
    regexes = _regexes(value.get("regex"), where, value, "regex")
    globs = _strings(value.get("path_glob"), where, value, "path_glob", "arg path_glob")
    contains = _strings(value.get("contains"), where, value, "contains", "arg contains")
    exists = _flag(value.get("exists"), where, value, "exists")
    equals = value.get("equals")
    # A list, not a set: a transcript field is any JSON shape, and `field: edits` can hand
    # us a list or a dict. `in` over a set would raise TypeError on one, which used to cost
    # the whole session its record rather than this one comparison.
    equals_any = None if equals is None else (
        list(equals) if isinstance(equals, list) else [equals])

    def one(raw):
        if exists is not None and (raw is not None) != exists:
            return False
        if equals_any is not None and not any(raw == want for want in equals_any):
            return False
        text = text_of(raw)
        if regexes and not any(rx.search(text) for rx in regexes):
            return False
        if globs and not any(fnmatch.fnmatchcase(text, g) for g in globs):
            return False
        if contains and not any(c in text for c in contains):
            return False
        return True

    def match(event, env):
        if event.get("kind") != "tool_use":
            return False
        data = input_of(event)
        return any(one(_dotted(data, field)) for field in fields)
    return match


def _m_command(value, where, owner, key):
    if isinstance(value, (str, list)):
        value = {"starts_with": value}
    value = _allowed(
        _mapping(value, where, owner, key, "command"),
        ("name", "starts_with", "contains", "none_of", "arg_count", "sole_segment",
         "redirect", "unparsed", "regex"), where, owner, key, "command")
    names = frozenset(_strings(value.get("name"), where, value, "name", "command name"))
    starts = list(_strings(value.get("starts_with"), where, value, "starts_with",
                           "command starts_with"))
    contains = _strings(value.get("contains"), where, value, "contains", "command contains")
    none_of = frozenset(_strings(value.get("none_of"), where, value, "none_of",
                                 "command none_of"))
    regexes = _regexes(value.get("regex"), where, value, "regex")
    count = _count(value.get("arg_count"), where, value, "arg_count")
    sole = _flag(value.get("sole_segment"), where, value, "sole_segment")
    redirect = _flag(value.get("redirect"), where, value, "redirect")
    unparsed = _flag(value.get("unparsed"), where, value, "unparsed")
    per_segment = bool(names or starts or contains or none_of or count is not None
                       or sole is not None or redirect is not None)

    def segment_ok(segment):
        if names and (not segment or segment[0] not in names):
            return False
        if starts and segment[:len(starts)] != starts:
            return False
        if contains and not any(token in segment for token in contains):
            return False
        if none_of and any(token in none_of for token in segment[1:]):
            return False
        if redirect is not None and has_redirect(segment) != redirect:
            return False
        if count is not None and not count(len(operands(segment))):
            return False
        return True

    def match(event, env):
        if event.get("kind") != "tool_use" or event.get("name") != "Bash":
            return False
        parsed = env.parsed(event)
        if parsed is None:
            return False
        if unparsed is not None and bool(parsed.skipped) != unparsed:
            return False
        if regexes and not all(rx.search(parsed.command) for rx in regexes):
            return False
        if not per_segment:
            return True
        for pipe in parsed.pipelines:
            if sole is not None and (len(pipe) == 1) != sole:
                continue
            for segment in pipe:
                if segment_ok(segment):
                    return True
        return False
    return match


def _m_git(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "git"),
                     ("subcommand", "args_any", "args_none", "token_prefix"),
                     where, owner, key, "git")
    subs = tuple(_strings(value.get("subcommand"), where, value, "subcommand",
                          "git subcommand"))
    if not subs:
        where.fail("git needs a subcommand", value, "subcommand")
    args_any = frozenset(_strings(value.get("args_any"), where, value, "args_any",
                                  "git args_any"))
    args_none = frozenset(_strings(value.get("args_none"), where, value, "args_none",
                                   "git args_none"))
    prefixes = _strings(value.get("token_prefix"), where, value, "token_prefix",
                        "git token_prefix")

    def match(event, env):
        if event.get("kind") != "tool_use" or event.get("name") != "Bash":
            return False
        parsed = env.parsed(event)
        if parsed is None:
            return False
        for segment, _sub, args in git_calls(parsed, subs):
            if args_any and not any(arg in args_any for arg in args):
                continue
            if args_none and any(arg in args_none for arg in args):
                continue
            if prefixes and not any(t.startswith(p) for t in segment for p in prefixes):
                continue
            return True
        return False
    return match


def _m_env(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "env"), ("name", "command"),
                     where, owner, key, "env")
    names = frozenset(_strings(value.get("name"), where, value, "name", "env name"))
    if not names:
        where.fail("env needs a name", value, "name")
    commands = frozenset(_strings(value.get("command"), where, value, "command",
                                  "env command"))

    def match(event, env):
        if event.get("kind") != "tool_use" or event.get("name") != "Bash":
            return False
        parsed = env.parsed(event)
        if parsed is None:
            return False
        for pipe in parsed.pipelines:
            for segment in pipe:
                assignments, words = split_assignments(segment)
                if commands and (not words or words[0] not in commands):
                    continue
                if any(token.split("=", 1)[0] in names for token in assignments):
                    return True
        return False
    return match


def _m_text(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "text"),
                     ("source", "regex", "contains"), where, owner, key, "text")
    source = value.get("source", "command")
    if source not in _TEXT_SOURCES:
        where.fail("unknown text source %r; one of %s"
                   % (source, ", ".join(_TEXT_SOURCES)), value, "source")
    regexes = _regexes(value.get("regex"), where, value, "regex")
    contains = _strings(value.get("contains"), where, value, "contains", "text contains")
    if not regexes and not contains:
        where.fail("text needs a regex or a contains", owner, key)

    def texts(event, env):
        if source == "assistant":
            return [text_of(event.get("text"))] \
                if event.get("kind") == "assistant_text" else []
        if event.get("kind") != "tool_use" or event.get("name") != "Bash":
            return []
        parsed = env.parsed(event)
        if parsed is None:
            return []
        if source == "command":
            return [parsed.command]
        if source == "heredocs":
            return list(parsed.heredocs)
        # `payload`: what the command carried - its heredoc bodies, or the whole command
        # when it was too long to parse and the bodies were never found.
        return [parsed.command] if parsed.skipped else list(parsed.heredocs)

    def match(event, env):
        for text in texts(event, env):
            if not text:
                continue
            if any(rx.search(text) for rx in regexes):
                return True
            if any(c in text for c in contains):
                return True
        return False
    return match


def _m_message(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "message"),
                     ("role", "final", "regex", "contains"), where, owner, key, "message")
    role = value.get("role", "assistant")
    if role not in ("assistant", "user"):
        where.fail("unknown message role %r; assistant or user" % (role,), value, "role")
    kind = "assistant_text" if role == "assistant" else "user_prompt"
    final = _flag(value.get("final"), where, value, "final")
    regexes = _regexes(value.get("regex"), where, value, "regex")
    contains = _strings(value.get("contains"), where, value, "contains",
                        "message contains")

    def match(event, env):
        if event.get("kind") != kind:
            return False
        if final is not None and bool(event.get("final")) != final:
            return False
        text = text_of(event.get("text"))
        if regexes and not any(rx.search(text) for rx in regexes):
            return False
        if contains and not any(c in text for c in contains):
            return False
        return True
    return match


def _m_any(value, where, owner, key):
    parts = _branches(value, where, owner, key, "any")
    return lambda event, env: any(part(event, env) for part in parts)


def _m_all(value, where, owner, key):
    parts = _branches(value, where, owner, key, "all")
    return lambda event, env: all(part(event, env) for part in parts)


def _m_not(value, where, owner, key):
    if isinstance(value, list):
        parts = _branches(value, where, owner, key, "not")
        return lambda event, env: not any(part(event, env) for part in parts)
    part = compile_matcher(value, where)
    return lambda event, env: not part(event, env)


def _branches(value, where, owner, key, what):
    if not isinstance(value, list) or not value:
        where.fail("%s takes a non-empty list of matchers" % what, owner, key)
    return [compile_matcher(item, where) for item in value]


# --- the three that read the session ----------------------------------------------------


def _a_order(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "order"),
                     ("first", "then", "within"), where, owner, key, "order")
    for name in ("first", "then"):
        if name not in value:
            where.fail("order needs a %s matcher" % name, owner, key)
    first = compile_matcher(value["first"], where)
    then = compile_matcher(value["then"], where)
    within = value.get("within", 5)
    if not isinstance(within, int) or isinstance(within, bool) or within < 1:
        where.fail("order within must be a positive number", value, "within")

    def run(events, env):
        hits = []
        for i, event in enumerate(events):
            if not first(event, env):
                continue
            for later in events[i + 1:i + 1 + within]:
                if then(later, env):
                    hits.append(_hit(event))
                    break
        return hits
    return _Aggregate(run)


def _a_absent(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "absent"), ("of", "scope"),
                     where, owner, key, "absent")
    if "of" not in value:
        where.fail("absent needs an of matcher", owner, key)
    of = compile_matcher(value["of"], where)
    scope = value.get("scope", "session")
    if scope not in ("session", "turn"):
        where.fail("unknown absent scope %r; session or turn" % (scope,), value, "scope")

    def run(events, env):
        if scope == "session":
            if any(of(event, env) for event in events):
                return []
            return [(events[-1].get("turn", 0) if events else 0, None)]
        order, matched = [], set()
        for event in events:
            turn = event.get("turn", 0)
            if turn not in order:
                order.append(turn)
            if of(event, env):
                matched.add(turn)
        return [(turn, None) for turn in order if turn not in matched]
    return _Aggregate(run)


def _a_change(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "change"),
                     ("kind", "field", "ignore_prefix", "ignore_empty"),
                     where, owner, key, "change")
    kind = value.get("kind", "assistant_text")
    if not isinstance(kind, str):
        where.fail("change kind must be an event kind", value, "kind")
    field = value.get("field")
    if not isinstance(field, str) or not field:
        where.fail("change needs a field", value, "field")
    prefixes = _strings(value.get("ignore_prefix"), where, value, "ignore_prefix",
                        "change ignore_prefix")
    ignore_empty = value.get("ignore_empty", True)
    if not isinstance(ignore_empty, bool):
        where.fail("change ignore_empty must be true or false", value, "ignore_empty")

    def run(events, env):
        hits, current = [], None
        for event in events:
            if event.get("kind") != kind:
                continue
            seen = text_of(_dotted(event, field))
            if ignore_empty and not seen:
                continue
            if any(seen.startswith(p) for p in prefixes):
                continue
            if current is not None and seen != current:
                hits.append(_hit(event))
            current = seen
        return hits
    return _Aggregate(run)


PREDICATES = {
    "tool": _m_tool, "kind": _m_kind, "arg": _m_arg, "command": _m_command, "git": _m_git,
    "env": _m_env, "text": _m_text, "message": _m_message,
    "any": _m_any, "all": _m_all, "not": _m_not,
}
AGGREGATES = {"order": _a_order, "absent": _a_absent, "change": _a_change}


def compile_matcher(spec, where, allow_aggregate=False):
    """A matcher spec as a predicate `f(event, env)`, or an `_Aggregate` when it reads the
    whole session and `allow_aggregate` says that is where it sits."""
    if not isinstance(spec, dict):
        where.fail("a matcher is a mapping, not %s" % type(spec).__name__)
    if not spec:
        where.fail("an empty matcher would match nothing")
    aggregate = [k for k in spec if k in AGGREGATES]
    if aggregate:
        name = aggregate[0]
        if not allow_aggregate:
            where.fail("%r reads the whole session, so it may only be the whole of a "
                       "session detector's when" % name, spec, name)
        if len(spec) > 1:
            where.fail("%r may not be combined with another matcher" % name, spec, name)
        return AGGREGATES[name](spec[name], where, spec, name)
    parts = []
    for name in spec:
        if name not in PREDICATES:
            where.fail("unknown matcher %r; one of %s"
                       % (name, ", ".join(sorted(PREDICATES) + sorted(AGGREGATES))),
                       spec, name)
        parts.append(PREDICATES[name](spec[name], where, spec, name))
    if len(parts) == 1:
        return parts[0]
    return lambda event, env: all(part(event, env) for part in parts)


def _gate(spec, where, owner):
    if spec is None:
        return None
    spec = _allowed(_mapping(spec, where, owner, "gate", "gate"), ("stance", "variants"),
                    where, owner, "gate", "gate")
    dimension = spec.get("stance")
    if not isinstance(dimension, str) or not dimension:
        where.fail("a gate needs a stance", spec, "stance")
    variants = _strings(spec.get("variants"), where, spec, "variants", "gate variants")
    return (dimension, list(variants) or None)


def _select(event_kind):
    if event_kind == "session":
        return lambda event: True
    return lambda event, wanted=event_kind: event.get("kind") == wanted


def compile_examples(value, where, container=None):
    """An `examples:` block as `Examples(fire, skip)`, each a list of `(note, events)`.

    Nothing here runs a detector: this is the reading of the block, and
    `ruleprobe.validity.score_examples` is the scoring of it.
    """
    if value is None:
        return None
    spec = _allowed(_mapping(value, where, container, "examples", "examples"),
                    EXAMPLE_KEYS, where, container, "examples", "examples")
    out = {}
    for name in EXAMPLE_KEYS:
        cases = spec.get(name)
        if cases is None:
            out[name] = []
            continue
        if not isinstance(cases, list):
            where.fail("examples %s must be a list of cases" % name, spec, name)
        out[name] = [_case(case, where, spec, name, index)
                     for index, case in enumerate(cases)]
    if not out["fire"] and not out["skip"]:
        where.fail("an examples block with no cases in it", container, "examples")
    return Examples(out["fire"], out["skip"])


def _case(case, where, container, key, index):
    """One example case as `(note, events)`."""
    spec = _allowed(_mapping(case, where, container, key, "an example case"),
                    CASE_KEYS, where, container, key, "example case")
    named = [k for k in ("bash", "event", "events") if k in spec]
    if len(named) != 1:
        where.fail("an example case is one of bash, event or events", spec, None)
    note = spec.get("note")
    if note is not None and not isinstance(note, str):
        where.fail("an example note is a string", spec, "note")
    if "bash" in spec:
        command = spec["bash"]
        if not isinstance(command, str) or not command:
            where.fail("examples bash must be a command string", spec, "bash")
        raw = [{"kind": "tool_use", "name": "Bash", "input": {"command": command}}]
    elif "event" in spec:
        raw = [spec["event"]]
    else:
        raw = spec["events"]
        if not isinstance(raw, list) or not raw:
            where.fail("examples events must be a non-empty list", spec, "events")
    return (note or "", [_snippet(e, where, spec, index + i)
                         for i, e in enumerate(raw)])


def _snippet(event, where, container, index):
    """One event snippet, filled out to the event schema. Defaults are the common case: a
    Bash tool use on turn one, with an id of its own so two snippets never collide."""
    spec = _allowed(_mapping(event, where, container, None, "an event snippet"),
                    SNIPPET_KEYS, where, container, None, "event snippet")
    out = dict(spec)
    out.setdefault("kind", "tool_use")
    out.setdefault("turn", index + 1)
    if out["kind"] == "tool_use":
        out.setdefault("name", "Bash")
        out.setdefault("id", "example-%d" % (index + 1))
        if not isinstance(out.get("input"), dict):
            where.fail("an event snippet's input is a mapping", spec, "input")
    return out


def compile_detector(spec, path="<spec>", lines=None, line=0):
    """One entry as a `Detector`. Raises `DeclarativeError` with a line for any spec error."""
    where = _Where(path, lines, line or (lines.line_of(spec) if lines else 0))
    if not isinstance(spec, dict):
        where.fail("a detector entry is a mapping, not %s" % type(spec).__name__)
    _allowed(spec, ENTRY_KEYS, where, spec, None, "detector")
    detector_id = spec.get("id")
    if not isinstance(detector_id, str) or "/" not in detector_id:
        where.fail("a detector needs an id of the shape rule/observable", spec, "id")
    rule = spec.get("rule") or detector_id.split("/")[0]
    if not isinstance(rule, str) or "/" in rule:
        where.fail("a rule name has no slash in it", spec, "rule")
    event_kind = spec.get("event", "tool_use")
    if event_kind not in EVENTS:
        where.fail("unknown event %r; one of %s" % (event_kind, ", ".join(EVENTS)),
                   spec, "event")
    if "when" not in spec:
        where.fail("a detector needs a when", spec, None)
    matcher = compile_matcher(spec["when"], _Where(path, lines, where.at(spec, "when")),
                              allow_aggregate=(event_kind == "session"))
    gate = _gate(spec.get("gate"), where, spec)
    examples = compile_examples(spec.get("examples"),
                                _Where(path, lines, where.at(spec, "examples")), spec)

    if isinstance(matcher, _Aggregate):
        run = matcher.run

        def fn(events, ctx):
            return run(events, _Env(ctx))
    else:
        selects = _select(event_kind)

        def fn(events, ctx):
            env = _Env(ctx)
            return [_hit(event) for event in events
                    if selects(event) and matcher(event, env)]

    fn.__name__ = re.sub(r"\W", "_", detector_id)
    return Detector(detector_id, rule, event_kind, fn, gate, examples)


register_compiler(SPEC_KIND, lambda spec: compile_detector(spec))
