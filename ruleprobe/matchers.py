# SPDX-License-Identifier: MIT
"""Matchers: a detector written as data, compiled to the same function a Python one is.

An entry is `id`, `rule`, `event` and `when`, with an optional `gate`, `description`,
`examples`, `schema_version` and `kind` (which `registry.from_spec` reads) - and `when`
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

A list is alternatives everywhere: `regex`, `contains` and `path_glob` hold when any one of
their patterns does. `contains` is a substring, in a command's token as much as in a
message. `path_glob` is a path and not a string - `*` and `?` stop at a `/`, `**` crosses
one - and a pattern that does not start at the root matches any suffix of the path at a
component boundary, because a transcript's `file_path` is absolute.

Three read the session rather than one event, and may only be the whole of a `session`
detector's `when`, because a hit they produce is not a hit on the event in hand:

- `order` - `first`, `then`, `within`: one event followed by another within N events.
- `absent` - `of`, `scope` (`session` or `turn`): nothing matched, which is the only way to
  measure a rule that asks for something to happen.
- `change` - `kind`, `field`, `ignore_prefix`, `ignore_empty`: a field that differs from the
  previous event of that kind.

An entry may carry `schema_version`, the integer schema it was written under. Absent, it is
the top-level `version` of the `detectors:` file it sits in, and absent there too it is 1;
rule-file front matter has no file-level default, so an entry there without the key is 1. A
value that is not a schema this package knows - not in `registry.KNOWN_SCHEMA_VERSIONS`, or
not an integer - is an error, so an entry written for a later schema is refused rather than
read under the wrong one.

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

A matcher that cannot decide says so rather than guessing. Over a Bash command the shared
parse skipped - empty or missing, longer than `MAX_COMMAND`, or one that does not tokenize
or parse - every `command` key but `regex` and `unparsed`, every `git` key, every `env` key and a `text` read
of `source: heredocs` is undecided, not false. `not` of undecided is undecided; `any` is
true on any true child, else undecided on any undecided one; `all` is false on any false
child, else undecided on any undecided one. An undecided `when` is no hit, an `order` hit
needs `first` and `then` both true, and an `absent` scope holding an undecided candidate is
no hit - so a negation never turns a command nobody could read into a count. A predicate
from `compile_matcher` returns that undecided value, which is falsy: a Python caller who
negates a predicate itself reads it as false and can over-count. Either compose through the
declarative `not`, `any` and `all`, or test the result with `is_undecided` before negating it.

`order`, and `absent` with `scope: turn`, also count opportunities - each point at which the
rule applied, and whether it was followed - as the detector's `opportunities`. It and `fn`
read one evaluation: the detector keeps the last event list it was handed and what it found
there, so the second of the two calls on the same list evaluates nothing, and a hit is
always an opportunity. Each event `first` matches opens one `order` opportunity, followed
when `then` matched within `within`, so a hit is a followed opportunity. Each turn in the
event list is one `absent` opportunity, followed when `of` matched in it, so a hit is one
not followed; `absent` has no trigger, so a turn in which the rule asked for nothing is an
opportunity too. `absent` with `scope: session`, `change`, and every detector whose `when`
reads one event at a time (`tool`, `command`, `any` and the rest) count none: their
`opportunities` is `None`. Undecided stays undecided here as well: an event `first` is
undecided on, an `order` whose `then` is never true and undecided at least once within the
window, and an `absent` turn holding an undecided candidate and no true one each have
`followed` of `None` - never false. The callable returns those undecided triples too, so
the length of its list is not the opportunity count: the count is the triples whose
`followed` is `True` or `False`, and the undecided ones are counted apart.

Every spec error is a `DeclarativeError` with a line number. Nothing here compiles a
half-valid detector: a typo in a key name is a finding, never a detector that quietly never
fires.
"""
import fnmatch
import re
from collections import namedtuple

from .declarative import DeclarativeError
from .events import hit, input_of, text_of
from .registry import KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION, Detector, register_compiler
from .shell import git_calls, has_redirect, operands, split_assignments

__all__ = ["SPEC_KIND", "Examples", "compile_detector", "compile_examples",
           "compile_matcher", "is_undecided"]

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


class _Undecided(object):
    """The third truth value: the matcher could not read its input. Falsy, so a caller that
    only asks "did it match" reads it as no match; `not` must never be applied to it."""

    __slots__ = ()

    def __bool__(self):
        return False

    def __repr__(self):
        return "UNDECIDED"


_UNDECIDED = _Undecided()


def is_undecided(value):
    """Whether `value` is the undecided result a `compile_matcher` predicate returns.

    Undecided is falsy, so `not predicate(event, env)` reads it as a decided false; a Python
    caller negating a predicate itself asks this first and treats undecided as no hit."""
    return isinstance(value, _Undecided)


def _not3(value):
    return _UNDECIDED if value is _UNDECIDED else not value


def _any3(values):
    """Kleene `any`: true on any true, else undecided on any undecided, else false."""
    undecided = False
    for value in values:
        if value is _UNDECIDED:
            undecided = True
        elif value:
            return True
    return _UNDECIDED if undecided else False


def _all3(values):
    """Kleene `all`: false on any false, else undecided on any undecided, else true."""
    undecided = False
    for value in values:
        if value is _UNDECIDED:
            undecided = True
        elif not value:
            return False
    return _UNDECIDED if undecided else True


ENTRY_KEYS = ("id", "rule", "event", "when", "gate", "kind", "description", "examples",
              "schema_version")
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

    __slots__ = ("run", "evaluate", "opportunities")

    def __init__(self, run, evaluate=None, opportunities=None):
        # With `evaluate`, `run` and `opportunities` take its result rather than the session,
        # so the compiled detector can evaluate once for both.
        self.run = run
        self.evaluate = evaluate
        self.opportunities = opportunities


def _followed(value):
    """A three-valued match as an opportunity's `followed`: `True`, `False`, or `None`."""
    return None if value is _UNDECIDED else bool(value)


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


def schema_version_error(value, key="schema_version"):
    """Why `value` is not a known schema version, or `None` when it is one. A boolean is
    refused although Python counts it as an integer, as `arg_count` refuses one."""
    if not isinstance(value, int) or isinstance(value, bool):
        return "%s must be an integer, not %r" % (key, value)
    if value in KNOWN_SCHEMA_VERSIONS:
        return None
    if value > SCHEMA_VERSION:
        return ("%s %d is newer than this ruleprobe reads (%d); upgrade ruleprobe"
                % (key, value, SCHEMA_VERSION))
    return ("%s %d is not a schema version; they start at %d"
            % (key, value, min(KNOWN_SCHEMA_VERSIONS)))


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


#: Compiled `path_glob` patterns, keyed by the pattern. A detector compiles once and runs
#: over every event in every session, so the translation is not worth doing twice.
_PATH_GLOBS = {}


def _path_glob(pattern):
    """`path_glob` as a compiled regular expression.

    Two differences from `fnmatch`, both of them about a file path being a path and not a
    string. `*` and `?` do not cross a `/` - `src/*.py` is one directory's files, and `**`
    is how you ask for any depth - and a pattern that does not start at the root matches
    any suffix of the path at a component boundary, because `file_path` in a transcript is
    absolute and nobody writes `/home/you/work/repo/src/*.py` in a detector.
    """
    compiled = _PATH_GLOBS.get(pattern)
    if compiled is not None:
        return compiled
    out, i, n = [], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out.append(re.escape(c))
                i += 1
            else:
                body = pattern[i + 1:end].replace("\\", "\\\\")
                out.append("[%s]" % ("^" + body[1:] if body[:1] == "!" else body))
                i = end + 1
        else:
            out.append(re.escape(c))
            i += 1
    anchor = "^" if pattern.startswith("/") or pattern.startswith("**") else "(?:^|.*/)"
    compiled = re.compile(anchor + "".join(out) + "$")
    _PATH_GLOBS[pattern] = compiled
    return compiled


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
        if globs and not any(_path_glob(g).match(text) for g in globs):
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
        # Substring, as `contains` is everywhere else in the format: `contains: no-verify`
        # asking for the token `--no-verify` and getting nothing was a matcher that read
        # like one thing and did another.
        if contains and not any(c in token for c in contains for token in segment):
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
        # Any, as `arg`, `text` and `message` read a list of patterns: a list of
        # alternatives that had to all hold was a detector that could not fire.
        if regexes and not any(rx.search(parsed.command) for rx in regexes):
            return False
        if not per_segment:
            return True
        if parsed.skipped:
            return _UNDECIDED
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
        if parsed.skipped:
            return _UNDECIDED
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
        if parsed.skipped:
            return _UNDECIDED
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
            # A skipped parse never looked for the bodies, so none found is not none there.
            return None if parsed.skipped else list(parsed.heredocs)
        # `payload`: what the command carried - its heredoc bodies, or the whole command
        # when it was too long to parse and the bodies were never found.
        return [parsed.command] if parsed.skipped else list(parsed.heredocs)

    def match(event, env):
        found = texts(event, env)
        if found is None:
            return _UNDECIDED
        for text in found:
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
    return lambda event, env: _any3(part(event, env) for part in parts)


def _m_all(value, where, owner, key):
    parts = _branches(value, where, owner, key, "all")
    return lambda event, env: _all3(part(event, env) for part in parts)


def _m_not(value, where, owner, key):
    if isinstance(value, list):
        parts = _branches(value, where, owner, key, "not")
        return lambda event, env: _not3(_any3(part(event, env) for part in parts))
    part = compile_matcher(value, where)
    return lambda event, env: _not3(part(event, env))


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

    def evaluate(events, env):
        # Every event `first` does not decidedly miss, with whether `then` followed it. A
        # hit is one followed; `run` and `opportunities` both read this one result.
        out = []
        for i, event in enumerate(events):
            opened = first(event, env)
            if opened is _UNDECIDED:
                out.append((_hit(event), None))
                continue
            if not opened:
                continue
            followed, distance = False, 0
            for later in events[i + 1:]:
                seen = then(later, env)
                if seen is _UNDECIDED:
                    followed = None
                elif seen:
                    followed = True
                    break
                # A `tool_result` is the answer to the call before it, not a step the agent
                # took, and on a Claude Code transcript there is one after every call. Left
                # in the budget, `within: 2` meant one tool use.
                if later.get("kind") == "tool_result":
                    continue
                distance += 1
                if distance >= within:
                    break
            out.append((_hit(event), followed))
        return out

    def run(found):
        return [at for at, followed in found if followed is True]

    def opportunities(found):
        return [(turn, tool_use_id, followed) for (turn, tool_use_id), followed in found]
    return _Aggregate(run, evaluate, opportunities)


def _a_absent(value, where, owner, key):
    value = _allowed(_mapping(value, where, owner, key, "absent"), ("of", "scope"),
                     where, owner, key, "absent")
    if "of" not in value:
        where.fail("absent needs an of matcher", owner, key)
    of = compile_matcher(value["of"], where)
    scope = value.get("scope", "session")
    if scope not in ("session", "turn"):
        where.fail("unknown absent scope %r; session or turn" % (scope,), value, "scope")

    if scope == "session":
        def run(events, env):
            # A session with no events at all - an aborted rollout carrying only its
            # header - is not a session in which something failed to happen. Counting one
            # as a hit walks a rule like `no-test-run` towards 100% on nothing.
            if not events or _any3(of(event, env) for event in events) is not False:
                return []
            return [(events[-1].get("turn", 0), None)]
        return _Aggregate(run)

    def evaluate(events, env):
        # Each turn, in the order it first appears, with whether `of` matched in it. A turn
        # is absent only when every event in it is decidedly not `of`: one the parse could
        # not read may have been the very thing asked for.
        order, seen = [], {}
        for event in events:
            turn = event.get("turn", 0)
            if turn not in seen:
                order.append(turn)
                seen[turn] = []
            seen[turn].append(of(event, env))
        return [(turn, _followed(_any3(seen[turn]))) for turn in order]

    def run(found):
        return [(turn, None) for turn, followed in found if followed is False]

    def opportunities(found):
        return [(turn, None, followed) for turn, followed in found]
    return _Aggregate(run, evaluate, opportunities)


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
    whole session and `allow_aggregate` says that is where it sits.

    The predicate returns true, false, or a falsy undecided value, so its truth is "matched"
    and its falsehood is "not known to match". A Python caller who negates it with its own
    `not` reads undecided as false and can over-count; compose with the declarative `not`,
    `any` and `all`, or test the result with `is_undecided` before negating it."""
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
    return lambda event, env: _all3(part(event, env) for part in parts)


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
    if not isinstance(out["turn"], int) or isinstance(out["turn"], bool):
        where.fail("an event snippet's turn is a whole number", spec, "turn")
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
    if "schema_version" in spec:
        reason = schema_version_error(spec["schema_version"])
        if reason:
            where.fail(reason, spec, "schema_version")
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

    opportunities = None
    if isinstance(matcher, _Aggregate) and matcher.evaluate is not None:
        run, count, evaluate = matcher.run, matcher.opportunities, matcher.evaluate
        # The last event list and what was found in it. Holding the list itself, not its
        # id, means the id cannot be reused by another list while the entry stands.
        memo = [None, None]

        def evaluated(events, ctx):
            if memo[0] is not events:
                found = evaluate(events, _Env(ctx))
                memo[:] = [events, found]
            return memo[1]

        def fn(events, ctx):
            return run(evaluated(events, ctx))

        def opportunities(events, ctx):
            return count(evaluated(events, ctx))

        opportunities.__name__ = re.sub(r"\W", "_", detector_id) + "_opportunities"
    elif isinstance(matcher, _Aggregate):
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
    return Detector(detector_id, rule, event_kind, fn, gate, examples,
                    opportunities=opportunities)


register_compiler(SPEC_KIND, lambda spec: compile_detector(spec))
