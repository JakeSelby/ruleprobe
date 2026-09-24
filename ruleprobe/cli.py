# SPDX-License-Identifier: MIT
"""`ruleprobe` on the command line.

    ruleprobe report [--by rule|repo|stance] [--since DATE] [--root DIR] [--runtime NAME]
                     [--stance DIM=VARIANT] [--rules DIR] [--detectors FILE] [--no-config]
                     [--validity] [--json]
    ruleprobe detectors [--rules DIR] [--detectors FILE] [--no-config]
    ruleprobe corpus [--floor F] [--json] [--corpus DIR] [--rules DIR] [--detectors FILE]
    ruleprobe explain [--session RUNTIME:ID] [--detector ID] [--key TURN:TOOL_USE_ID]
                      [--since DATE] [--root DIR] [--runtime NAME]
                      [--stance DIM=VARIANT] [--plugins]
                      [--rules DIR] [--detectors FILE] [--no-config]
    ruleprobe label --session RUNTIME:ID --detector ID --key TURN:TOOL_USE_ID
                    --corpus DIR --name NAME
                    [--since DATE] [--root DIR] [--runtime NAME]
                    [--stance DIM=VARIANT] [--plugins]
                    [--rules DIR] [--detectors FILE] [--no-config]

Declarative detectors are read from `.ruleprobe/detectors.yaml` in the repository you are
in and from `~/.config/ruleprobe/detectors.yaml`, unless `--no-config` says otherwise;
`--rules <dir>` also reads a directory of markdown rule files, and reports which of them
nothing measures.

Nothing leaves the machine, and every command but `label` writes nothing: the transcripts are
read, the detectors are run over them in memory, and a table is printed. `label` writes one
event-schema session and one `near` label, redacted, under the corpus directory it is given,
and nowhere else; `cmd_label` says what it refuses.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

from . import __version__
from .declarative import DeclarativeError, emit, load, parse
from .detectors.common import REDACTED, SECRET_PATTERNS, redact
from .readers import RUNTIMES, iter_sessions
from .registry import DEFAULT, Registry, run
from .report import (BY, RULE_MIN_OPPORTUNITIES, RULE_MIN_SESSIONS, RULE_FREQUENT_SHARE,
                     _redact, explain, explain_text, measure, report, report_data,
                     session_address)
from .rules import load_bundle
from .validity import (EVENTS_SUFFIX, LABELS_FILE, SESSIONS_DIRNAME, CorpusError,
                       DEFAULT_FLOOR, below_floor, event_key, hit_key, load_corpus,
                       read_events, score_corpus, scores_as_dict, validity, validity_table)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ruleprobe",
        description="Find out which of your agent rules actually fire.")
    parser.add_argument("--version", action="version", version="ruleprobe " + __version__)
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("report", help="count detector hits over your transcripts")
    run_cmd.add_argument("--by", choices=list(BY), default="rule",
                         help="group by detector (default), by repository, or by stance")
    run_cmd.add_argument("--since", default=None, metavar="DATE", type=_since,
                         help="a YYYY-MM-DD date, or a number of days back")
    run_cmd.add_argument("--stance", action="append", default=None, type=_stance,
                         metavar="DIM=VARIANT",
                         help="the configuration these sessions ran under, e.g. "
                              "--stance commits=conventional; repeatable, read by gated "
                              "detectors and by --by stance")
    run_cmd.add_argument("--root", default=None, metavar="DIR",
                         help="a directory of transcripts to read instead of the defaults")
    run_cmd.add_argument("--runtime", choices=["auto"] + sorted(RUNTIMES), default="auto",
                         help="which runtime wrote them (default: decide per file)")
    run_cmd.add_argument("--min-sessions", type=int, default=RULE_MIN_SESSIONS,
                         metavar="N", help="sessions needed before a note is printed")
    run_cmd.add_argument("--frequent-share", type=float, default=RULE_FREQUENT_SHARE,
                         metavar="F", help="share of sessions that earns a frequent note")
    run_cmd.add_argument("--min-opportunities", type=int, default=RULE_MIN_OPPORTUNITIES,
                         metavar="N", help="opportunities needed in a line or group before a "
                                           "compliance rate is printed")
    run_cmd.add_argument("--plugins", action="store_true",
                         help="also load detectors installed packages advertise")
    run_cmd.add_argument("--json", action="store_true",
                         help="print the report as JSON - the same denominators, folds "
                              "and notes as the table, plus the rows")
    run_cmd.add_argument("--validity", action="store_true",
                         help="add each detector's precision and recall over the corpus")

    _declarative_options(run_cmd)
    _declarative_options(sub.add_parser("detectors",
                                        help="list the detectors that would run"))

    corpus_cmd = sub.add_parser(
        "corpus", help="score every detector against the labelled corpus")
    corpus_cmd.add_argument("--floor", type=float, default=DEFAULT_FLOOR, metavar="F",
                            help="exit non-zero when a scored detector's precision or "
                                 "recall is under this (default: %.2f)" % DEFAULT_FLOOR)
    corpus_cmd.add_argument("--corpus", default=None, metavar="DIR",
                            help="a corpus directory of your own; the shipped one by "
                                 "default, or $RULEPROBE_CORPUS")
    corpus_cmd.add_argument("--json", action="store_true",
                            help="print the scores as JSON instead of a table")
    _declarative_options(corpus_cmd)

    explain_cmd = sub.add_parser(
        "explain", help="print the session, key, detector and event behind every hit")
    explain_cmd.add_argument("--session", default=None, metavar="RUNTIME:ID",
                             help="only this session: its address as explain prints it, "
                                  "or its bare id")
    explain_cmd.add_argument("--detector", default=None, metavar="ID",
                             help="only this detector's hits")
    explain_cmd.add_argument("--key", default=None, metavar="TURN:TOOL_USE_ID",
                             help="only the hit at this key, e.g. 3:toolu_01 or 3:-")
    explain_cmd.add_argument("--since", default=None, metavar="DATE", type=_since,
                             help="a YYYY-MM-DD date, or a number of days back")
    explain_cmd.add_argument("--root", default=None, metavar="DIR",
                             help="a directory of transcripts to read instead of the "
                                  "defaults")
    explain_cmd.add_argument("--runtime", choices=["auto"] + sorted(RUNTIMES),
                             default="auto",
                             help="which runtime wrote them (default: decide per file)")
    explain_cmd.add_argument("--stance", action="append", default=None, type=_stance,
                             metavar="DIM=VARIANT",
                             help="the configuration these sessions ran under, as for "
                                  "report; repeatable, read by gated detectors")
    explain_cmd.add_argument("--plugins", action="store_true",
                             help="also load detectors installed packages advertise")
    _declarative_options(explain_cmd)

    label_cmd = sub.add_parser(
        "label", help="record one wrong hit as a labelled negative in a corpus of your own")
    label_cmd.add_argument("--session", required=True, metavar="RUNTIME:ID",
                           help="the session, as explain prints its address")
    label_cmd.add_argument("--detector", required=True, metavar="ID",
                           help="the detector whose hit is wrong")
    label_cmd.add_argument("--key", required=True, metavar="TURN:TOOL_USE_ID",
                           help="the hit's key, as explain prints it; a session hit "
                                "(TURN:-) is refused")
    label_cmd.add_argument("--corpus", required=True, metavar="DIR",
                           help="an existing corpus directory of your own; nothing is "
                                "written outside it")
    label_cmd.add_argument("--name", required=True, metavar="NAME",
                           help="the new session's file stem: DIR/sessions/"
                                "NAME.events.jsonl")
    label_cmd.add_argument("--since", default=None, metavar="DATE", type=_since,
                           help="a YYYY-MM-DD date, or a number of days back")
    label_cmd.add_argument("--root", default=None, metavar="DIR",
                           help="a directory of transcripts to read instead of the "
                                "defaults")
    label_cmd.add_argument("--runtime", choices=["auto"] + sorted(RUNTIMES),
                           default="auto",
                           help="which runtime wrote them (default: decide per file)")
    label_cmd.add_argument("--stance", action="append", default=None, type=_stance,
                           metavar="DIM=VARIANT",
                           help="the configuration these sessions ran under, as for "
                                "report; repeatable, read by gated detectors")
    label_cmd.add_argument("--plugins", action="store_true",
                           help="also load detectors installed packages advertise")
    _declarative_options(label_cmd)
    return parser


def _declarative_options(parser):
    """The options that say where declarative detectors come from. Both subcommands take
    them, so `ruleprobe detectors --rules docs/rules` answers "what would measure this?"
    without running anything over a transcript."""
    parser.add_argument("--rules", default=None, metavar="DIR",
                        help="a directory of markdown rule files to bind detectors to")
    parser.add_argument("--detectors", action="append", default=None, metavar="FILE",
                        help="a detector file to load; repeatable")
    parser.add_argument("--no-config", action="store_true",
                        help="do not read .ruleprobe/detectors.yaml or the user's file")


def _since(value):
    """`--since` as a number of days or a `YYYY-MM-DD` string.

    A bare four-digit number is refused rather than read as a number of days: `--since 2024`
    is somebody asking for a year, and answering it with 2024 days back is a window five and
    a half years wide that nobody was told about.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        if len(text) > 3:
            raise argparse.ArgumentTypeError(
                "%r is neither a date nor a plausible number of days back; write a date as "
                "YYYY-MM-DD, or a number of days under 1000" % text)
        return int(text)
    if not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        raise argparse.ArgumentTypeError(
            "%r is not a date; write YYYY-MM-DD, or a number of days back" % text)
    return text


def _stance(value):
    """One `--stance dimension=variant` pair. A gated detector reads these, and `--by
    stance` groups on them; without one, a `gate:` block is a detector that never fires."""
    text = str(value)
    dimension, _sep, variant = text.partition("=")
    if not _sep or not dimension.strip() or not variant.strip():
        raise argparse.ArgumentTypeError(
            "a stance is dimension=variant, e.g. commits=conventional, not %r" % text)
    return (dimension.strip(), variant.strip())


def _gate_note(detector):
    """What `ruleprobe detectors` says about a gate. It names the dimension, because a
    detector listed as "gated" with nothing to gate on is one that never fires and never
    says why: `--stance <dimension>=<variant>` is the thing the reader has to supply."""
    gate = detector.gate
    if gate is None:
        return ""
    if callable(gate):
        return "gated (a callable)"
    dimension, variants = gate
    if not variants:
        return "gated on --stance %s=<variant>" % dimension
    return "gated on --stance %s=%s" % (dimension, "|".join(variants))


def _bundle_and_registry(args, plugins=None):
    """The declarative bundle for this invocation, and the registry to run: the shipped
    detectors, plus plugins when asked, plus everything the bundle loaded."""
    bundle = load_bundle(paths=args.detectors, rules_dir=args.rules,
                         config=not args.no_config)
    if plugins is None:
        plugins = getattr(args, "plugins", False)
    base = Registry.from_entry_points() if plugins else DEFAULT
    return bundle, bundle.registry(base)


def _read_errors_line(errors):
    """What to say about the transcripts that never became a row. A swallowed per-item
    error is unknown, not absent, so the count is printed even when every row is fine."""
    if not errors:
        return ""
    named = ", ".join("%s (%s)" % (os.path.basename(e["path"]), e["error"])
                      for e in errors[:3])
    more = "" if len(errors) <= 3 else ", and %d more" % (len(errors) - 3)
    return "%d transcript(s) produced no session: %s%s" % (len(errors), named, more)


def cmd_report(args, out):
    bundle, registry = _bundle_and_registry(args)
    stances = dict(args.stance or [])
    read_errors = []
    rows = [measure(session, stances=stances, registry=registry)
            for session in iter_sessions(root=args.root, runtime=args.runtime,
                                         since=args.since, errors=read_errors)]
    unread = _read_errors_line(read_errors)
    if unread:
        sys.stderr.write(unread + "\n")
    scores = None
    if args.validity:
        try:
            scores = validity(registry=registry)
        except CorpusError as exc:
            sys.stderr.write("corpus: %s\n" % exc)
            return 2
    if args.json:
        # The same numbers the table prints, through the same function: a denominator, a
        # rename fold or a min_sessions note that the two disagreed about would make the
        # machine-readable half a second, quieter instrument.
        data = report_data(rows, by=args.by, min_sessions=args.min_sessions,
                           frequent_share=args.frequent_share, registry=registry,
                           validity=scores, min_opportunities=args.min_opportunities)
        data["rows"] = rows
        data["read_errors"] = read_errors
        data["coverage"] = bundle.coverage()
        summary = bundle.summary()
        if summary:
            sys.stderr.write(summary + "\n")
        out.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
        return 0 if rows else 1
    if not rows:
        out.write("no transcripts found; pass --root to point at a directory of them\n")
        return 1
    out.write(report(rows, by=args.by, min_sessions=args.min_sessions,
                     frequent_share=args.frequent_share, registry=registry,
                     validity=scores, min_opportunities=args.min_opportunities) + "\n")
    summary = bundle.summary()
    if summary:
        out.write("\n" + summary + "\n")
    return 0


def cmd_corpus(args, out):
    """Every detector over the labelled corpus, and the floor as an exit code.

    The floor is this repository's CI gate, not a runtime failure for a user: nothing in
    `ruleprobe report` reads it, and a detector nobody labelled is passed over rather than
    failed.
    """
    bundle, registry = _bundle_and_registry(args)
    try:
        scores = validity(registry=registry, directory=args.corpus)
    except CorpusError as exc:
        sys.stderr.write("corpus: %s\n" % exc)
        return 2
    failed = below_floor(scores, args.floor)
    if args.json:
        out.write(json.dumps(scores_as_dict(scores, args.floor), indent=2,
                             sort_keys=True) + "\n")
        return 1 if failed else 0
    out.write(validity_table(scores, args.floor) + "\n")
    summary = bundle.summary()
    if summary:
        out.write("\n" + summary + "\n")
    if failed:
        out.write("\n%d detector(s) under the %.2f floor: %s\n"
                  % (len(failed), args.floor, ", ".join(failed)))
        return 1
    return 0


def cmd_detectors(args, out):
    bundle, registry = _bundle_and_registry(args, plugins=True)
    for detector in registry:
        out.write("%-40s%-20s%s\n" % (detector.id, detector.event, _gate_note(detector)))
    summary = bundle.summary()
    if summary:
        out.write("\n" + summary + "\n")
    return 0


def cmd_explain(args, out):
    """Every hit, with the event behind it, redacted. It reruns the detectors over the
    transcripts rather than reading rows, because a row keeps counts only. Every line it
    writes, to either stream, passes through `report._redact`."""
    bundle, registry = _bundle_and_registry(args)
    stances = dict(args.stance or [])
    detector = args.detector
    if detector is not None:
        detector = registry.renamed.get(detector, detector)
    read_errors, detector_errors, seen = [], [], [0]

    def counted():
        # Streamed: a session's events are held only while its hits are printed.
        for session in iter_sessions(root=args.root, runtime=args.runtime,
                                     since=args.since, errors=read_errors):
            seen[0] += 1
            yield session

    wrote = False
    # The filters are applied inside `explain`, to the values before redaction.
    for item in explain(counted(), stances=stances, registry=registry,
                        errors=detector_errors, session=args.session, detector=detector,
                        key=args.key):
        out.write(("\n" if wrote else "") + explain_text(item) + "\n")
        wrote = True
    unread = _read_errors_line(read_errors)
    if unread:
        sys.stderr.write(_redact(unread) + "\n")
    summary = bundle.summary()
    if summary:
        sys.stderr.write(_redact(summary) + "\n")
    if not seen[0]:
        out.write(_redact("no transcripts found; pass --root to point at a directory of "
                          "them") + "\n")
        return 1
    if detector_errors:
        more = "" if len(detector_errors) <= 3 else ", and %d more" % (len(detector_errors) - 3)
        sys.stderr.write(_redact("%d detector error(s): %s%s" % (
            len(detector_errors), ", ".join("%s (%s) in %s" % (e["detector"], e["error"],
                                                              e["session"])
                                            for e in detector_errors[:3]), more)) + "\n")
    return 0


class _Refused(Exception):
    """Why `label` wrote nothing."""


def cmd_label(args, out):
    """One wrong hit as a labelled negative: `DIR/sessions/NAME.events.jsonl` holding the
    event behind it, redacted, and one `near` entry for it in `DIR/labels.yaml`.

    It refuses, says why on stderr and exits 2, leaving every file as it found it, for a
    session hit, which one event cannot reproduce; a name that is not a plain file stem; a
    corpus directory that does not exist; a session file that already exists or is already
    labelled; no session, or more than one, at the address; no hit at the key, or not one
    event behind it; a detector that is gated, since the corpus runs no stances; a written
    event the detector no longer hits, because redaction changed what it matched or the hit
    needs more than one event, since that negative would pass trivially; any secret shape
    left in the bytes it would write; and a `labels.yaml` it cannot append to and read back
    as the old document plus the one entry. The corpus is read back after writing, and
    anything short of the new negative scoring is rolled back.
    """
    try:
        lines = _label(args)
    except _Refused as exc:
        sys.stderr.write(_redact("label: refused: %s" % exc) + "\n")
        return 2
    for line in lines:
        out.write(_redact(line) + "\n")
    return 0


def _label(args):
    name = _label_name(args.name)
    key = args.key
    if key.endswith(":-"):
        raise _Refused("%s is a session hit; one event cannot reproduce a hit that names no "
                       "tool use, such as an absent or order hit" % key)
    base = os.path.abspath(os.path.expanduser(args.corpus))
    if not os.path.isdir(base):
        raise _Refused("%s is not a directory; label writes only into a corpus directory "
                       "that exists" % base)
    sessions_dir = os.path.join(base, SESSIONS_DIRNAME)
    labels_path = os.path.join(base, LABELS_FILE)
    for path, kind in ((sessions_dir, os.path.isdir), (labels_path, os.path.isfile)):
        # A link could point outside the directory the user named.
        if os.path.islink(path) or (os.path.lexists(path) and not kind(path)):
            raise _Refused("%s is a link or not a plain %s" % (
                path, "directory" if kind is os.path.isdir else "file"))
    file_name = name + EVENTS_SUFFIX
    events_path = os.path.join(sessions_dir, file_name)
    if os.path.lexists(events_path):
        raise _Refused("%s already exists" % events_path)

    _bundle, registry = _bundle_and_registry(args)
    detector_id = registry.fold_map().get(args.detector, args.detector)
    detector = registry.get(detector_id)
    if detector is None:
        raise _Refused("no detector %s is loaded" % args.detector)
    if not detector.enabled(None):
        raise _Refused("%s is gated on a stance and the corpus runs with none, so a negative "
                       "for it would pass trivially" % detector_id)
    only = Registry([detector])
    event = _labelled_event(args, only, detector_id, key)

    written = _redacted_event(event)
    line = json.dumps(written, sort_keys=True, ensure_ascii=True) + "\n"
    loaded = read_events(line, events_path)
    if event_key(loaded[0]) != key:
        raise _Refused("redaction changed the event's key, so the label could not name it")
    if key not in _hit_keys(loaded, only, detector_id):
        if key in _hit_keys([event], only, detector_id):
            raise _Refused("redaction changed what %s matched at %s: the written event no "
                           "longer hits, so the negative would pass trivially"
                           % (detector_id, key))
        raise _Refused("%s does not hit at %s on that event alone: the hit needs events "
                       "around it, which one event cannot carry" % (detector_id, key))

    entry = {"session": file_name, "labels": [{"at": key, "near": [detector_id]}]}
    original, addition = _labels_addition(labels_path, entry)
    for text in (line, addition):
        if redact(text) != text or any(re.search(p, text) for p in SECRET_PATTERNS):
            raise _Refused("a secret shape would survive into the written bytes; nothing "
                           "was written")

    _write_label(base, sessions_dir, events_path, labels_path, line, original, addition,
                 registry, detector_id, file_name)
    return ["wrote %s (1 event)" % events_path,
            "%s %s: near %s at %s" % ("appended to" if original is not None else "created",
                                      labels_path, detector_id, key),
            "score it with: ruleprobe corpus --corpus %s" % base]


def _label_name(name):
    """`name` when it is a plain file stem, so nothing is written outside the directory."""
    seps = [os.sep] + ([os.altsep] if os.altsep else []) + ["/", "\\"]
    if not name or name.startswith(".") or ".." in name or any(s in name for s in seps) \
            or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in name):
        raise _Refused("--name %r is not a plain file stem: no separator, no '..', no "
                       "leading dot, not empty" % name)
    return name


def _labelled_event(args, registry, detector_id, key):
    """The one event behind `detector_id`'s hit at `key` in the one session at the address,
    rerun from the transcripts."""
    read_errors, found, matches = [], None, 0
    for session in iter_sessions(root=args.root, runtime=args.runtime, since=args.since,
                                 errors=read_errors):
        if session_address(session.runtime, session.id) != args.session:
            continue
        matches += 1
        if found is None:
            found = session
    if not matches:
        unread = _read_errors_line(read_errors)
        raise _Refused("no session %s among the transcripts read%s"
                       % (args.session, "; " + unread if unread else ""))
    if matches > 1:
        raise _Refused("%d sessions are at %s; narrow --root or --runtime to one"
                       % (matches, args.session))
    stances = dict(args.stance or [])
    if key not in _hit_keys(found.events, registry, detector_id, stances):
        raise _Refused("%s has no hit at %s in %s; ruleprobe explain lists its hits"
                       % (detector_id, key, args.session))
    events = [e for e in found.events if isinstance(e, dict) and e.get("kind") == "tool_use"
              and event_key(e) == key]
    if len(events) != 1:
        raise _Refused("%s is %s event in %s" % (
            key, "not an" if not events else "more than one", args.session))
    return events[0]


def _hit_keys(events, registry, detector_id, stances=None):
    return [hit_key(h) for h in run(events, stances, registry=registry,
                                    errors=[]).get(detector_id, [])]


def _redacted_event(value):
    """`value` with every string through `redact`. A mapping key that is, or is named like,
    a secret becomes `REDACTED` and so does its whole value, since the value was redacted
    apart from the name that marked it."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redacted_event(item) for item in value]
    if isinstance(value, dict):
        out = {}
        for name, item in value.items():
            name = name if isinstance(name, str) else str(name)
            assigned = "%s: v" % name
            if redact(name) != name or redact(assigned) != assigned:
                out[REDACTED] = REDACTED
            else:
                out[name] = _redacted_event(item)
        return out
    return value


def _labels_addition(labels_path, entry):
    """`(the original bytes or None, the text to append or create)`, refusing anything that
    would not read back as the old document plus `entry`."""
    if not os.path.lexists(labels_path):
        return None, emit({"version": 1, "sessions": [entry]})
    try:
        with open(labels_path, "rb") as handle:
            original = handle.read()
        text = original.decode("utf-8")
        document, _lines = load(labels_path)
    except (OSError, UnicodeDecodeError, DeclarativeError) as exc:
        raise _Refused("cannot read %s: %s" % (labels_path, exc))
    if not isinstance(document, dict) or not isinstance(document.get("sessions"), list):
        raise _Refused("%s is not a mapping with a sessions list" % labels_path)
    if list(document)[-1] != "sessions":
        raise _Refused("sessions is not the last key in %s, so an entry cannot be appended"
                       % labels_path)
    if any(isinstance(e, dict) and e.get("session") == entry["session"]
           for e in document["sessions"]):
        raise _Refused("%s already names %s" % (labels_path, entry["session"]))
    indent = _item_indent(text)
    try:
        addition = emit([entry], indent)
    except DeclarativeError as exc:
        raise _Refused("the label cannot be written in the YAML subset: %s" % exc.reason)
    if text and not text.endswith("\n"):
        addition = "\n" + addition
    expected = dict(document, sessions=document["sessions"] + [entry])
    try:
        same = parse(text + addition) == expected
    except DeclarativeError:
        same = False
    if not same:
        raise _Refused("appending to %s would not read back as the old document plus one "
                       "entry" % labels_path)
    return original, addition


def _item_indent(text):
    """The indentation of the entries under the top-level `sessions:`, or 2 for none."""
    lines = text.replace("\r\n", "\n").split("\n")
    for i, raw in enumerate(lines):
        if re.match(r"^sessions\s*:", raw):
            for later in lines[i + 1:]:
                stripped = later.strip()
                if stripped and not stripped.startswith("#"):
                    found = re.match(r"^( *)-(?: |$)", later)
                    return len(found.group(1)) if found else 2
    return 2


def _write_label(base, sessions_dir, events_path, labels_path, line, original, addition,
                 registry, detector_id, file_name):
    """Both writes, then the corpus read back; any failure removes what was written and
    restores `labels.yaml` byte for byte."""
    made_dir = wrote_events = wrote_labels = False
    try:
        if not os.path.isdir(sessions_dir):
            os.mkdir(sessions_dir)
            made_dir = True
        handle = os.fdopen(os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                   0o644), "w", encoding="utf-8", newline="\n")
        wrote_events = True
        with handle:
            handle.write(line)
        if original is None:
            with open(labels_path, "x", encoding="utf-8", newline="\n") as labels:
                wrote_labels = True
                labels.write(addition)
        else:
            with open(labels_path, "ab") as labels:
                wrote_labels = True
                labels.write(addition.encode("utf-8"))
        labelled = [one for one in load_corpus(base) if one.name == file_name]
        score = score_corpus(registry, corpus=labelled)[detector_id]
        if (score.negatives, score.fp) != (1, 1):
            raise _Refused("the corpus read back did not score the new negative")
    except BaseException as exc:
        if wrote_labels:
            if original is None:
                _quietly(os.remove, labels_path)
            else:
                with open(labels_path, "wb") as labels:
                    labels.write(original)
        if wrote_events:
            _quietly(os.remove, events_path)
        if made_dir:
            _quietly(os.rmdir, sessions_dir)
        if isinstance(exc, _Refused):
            raise
        if isinstance(exc, (OSError, CorpusError)):
            raise _Refused("%s; nothing was kept" % exc)
        if isinstance(exc, Exception):
            raise _Refused("a detector raised %s over the written corpus; nothing was kept"
                           % type(exc).__name__)
        raise


def _quietly(remove, path):
    try:
        remove(path)
    except OSError:
        pass


def main(argv=None, out=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = sys.stdout if out is None else out
    if args.command == "report":
        return cmd_report(args, out)
    if args.command == "detectors":
        return cmd_detectors(args, out)
    if args.command == "corpus":
        return cmd_corpus(args, out)
    if args.command == "explain":
        return cmd_explain(args, out)
    if args.command == "label":
        return cmd_label(args, out)
    parser.print_help(out)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
