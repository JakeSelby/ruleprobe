# SPDX-License-Identifier: MIT
"""The six detectors that mean the same thing in any repository.

Each is a shape a transcript shows plainly and nobody has to configure: reading a whole file
into the context window, an unfiltered `find`, a commit or push that walks past the hooks, a
secret-shaped string written to disk, a context compaction, and a model change mid-session.

Under-counting is the design throughout. A missed hit is a quieter report; a false hit is a
wrong one, and a wrong one is what makes a measurement unusable.
"""
import bisect
import re

from ..events import hit, input_of, text_of
from ..registry import Detector
from ..shell import git_calls, git_config, has_redirect, operands, split_assignments

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

#: Shapes that are themselves a secret, for `redact` only. A PGP private key runs to its
#: footer as the other private keys do. A URL's password is found apart from these, from
#: each `://`.
SECRET_TOKEN_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_-]+", r"sk-proj-[A-Za-z0-9_-]+", r"github_pat_[A-Za-z0-9_]+",
    r"gh[opsur]_[A-Za-z0-9]+", r"xox[abprs]-[A-Za-z0-9-]*",
    r"-----BEGIN PGP PRIVATE KEY BLOCK-----",
]

#: What `redact` puts where a secret was.
REDACTED = "[redacted]"

_PRIVATE_KEY_HEADER = "PRIVATE KEY"
_PRIVATE_KEY_END = re.compile(r"-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")
# A URL's `user:password@`, matched from just after its `://`; the password is group 1.
_URL_USERINFO = re.compile(r"[^\s/:@\"']*:([^\s/@\"']+)@")
# A token ends at whitespace, a quote, a backslash - so a `\n` escape ends it - a comma or a
# bracket.
_TOKEN_REST = re.compile(r"[^\s\"'\\,()\[\]{}<>]*")
# A line ends at a real newline or at a `\n` escape, as a JSON-dumped input writes one.
_BREAK = re.compile(r"\n|\\n")
# What may sit between a key name and a value that starts on a later line. No two
# alternatives can match the same text - a `#` comment only ends the line - so a failed match
# is linear rather than exponential.
_NO_VALUE = re.compile(r"(?:[\s:=\"'\\|>\-(\[{]|<<-?[ \t]*(?:\"\w+\"|'\w+'|\w+))*"
                       r"(?:#[^\n]*)?\Z")
# A heredoc a key's line opens, `<<EOF`, `<<-'EOF'`; group 2 is the terminator.
_HEREDOC = re.compile(r"<<(-?)[ \t]*[\"']?(\w+)")


def redact(text):
    """`text` with every secret the patterns above find replaced by `REDACTED`: the one path
    for text ruleprobe prints from a transcript.

    Every pattern is matched against the original text and each match becomes a span; the spans
    are widened, merged where they overlap or touch, and each merged span is replaced once, so
    no pattern ever reads another's output. A private key's header widens to its footer, across
    real newlines and `\\n` escapes, or to the end of the text. A key name widens through the
    end of its line, through each backslash continuation, and - when the rest of its line holds
    no value - through the following lines that are blank or indented deeper than it, and at
    least the next non-blank one; a quote its line leaves open - `"`, `'`, a backtick or a
    JSON-escaped `\\"` - widens it to the closing quote, across real newlines and `\\n`
    escapes, or to the end of the text, as it does when it opens on the first value line; a
    heredoc its line opens widens it to the terminator. Any other shape widens to the end of
    its token, and a URL's password is redacted alone.
    Over-redacting is the safe side. Anything but a string is returned as the empty string.
    """
    if not isinstance(text, str):
        return ""
    breaks = [found.end() for found in _BREAK.finditer(text)]

    def key_end(text, found):
        return _key_end(text, found, breaks)

    spans = []
    for pattern in SECRET_KEY_PATTERNS + SECRET_NAME_PATTERNS:
        spans.extend(_spans(re.compile(pattern), text, key_end))
    for pattern in SECRET_PATTERNS + SECRET_TOKEN_PATTERNS:
        spans.extend(_spans(re.compile(pattern), text, _token_end))
    spans.extend(_url_passwords(text))
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
        start, end = found.start(), end_of(text, found)
        out.append((start, end))
        pos = max(end, found.start() + 1)


def _url_passwords(text):
    """The password span of every `scheme://user:password@`, found from each `://` so a
    long run of scheme characters with none is not searched again from every offset."""
    out, pos = [], text.find("://")
    while pos >= 0:
        found = _URL_USERINFO.match(text, pos + 3)
        if found is not None:
            out.append(found.span(1))
        pos = text.find("://", pos + 3)
    return out


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


def _open_quote(text, start, end):
    """The quote left open at `end` by `text[start:end]`: a `"`, `'` or backtick, or `\\"`,
    the JSON-escaped double quote; None when every quote closes. Inside a plain quote a
    backslash escapes the next character."""
    open_quote, pos = None, start
    while pos < end:
        char = text[pos]
        if open_quote is None:
            if char == "\\" and text[pos + 1:pos + 2] == "\"" and pos + 1 < end:
                open_quote, pos = "\\\"", pos + 2
                continue
            if char in "\"'`":
                open_quote = char
        elif open_quote == "\\\"":
            if text[pos:pos + 2] == "\\\\":
                pos += 2
                continue
            if text[pos:pos + 2] == "\\\"":
                open_quote, pos = None, pos + 2
                continue
        elif char == "\\":
            pos += 2
            continue
        elif char == open_quote:
            open_quote = None
        pos += 1
    return open_quote


def _quote_close(text, quote, pos):
    """Just past the quote that closes `quote` at or after `pos`, across real newlines and
    `\\n` escapes, or the end of the text when none does."""
    while pos < len(text):
        if quote == "\\\"":
            if text[pos:pos + 2] == "\\\\":
                pos += 2
                continue
            if text[pos:pos + 2] == "\\\"":
                return pos + 2
        elif text[pos] == "\\":
            pos += 2
            continue
        elif text[pos] == quote:
            return pos + 1
        pos += 1
    return len(text)


def _heredoc_end(text, opened, pos):
    """Just past the terminator line of the heredoc `opened` found, searched from `pos`, or
    the end of the text when it never comes."""
    indent = r"[ \t]*" if opened.group(1) else ""
    terminator = re.compile(r"(?:\n|\\n)%s%s[ \t]*(?=\r?\n|\\n|\)|\Z)"
                            % (indent, re.escape(opened.group(2))))
    closed = terminator.search(text, pos)
    return closed.end() if closed else len(text)


def _key_end(text, found, breaks):
    """Where a key name's span ends; `breaks` is where every line after the first starts."""
    at = bisect.bisect_right(breaks, found.start())
    line_start = breaks[at - 1] if at else 0
    key_indent = _indent(text, line_start, found.start())[0]
    line_end, next_start = _line_break(text, found.end())
    while _continued(text, found.end(), line_end) and next_start < len(text):
        line_end, next_start = _line_break(text, next_start)
    rest = text[found.end():line_end]
    heredoc = _HEREDOC.search(rest)
    if heredoc is not None:
        return _heredoc_end(text, heredoc, line_end)
    quote = _open_quote(text, line_start, line_end)
    if quote is not None:
        return _quote_close(text, quote, line_end)
    if _NO_VALUE.match(rest) is None:
        return line_end
    seen_value = False
    while next_start < len(text):
        end, following = _line_break(text, next_start)
        indent, blank = _indent(text, next_start, end)
        if not blank and seen_value and indent <= key_indent:
            break
        if not blank and not seen_value:
            quote = _open_quote(text, next_start, end)
            if quote is not None:
                return _quote_close(text, quote, end)
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
#: A `-c` setting that turns hooks off: `core.hooksPath` empty or exactly `/dev/null`. The
#: key is case-insensitive, as git's is; the value is not. `common.yaml` and the catalog
#: carry the same pattern.
_HOOKS_OFF = re.compile(r"^(?i:core\.hookspath)=(?:/dev/null)?$")


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

    Three spellings: the flag, a `-c core.hooksPath=` override that turns hooks off, and
    the environment assignment pre-commit reads. Each has to be the command being run, never
    a string argument to another one, which is what the parse into segments buys.

    Only the effective `core.hooksPath`, the last `-c` given for it, counts, and only when
    it is empty or exactly `/dev/null`. Pointing it at a tracked directory such as
    `.githooks` is how a repository turns its own hooks on, so every hook ran. Any other
    path goes uncounted, one that is missing or empty on disk included, as do settings given
    by `--config-env` or the `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>` and
    `GIT_CONFIG_VALUE_<n>` environment: under-counts, which the format prefers.
    """
    hits = []
    for parsed in ctx.bash:
        flagged = False
        for segment, sub, args in git_calls(parsed, ("commit", "push")):
            if "--no-verify" in args or (sub == "commit" and "-n" in args):
                flagged = True
            if any(_HOOKS_OFF.search(v) for v in git_config(segment)):
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


# What `secrets/secret-in-write` counts: a live credential, never a mention of one.
# `SECRET_PATTERNS` stays broad because `redact` prints through it; these are the detection-side
# filter, each one narrower than a shape `redact` already removes, so anything counted here is
# redacted when `explain` prints it. A credential counts only as an issuer's shape with a value
# behind it: an AWS key id, an `aws_secret_access_key` or `client_secret` assigned a literal, a
# Bearer, GitHub, Slack, OpenAI or Anthropic token, or a private-key header followed by a body.
# Each value must not be a placeholder (`xxx`, `your`, `changeme`, `redacted`, `fake`...), a
# variable name (`UPPER_SNAKE`, `lower_snake`), an expression (`os.environ[...]`, `${VAR}`) or
# a token of one repeated character, and a token value must mix letters and digits - the only
# entropy check, chosen because it is exact. A line that reads as a pattern source or as
# redaction code - `re.compile(`, a character class, a quantifier, a regex escape, `redact`,
# `mask` - counts nothing. A pattern's left edge excludes its own body's characters, so a match
# never starts inside another and a long run is scanned once.
_PLACEHOLDER = r"(?i:x{3}|your|change[_-]?me|placeholder|redact|dummy|fake|replace|insert)"
_PATTERN_OR_REDACTION = (
    r"(?:re\.(?:compile|search|match|fullmatch|findall|finditer|sub|split)\(|[Rr]eg[Ee]xp?"
    r"|\\[dwsDWS]|\[\^?[A-Za-z0-9]-[A-Za-z0-9]|\{[0-9]+(?:,[0-9]*)?\}"
    r"|(?i:redact|scrub|sanitiz|censor|mask))")
# Between a key name and its value: an optional closing quote, escaped or not, and bracket.
_KEY_GAP = r"(?:\\?[\"'])?\]?[ \t]*[:=][ \t]*"


def _value(chars, mixed=True, name=False):
    """Lookaheads at the start of a value made of `chars`."""
    out = "(?!%s*%s)" % (chars, _PLACEHOLDER)
    if name:
        out += "(?!(?:[A-Z0-9]*_[A-Z0-9_]*|[a-z0-9]*_[a-z0-9_]*)(?!%s))" % chars
    if mixed:
        out += "(?=%s*[0-9])(?=%s*[A-Za-z])" % (chars, chars)
    return out


def _on_a_plain_line(token):
    """`token` on a line that holds no pattern source and no redaction code."""
    return r"(?m)^(?=[^\n]*?%s)(?![^\n]*%s)" % (token, _PATTERN_OR_REDACTION)


_QUOTED = r"[^\s\"'\\<>${}%]"
_UNQUOTED = r"[A-Za-z0-9/+=_-]"
_KEY_END = r"(?![A-Za-z0-9/+=_.$({\[-])"
# `[_]` keeps the key name out of a grep for it, as `SECRET_PATTERNS` splits it.
_AWS_SECRET_KEY = r"(?<![A-Za-z0-9_])(?i:aws_secret[_]access_key)"
_CLIENT_SECRET_KEY = r"(?<![A-Za-z0-9_])(?i:client_secret)"
_LIVE_SECRET_PATTERNS = [_on_a_plain_line(token) for token in (
    r"(?<![A-Za-z0-9])AKIA" + _value("[A-Z0-9]") + r"[A-Z0-9]{16}(?![A-Za-z0-9])",
    _AWS_SECRET_KEY + _KEY_GAP + r"(?:\\?[\"'])?" + _value("[A-Za-z0-9/+]")
    + r"[A-Za-z0-9/+]{20,}={0,2}" + _KEY_END,
    r"(?<![A-Za-z0-9])Bearer " + _value("[A-Za-z0-9._-]", name=True) + r"[A-Za-z0-9._-]{20,}",
    _CLIENT_SECRET_KEY + _KEY_GAP + r"(\\?[\"'])" + _value(_QUOTED, mixed=False, name=True)
    + r"(?!(%s)\2*\1)%s{8,}\1" % (_QUOTED, _QUOTED),
    _CLIENT_SECRET_KEY + _KEY_GAP + _value(_UNQUOTED, name=True) + _UNQUOTED + "{20,}" + _KEY_END,
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\r?\n|\\r?\\n)" + _value("[A-Za-z0-9+/=]", mixed=False)
    + r"(?!([A-Za-z0-9+/=])\1*(?![A-Za-z0-9+/=]))[A-Za-z0-9+/=]{16,}",
    r"(?<![A-Za-z0-9_-])xox[bp]-" + _value("[A-Za-z0-9-]") + r"[0-9]+-[A-Za-z0-9]{4,}",
    r"(?<![A-Za-z0-9_])gh[pousr]_" + _value("[A-Za-z0-9]") + r"[A-Za-z0-9]{20,}",
    r"(?<![A-Za-z0-9_])github_pat_" + _value("[A-Za-z0-9_]") + r"[A-Za-z0-9_]{20,}",
    r"(?<![A-Za-z0-9_-])sk-" + _value("[A-Za-z0-9]") + r"[A-Za-z0-9]{20,}",
    r"(?<![A-Za-z0-9_-])sk-(?:ant|proj)-" + _value("[A-Za-z0-9_-]") + r"[A-Za-z0-9_-]{20,}",
)]
_LIVE_SECRETS = [re.compile(p) for p in _LIVE_SECRET_PATTERNS]
# A test or fixture path, and a file that says its values are fake: a write to one carrying
# both counts nothing, since a fixture that marks its credentials fake is not leaking one.
_FIXTURE_PATH_PATTERN = (
    r"(?:^|[/\\])(?:tests?|__tests__|specs?|testdata|fixtures?|__fixtures__|__mocks__)[/\\]"
    r"|(?:^|[/\\])(?:test_[^/\\]*|[^/\\]*_test\.[A-Za-z0-9]+|[^/\\]*\.(?:test|spec)\.[A-Za-z0-9]+"
    r"|conftest\.py)$")
_MARKED_FAKE_PATTERN = r"(?i)(?<![a-z])(?:fake|dummy|not[ _-]a[ _-]real)"
_FIXTURE_PATH = re.compile(_FIXTURE_PATH_PATTERN)
_MARKED_FAKE = re.compile(_MARKED_FAKE_PATTERN)


def _secret_in(text):
    return any(rx.search(text) for rx in _LIVE_SECRETS)


def secret_in_write(events, ctx):
    """A live credential written to a file or into a heredoc body: an issuer's shape with a
    value behind it, never a variable name, a placeholder, a pattern source or redaction code
    that only mentions one. A Write or Edit to a test path whose text marks it fake counts
    nothing."""
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
        if name in ("Write", "Edit") and texts[0] \
                and _FIXTURE_PATH.search(text_of(data.get("file_path"))) \
                and _MARKED_FAKE.search(texts[0]):
            continue
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
