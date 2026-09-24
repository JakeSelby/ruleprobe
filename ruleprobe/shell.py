# SPDX-License-Identifier: MIT
"""Shell decomposition: one Bash command, parsed once, shared by every detector.

The parser is deliberately partial. It answers "which words were the command and its
arguments, in which pipeline segment, and what did a heredoc body hold" — enough for a
detector to recognise a shape — and nothing else. It never runs anything, never resolves a
variable, and never opens a file.

Known misses, all of them under-counts by design. A missed hit is a quieter report; a false
hit is a wrong one.

- A heredoc header behind a `#` comment (`cat <<EOF  # note`) is read as a heredoc, because
  the body is lifted out before comments are stripped.
- A command nested inside a substitution (`$(git commit -m ...)`) is invisible: the
  substitution is replaced wholesale before the segments are split.
- Literal text equal to a heredoc marker in an argument is resolved as if it were that
  heredoc's body.
"""
import re
import shlex

# Longest Bash command worth tokenizing. The tokenizer is superlinear in line length and a
# pasted file is never the shape a detector is looking for; a longer command is left
# unparsed, and `Parsed.skipped` says so.
MAX_COMMAND = 16 * 1024

# What stands in for a command, process or arithmetic substitution once it is lifted out.
# An argument that resolves to one was never read, so it is never judged.
SUB_PLACEHOLDER = "__RULEPROBE_SUB__"

# A heredoc body is lifted out of the command and left behind as this marker, so the command
# a body belongs to is still visible in the token stream.
_MARKER = "__RULEPROBE_HEREDOC_%d__"
MARKER_RE = re.compile(r"^__RULEPROBE_HEREDOC_(\d+)__$")
# `cmd -m "$(cat <<'EOF' ... EOF)"`, the form a coding agent writes for a multi-line commit
# message: the substitution exists only to carry the heredoc, so the marker takes its place.
_CAT_SUB_RE = re.compile(r"\$\(\s*cat\s+<<\s*(__RULEPROBE_HEREDOC_\d+__)\s*\)")

_PIPE = frozenset(("|", "|&"))
_BREAK = frozenset((";", "&&", "||", "&", ";;", "(", ")"))
_DROP = frozenset(("do", "done", "then", "fi", "else", "esac", "{", "}", "!",
                   "while", "until", "if", "elif", "for", "select", "case", "in"))
_REDIRECTS = re.compile(r"^\d*(<|<<|<<<|<&|>|>>|&>|>&)$")
_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


# --- substitutions and comments ----------------------------------------------------


def _match_paren(text, start):
    """The index of the `)` closing the `(` at `start`, or None."""
    depth = 0
    i = start
    n = len(text)
    sq = dq = False
    while i < n:
        c = text[i]
        if sq:
            sq = c != "'"
        elif dq:
            if c == "\\":
                i += 1
            elif c == '"':
                dq = False
        elif c == "\\":
            i += 1
        elif c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def strip_subs(command):
    """`command` with every substitution replaced by `SUB_PLACEHOLDER`, or None.

    None means the text does not parse — an unterminated quote or backtick, an unclosed
    `$(` — and the caller keeps the raw text rather than a half-rewritten one.
    """
    out = []
    i = 0
    n = len(command)
    sq = dq = False
    while i < n:
        c = command[i]
        if sq:
            out.append(c)
            if c == "'":
                sq = False
            i += 1
            continue
        if c == "'" and not dq:
            sq = True
            out.append(c)
            i += 1
            continue
        if c == '"':
            dq = not dq
            out.append(c)
            i += 1
            continue
        if c == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        if c == "`":
            j = i + 1
            while j < n and command[j] != "`":
                j += 2 if command[j] == "\\" else 1
            if j >= n:
                return None
            out.append(SUB_PLACEHOLDER)
            i = j + 1
            continue
        if command.startswith("$(", i):
            end = _match_paren(command, i + 1)
            if end is None:
                return None
            out.append(SUB_PLACEHOLDER)
            i = end + 1
            continue
        if c in "<>" and not dq and command.startswith("(", i + 1):
            end = _match_paren(command, i + 1)
            if end is None:
                return None
            out.append(SUB_PLACEHOLDER)
            i = end + 1
            continue
        out.append(c)
        i += 1
    if sq or dq:
        return None
    return "".join(out)


def strip_comment(line):
    """`line` without its trailing bash comment: an unquoted `#` at the start of a word.
    Substitutions are already placeholders by here, so only quotes need tracking."""
    sq = dq = False
    i = 0
    n = len(line)
    escaped = -1  # the index of the last character a backslash made literal
    while i < n:
        c = line[i]
        if sq:
            sq = c != "'"
        elif dq:
            if c == "\\":
                i += 1
            elif c == '"':
                dq = False
        elif c == "\\":
            i += 1
            escaped = i
        elif c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c == "#" and (i == 0 or (line[i - 1] in " \t;|&()" and escaped != i - 1)):
            return line[:i]
        i += 1
    return line


# --- heredocs ----------------------------------------------------------------------


def _heredoc_headers(line):
    """`(start, end, delimiter, dash)` for every heredoc operator that is a real shell word.

    `<<` inside quotes is data — `grep -n '<<EOF' file` opens no heredoc — so the scan
    tracks quoting. `<<-`, `<<"EOF"`, `<<'MSG-END'` and `<<\\EOF` are all headers; `<<<` is
    not. A substitution quotes afresh, which is what makes the `-m "$(cat <<'EOF' ...)"`
    form a heredoc and not a string. `dash` says the operator was `<<-`, which is the only
    spelling whose terminator may be indented, and then only by tabs.
    """
    out = []
    sq = dq = False
    stack = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if sq:
            sq = c != "'"
            i += 1
            continue
        if dq and not line.startswith("$(", i):
            if c == "\\":
                i += 2
                continue
            dq = c != '"'
            i += 1
            continue
        if line.startswith("$(", i):
            stack.append(dq)
            dq = False
            i += 2
            continue
        if c == ")" and stack:
            dq = stack.pop()
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c == "'":
            sq = True
            i += 1
            continue
        if c == '"':
            dq = True
            i += 1
            continue
        if line.startswith("<<<", i):  # a herestring, not a heredoc
            i += 3
            continue
        if line.startswith("<<", i):
            j = i + 2
            dash = j < n and line[j] == "-"
            if dash:
                j += 1
            while j < n and line[j] in " \t":
                j += 1
            if j < n and line[j] in "\"'":
                quote = line[j]
                k = line.find(quote, j + 1)
                if k == -1:
                    break
                out.append((i, k + 1, line[j + 1:k], dash))
                i = k + 1
                continue
            # An unquoted delimiter may still be escaped a character at a time: `<<\EOF`
            # is bash's third spelling of `<<'EOF'`, and reading the backslash as the end
            # of the word would leave the body to be parsed as commands.
            k = j
            word = []
            while k < n:
                c = line[k]
                if c == "\\" and k + 1 < n:
                    word.append(line[k + 1])
                    k += 2
                    continue
                if c.isalnum() or c in "_-.":
                    word.append(c)
                    k += 1
                    continue
                break
            if word:
                out.append((i, k, "".join(word), dash))
                i = k
                continue
        i += 1
    return out


def _terminates(line, delimiter, dash):
    """Whether `line` is the terminator of a heredoc on `delimiter`."""
    return (line.lstrip("\t") if dash else line) == delimiter


def strip_heredocs(command):
    """`(command with each heredoc body lifted out, [body, ...])`.

    The operator stays as `<< __RULEPROBE_HEREDOC_n__`, so a segment carrying a heredoc is
    still recognisable as redirected and the body can be bound back to its own command.

    A terminator is matched the way bash matches one: the line is the delimiter and nothing
    else. Only `<<-` allows it to be indented, and only by tabs. An indented `  EOF` closes
    nothing, so the lines after it stay body rather than becoming commands nobody ran.
    """
    lines = command.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept, bodies = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        headers = _heredoc_headers(line)
        rewritten, cursor = [], 0
        for start, end, delimiter, dash in headers:
            body = []
            while i < len(lines) and not _terminates(lines[i], delimiter, dash):
                body.append(lines[i])
                i += 1
            i += 1  # the terminator line itself
            rewritten.append(line[cursor:start])
            rewritten.append("<< " + (_MARKER % len(bodies)))
            cursor = end
            bodies.append("\n".join(body))
        rewritten.append(line[cursor:])
        kept.append("".join(rewritten))
    return "\n".join(kept), bodies


# --- tokens and pipelines ----------------------------------------------------------


def _shell_lines(text):
    """`text` split at the newlines bash treats as command separators: the ones outside
    quotes. A newline inside a `-m "..."` message is part of the message, not a new
    command."""
    out, start = [], 0
    sq = dq = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and not sq:
            i += 2
            continue
        if sq:
            sq = c != "'"
        elif dq:
            dq = c != '"'
        elif c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c == "\n":
            out.append(text[start:i])
            start = i + 1
        i += 1
    out.append(text[start:])
    return out


class Literal(str):
    """A word that was quoted or escaped, in whole or in part: `\\(`, `'|'`, `\\;`, `'done'`.

    `shlex` hands back `(` for both `(` and `\\(`, but only the first opens a subshell;
    `find . \\( -name x \\)` is one command. The type is how the split tells an operator or
    a reserved word from a word that only spells one, and a detector comparing words sees an
    ordinary string.
    """

    __slots__ = ()


# Where the quoting mark is chosen from: the supplementary private-use area, which no shell
# gives a meaning to.
_MARK_FIRST, _MARK_LAST = 0xF0000, 0xFFFFD


def _free_mark(text):
    """The first supplementary private-use character absent from `text`, or None.

    Choosing it per command means a transcript cannot forge a `Literal` by holding the
    mark, and a command that holds some private-use glyphs is still marked.
    """
    present = set(text)
    for point in range(_MARK_FIRST, _MARK_LAST + 1):
        if chr(point) not in present:
            return chr(point)
    return None


def _mark_literals(text, mark):
    """`text` with `mark` added to every quoted span and after every escaped character.

    The quoting rules are the ones `shlex` applies in POSIX mode: a single-quoted span, a
    double-quoted span in which only `\\"` and `\\\\` are escapes, and the character after an
    unquoted backslash. `shlex` already reads a quoted or escaped operator as a word; the mark
    is what survives the quote removal to say so. It joins the word around it only because
    `tokenize` sets `whitespace_split`, under which every character that is neither
    whitespace nor punctuation continues a word.
    """
    out = []
    sq = dq = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if sq:
            sq = c != "'"
        elif dq and c == "\\" and text[i + 1:i + 2] in ('"', "\\"):
            out.append(text[i:i + 2])
            i += 2
            continue
        elif dq:
            dq = c != '"'
        elif c == "\\" and i + 1 < n:
            out.append(text[i:i + 2] + mark)
            i += 2
            continue
        elif c in "'\"":
            sq, dq = c == "'", c == '"'
            out.append(c + mark)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _unmark(token, mark):
    """`token` without `mark`; a `Literal` when it held one."""
    return Literal(token.replace(mark, "")) if mark in token else token


def _is_operator(token, operators):
    return token in operators and not isinstance(token, Literal)


def _is_redirect(token):
    return bool(_REDIRECTS.match(token)) and not isinstance(token, Literal)


def tokenize(text, strict=False):
    """Shell tokens for already-heredoc-stripped `text`: substitutions become placeholders,
    comments go, and the newlines that separate commands become `;` — the ones inside a
    quoted argument are left alone.

    `strict=True` returns None instead of a token list for text that does not parse — an
    unterminated quote, an unclosed `$(` — so a caller can tell "no words in it" from "no
    parse of it". `Parsed` uses it: a command nobody could tokenize is `unparsed`, not a
    command with nothing in it.
    """
    # A continuation is one command, so it is joined before anything is split.
    text = re.sub(r"\\\r?\n[ \t]*", " ", text)
    stripped = strip_subs(text)
    if stripped is None and strict:
        return None
    if stripped is not None:
        text = stripped
    text = " ; ".join(strip_comment(line) for line in _shell_lines(text))
    try:
        mark = _free_mark(text)
        lex = shlex.shlex(text if mark is None else _mark_literals(text, mark), posix=True,
                          punctuation_chars=True)
        lex.commenters = ""
        lex.whitespace_split = True  # what lets the mark join a word; see `_mark_literals`
        return list(lex) if mark is None else [_unmark(token, mark) for token in lex]
    except ValueError:
        return None if strict else []


def _pipelines(tokens):
    """Tokens as a list of pipelines, each a list of segments, each a token list."""
    out, pipe, seg = [], [], []
    for token in tokens:
        if _is_operator(token, _BREAK):
            if seg:
                pipe.append(seg)
                seg = []
            if pipe:
                out.append(pipe)
                pipe = []
            continue
        if _is_operator(token, _PIPE):
            if seg:
                pipe.append(seg)
                seg = []
            continue
        if not seg and _is_operator(token, _DROP):
            continue
        seg.append(token)
    if seg:
        pipe.append(seg)
    if pipe:
        out.append(pipe)
    return out


def pipelines(command):
    """`command` parsed from raw text. `analyse()` is the path detectors use; this one is
    for a caller with a single command in hand, and for the tests."""
    text, _ = strip_heredocs(command)
    return _pipelines(tokenize(_CAT_SUB_RE.sub(r"\1", text)))


def operands(segment):
    """The segment's positional words: no flags, no redirect operators or targets."""
    out = []
    skip = False
    for token in segment[1:]:
        if skip:
            skip = False
            continue
        if _is_redirect(token):
            skip = True
            continue
        if token.startswith("-"):
            continue
        out.append(token)
    return out


def has_redirect(segment):
    return any(_is_redirect(t) for t in segment)


def normalise(command):
    """Whitespace-collapsed command text, without a leading `cd <dir> &&`. An escaped
    `\\&` belongs to the directory's name, so `cd a\\&& ls` keeps its `cd`."""
    text = " ".join(command.split())
    return re.sub(r"^cd\s+(?:[^\s\\]|\\.)+\s*&&\s*", "", text).strip()


def split_assignments(segment):
    """`(leading NAME=VALUE assignments, the command and its arguments)`."""
    i = 0
    while i < len(segment) and _ASSIGNMENT_RE.match(segment[i]):
        i += 1
    return segment[:i], segment[i:]


def git_calls(parsed, subcommands):
    """`(segment, subcommand, args)` for every `git <subcommand>` in a parsed command."""
    for pipe in parsed.pipelines:
        for segment in pipe:
            _, words = split_assignments(segment)
            if not words or words[0] != "git":
                continue
            rest = words[1:]
            i = 0
            while i < len(rest) and rest[i].startswith("-"):
                i += 2 if rest[i] in ("-C", "-c") else 1
            if i < len(rest) and rest[i] in subcommands:
                yield segment, rest[i], rest[i + 1:]


def git_config(segment):
    """The value of every `-c` given to `git` in one segment before its subcommand."""
    words = split_assignments(segment)[1][1:]
    values, i = [], 0
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-c" and i + 1 < len(words):
            values.append(words[i + 1])
        i += 2 if words[i] in ("-C", "-c") else 1
    return values


# --- the parsed view ---------------------------------------------------------------


class Parsed(object):
    """One Bash tool use, parsed once and shared by every shell detector."""

    __slots__ = ("event", "command", "skipped", "heredocs", "pipelines", "normalised")

    def __init__(self, event):
        from .events import input_of, text_of

        self.event = event
        self.command = text_of(input_of(event).get("command"))
        self.heredocs, self.pipelines, self.normalised = [], [], ""
        # A command that is absent, a number, a list or bytes parses to nothing at all; the
        # event stays in the list and every shell detector simply passes over it.
        self.skipped = not self.command or len(self.command) > MAX_COMMAND
        if self.skipped:
            return
        try:
            text, self.heredocs = strip_heredocs(self.command)
            tokens = tokenize(_CAT_SUB_RE.sub(r"\1", text), strict=True)
            # Text that does not tokenize is `unparsed`, not a command with no words in it:
            # a matcher asking for `unparsed` is the only thing that should see it, and a
            # segment matcher should not read half a parse.
            if tokens is None:
                self.heredocs, self.pipelines, self.normalised = [], [], ""
                self.skipped = True
                return
            self.pipelines = _pipelines(tokens)
            self.normalised = normalise(self.command)
        except Exception:
            self.heredocs, self.pipelines, self.normalised = [], [], ""
            self.skipped = True

    @property
    def turn(self):
        return self.event.get("turn", 0)

    @property
    def id(self):
        return self.event.get("id")


class Context(object):
    """One pass over the events: the Bash parses and the final assistant messages."""

    __slots__ = ("events", "bash", "finals")

    def __init__(self, events):
        self.events = events
        self.bash = []
        self.finals = []
        for event in events:
            kind = event.get("kind")
            if kind == "tool_use" and event.get("name") == "Bash":
                self.bash.append(Parsed(event))
            elif kind == "assistant_text" and event.get("final"):
                self.finals.append(event)


def analyse(events):
    """The parsed view `run()` hands to every detector. Anything that is not a dict event is
    dropped here, so no detector has to defend itself against the shape."""
    if not isinstance(events, (list, tuple)):
        events = []
    return Context([e for e in events if isinstance(e, dict)])
