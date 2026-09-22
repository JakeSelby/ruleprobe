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
