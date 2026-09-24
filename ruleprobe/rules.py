# SPDX-License-Identifier: MIT
"""Where detector files live, and how a directory of rule files binds to them.

Three places hold a declarative detector, and all three are read into one bundle:

- `.ruleprobe/detectors.yaml` (or `.json`) at the root of the repository you are in, found
  by walking up from the working directory;
- `~/.config/ruleprobe/detectors.yaml`, honouring `XDG_CONFIG_HOME`, for the ones you want
  everywhere;
- front matter inside a markdown rule file, when `--rules <dir>` points at your rules.

The third is the one that makes a report readable, because it also says what is *not*
measured. A rule file carrying a `detector:` block is measured; one carrying
`opt_out: <reason>` is dark on purpose, and either way the file is one rule. A file carrying
neither is split at its ATX headings, one rule per section, each unmeasured and listed as such
so the gap is visible rather than assumed; one with no heading stays one unmeasured rule, named
by its `rule:` key or else its file name. Known misses: text above the first heading of a
headed file is no rule, and a setext heading does not split. Nothing here fails a build: a bad
entry is a finding with a file, a line and a reason, and the rest of the file still loads.
"""
import os
import re
from collections import namedtuple

from .declarative import DeclarativeError, load, parse_with_lines, split_front_matter
from .matchers import compile_detector, schema_version_error
from .registry import DEFAULT, Registry

__all__ = ["Bundle", "Finding", "RuleEntry", "discover", "load_bundle", "load_file",
           "load_rules_dir"]

#: The sidecar a repository keeps its own detectors in, in preference order.
REPO_DIR = ".ruleprobe"
FILENAMES = ("detectors.yaml", "detectors.yml", "detectors.json")
#: How far up the tree to look for `REPO_DIR` before giving up.
MAX_PARENTS = 40
STATES = ("measured", "dark", "unmeasured")

#: A detector file that could not be read in full: the file, the line, and why.
Finding = namedtuple("Finding", "path line reason")
#: One rule: its id, the file it lives in, whether anything measures it, the reason it is
#: dark when it is, and the detector ids bound to it. A one-rule file is named by its
#: `rule:` key, else its file name; a section rule's id is `<path>#<heading-slug>`.
RuleEntry = namedtuple("RuleEntry", "rule path state reason detectors")


class Bundle(object):
    """Everything a run loaded: the detectors, the rule files, and the findings."""

    __slots__ = ("detectors", "rules", "findings", "sources")

    def __init__(self, detectors=None, rules=None, findings=None, sources=None):
        self.detectors = list(detectors or [])
        self.rules = list(rules or [])
        self.findings = list(findings or [])
        self.sources = list(sources or [])

    def registry(self, base=DEFAULT):
        """`base` plus everything loaded. A declarative detector whose id is already taken
        replaces the one that held it, which is how a repository overrides a shipped
        detector without editing the package."""
        registry = base.copy() if base is not None else Registry()
        for detector in self.detectors:
            registry.add(detector)
        return registry

    def counts(self):
        out = dict((state, 0) for state in STATES)
        for entry in self.rules:
            out[entry.state] = out.get(entry.state, 0) + 1
        return out

    def coverage(self):
        """The counts, plus `share`: measured rules over all rules, dark ones included, or
        `None` when there are no rules. `summary()` prints this share floored to a whole
        percent and `report --json` carries it exact, so the two count the same rules."""
        out = self.counts()
        total = sum(out.values())
        out["share"] = out["measured"] / float(total) if total else None
        return out

    def summary(self, relative_to=None):
        """The coverage block a report prints under its table, or `""` when nothing was
        loaded and there is nothing to say."""
        lines = []
        if self.rules:
            coverage = self.coverage()
            lines.append("rules: %d measured, %d dark, %d unmeasured%s"
                         % (coverage["measured"], coverage["dark"], coverage["unmeasured"],
                            _percent(coverage)))
            # Every id prints whole: a section id cut short names a different rule, or none.
            width = max([28] + [len(entry.rule) + 1 for entry in self.rules])
            for entry in self.rules:
                note = ": " + entry.reason if entry.reason else ""
                lines.append("  %-11s%-*s%s%s"
                             % (entry.state, width, entry.rule,
                                _short(entry.path, relative_to), note))
        if self.findings:
            lines.append("findings: %d (everything else still loaded)"
                         % len(self.findings))
            for finding in self.findings:
                lines.append("  %s:%d  %s" % (_short(finding.path, relative_to),
                                              finding.line, finding.reason))
        return "\n".join(lines)


def _percent(coverage):
    """The share as the `rules:` line prints it. Floored, so a file with one rule unmeasured
    never reads 100%; `<1%` when the floor would hide a measured rule."""
    total = sum(v for k, v in coverage.items() if k != "share")
    if not total:
        return ""
    percent = 100 * coverage["measured"] // total
    if not percent and coverage["measured"]:
        return " (<1% measured)"
    return " (%d%% measured)" % percent


def _short(path, relative_to=None):
    """A path to print: relative to the working directory when it is under it, so a report
    never carries somebody's home directory."""
    try:
        relative = os.path.relpath(path, relative_to or os.getcwd())
    except ValueError:  # pragma: no cover - a different drive on Windows
        return path
    return path if relative.startswith("..") else relative


# --- discovery -------------------------------------------------------------------------


def discover(cwd=None, user=True):
    """The detector files to read, user file first so a repository's own overrides it."""
    found = []
    if user:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config")
        for name in FILENAMES:
            path = os.path.join(base, "ruleprobe", name)
            if os.path.isfile(path):
                found.append(path)
                break
    directory = os.path.abspath(cwd or os.getcwd())
    for _ in range(MAX_PARENTS):
        for name in FILENAMES:
            path = os.path.join(directory, REPO_DIR, name)
            if os.path.isfile(path):
                found.append(path)
                return found
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return found


# --- detector files ----------------------------------------------------------------------


def load_file(path):
    """`(detectors, findings)` for one detector file. Never raises."""
    try:
        doc, lines = load(path)
    except DeclarativeError as exc:
        return [], [Finding(exc.path, exc.line, exc.reason)]
    findings = []
    version = _file_version(doc, path, lines, findings)
    detectors, problems = _compile_entries(_entries(doc), path, lines, version=version)
    return detectors, findings + problems


def _file_version(doc, path, lines, findings):
    """The schema version a `detectors:` file sets for entries that name none: its top-level
    `version`, else 1. An unknown one, or a top-level `schema_version`, is a finding, and
    `None`, so that only the entries that would take it are skipped; an entry with a known
    `schema_version` of its own wins. Each finding names the entries it skipped."""
    if not isinstance(doc, dict) or "detectors" not in doc:
        return 1
    problems = []
    if "schema_version" in doc:
        problems.append(("schema_version",
                         "the file-level key is `version`, not `schema_version`"))
    if "version" in doc:
        reason = schema_version_error(doc["version"], "version")
        if reason:
            problems.append(("version", reason))
    if not problems:
        return doc.get("version", 1)
    entries = doc["detectors"] if isinstance(doc["detectors"], list) else []
    skipped = [e for e in entries if isinstance(e, dict) and "schema_version" not in e]
    ids = [e["id"] for e in skipped if isinstance(e.get("id"), str)]
    note = "; skipped %d %s without their own schema_version%s" % (
        len(skipped), "entry" if len(skipped) == 1 else "entries",
        ": " + ", ".join(ids) if ids else "")
    for key, reason in problems:
        findings.append(Finding(path, lines.line_of(doc, key) if lines else 0, reason + note))
    return None


def _entries(doc):
    """The entry list, whether the file is a bare list or a `detectors:` mapping."""
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        found = doc.get("detectors")
        return found if isinstance(found, list) else [doc] if "when" in doc else None
    return None


def _compile_entries(entries, path, lines, rule=None, default_prefix=None, version=1):
    """`version` is the file's default schema version, or `None` when the file named one
    it does not know: an entry without its own `schema_version` is then skipped, its
    finding already made once against the file."""
    detectors, findings = [], []
    if entries is None:
        return detectors, [Finding(path, 0, "expected a list of detectors, or a mapping "
                                            "with a detectors: list")]
    for index, entry in enumerate(entries):
        if version is None and isinstance(entry, dict) and "schema_version" not in entry:
            continue
        if isinstance(entry, dict) and (rule or default_prefix):
            filled = dict(entry)
            if rule and not filled.get("rule"):
                filled["rule"] = rule
            if default_prefix and not filled.get("id"):
                filled["id"] = "%s/%d" % (default_prefix, index + 1)
            if lines is not None:
                lines.copy_marks(entry, filled)
            entry = filled
        try:
            detectors.append(compile_detector(entry, path, lines))
        except DeclarativeError as exc:
            findings.append(Finding(exc.path, exc.line, exc.reason))
        except (TypeError, ValueError) as exc:
            findings.append(Finding(path, lines.line_of(entry) if lines else 0, str(exc)))
    return detectors, findings


# --- rule files ---------------------------------------------------------------------------


def load_rules_dir(directory):
    """`(detectors, rule entries, findings)` for a directory of markdown rule files.

    Every `.md` under `directory` is one rule, or one per section when nothing in its front
    matter binds it. The walk is sorted, so the report is the same on every machine, and a
    file that cannot be read is a finding rather than a stack trace.
    """
    detectors, rules, findings = [], [], []
    if not os.path.isdir(directory):
        return detectors, rules, [Finding(directory, 0, "not a directory")]
    for path in _markdown(directory):
        found, entries, problems = read_rule_file(path, root=directory)
        detectors.extend(found)
        rules.extend(entries)
        findings.extend(problems)
    return detectors, rules, findings


def _markdown(directory):
    out = []
    for base, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.endswith(".md") and not name.startswith("."):
                out.append(os.path.join(base, name))
    return out


def read_rule_file(path, root=None):
    """`(detectors, [RuleEntry], findings)` for one markdown rule file.

    Front matter keys this reads are `rule`, `detector` and `opt_out`; every other key is
    somebody else's, and is left alone rather than rejected, because a rule file's front
    matter belongs to the rule file. A file whose front matter carries `detector:` or
    `opt_out:`, or cannot be read as a mapping, is one rule, and so is a file with no heading.
    Any other file is split into section rules (`sections`); `root` is the `--rules`
    directory their ids are relative to, the file's own directory when not given.

    Known miss: in a file with headings, text above the first heading is no rule.
    """
    rule = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        return [], [RuleEntry(rule, path, "unmeasured", "unreadable", [])], \
            [Finding(path, 0, "cannot read: %s" % exc)]
    front, first_line, body = split_front_matter(text)
    if front is None:
        entries, findings = _section_rules(path, root, text, 1, rule)
        return [], entries, findings
    try:
        doc, lines = parse_with_lines(front, path, first_line)
    except DeclarativeError as exc:
        return [], [RuleEntry(rule, path, "unmeasured", "front matter did not parse", [])], \
            [Finding(exc.path, exc.line, exc.reason)]
    if doc is None and not front.strip():
        doc = {}
    if not isinstance(doc, dict):
        return [], [RuleEntry(rule, path, "unmeasured", "front matter is not a mapping", [])], \
            [Finding(path, first_line, "front matter is not a mapping")]
    named = doc.get("rule")
    findings = []
    bound = "detector" in doc or "detectors" in doc or "opt_out" in doc
    body_line = text.count("\n") - body.count("\n") + 1
    if not bound and "rule" in doc and sections(body):
        findings.append(Finding(path, lines.line_of(doc, "rule", first_line),
                                "rule: does not apply to a file split at its headings; its "
                                "rules are named by path and heading"))
    elif isinstance(named, str) and named and "/" not in named:
        rule = named
    elif named is not None:
        findings.append(Finding(path, lines.line_of(doc, "rule", first_line),
                                "a rule name is a slash-free string"))
    opt_out = doc.get("opt_out")
    spec = doc.get("detector", doc.get("detectors"))
    if "detector" in doc or "detectors" in doc:
        entries = spec if isinstance(spec, list) else [spec]
        detectors, problems = _compile_entries(entries, path, lines, rule=rule,
                                               default_prefix=rule)
        findings.extend(problems)
        if detectors:
            return detectors, [RuleEntry(rule, path, "measured", "",
                                         [d.id for d in detectors])], findings
        return [], [RuleEntry(rule, path, "unmeasured", "its detector did not compile", [])], \
            findings
    if "opt_out" in doc:
        reason = opt_out if isinstance(opt_out, str) and opt_out else "no reason given"
        return [], [RuleEntry(rule, path, "dark", reason, [])], findings
    entries, problems = _section_rules(path, root, body, body_line, rule)
    return [], entries, findings + problems


# --- sections -----------------------------------------------------------------------------

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_QUOTE = re.compile(r"^ {0,3}>")
_DELIMITER = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_TEXT = re.compile(r"[^\W_]", re.UNICODE)
_COMMENT = re.compile(r"^ {0,3}<!--")


def sections(body):
    """`[(heading text, heading line index, is a rule)]` for a markdown body, in order.

    The split unit is the ATX heading, at any level; a `#` line inside a fenced block or an
    HTML comment is not one, and a setext heading is not split. Text above the first heading
    belongs to no section. A section is a rule when at least one line under its heading has
    a letter or digit and sits outside a fenced or indented code block, an HTML comment, a
    table and a blockquote, so a heading with nothing under it, or only an example, is not.
    """
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kinds = _line_kinds(lines)
    out = []
    for index, kind in enumerate(kinds):
        if kind == "heading":
            text = _HEADING.match(lines[index]).group(2) or ""
            out.append([_CLOSING.sub("", text).strip(), index, False])
        elif kind == "text" and out:
            out[-1][2] = True
    return [tuple(s) for s in out]


def _line_kinds(lines):
    """Each line's kind: `heading`, `fence`, `comment`, `code`, `table`, `quote`, `blank`
    or `text`. An indented code block starts after a blank line or a heading, so an indented
    list continuation after one is read as code too: an under-count, never a false rule."""
    kinds, fence, comment = [], None, False
    for line in lines:
        if comment:
            kinds.append("comment")
            comment = "-->" not in line
            continue
        if fence:
            kinds.append("fence")
            closing = _FENCE.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= \
                    len(fence) and not closing.group(2).strip():
                fence = None
            continue
        opening = _FENCE.match(line)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = opening.group(1)
            kinds.append("fence")
        elif _COMMENT.match(line):
            kinds.append("comment")
            comment = "-->" not in line.split("<!--", 1)[1]
        elif line.strip() and _indent(line) >= 4 and \
                (not kinds or kinds[-1] in ("blank", "heading", "code")):
            kinds.append("code")
        elif _HEADING.match(line):
            kinds.append("heading")
        elif not line.strip():
            kinds.append("blank")
        elif _QUOTE.match(line) or (kinds and kinds[-1] == "quote"):
            kinds.append("quote")
        elif line.lstrip(" ").startswith("|"):
            kinds.append("table")
        elif _TEXT.search(line):
            kinds.append("text")
        else:
            kinds.append("blank")
    for index, line in enumerate(lines):
        # A pipe table without leading pipes: a header row, its delimiter row, and the rows
        # under it up to the first line without a pipe.
        if kinds[index] in ("text", "blank") and "|" in line and "-" in line and \
                _DELIMITER.match(line) and index and kinds[index - 1] == "text" and \
                "|" in lines[index - 1]:
            kinds[index - 1] = kinds[index] = "table"
            below = index + 1
            while below < len(lines) and kinds[below] == "text" and "|" in lines[below]:
                kinds[below] = "table"
                below += 1
    return kinds


def _indent(line):
    stripped = line.lstrip(" \t")
    return len(line[:len(line) - len(stripped)].expandtabs(4))


def slug(heading):
    """A heading's anchor: lower case, punctuation dropped, each space a hyphen; `section`
    when nothing is left, as for a heading of only punctuation or emoji."""
    kept = re.sub(r"[^\w\- ]", "", heading.strip().lower(), flags=re.UNICODE).strip()
    return kept.replace(" ", "-") or "section"


def _section_rules(path, root, body, first_line, name):
    """One unmeasured `RuleEntry` per section of `body` that is a rule, with its id; or,
    when `body` has no heading, one unmeasured rule called `name`, as the file always was.

    A slug repeated in the file takes an ordinal suffix in document order (`testing`,
    `testing-2`), counted over every heading so that a section's id does not move when a
    section above it stops or starts being a rule. A rule id that still repeats, as when a
    later heading's own text is `Testing 2`, is a finding against that heading's line, and
    both rules are still listed.
    """
    relative = os.path.relpath(path, root or os.path.dirname(path)).replace(os.sep, "/")
    units = sections(body)
    if not units:
        return [RuleEntry(name, path, "unmeasured", "", [])], []
    entries, findings, seen, taken = [], [], {}, set()
    for heading, index, is_rule in units:
        base = slug(heading)
        seen[base] = seen.get(base, 0) + 1
        anchor = base if seen[base] == 1 else "%s-%d" % (base, seen[base])
        rule = "%s#%s" % (relative, anchor)
        if not is_rule:
            continue
        if rule in taken:
            findings.append(Finding(path, first_line + index,
                                    "the section id %s is already taken in this file" % rule))
        taken.add(rule)
        entries.append(RuleEntry(rule, path, "unmeasured", "", []))
    return entries, findings


# --- the whole load ------------------------------------------------------------------------


def load_bundle(paths=None, rules_dir=None, cwd=None, config=True, user=True):
    """Every declarative detector a run should have: the files named, the ones discovered,
    and the rule directory. Findings accumulate; nothing raises."""
    sources = list(paths or [])
    if config:
        sources = discover(cwd=cwd, user=user) + sources
    bundle = Bundle(sources=sources)
    for path in sources:
        detectors, findings = load_file(path)
        bundle.detectors.extend(detectors)
        bundle.findings.extend(findings)
    if rules_dir:
        detectors, rules, findings = load_rules_dir(rules_dir)
        bundle.detectors.extend(detectors)
        bundle.rules.extend(rules)
        bundle.findings.extend(findings)
    return bundle
