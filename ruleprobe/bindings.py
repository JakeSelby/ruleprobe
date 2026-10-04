# SPDX-License-Identifier: MIT
"""Bindings the user confirmed: what `ruleprobe bind` writes and `report` reads.

The catalog binds a rule section only when one of its sentences says exactly what a detector
counts (`ruleprobe.rules`), so most sections of a real rule file stay unmeasured. `bind --plan`
lists each one with the catalog entries its sentences came nearest to and the reason it did not
bind; the user names a detector for the sections they choose, and `bind --apply` records each
choice in a sidecar file. Nothing here asks a model, and nothing binds that the user did not
name. A rule file is never edited: the agent reads it, and front matter there costs tokens.

A bindings file is the declarative subset (or JSON), sorted, with no timestamp:

    version: 1
    bindings:
      - detector: git-safety/force-push-default
        path: ~/work/app/AGENTS.md
        section: git
        sha256: 3f0c...

`path` is the rule file under the home folder (`~/...`) in the global file,
`$XDG_CONFIG_HOME/ruleprobe/bindings.yaml`, and relative to the project in a project's
`.ruleprobe/bindings.yaml`. `section` is the rule id's anchor, and `sha256` hashes the
section's text as the binder reads it (`section_digest`), so a binding to a section that has
since changed is stale and measures nothing until it is bound again.

Trust: `report` reads the global file and the bindings file of the project the user points at,
the working directory or `--rules`, found by walking up from it. A bindings file in a project
found only through the transcripts may be a clone of somebody else's repository, so it is never
read, only counted. An entry names a detector id the run already knows (`rules.known_ids`); it
cannot define one, and an entry with any other key is refused.
"""
import hashlib
import json
import os
import tempfile
from collections import namedtuple

from .declarative import DeclarativeError, emit, load
from .rules import (MAX_PARENTS, REPO_DIR, Finding, RuleEntry, _CATALOG, _binding, _label,
                    _match, _normalize)

__all__ = ["Binding", "Bindings", "global_path", "load_trusted", "plan", "section_digest"]

#: The bindings file's names, in preference order, in the global folder and in `REPO_DIR`.
FILENAMES = ("bindings.yaml", "bindings.yml", "bindings.json")
VERSION = 1
#: Every key an entry holds, and the only ones it may.
KEYS = ("detector", "path", "section", "sha256")
STALE = "binding stale, run ruleprobe bind"

#: One confirmed binding: the rule file as the bindings file names it, the section's anchor,
#: the detector id, and the sha256 of the section's text when it was bound.
Binding = namedtuple("Binding", "path section detector sha256")


class BindError(Exception):
    """A plan or a bindings file `bind --apply` will not write from, with every reason."""

    def __init__(self, reasons):
        Exception.__init__(self, "; ".join(reasons))
        self.reasons = list(reasons)


def section_digest(heading, paragraphs):
    """The sha256 of a section's text as the binder reads it: the heading and each paragraph,
    each normalized (`rules._normalize`), one per line. Markup and spacing changes that do not
    change what the binder reads leave it alone."""
    text = "\n".join(_normalize(part) for part in [heading] + list(paragraphs))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def global_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ruleprobe")


def _existing(directory):
    for name in FILENAMES:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def global_path():
    """The global bindings file: the one that exists, else where `bind` writes it."""
    directory = global_dir()
    return _existing(directory) or os.path.join(directory, FILENAMES[0])


def _project_file(start):
    """`(project root, bindings file)` for the nearest `REPO_DIR` holding a bindings file at
    or above `start`, or None."""
    directory = os.path.abspath(start)
    for _ in range(MAX_PARENTS):
        found = _existing(os.path.join(directory, REPO_DIR))
        if found:
            return directory, found
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return None


def project_root(cwd=None):
    """Where `bind --project` writes: the nearest directory at or above `cwd` holding
    `REPO_DIR` or `.git`, else `cwd` itself."""
    start = os.path.abspath(cwd or os.getcwd())
    directory = start
    for _ in range(MAX_PARENTS):
        if any(os.path.exists(os.path.join(directory, name)) for name in (REPO_DIR, ".git")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return start


def project_path(root):
    directory = os.path.join(root, REPO_DIR)
    return _existing(directory) or os.path.join(directory, FILENAMES[0])


def _key(path, base):
    """How a bindings file names the rule file at `path`: `~/...` (or the whole path outside
    home) when `base` is None, the global file; else the path relative to the project `base`,
    or None when it is outside it."""
    path = os.path.abspath(path)
    if base is None:
        return _label(path)
    # Both real, so a working directory spelled through a link still holds its own files.
    relative = os.path.relpath(os.path.realpath(path), os.path.realpath(base))
    if relative == os.pardir or relative.startswith(os.pardir + os.sep) or os.path.isabs(relative):
        return None
    return relative.replace(os.sep, "/")


def read_file(path, project=False):
    """`([Binding], [Finding])` for one bindings file. Never raises. An entry that is not a
    mapping of exactly `KEYS`, all strings, is refused with a finding, so a bindings file can
    name a detector and never define one."""
    try:
        doc, _lines = load(path)
    except DeclarativeError as exc:
        return [], [Finding(path, exc.line, exc.reason)]
    if doc is None:
        return [], []
    if not isinstance(doc, dict) or not isinstance(doc.get("bindings", []), list):
        return [], [Finding(path, 0, "expected a mapping with a bindings: list")]
    if doc.get("version", VERSION) != VERSION:
        return [], [Finding(path, 0, "unknown bindings version %r; this release reads %d"
                            % (doc.get("version"), VERSION))]
    out, findings = [], []
    for index, entry in enumerate(doc.get("bindings") or []):
        reason = _entry_error(entry, project)
        if reason:
            findings.append(Finding(path, 0, "binding %d refused: %s" % (index + 1, reason)))
            continue
        out.append(Binding(entry["path"], entry["section"], entry["detector"],
                           entry["sha256"]))
    return out, findings


def _entry_error(entry, project):
    if not isinstance(entry, dict):
        return "not a mapping"
    extra = sorted(set(entry) - set(KEYS))
    if extra:
        return ("a binding holds only %s; %s cannot be set here, and a detector is defined "
                "in a detector file" % (", ".join(KEYS), ", ".join(extra)))
    missing = [key for key in KEYS if not isinstance(entry.get(key), str) or not entry[key]]
    if missing:
        return "%s must be a non-empty string" % ", ".join(missing)
    digest = entry["sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return "sha256 is not a lowercase hex sha256"
    if project and (entry["path"].startswith(("/", "~")) or ".." in entry["path"].split("/")):
        return "a project binding names a file inside the project"
    return ""


class Bindings(object):
    """The bindings a run honours: `sources` is `[(bindings file, project root or None for
    the global file)]`, each with the entries read from it."""

    def __init__(self, sources=(), findings=()):
        self.sources = list(sources)
        self.findings = list(findings)

    @property
    def files(self):
        return [path for path, _base, _entries in self.sources]

    def lookup(self, path, section):
        """Every binding any source holds for `section` of the rule file at `path`."""
        out = []
        for _file, base, entries in self.sources:
            key = _key(path, base)
            if key is not None:
                out.extend(b for b in entries if b.path == key and b.section == section)
        return out

    def apply(self, bundle, known):
        """Bind each section rule of `bundle` the catalog left unmeasured to the detectors
        its bindings name: measured and `user`-sourced when every binding's hash matches the
        section's text today and names an id in `known`, else unmeasured and saying why."""
        bundle.findings.extend(self.findings)
        out = []
        for entry in bundle.rules:
            section = bundle.sections.get(entry.rule)
            if entry.state != "unmeasured" or section is None:
                out.append(entry)
                continue
            found = self.lookup(entry.path, entry.rule.rsplit("#", 1)[1])
            if not found:
                out.append(entry)
                continue
            digest = section_digest(*section)
            unknown = sorted(set(b.detector for b in found) - set(known))
            if any(b.sha256 != digest for b in found):
                entry = RuleEntry(entry.rule, entry.path, "unmeasured", STALE, [], None)
            elif unknown:
                entry = RuleEntry(entry.rule, entry.path, "unmeasured",
                                  "its user binding names %s, which no detector holds"
                                  % unknown[0], [], None)
            else:
                entry = RuleEntry(entry.rule, entry.path, "measured", "",
                                  sorted(set(b.detector for b in found)), "user")
            out.append(entry)
        bundle.rules = out


def load_trusted(cwd=None, rules_dir=None, user=True):
    """The bindings `report` honours: the global file when `user`, and the project bindings
    file found walking up from `cwd` and from `rules_dir`, each read once."""
    sources, findings, seen = [], [], set()
    candidates = []
    if user:
        path = _existing(global_dir())
        if path:
            candidates.append((path, None))
    for start in (cwd or os.getcwd(), rules_dir):
        found = _project_file(start) if start else None
        if found:
            candidates.append((found[1], found[0]))
    for path, base in candidates:
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        entries, problems = read_file(path, project=base is not None)
        sources.append((path, base, entries))
        findings.extend(problems)
    return Bindings(sources, findings)


def ignored_files(workdirs, trusted):
    """How many bindings files sit in the discovered working directories `workdirs` and are
    not one of `trusted`, the files `load_trusted` read. Each is counted, never read."""
    honoured = set(os.path.realpath(path) for path in trusted)
    count = 0
    for directory in sorted(set(d for d in workdirs if isinstance(d, str) and os.path.isabs(d))):
        path = _existing(os.path.join(directory, REPO_DIR))
        if path and os.path.realpath(path) not in honoured:
            count += 1
    return count


# --- the plan --------------------------------------------------------------------------------

_ORDER = dict((detector.id, index) for index, (_pattern, detector) in enumerate(_CATALOG))
NO_MATCH = "no catalog pattern matched any of its sentences"


def plan(bundle, bindings=None):
    """The plan `bind --plan` prints: `{"version", "sections"}`, one section per section rule
    the run left unmeasured, sorted by rule id, each with its rule id, its `sha256`, the
    reason the catalog did not bind it, its candidates ranked by the binder's own evidence
    (`_candidates`), the detectors it was bound to when that binding is now stale, and an
    empty `bind` for the user to fill."""
    sections = []
    for entry in sorted(bundle.rules, key=lambda e: e.rule):
        section = bundle.sections.get(entry.rule)
        if entry.state != "unmeasured" or section is None:
            continue
        heading, paragraphs = section
        auto = _binding(entry.rule, entry.path, heading, paragraphs)[0]
        reason = auto.reason if auto.state == "unmeasured" else entry.reason
        item = {"bind": None, "candidates": _candidates(heading, paragraphs),
                "reason": reason or NO_MATCH, "rule": entry.rule,
                "sha256": section_digest(heading, paragraphs)}
        if entry.reason == STALE and bindings is not None:
            item["stale"] = sorted(set(b.detector for b in bindings.lookup(
                entry.path, entry.rule.rsplit("#", 1)[1])))
        sections.append(item)
    return {"sections": sections, "version": VERSION}


def _candidates(heading, paragraphs):
    """The catalog detectors the section's sentences matched, the most sentences first, then
    catalog order, each with its evidence: how many sentences matched it, the words that
    unbound them, and the entries a sentence matched with it. A section no pattern matched has
    none, and none is guessed."""
    seen = {}
    for sentence in _match(heading, paragraphs):
        for detector in sentence.detectors:
            facts = seen.setdefault(detector.id, [0, set(), set()])
            facts[0] += 1
            if sentence.marker:
                facts[1].add(sentence.marker)
            facts[2].update(d.id for d in sentence.detectors if d.id != detector.id)
    ranked = sorted(seen, key=lambda did: (-seen[did][0], _ORDER.get(did, len(_ORDER)), did))
    out = []
    for did in ranked:
        count, markers, shared = seen[did]
        evidence = ["%d sentence%s matched" % (count, "" if count == 1 else "s")]
        if markers:
            evidence.append("unbound by %s" % ", ".join(sorted(markers)))
        if shared:
            evidence.append("matched together with %s" % ", ".join(sorted(shared)))
        out.append({"detector": did, "evidence": "; ".join(evidence)})
    return out


PLAN_HEADER = """\
# ruleprobe bind plan: the rule sections the catalog left unmeasured, and why.
# To bind one, set its `bind:` to a detector id: a candidate, or any id
# `ruleprobe detectors` lists. Leave `bind: null` to skip it. Then run
#   ruleprobe bind --apply <this file>
# with the same --rules or --root, adding --project to write this project's file.
"""


def plan_text(doc):
    return PLAN_HEADER + emit(doc)


# --- apply --------------------------------------------------------------------------------


def choices(doc):
    """`[(rule id, sha256, [detector ids])]` the user chose in an edited plan, in rule order.
    Raises `BindError` naming every malformed section."""
    if not isinstance(doc, dict) or not isinstance(doc.get("sections"), list):
        raise BindError(["a plan is a mapping with a sections: list"])
    out, reasons = [], []
    for index, item in enumerate(doc["sections"]):
        where = "section %d" % (index + 1)
        if not isinstance(item, dict) or not isinstance(item.get("rule"), str):
            reasons.append("%s: no rule id" % where)
            continue
        chosen = item.get("bind")
        if chosen is None or chosen == "" or chosen == []:
            continue
        ids = chosen if isinstance(chosen, list) else [chosen]
        if not all(isinstance(did, str) and did for did in ids):
            reasons.append("%s: bind: is a detector id or a list of them" % item["rule"])
            continue
        if not isinstance(item.get("sha256"), str):
            reasons.append("%s: no sha256; print the plan again" % item["rule"])
            continue
        out.append((item["rule"], item["sha256"], sorted(set(ids))))
    if reasons:
        raise BindError(reasons)
    return sorted(out)


def resolve(bundle, chosen, known, base):
    """The `Binding`s to record for `chosen` (`choices`), for a bindings file of the global
    kind when `base` is None, else of the project at `base`. Raises `BindError` naming each
    choice it refuses: a rule this run did not read as a section, one whose text changed
    since the plan, one the catalog measures, a file outside the project, an unknown id."""
    entries = dict((entry.rule, entry) for entry in bundle.rules)
    out, reasons = [], []
    for rule, digest, ids in chosen:
        entry, section = entries.get(rule), bundle.sections.get(rule)
        if entry is None or section is None:
            reasons.append("%s: not a rule section this run read; pass the same --rules or "
                           "--root as the plan" % rule)
            continue
        if section_digest(*section) != digest:
            reasons.append("%s: its text changed since the plan; print the plan again" % rule)
            continue
        if entry.state != "unmeasured" and entry.source != "user":
            reasons.append("%s: already %s; nothing to bind" % (
                rule, "measured by the catalog" if entry.state == "measured" else entry.state))
            continue
        key = _key(entry.path, base)
        if key is None:
            reasons.append("%s: outside this project; bind it in your global file" % rule)
            continue
        unknown = [did for did in ids if did not in known]
        if unknown:
            reasons.append("%s: unknown detector id %s; a binding names a shipped, catalog "
                           "or detector-file id and never defines one" % (rule, unknown[0]))
            continue
        section_id = rule.rsplit("#", 1)[1]
        out.extend(Binding(key, section_id, did, digest) for did in ids)
    if reasons:
        raise BindError(reasons)
    return out


def merged(existing, new):
    """`existing` with every binding of a section `new` binds replaced by `new`'s, sorted."""
    replaced = set((b.path, b.section) for b in new)
    kept = [b for b in existing if (b.path, b.section) not in replaced]
    return sorted(set(kept + list(new)))


def file_text(path, bindings):
    """A bindings file's bytes: sorted keys and entries, no timestamp."""
    doc = {"bindings": [dict(zip(Binding._fields, b)) for b in sorted(bindings)],
           "version": VERSION}
    doc["bindings"] = [dict(sorted(entry.items())) for entry in doc["bindings"]]
    if path.endswith(".json"):
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"
    return emit(doc)


def write(path, bindings):
    """Write `bindings` to `path` whole, through a temporary file in the same folder and a
    rename, so a reader never sees half a file. A link or a non-file at `path` is refused."""
    if os.path.islink(path) or (os.path.exists(path) and not os.path.isfile(path)):
        raise BindError(["%s is not a regular file; not written" % path])
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    data = file_text(path, bindings).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".bindings-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
