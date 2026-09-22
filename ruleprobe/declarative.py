# SPDX-License-Identifier: MIT
"""A strict, minimal YAML subset, and the front matter a rule file carries.

A detector written as data has to be written in something, and neither YAML nor TOML is in
the 3.9 standard library. Rather than take a dependency for a file that holds a dozen keys,
this module parses the subset a detector needs and refuses everything else by name:

- block mappings and block sequences, nested by indentation;
- flow mappings and flow sequences on one line (`{name: Bash}`, `[a, b]`);
- scalars: single- and double-quoted strings, plain strings, integers, floats,
  `true`, `false`, `null` and `~`;
- `#` comments, outside quotes.

Refused, each with a line number and a reason rather than a wrong parse: anchors and
aliases (`&`, `*`), tags (`!`), block scalars (`|`, `>`), directives (`%`), merge keys, and
more than one document in a file. Tabs may not indent.

JSON is the other accepted spelling: `load()` reads a `.json` file with the standard library
and reports its errors the same way. The two produce the same objects, so which one a
detector file is written in is a matter of taste.

    >>> parse("detectors:\\n  - id: a/b\\n    when: {tool: {name: Bash}}\\n")
    {'detectors': [{'id': 'a/b', 'when': {'tool': {'name': 'Bash'}}}]}
"""
import json
import re

__all__ = ["DeclarativeError", "LineMap", "load", "parse", "parse_with_lines",
           "split_front_matter"]

#: How deeply a document may nest. A detector is a handful of levels; anything past this is
#: a file that will not be read by a human either.
MAX_DEPTH = 32

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")
_CONSTANTS = {"true": True, "false": False, "null": None, "~": None}
# The characters YAML gives a meaning this parser does not implement. Refusing them by name
# is the difference between an unsupported file and a silently wrong one.
_RESERVED = {
    "&": "anchors are not supported", "*": "aliases are not supported",
    "!": "tags are not supported", "|": "block scalars are not supported",
    ">": "folded scalars are not supported", "%": "directives are not supported",
    "@": "'@' may not start a scalar; quote it", "`": "'`' may not start a scalar; quote it",
}


class DeclarativeError(Exception):
    """A file that could not be read, with the line and the reason. Never fatal to a run:
    every caller in this package collects these and carries on with what did parse."""

    def __init__(self, reason, line=0, path=""):
        self.reason = reason
        self.line = int(line or 0)
        self.path = path or "<string>"
        Exception.__init__(self, "%s:%d: %s" % (self.path, self.line, reason))


class LineMap(object):
    """Where each mapping key was written, so a bad detector can be reported at its line.

    Keyed by the identity of the container, which is why the parsed document is kept alive
    here too: a map of `id()` to anything outlives the object it describes otherwise.
    """

    def __init__(self):
        self._at = {}
        self._keep = []

    def mark(self, container, key, line):
        self._at[(id(container), key)] = line
        self._keep.append(container)

    def copy_marks(self, source, target):
        """Give `target` the lines `source` was written on. A caller that rewrites an entry
        - filling in a default id, say - would otherwise lose every line it had."""
        for (holder, key), line in list(self._at.items()):
            if holder == id(source):
                self.mark(target, key, line)
        return target

    def line_of(self, container, key=None, default=0):
        at = self._at
        return at.get((id(container), key), at.get((id(container), None), default))


class _Line(object):
    __slots__ = ("no", "indent", "text")

    def __init__(self, no, indent, text):
        self.no = no
        self.indent = indent
        self.text = text


def parse(text, path="<string>"):
    """The document in `text` as plain Python objects. Raises `DeclarativeError`."""
    return parse_with_lines(text, path)[0]


def parse_with_lines(text, path="<string>", first_line=1):
    """`(document, LineMap)`. `first_line` is the line the text starts on, so front matter
    lifted out of a markdown file still reports the line numbers of that file."""
    if not isinstance(text, str):
        raise DeclarativeError("not text: %r" % type(text).__name__, first_line, path)
    lines = _scan(text, path, first_line)
    lines_map = LineMap()
    if not lines:
        return None, lines_map
    value, index = _block(lines, 0, lines[0].indent, lines_map, path, 0)
    if index < len(lines):
        raise DeclarativeError("unexpected indentation", lines[index].no, path)
    lines_map._keep.append(value)
    return value, lines_map


def load(path):
    """`(document, LineMap)` from a file. `.json` is read as JSON, anything else as the
    YAML subset. Raises `DeclarativeError` for a missing file too, so one caller's `except`
    covers reading and parsing alike."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise DeclarativeError("cannot read: %s" % exc.strerror or "unreadable", 0, path)
    except UnicodeDecodeError:
        raise DeclarativeError("not UTF-8 text", 0, path)
    if str(path).endswith(".json"):
        return _load_json(text, path)
    return parse_with_lines(text, path)


def _load_json(text, path):
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise DeclarativeError("invalid JSON: %s" % exc, getattr(exc, "lineno", 0), path)
    return value, LineMap()


def split_front_matter(text):
    """`(front matter text or None, the line it starts on, the body)`.

    Front matter is a `---` on the first line and the next `---` or `...` on its own line;
    anything else is all body, because a rule file without front matter is the common case
    and is not an error.
    """
    if not isinstance(text, str):
        return None, 0, ""
    lines = text.split("\n")
    if not lines or lines[0].strip() not in ("---", "---\r"):
        return None, 0, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[1:i]), 2, "\n".join(lines[i + 1:])
    return None, 0, text


# --- scanning ------------------------------------------------------------------------


def _scan(text, path, first_line):
    """Comment-free, blank-free lines, each with its indentation and its real line number."""
    out = []
    for offset, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        no = first_line + offset
        if "\t" in raw[:len(raw) - len(raw.lstrip(" \t"))]:
            raise DeclarativeError("a tab may not indent; use spaces", no, path)
        content = _strip_comment(raw).rstrip()
        if not content.strip():
            continue
        if content.strip() in ("---", "..."):
            raise DeclarativeError("more than one document in a file is not supported",
                                   no, path)
        out.append(_Line(no, len(content) - len(content.lstrip(" ")), content.strip()))
    return out


def _strip_comment(line):
    """`line` without a trailing `#` comment. A `#` inside quotes, or joined to a word, is
    data: `--exclude=#tmp` is a token and `'# 1'` is a string."""
    sq = dq = False
    for i, c in enumerate(line):
        if sq:
            sq = c != "'"
        elif dq:
            dq = c != '"'
        elif c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


# --- blocks --------------------------------------------------------------------------


def _block(lines, i, indent, lines_map, path, depth):
    if depth > MAX_DEPTH:
        raise DeclarativeError("nested too deeply", lines[i].no, path)
    if _is_item(lines[i].text):
        return _sequence(lines, i, indent, lines_map, path, depth)
    return _mapping(lines, i, indent, lines_map, path, depth)


def _is_item(text):
    return text == "-" or text.startswith("- ")


def _sequence(lines, i, indent, lines_map, path, depth):
    out = []
    while i < len(lines) and lines[i].indent == indent and _is_item(lines[i].text):
        line = lines[i]
        rest = line.text[1:]
        offset = len(rest) - len(rest.lstrip(" "))
        rest = rest.strip()
        lines_map.mark(out, len(out), line.no)
        if not rest:
            value, i = _nested(lines, i + 1, indent, lines_map, path, depth, line)
        elif _is_item(rest):
            # `- - 1`: a sequence that starts on its parent's dash.
            inline = _Line(line.no, indent + 1 + offset, rest)
            value, consumed = _sequence([inline] + lines[i + 1:], 0, inline.indent,
                                        lines_map, path, depth + 1)
            i += consumed
        elif _key_split(rest) is not None:
            # `- id: a/b`, the common entry shape: a mapping that starts on the dash's line
            # and continues at the column its first key sits in.
            inline = _Line(line.no, indent + 1 + offset, rest)
            value, consumed = _mapping([inline] + lines[i + 1:], 0, inline.indent,
                                       lines_map, path, depth + 1)
            i += consumed
        else:
            value, i = _scalar(rest, line.no, path), i + 1
        out.append(value)
    if i < len(lines) and lines[i].indent > indent:
        raise DeclarativeError("unexpected indentation", lines[i].no, path)
    return out, i


def _mapping(lines, i, indent, lines_map, path, depth):
    out = {}
    while i < len(lines) and lines[i].indent == indent and not _is_item(lines[i].text):
        line = lines[i]
        split = _key_split(line.text)
        if split is None:
            if line.text[:1] in _RESERVED:
                raise DeclarativeError(_RESERVED[line.text[:1]], line.no, path)
            raise DeclarativeError("expected 'key: value'", line.no, path)
        key, rest = split
        key = _plain_key(key, line.no, path)
        if key in out:
            raise DeclarativeError("duplicate key %r" % key, line.no, path)
        lines_map.mark(out, key, line.no)
        if rest:
            out[key] = _scalar(rest, line.no, path)
            i += 1
        else:
            out[key], i = _nested(lines, i + 1, indent, lines_map, path, depth, line)
    if i < len(lines) and lines[i].indent > indent:
        raise DeclarativeError("unexpected indentation", lines[i].no, path)
    return out, i


def _nested(lines, i, indent, lines_map, path, depth, line):
    """The block under a key with no value, or `null` when there is none."""
    if i >= len(lines) or lines[i].indent <= indent:
        # A sequence may be written at its parent's indentation, as YAML allows.
        if i < len(lines) and lines[i].indent == indent and _is_item(lines[i].text) \
                and not _is_item(line.text):
            return _sequence(lines, i, indent, lines_map, path, depth + 1)
        return None, i
    return _block(lines, i, lines[i].indent, lines_map, path, depth + 1)


def _key_split(text):
    """`(key, value)` when `text` opens a mapping entry, else None. The separator is the
    first `:` outside quotes and brackets that ends the line or is followed by a space."""
    sq = dq = False
    depth = 0
    for i, c in enumerate(text):
        if sq:
            sq = c != "'"
        elif dq:
            dq = c != '"'
        elif c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == ":" and depth == 0 and (i + 1 == len(text) or text[i + 1] == " "):
            if i == 0:
                return None
            return text[:i].strip(), text[i + 1:].strip()
    return None


def _plain_key(text, no, path):
    if text[:1] in ("'", '"'):
        return _quoted(text, no, path)
    if text[:1] in _RESERVED:
        raise DeclarativeError(_RESERVED[text[:1]], no, path)
    return text


# --- scalars and flow collections -----------------------------------------------------


def _scalar(text, no, path):
    text = text.strip()
    if text[:1] in ("[", "{"):
        value, end = _flow(text, 0, no, path, 0)
        _expect_end(text, end, no, path)
        return value
    if text[:1] in ("'", '"'):
        return _quoted(text, no, path)
    if text[:1] in _RESERVED:
        raise DeclarativeError(_RESERVED[text[:1]], no, path)
    return _plain(text)


def _expect_end(text, end, no, path):
    if text[end:].strip():
        raise DeclarativeError("trailing text after a flow collection", no, path)


def _plain(text):
    lowered = text.lower()
    if lowered in _CONSTANTS:
        return _CONSTANTS[lowered]
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def _quoted(text, no, path):
    value, end = _quoted_at(text, 0, no, path)
    if text[end:].strip():
        raise DeclarativeError("trailing text after a quoted string", no, path)
    return value


def _quoted_at(text, i, no, path):
    """`(string, index after the closing quote)` for the quote starting at `i`.

    Single quotes are literal, with `''` for one quote, as YAML has it. Double quotes take
    the JSON escapes, which is what a regex in a detector needs.
    """
    quote = text[i]
    out = []
    i += 1
    while i < len(text):
        c = text[i]
        if quote == "'":
            if c == "'":
                if text[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                return "".join(out), i + 1
            out.append(c)
            i += 1
            continue
        if c == "\\":
            nxt = text[i + 1:i + 2]
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\",
                        "/": "/", "0": "\0"}.get(nxt, "\\" + nxt))
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise DeclarativeError("unterminated quoted string", no, path)


def _flow(text, i, no, path, depth):
    """A `[...]` or `{...}` written on one line, nested as far as `MAX_DEPTH`."""
    if depth > MAX_DEPTH:
        raise DeclarativeError("nested too deeply", no, path)
    closing = "]" if text[i] == "[" else "}"
    mapping = closing == "}"
    out = {} if mapping else []
    i += 1
    while True:
        i = _skip_space(text, i)
        if i >= len(text):
            raise DeclarativeError("unterminated flow collection", no, path)
        if text[i] == closing:
            return out, i + 1
        item, i = _flow_item(text, i, no, path, depth)
        if mapping:
            key, value = item
            if key in out:
                raise DeclarativeError("duplicate key %r" % key, no, path)
            out[key] = value
        else:
            out.append(item)
        i = _skip_space(text, i)
        if i >= len(text):
            raise DeclarativeError("unterminated flow collection", no, path)
        if text[i] == ",":
            i += 1
            continue
        if text[i] == closing:
            return out, i + 1
        raise DeclarativeError("expected ',' or '%s' in a flow collection" % closing,
                               no, path)


def _flow_item(text, i, no, path, depth):
    value, i = _flow_value(text, i, no, path, depth)
    i = _skip_space(text, i)
    if i < len(text) and text[i] == ":":
        i = _skip_space(text, i + 1)
        if not isinstance(value, str):
            raise DeclarativeError("a flow mapping key must be a string", no, path)
        second, i = _flow_value(text, i, no, path, depth)
        return (value, second), i
    return value, i


def _flow_value(text, i, no, path, depth):
    if i >= len(text):
        raise DeclarativeError("unterminated flow collection", no, path)
    c = text[i]
    if c in "[{":
        return _flow(text, i, no, path, depth + 1)
    if c in "'\"":
        return _quoted_at(text, i, no, path)
    if c in _RESERVED:
        raise DeclarativeError(_RESERVED[c], no, path)
    start = i
    while i < len(text) and text[i] not in ",]}:":
        i += 1
    raw = text[start:i].strip()
    if not raw:
        raise DeclarativeError("an empty value in a flow collection", no, path)
    return _plain(raw), i


def _skip_space(text, i):
    while i < len(text) and text[i] in " \t":
        i += 1
    return i
