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
`opt_out: <reason>` is dark on purpose, and either way the file is one rule. A file giving
neither a value is split at its ATX headings, one rule per section; one with no heading, or
with no section that is a rule, stays one rule, named by its `rule:` key or else its file
name, and its whole text - above the first heading included - binds the catalog as one unit.
Known misses: in a file with a rule section, text above the first heading is no rule, and a
setext heading does not split. Nothing here fails a build: a bad entry is a finding with a
file, a line and a reason, and the rest of the file still loads.

A section rule is bound to the shipped catalog (`ruleprobe.detectors.catalog`) by what it
says, with no model, one sentence at a time: its heading and each sentence of its prose are
matched against every entry's anchored pattern, a sentence that matches exactly one entry
binds that entry, and the rule is measured by every entry its sentences bind, under its own
section id, as a rule whose source is `catalog`. A sentence matching none, or more than one,
binds nothing, and a rule none of whose sentences binds is unmeasured and listed, so the gap
is visible rather than assumed; under-counting is the point, since a loose binding would
lift the measured share on rules nobody would recognise. For the same reason a pattern
never spans a clause break (see `ruleprobe.detectors.catalog`), and a word that narrows a
rule unbinds it. An exception or a permission - except (excepted, exception), exempt, unless,
other than, apart from, excluding, allowed, fine, okay, ok - anywhere in the rule, its heading
included, unbinds every sentence of it, so "Never force-push to main. Hotfixes excepted." is no
force-push rule, and nor is "Except on release branches:" over "- Never force-push to main.".
A condition or a contrast - if, when, but, however, without - unbinds only its own sentence.
The catalog's negated markers ("no exceptions", "admit no exception") are neither where the
clause ends after them. `only` is left out,
since it intensifies as often as it narrows ("use only uv"), and so are `instead` and
`rather than`, which the pip shape itself uses. A rule bound in its front matter is `own`,
and so is a catalog-bound one whose detector id a detector file of the user's replaced.
"""
import os
import re
from collections import namedtuple

from .declarative import DeclarativeError, load, parse_with_lines, split_front_matter
from .detectors import catalog as _catalog
from .matchers import compile_detector, schema_version_error
from .registry import DEFAULT, Registry, fold_map

__all__ = ["Bundle", "Finding", "RuleEntry", "catalog_detectors", "discover", "load_bundle",
           "load_file", "load_rules_dir"]

#: The sidecar a repository keeps its own detectors in, in preference order.
REPO_DIR = ".ruleprobe"
FILENAMES = ("detectors.yaml", "detectors.yml", "detectors.json")
#: How far up the tree to look for `REPO_DIR` before giving up.
MAX_PARENTS = 40
STATES = ("measured", "dark", "unmeasured")
#: Where a measured rule's detectors came from: its own front matter or detector files, or
#: the shipped catalog.
SOURCES = ("own", "catalog")

#: A detector file that could not be read in full: the file, the line, and why.
Finding = namedtuple("Finding", "path line reason")
#: One rule: its id, the file it lives in, whether anything measures it, the reason it is
#: dark or unmeasured when there is one, the detector ids bound to it, and where those came
#: from, one of `SOURCES`, or `None` when nothing is bound. A one-rule file is named by its
#: `rule:` key, else its file name; a section rule's id is `<path>#<heading-slug>`.
RuleEntry = namedtuple("RuleEntry", "rule path state reason detectors source",
                       defaults=(None,))


def _compile_catalog():
    """`((pattern, detector), ...)` for every catalog entry, in catalog order."""
    return tuple((re.compile(entry["pattern"], re.IGNORECASE),
                  compile_detector(entry["detector"], "<catalog>"))
                 for entry in _catalog.ENTRIES)


#: The shipped catalog, compiled once at import. Its detectors are shared by every bundle's
#: registry and never added to `DEFAULT`.
_CATALOG = _compile_catalog()


def catalog_detectors(fold=None):
    """The catalog's detectors in catalog order, less any id `fold` retires: a registry's
    effective fold map (`Registry.fold_map()`), or the shipped one when not given."""
    retired = fold_map() if fold is None else fold
    return [detector for _pattern, detector in _CATALOG if detector.id not in retired]


def _is_catalog(detector):
    return any(detector is known for _pattern, known in _CATALOG)


class Bundle(object):
    """Everything a run loaded: the detectors, the rule files, and the findings."""

    __slots__ = ("detectors", "rules", "findings", "sources", "_bound")

    def __init__(self, detectors=None, rules=None, findings=None, sources=None):
        self.detectors = list(detectors or [])
        self.rules = list(rules or [])
        self.findings = list(findings or [])
        self.sources = list(sources or [])
        # Every entry any `registry()` call labelled, by identity, with the entry it was
        # labelled from: `{id(labelled): (labelled, bound)}`. The labelled entry is held so
        # its identity is never reused by another object.
        self._bound = {}

    def registry(self, base=DEFAULT, whole_catalog=False):
        """`base`, then the catalog detectors a rule bound, then everything loaded. A
        declarative detector whose id is already taken replaces the one that held it, which
        is how a repository overrides a shipped or a catalog detector without editing the
        package. A catalog entry that restates a detector `base` already holds leaves that
        one in place. `whole_catalog` adds every catalog entry, bound or not, which is how
        `ruleprobe corpus` and `ruleprobe detectors` list the whole catalog.

        A catalog id the result's fold map retires - the shipped renames with `base`'s own
        `Registry(renamed=)` over them - is never added, not even beside its successor.

        `self.rules` then reads as this call labels the rules, so the coverage block printed
        after it names what actually measures each: a catalog-bound rule whose id the result
        holds under another detector - a plugin's, `base`'s own or a loaded one - is `own`,
        and one whose id it does not hold at all is unmeasured. The labels are computed from
        the rules as `load_bundle` bound them, never from an earlier call's, so each call
        answers for its own `base` alone; before any call, `rules`, `coverage()` and
        `summary()` read as `load_bundle` left them. Rules added, removed or assigned after a
        call - an earlier call's list included - are read with every entry any call labelled
        put back as it was bound, and a catalog detector no rule binds any more does not
        join."""
        registry = base.copy() if base is not None else Registry()
        fold = registry.fold_map()
        binding = []
        for entry in self.rules:
            known = self._bound.get(id(entry))
            binding.append(known[1] if known is not None and known[0] is entry else entry)
        bound = set(did for entry in binding if entry.source == "catalog"
                    for did in entry.detectors)
        for detector in catalog_detectors(fold):
            if (whole_catalog or detector.id in bound) and detector.id not in registry:
                registry.add(detector)
        for detector in self.detectors:
            # A catalog detector `load_bundle` put here for a rule joins only while a rule
            # still binds it.
            if _is_catalog(detector) and (detector.id in registry or detector.id in fold
                                          or not (whole_catalog or detector.id in bound)):
                continue
            registry.add(detector)
        self.rules = _sourced(binding, registry, fold)
        for labelled, entry in zip(self.rules, binding):
            self._bound[id(labelled)] = (labelled, entry)
        return registry

    def counts(self):
        out = dict((state, 0) for state in STATES)
        for entry in self.rules:
            out[entry.state] = out.get(entry.state, 0) + 1
        return out

    def coverage(self):
        """The counts, plus `share`: measured rules over all rules, dark ones included, or
        `None` when there are no rules, and `catalog`: the measured rules the shipped catalog
        binds. `summary()` prints the share floored to a whole percent and `report --json`
        carries it exact, so the two count the same rules."""
        out = self.counts()
        total = sum(out.values())
        out["share"] = out["measured"] / float(total) if total else None
        out["catalog"] = sum(1 for entry in self.rules if entry.source == "catalog")
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
                if entry.source == "catalog":
                    note = ": catalog-bound, " + ", ".join(entry.detectors)
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


def _sourced(rules, registry, fold):
    """A new list of `rules`, each catalog-bound one relabelled for `registry`: `own` when
    it holds the id under a detector other than the catalog's or the shipped one it
    restates, and unmeasured when it does not hold the id at all, since nothing would
    measure the rule. `fold` is the registry's fold map, to say which ids are retired."""
    out = []
    for entry in rules:
        if entry.source == "catalog":
            for did in entry.detectors:
                held = registry.get(did)
                if held is None:
                    reason = ("its catalog entry %s is retired" % did if did in fold
                              else "its catalog entry %s is not registered" % did)
                    entry = RuleEntry(entry.rule, entry.path, "unmeasured", reason, [], None)
                    break
                if not _is_catalog(held) and held is not DEFAULT.get(did):
                    entry = entry._replace(source="own")
        out.append(entry)
    return out


def _percent(coverage):
    """The share as the `rules:` line prints it. Floored, so a file with one rule unmeasured
    never reads 100%; `<1%` when the floor would hide a measured rule."""
    total = sum(v for k, v in coverage.items() if k not in ("share", "catalog"))
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
    matter belongs to the rule file. A file whose front matter gives `detector:` or `opt_out:`
    a value, or cannot be read as a mapping, is one rule, and so is a file with no heading or
    none of whose sections is a rule; a key with no value binds nothing and is a finding.
    Any other file is split into section rules (`_sections`); `root` is the `--rules`
    directory their ids are relative to, the file's own directory when not given.

    A file with no heading, or none of whose sections is a rule, binds the catalog by its
    whole text, text above the first heading included. Known miss: in a file with a rule
    section, text above the first heading is no rule.
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
    if doc is None and all(not line.strip() or line.strip().startswith("#")
                           for line in front.split("\n")):
        doc = {}
    if not isinstance(doc, dict):
        reason = "front matter is not a mapping"
        return [], [RuleEntry(rule, path, "unmeasured", reason, [])], \
            [Finding(path, first_line, reason)]
    named = doc.get("rule")
    findings = []
    opt_out = doc.get("opt_out")
    spec = doc.get("detector", doc.get("detectors"))
    for key in ("detector", "detectors", "opt_out"):
        if key in doc and doc[key] is None:
            findings.append(Finding(path, lines.line_of(doc, key, first_line),
                                    "%s: has no value, so it binds nothing" % key))
    bound = spec is not None or opt_out is not None
    body_line = text.count("\n") - body.count("\n") + 1
    if not bound and "rule" in doc and any(unit[2] for unit in _sections(body)):
        findings.append(Finding(path, lines.line_of(doc, "rule", first_line),
                                "rule: does not apply to a file split at its headings; its "
                                "rules are named by path and heading"))
    elif isinstance(named, str) and named and "/" not in named:
        rule = named
    elif named is not None:
        findings.append(Finding(path, lines.line_of(doc, "rule", first_line),
                                "a rule name is a slash-free string"))
    if spec is not None:
        entries = spec if isinstance(spec, list) else [spec]
        detectors, problems = _compile_entries(entries, path, lines, rule=rule,
                                               default_prefix=rule)
        findings.extend(problems)
        if detectors:
            return detectors, [RuleEntry(rule, path, "measured", "",
                                         [d.id for d in detectors], "own")], findings
        return [], [RuleEntry(rule, path, "unmeasured", "its detector did not compile", [])], \
            findings
    if opt_out is not None:
        reason = opt_out if isinstance(opt_out, str) and opt_out else "no reason given"
        return [], [RuleEntry(rule, path, "dark", reason, [])], findings
    entries, problems = _section_rules(path, root, body, body_line, rule)
    return [], entries, findings + problems


# --- sections -----------------------------------------------------------------------------

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_QUOTE = re.compile(r"^ {0,3}>")
_LIST = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_DELIMITER = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_TEXT = re.compile(r"[^\W_]", re.UNICODE)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_EMPTY_LINK = re.compile(r"\[\s*\]\([^)]*\)")
_LINK_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*\S")
_LINK = re.compile(r"!?\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
_EMPHASIS = re.compile(r"(?<![^\W_])_+|_+(?![^\W_])", re.UNICODE)


def _sections(body):
    """`[(heading text, heading line index, is a rule)]` for a markdown body, in order.

    The split unit is the ATX heading, at any level; a `#` line inside a fenced block or an
    HTML comment is not one, and a setext heading is not split. Text above the first heading
    belongs to no section. A section is a rule when at least one line under its heading has
    a letter or digit outside a fenced or indented code block, an HTML comment, a table and
    a blockquote, and is not only an image or a link reference definition; so a heading with
    nothing under it, or only an example, is not.
    """
    return [unit[:3] for unit in _units(body)]


def _units(body):
    """`_sections` with a fourth item: the section's prose, a list of paragraphs, each list
    item starting one of its own. It is the text lines alone, so nothing a fence, a comment,
    a table or a quote holds is in it."""
    kinds, visible = _kinds_of(body)
    out = []
    for index, kind in enumerate(kinds):
        if kind == "heading":
            text = _HEADING.match(visible[index]).group(2) or ""
            out.append([_CLOSING.sub("", text).strip(), index, False, []])
        elif kind == "text" and out:
            out[-1][2] = True
            _add_prose(out[-1][3], kinds, visible, index)
    return [tuple(s) for s in out]


def _kinds_of(body):
    return _line_kinds(body.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


def _add_prose(paragraphs, kinds, visible, index):
    """Add text line `index` to `paragraphs`: it continues the paragraph above it unless
    the line above is not text or it opens a list item."""
    line = visible[index].strip()
    if index and kinds[index - 1] == "text" and not _LIST.match(line) and paragraphs:
        paragraphs[-1] += " " + line
    else:
        paragraphs.append(line)


def _file_prose(body):
    """Every text line of `body` as paragraphs, headings ignored: the text a file that is
    one rule binds by."""
    kinds, visible = _kinds_of(body)
    paragraphs = []
    for index, kind in enumerate(kinds):
        if kind == "text":
            _add_prose(paragraphs, kinds, visible, index)
    return paragraphs


# --- catalog binding ---------------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
#: The abbreviations a sentence never ends after, however it is punctuated.
_ABBREVIATION = re.compile(r"(?:^|[\s(\[])(?:e\.g|i\.e|etc|vs|cf)\.$", re.IGNORECASE)
#: An exception or a permission. Anywhere in a rule, its heading included, it unbinds every
#: sentence of the rule: "Never force-push to main. Hotfixes excepted." and "Use uv; pip is
#: fine for tools" are not the rules the catalog patterns read, and nor is "Run the tests
#: before finishing. Docs-only changes are exempt." A narrower reach was tried and each
#: markdown shape - a lead-in, a list item of two paragraphs, an abbreviation - carried an
#: exception past it.
_EXCEPTION = re.compile(r"\b(?:except(?:ed|ing|ions?)?|exempt(?:ed|ing|s|ions?)?|unless|other\s+than|"
                        r"apart\s+from|excluding|allowed|fine|okay|ok)\b", re.IGNORECASE)
#: A condition or a contrast. It unbinds only the sentence it is in ("Never force-push to
#: main when others share it"): elsewhere it qualifies another sentence, as "If one fails,
#: fix it." does beside "Run the tests before finishing.", and a file bound by its whole text
#: is full of them.
_CONDITION = re.compile(r"\b(?:if|when|but|however|without)\b", re.IGNORECASE)
#: The catalog's negated exception markers ("admit no exception"), longest first, each in
#: the singular or the plural, and only where the clause ends after it: "without exception
#: approval" names a kind of approval and denies nothing. They are removed before either
#: word list is read.
_CLAUSE_END = r"(?=\s*(?:[.,;:!?)\]\u2013\u2014]|$)|\s+-+(?:\s|$))"
_NEGATED = re.compile(r"\b(?:%s)s?%s" % ("|".join(
    r"\s+".join(re.escape(word) for word in phrase.split())
    for phrase in sorted(_catalog.NEGATED_EXCEPTIONS, key=lambda p: (-len(p), p))),
    _CLAUSE_END), re.IGNORECASE)
_MARKUP = re.compile(r"[`*]+")
_TASK = re.compile(r"^\[[ xX]\][ \t]+")

#: One sentence of a rule as the binder read it: the index of the paragraph it is in (-1
#: for the heading), where it starts in that paragraph's normalized text (`_normalize`), the
#: text, the catalog detectors whose pattern matches its start, in catalog order, and the
#: word that unbinds them, or None.
_Sentence = namedtuple("_Sentence", "paragraph start text detectors marker")


def _normalize(text):
    """A heading or a paragraph as a catalog pattern reads it: a link as its text, a list
    or task marker, code and emphasis markers dropped, a typographic apostrophe made plain,
    and whitespace collapsed."""
    text = _TASK.sub("", _LIST.sub("", text, count=1).lstrip(), count=1)
    text = _EMPHASIS.sub("", _MARKUP.sub("", _LINK.sub(r"\1", text)))
    return " ".join(text.replace("\u2019", "'").split())


def _split(text):
    """`[(start, sentence)]` for normalized `text`. A sentence ends at `.`, `!` or `?`
    followed by a space, but never inside parentheses or after e.g., i.e., etc., vs. or cf.,
    so an aside stays in the sentence it qualifies; an unmatched `(` keeps the rest of the
    text one sentence. An exception reaches the whole rule, so a split never moves one out
    of reach; another abbreviation still splits, which can move a condition word out of the
    rule's sentence and leave it bound - a known over-count."""
    out, start, last, depth = [], 0, 0, 0
    for found in _SENTENCE_END.finditer(text):
        chunk = text[last:found.start()]
        depth = max(0, depth + chunk.count("(") - chunk.count(")"))
        last = found.start()
        if depth or _ABBREVIATION.search(text[max(0, last - 6):last]):
            continue
        out.append((start, text[start:last]))
        start = found.end()
    if text[start:]:
        out.append((start, text[start:]))
    return out


def _pieces(heading, paragraphs):
    """`[(paragraph index, start, sentence)]` for the heading (index -1) and each paragraph."""
    out = []
    for index, text in enumerate([heading] + list(paragraphs)):
        out.extend((index - 1, start, part) for start, part in _split(_normalize(text)))
    return out


def _sentences(heading, paragraphs):
    """The heading and each sentence of `paragraphs`, as a catalog pattern reads them
    (`_normalize`, `_split`)."""
    return [part for _index, _start, part in _pieces(heading, paragraphs)]


def _match(heading, paragraphs):
    """`[_Sentence]`, one per sentence of the rule, heading first. A matching sentence's
    unbinding word is an exception or permission (`_EXCEPTION`) anywhere in the rule, else a
    condition (`_CONDITION`) in the sentence itself. A negated marker such as "no exceptions"
    at the end of a clause is never one. Binding reads text and nothing else, against the
    shipped fold map: a consumer's own renames are applied when `Bundle.registry` is built."""
    pieces = _pieces(heading, paragraphs)
    plain = [_NEGATED.sub(" ", part) for _index, _start, part in pieces]
    granted = next((found for found in map(_EXCEPTION.search, plain) if found), None)
    retired = fold_map()
    live = [(pattern, detector) for pattern, detector in _CATALOG
            if detector.id not in retired]
    out = []
    for n, (index, start, part) in enumerate(pieces):
        matched = [detector for pattern, detector in live if pattern.match(part)]
        found = (granted or _CONDITION.search(plain[n])) if matched else None
        out.append(_Sentence(index, start, part, matched,
                             found.group(0).lower() if found else None))
    return out


def _binds(matches):
    """`[(sentence, detector)]` for each of `_match`'s sentences that binds: it matches
    exactly one entry and no word unbinds it."""
    return [(s, s.detectors[0]) for s in matches if len(s.detectors) == 1 and not s.marker]


def _bound(matches):
    """The detectors `_match`'s sentences bind (`_binds`), in catalog order, once each."""
    ids = set(detector.id for _sentence, detector in _binds(matches))
    return [detector for _pattern, detector in _CATALOG if detector.id in ids]


def _catalog_matches(heading, paragraphs):
    """The catalog detectors a rule binds to, one or more per sentence (`_match`)."""
    return _bound(_match(heading, paragraphs))


def _bind(rule, path, heading, paragraphs, reason=""):
    """A rule's entry (`_binding`)."""
    return _binding(rule, path, heading, paragraphs, reason)[0]


def _binding(rule, path, heading, paragraphs, reason=""):
    """`(entry, [(sentence, detector id)])`: the rule's entry, and the sentences that bound
    the detectors it lists, which `ruleprobe corpus` scores line by line. The entry is
    measured and catalog-bound to every detector a sentence binds, in catalog order, when at
    least one does. Else it is unmeasured, naming the word that unbound a matching sentence,
    or else the entries a sentence matched together, or else `reason`, and lists none."""
    matches = _match(heading, paragraphs)
    bound = _bound(matches)
    if bound:
        return (RuleEntry(rule, path, "measured", "", [d.id for d in bound], "catalog"),
                [(sentence, detector.id) for sentence, detector in _binds(matches)])
    for sentence in matches:
        if sentence.detectors and sentence.marker:
            return RuleEntry(rule, path, "unmeasured",
                             "a catalog shape with an exception or condition (%s)"
                             % sentence.marker, []), []
    for sentence in matches:
        if len(sentence.detectors) > 1:
            return RuleEntry(rule, path, "unmeasured", "matches %d catalog entries: %s"
                             % (len(sentence.detectors),
                                ", ".join(d.id for d in sentence.detectors)), []), []
    return RuleEntry(rule, path, "unmeasured", reason, []), []


def _uncomment(line, open_comment):
    """`(the line outside HTML comments, whether a comment is still open at its end)`."""
    kept, rest = [], line
    while rest:
        if open_comment:
            end = rest.find("-->")
            if end < 0:
                return "".join(kept), True
            rest, open_comment = rest[end + 3:], False
        else:
            start = rest.find("<!--")
            if start < 0:
                kept.append(rest)
                break
            kept.append(rest[:start])
            rest, open_comment = rest[start + 4:], True
    return "".join(kept), open_comment


def _line_kinds(lines):
    """`(kinds, visible lines)`: each line's kind, one of `heading`, `fence`, `comment`,
    `code`, `table`, `quote`, `blank` or `text`, and the line with HTML comments removed.

    An indented code block starts after a blank line, a heading, a closed fence or a
    comment, so an indented list continuation after one is read as code too: an
    under-count, never a false rule."""
    kinds, visible, fence, comment = [], [], None, False
    for line in lines:
        if fence:
            kinds.append("fence")
            visible.append(line)
            closing = _FENCE.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= \
                    len(fence) and not closing.group(2).strip():
                fence = None
            continue
        was_open = comment
        shown, comment = _uncomment(line, comment)
        visible.append(shown)
        opening = _FENCE.match(shown) if not was_open else None
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = opening.group(1)
            kinds.append("fence")
        elif shown != line and not _TEXT.search(shown):
            kinds.append("comment")
        elif shown.strip() and _indent(shown) >= 4 and \
                (not kinds or kinds[-1] in ("blank", "heading", "code", "fence", "comment")):
            kinds.append("code")
        elif _HEADING.match(shown):
            kinds.append("heading")
        elif not shown.strip():
            kinds.append("blank")
        elif _QUOTE.match(shown) or \
                (kinds and kinds[-1] == "quote" and not _LIST.match(shown)):
            kinds.append("quote")
        elif shown.lstrip(" ").startswith("|"):
            kinds.append("table")
        elif _LINK_DEFINITION.match(shown) or _only_images(shown):
            kinds.append("blank")
        elif _TEXT.search(shown):
            kinds.append("text")
        else:
            kinds.append("blank")
    for index, line in enumerate(visible):
        # A pipe table without leading pipes: a header row, its delimiter row, and the rows
        # under it up to the first line without a pipe.
        if kinds[index] in ("text", "blank") and "|" in line and "-" in line and \
                _DELIMITER.match(line) and index and kinds[index - 1] == "text" and \
                "|" in visible[index - 1]:
            kinds[index - 1] = kinds[index] = "table"
            below = index + 1
            while below < len(visible) and kinds[below] == "text" and "|" in visible[below]:
                kinds[below] = "table"
                below += 1
    return kinds, visible


def _only_images(line):
    """True for a line of images and nothing else, a badge row or a linked image included."""
    if not _IMAGE.search(line):
        return False
    return not _EMPTY_LINK.sub("", _IMAGE.sub("", line)).strip()


def _indent(line):
    stripped = line.lstrip(" \t")
    return len(line[:len(line) - len(stripped)].expandtabs(4))


def _slug(heading):
    """A heading's anchor: a link's text without its target, emphasis markers and other
    punctuation dropped, lower case, each space a hyphen; `section` when nothing is left,
    as for a heading of only punctuation or emoji."""
    text = _EMPHASIS.sub("", _LINK.sub(r"\1", heading))
    kept = re.sub(r"[^\w\- ]", "", text.strip().lower(), flags=re.UNICODE).strip()
    return kept.replace(" ", "-") or "section"


def _section_rules(path, root, body, first_line, name):
    """One `RuleEntry` per section of `body` that is a rule, with its id, bound to the
    catalog entry each of its sentences binds (`_bind`) and unmeasured when none does; or,
    when `body` has no heading or none of its sections is a rule, one rule called `name`, as
    the file always was, so that no file drops out of the coverage block; its whole text binds
    the catalog as one unit.

    A headed file takes section ids even when it has one section, so that an id does not
    change when a section is added below. A slug repeated in the file takes an ordinal
    suffix in document order (`testing`, `testing-2`), counted over every heading so that a
    section's id does not move when a section above it stops or starts being a rule. A rule
    id that still repeats, as when a later heading's own text is `Testing 2`, is a finding
    against that heading's line, and both rules are still listed.
    """
    relative = os.path.relpath(path, root or os.path.dirname(path)).replace(os.sep, "/")
    units = _units(body)
    if not units:
        return [_bind(name, path, "", _file_prose(body))], []
    entries, findings, seen, taken = [], [], {}, set()
    for heading, index, is_rule, paragraphs in units:
        base = _slug(heading)
        seen[base] = seen.get(base, 0) + 1
        anchor = base if seen[base] == 1 else "%s-%d" % (base, seen[base])
        rule = "%s#%s" % (relative, anchor)
        if not is_rule:
            continue
        if rule in taken:
            findings.append(Finding(path, first_line + index,
                                    "the section id %s is already taken in this file" % rule))
        taken.add(rule)
        entries.append(_bind(rule, path, heading, paragraphs))
    if not entries:
        return [_bind(name, path, "", _file_prose(body), "no section is a rule")], findings
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
    # A detector of the user's that takes a catalog id replaces the catalog one, so a rule
    # bound to that id is the user's own. The bound catalog detectors lead `detectors`, so a
    # consumer building from `DEFAULT` plus `detectors` measures what the rules say is
    # measured; one `DEFAULT` already holds is left to it.
    own = set(d.id for d in bundle.detectors)
    bundle.rules = [entry._replace(source="own")
                    if entry.source == "catalog" and own.intersection(entry.detectors)
                    else entry for entry in bundle.rules]
    bound = set(did for entry in bundle.rules if entry.source == "catalog"
                for did in entry.detectors)
    bundle.detectors[:0] = [d for d in catalog_detectors()
                            if d.id in bound and d.id not in DEFAULT]
    return bundle
