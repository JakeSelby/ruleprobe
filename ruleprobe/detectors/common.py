# SPDX-License-Identifier: MIT
"""The six detectors that mean the same thing in any repository.

Each is a shape a transcript shows plainly and nobody has to configure: reading a whole file
into the context window, an unfiltered `find`, a commit or push that walks past the hooks, a
secret-shaped string written to disk, a context compaction, and a model change mid-session.

Under-counting is the design throughout. A missed hit is a quieter report; a false hit is a
wrong one, and a wrong one is what makes a measurement unusable.
"""
import re

from ..events import hit, input_of, text_of
from ..registry import Detector
from ..shell import git_calls, has_redirect, operands, split_assignments

# The `aws_secret` literal is split so a repository that greps its own tracked files for
# secret shapes does not trip over this line.
SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}", r"(?i)aws_secret" r"_access_key", r"Bearer [A-Za-z0-9._-]{20,}",
    r"(?i)client_secret\s*[:=]", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"xox[bp]-",
    r"ghp_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{20,}",
]

#: Key names a secret is assigned to, for `redact` only - detection uses `SECRET_PATTERNS`.
#: Each matches the bare name, so a quoted, subscripted or JSON-escaped key is caught too:
#: `"client_secret": "v"`, `env["AWS_SECRET_ACCESS_KEY"] = "v"`. A key-name shape added to
#: `SECRET_PATTERNS` gets its name here as well. Split like the list above.
SECRET_KEY_PATTERNS = [
    r"(?i)aws_secret" r"_access_key", r"(?i)client_secret",
]

#: Generic key names, for `redact` only: a name with a `:` or `=` after it, past an optional
#: closing quote (escaped or not) and bracket, so `DB_PASSWORD=`, `"api_key": ` and
#: `env['token'] = ` all count and `max_tokens:` does not.
SECRET_NAME_PATTERNS = [
    r"(?i)(?<![a-z0-9])(?:password|passwd|pwd|token|api[_-]?key|apikey|secret|access_key)"
    r"(?:\\?[\"'])?\]?[ \t]*[:=]",
]

#: Shapes that are themselves a secret, for `redact` only. A pattern with a `secret` group
#: redacts that group alone - a URL's password, not its host.
SECRET_TOKEN_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_-]+", r"sk-proj-[A-Za-z0-9_-]+", r"github_pat_[A-Za-z0-9_]+",
    r"gh[opsur]_[A-Za-z0-9]+", r"xox[abprs]-[A-Za-z0-9-]*",
    r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@\"']*:(?P<secret>[^\s/@\"']+)@",
]

#: What `redact` puts where a secret was.
REDACTED = "[redacted]"

_PRIVATE_KEY_HEADER = "PRIVATE KEY"
_PRIVATE_KEY_END = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
# A token ends at whitespace, a quote, a backslash - so a `\n` escape ends it - a comma or a
# bracket.
_TOKEN_REST = re.compile(r"[^\s\"'\\,()\[\]{}<>]*")
# A line ends at a real newline or at a `\n` escape, as a JSON-dumped input writes one.
_BREAK = re.compile(r"\n|\\n")
# What may sit between a key name and a value that starts on a later line.
_NO_VALUE = re.compile(r"(?:[\s:=\"'\\|>\-(\[{]|<<-?[ \t]*[\"']?\w+[\"']?|#.*)*\Z")


def redact(text):
    """`text` with every secret the patterns above find replaced by `REDACTED`: the one path
    for text ruleprobe prints from a transcript.

    Every pattern is matched against the original text and each match becomes a span; the spans
    are widened, merged where they overlap or touch, and each merged span is replaced once, so
    no pattern ever reads another's output. A private key's header widens to its footer, across
    real newlines and `\\n` escapes, or to the end of the text. A key name widens through the
    end of its line, through each backslash continuation, and - when the rest of its line holds
    no value - through the following lines that are blank or indented deeper than it, and at
    least the next non-blank one; an unclosed quote on its line (an escaped one aside) widens it
    to the line holding the closing quote. Any other shape widens to the end of its token.
    Over-redacting is the safe side. Anything but a string is returned as the empty string.
    """
    if not isinstance(text, str):
        return ""
    spans = []
    for pattern in SECRET_KEY_PATTERNS + SECRET_NAME_PATTERNS:
        spans.extend(_spans(re.compile(pattern), text, _key_end))
    for pattern in SECRET_PATTERNS + SECRET_TOKEN_PATTERNS:
        spans.extend(_spans(re.compile(pattern), text, _token_end))
    if not spans:
        return text
    spans.sort()
    out, pos = [], 0
    start, end = spans[0]
    for next_start, next_end in spans[1:]:
        if next_start <= end:
            end = max(end, next_end)
            continue
        out.extend((text[pos:start], REDACTED))
        pos, start, end = end, next_start, next_end
    out.extend((text[pos:start], REDACTED, text[end:]))
    return "".join(out)


def _spans(compiled, text, end_of):
    """Each match's widened `(start, end)`. A match inside the span before it is skipped, so
    a run of matches is widened once, in linear time."""
    out, pos = [], 0
    while True:
        found = compiled.search(text, pos)
        if found is None:
            return out
        if "secret" in compiled.groupindex:
            start, end = found.span("secret")
        else:
            start, end = found.start(), end_of(text, found)
        out.append((start, end))
        pos = max(end, found.start() + 1)


def _token_end(text, found):
    if _PRIVATE_KEY_HEADER in found.group(0):
        footer = _PRIVATE_KEY_END.search(text, found.end())
        return footer.end() if footer else len(text)
    return _TOKEN_REST.match(text, found.end()).end()


def _line_break(text, pos):
    """`(where the line holding pos ends, where the next line starts)`."""
    found = _BREAK.search(text, pos)
    return (len(text), len(text)) if found is None else found.span()


def _continued(text, line_start, line_end):
    """Whether the line ends in a backslash continuation, a `\\r` before it aside."""
    end = line_end
    if end > line_start and text[end - 1] == "\r":
        end -= 1
    elif end - 2 >= line_start and text[end - 2:end] == "\\r":
        end -= 2
    return end > line_start and text[end - 1] == "\\"


def _indent(text, line_start, line_end):
    pos = line_start
    while pos < line_end and text[pos] in " \t":
        pos += 1
    return pos - line_start, pos == line_end


def _key_end(text, found):
    escaped = text.rfind("\\n", 0, found.start())
    line_start = max(text.rfind("\n", 0, found.start()) + 1,
                     escaped + 2 if escaped >= 0 else 0)
    key_indent = _indent(text, line_start, found.start())[0]
    line_end, next_start = _line_break(text, found.end())
    while _continued(text, found.end(), line_end) and next_start < len(text):
        line_end, next_start = _line_break(text, next_start)
    rest = text[found.end():line_end]
    line = text[line_start:line_end]
    for quote in ("\"", "'"):
        if (line.count(quote) - line.count("\\" + quote)) % 2:
            close = text.find(quote, line_end)
            if close < 0:
                return len(text)
            line_end, next_start = _line_break(text, close + 1)
            return line_end
    if _NO_VALUE.match(rest) is None:
        return line_end
    seen_value = False
    while next_start < len(text):
        end, following = _line_break(text, next_start)
        indent, blank = _indent(text, next_start, end)
        if not blank and seen_value and indent <= key_indent:
            break
        seen_value = seen_value or not blank
        line_end = end
        while _continued(text, next_start, line_end) and following < len(text):
            line_end, following = _line_break(text, following)
        next_start = following
    return line_end


#: A `find` argument that narrows the search, or consumes the result. One of these present
#: and the call is not the unfiltered walk this detector is looking for.
FIND_FILTERS = frozenset((
    "-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-type", "-maxdepth",
    "-mindepth", "-mmin", "-mtime", "-newer", "-newermt", "-size", "-perm", "-user",
    "-group", "-empty", "-prune", "-exec", "-execdir", "-delete", "-print0",
))

# An environment assignment that turns a hook off, and the two commands that read one.
_HOOK_BYPASS_ASSIGNMENTS = ("SKIP", "PRE_COMMIT_ALLOW_NO_CONFIG")
_HOOK_AWARE = frozenset(("git", "pre-commit"))


def whole_file_cat(events, ctx):
    """A lone `cat <one path>`: no pipe, no filter, no heredoc, no redirect."""
    hits = []
    for parsed in ctx.bash:
        for pipe in parsed.pipelines:
            if len(pipe) != 1:
                continue
            segment = pipe[0]
            if not segment or segment[0] != "cat":
                continue
            if has_redirect(segment) or len(operands(segment)) != 1:
                continue
            hits.append(hit(parsed.event))
            break
    return hits


def unfiltered_find(events, ctx):
    """`find <dir>` with no filtering predicate and nothing consuming its output."""
    hits = []
    for parsed in ctx.bash:
        for pipe in parsed.pipelines:
            if len(pipe) != 1:
                continue
            segment = pipe[0]
            if not segment or segment[0] != "find":
                continue
            if has_redirect(segment) or any(t in FIND_FILTERS for t in segment[1:]):
                continue
            hits.append(hit(parsed.event))
            break
    return hits


def no_verify(events, ctx):
    """A commit or push that walks past the repository's own hooks.

    Three spellings: the flag, a `-c core.hooksPath=` override, and the environment
    assignment pre-commit reads. Each has to be the command being run, never a string
    argument to another one, which is what the parse into segments buys.
    """
    hits = []
    for parsed in ctx.bash:
        flagged = False
        for segment, sub, args in git_calls(parsed, ("commit", "push")):
            if "--no-verify" in args or (sub == "commit" and "-n" in args):
                flagged = True
            if any(t.startswith("core.hooksPath=") for t in segment):
                flagged = True
        for pipe in parsed.pipelines:
            for segment in pipe:
                assignments, words = split_assignments(segment)
                if not words or words[0] not in _HOOK_AWARE:
                    continue
                for token in assignments:
                    if token.split("=", 1)[0] in _HOOK_BYPASS_ASSIGNMENTS:
                        flagged = True
        if flagged:
            hits.append(hit(parsed.event))
    return hits


def _secret_in(text):
    return any(re.search(p, text) for p in SECRET_PATTERNS)


def secret_in_write(events, ctx):
    """A secret-shaped string written to a file or into a heredoc body."""
    hits = []
    parsed_by_id = dict((id(p.event), p) for p in ctx.bash)
    for event in events:
        if event.get("kind") != "tool_use":
            continue
        name = event.get("name")
        data = input_of(event)
        texts = []
        if name == "Write":
            texts.append(text_of(data.get("content")))
        elif name == "Edit":
            texts.append(text_of(data.get("new_string")))
        elif name == "Bash":
            parsed = parsed_by_id.get(id(event))
            # An unparsed command is scanned whole: a key in it matters more than which word
            # of it the key sat in.
            texts.extend([parsed.command] if parsed is not None and parsed.skipped
                         else (parsed.heredocs if parsed is not None else []))
        if any(_secret_in(t) for t in texts if t):
            hits.append(hit(event))
    return hits


def compaction(events, ctx):
    """One hit per context compaction: the cached prefix is gone and the session is now
    reasoning over a summary of itself."""
    return [hit(e, tool_use_id=False) for e in events if e.get("kind") == "compact"]


def model_switch(events, ctx):
    """A model change mid-session rebuilds the cached prefix; one hit per change.

    A synthetic model name (`<synthetic>`, and anything else the transcript brackets) marks a
    runtime-generated turn, not a switch anyone made; it is ignored.
    """
    hits, current = [], None
    for event in events:
        if event.get("kind") != "assistant_text":
            continue
        model = text_of(event.get("model"))
        if not model or model.startswith("<"):
            continue
        if current is not None and model != current:
            hits.append(hit(event, tool_use_id=False))
        current = model
    return hits


DETECTORS = [
    Detector("transcript-hygiene/whole-file-cat", "transcript-hygiene", "bash", whole_file_cat),
    Detector("transcript-hygiene/unfiltered-find", "transcript-hygiene", "bash", unfiltered_find),
    Detector("verification/no-verify", "verification", "bash", no_verify),
    Detector("secrets/secret-in-write", "secrets", "write", secret_in_write),
    Detector("cache-hygiene/compact", "cache-hygiene", "session", compaction),
    Detector("cache-hygiene/model-switch", "cache-hygiene", "session", model_switch),
]


def register(registry):
    """Add the six to `registry` and return it. This is also the shape a third-party plugin
    advertises under the `ruleprobe.detectors` entry point group."""
    return registry.extend(DETECTORS)
