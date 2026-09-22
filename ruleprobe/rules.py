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
`opt_out: <reason>` is dark on purpose; one carrying neither is unmeasured, and is listed as
such so the gap is visible rather than assumed. Nothing here fails a build: a bad entry is a
finding with a file, a line and a reason, and the rest of the file still loads.
"""
import os
from collections import namedtuple

from .declarative import DeclarativeError, load, parse_with_lines, split_front_matter
from .matchers import compile_detector
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
#: One rule file: the rule it states, where it lives, whether anything measures it, the
#: reason it is dark when it is, and the detector ids bound to it.
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

    def summary(self, relative_to=None):
        """The coverage block a report prints under its table, or `""` when nothing was
        loaded and there is nothing to say."""
        lines = []
        if self.rules:
            counts = self.counts()
            lines.append("rules: %d measured, %d dark, %d unmeasured"
                         % (counts["measured"], counts["dark"], counts["unmeasured"]))
            for entry in self.rules:
                note = ": " + entry.reason if entry.reason else ""
                lines.append("  %-11s%-28s%s%s"
                             % (entry.state, entry.rule[:27],
                                _short(entry.path, relative_to), note))
        if self.findings:
            lines.append("detector findings: %d (each entry skipped, the rest still ran)"
                         % len(self.findings))
            for finding in self.findings:
                lines.append("  %s:%d  %s" % (_short(finding.path, relative_to),
                                              finding.line, finding.reason))
        return "\n".join(lines)


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
    return _compile_entries(_entries(doc), path, lines)


def _entries(doc):
    """The entry list, whether the file is a bare list or a `detectors:` mapping."""
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        found = doc.get("detectors")
        return found if isinstance(found, list) else [doc] if "when" in doc else None
    return None


def _compile_entries(entries, path, lines, rule=None, default_prefix=None):
    detectors, findings = [], []
    if entries is None:
        return detectors, [Finding(path, 0, "expected a list of detectors, or a mapping "
                                            "with a detectors: list")]
    for index, entry in enumerate(entries):
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

    Every `.md` under `directory` is one rule. The walk is sorted, so the report is the same
    on every machine, and a file that cannot be read is a finding rather than a stack trace.
    """
    detectors, rules, findings = [], [], []
    if not os.path.isdir(directory):
        return detectors, rules, [Finding(directory, 0, "not a directory")]
    for path in _markdown(directory):
        found, entry, problems = read_rule_file(path)
        detectors.extend(found)
        rules.append(entry)
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


def read_rule_file(path):
    """`(detectors, RuleEntry, findings)` for one markdown rule file.

    Front matter keys this reads are `rule`, `detector` and `opt_out`; every other key is
    somebody else's, and is left alone rather than rejected, because a rule file's front
    matter belongs to the rule file.
    """
    rule = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        return [], RuleEntry(rule, path, "unmeasured", "unreadable", []), \
            [Finding(path, 0, "cannot read: %s" % exc)]
    front, first_line, _body = split_front_matter(text)
    if front is None:
        return [], RuleEntry(rule, path, "unmeasured", "", []), []
    try:
        doc, lines = parse_with_lines(front, path, first_line)
    except DeclarativeError as exc:
        return [], RuleEntry(rule, path, "unmeasured", "front matter did not parse", []), \
            [Finding(exc.path, exc.line, exc.reason)]
    if not isinstance(doc, dict):
        return [], RuleEntry(rule, path, "unmeasured", "front matter is not a mapping", []), \
            [Finding(path, first_line, "front matter is not a mapping")]
    named = doc.get("rule")
    findings = []
    if isinstance(named, str) and named and "/" not in named:
        rule = named
    elif named is not None:
        findings.append(Finding(path, lines.line_of(doc, "rule", first_line),
                                "a rule name is a slash-free string"))
    opt_out = doc.get("opt_out")
    spec = doc.get("detector", doc.get("detectors"))
    if spec is not None:
        entries = spec if isinstance(spec, list) else [spec]
        detectors, problems = _compile_entries(entries, path, lines, rule=rule,
                                               default_prefix=rule)
        findings.extend(problems)
        if detectors:
            return detectors, RuleEntry(rule, path, "measured", "",
                                        [d.id for d in detectors]), findings
        return [], RuleEntry(rule, path, "unmeasured", "its detector did not compile", []), \
            findings
    if opt_out is not None:
        reason = opt_out if isinstance(opt_out, str) and opt_out else "no reason given"
        return [], RuleEntry(rule, path, "dark", reason, []), findings
    return [], RuleEntry(rule, path, "unmeasured", "", []), findings


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
