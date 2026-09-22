# SPDX-License-Identifier: MIT
"""`ruleprobe` on the command line.

    ruleprobe report [--by rule|repo|stance] [--since DATE] [--root DIR] [--runtime NAME]
                     [--rules DIR] [--detectors FILE] [--no-config] [--validity]
    ruleprobe detectors [--rules DIR] [--detectors FILE] [--no-config]
    ruleprobe corpus [--floor F] [--json] [--corpus DIR] [--rules DIR] [--detectors FILE]

Declarative detectors are read from `.ruleprobe/detectors.yaml` in the repository you are
in and from `~/.config/ruleprobe/detectors.yaml`, unless `--no-config` says otherwise;
`--rules <dir>` also reads a directory of markdown rule files, and reports which of them
nothing measures.

Nothing is written anywhere and nothing leaves the machine: the transcripts are read, the
detectors are run over them in memory, and a table is printed.
"""
import argparse
import json
import os
import sys

from . import __version__
from .readers import RUNTIMES, iter_sessions
from .registry import DEFAULT, Registry
from .report import BY, RULE_MIN_SESSIONS, RULE_PROMOTE_SHARE, measure, report
from .rules import load_bundle
from .validity import (CorpusError, DEFAULT_FLOOR, below_floor, scores_as_dict, validity,
                       validity_table)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ruleprobe",
        description="Find out which of your agent rules actually fire.")
    parser.add_argument("--version", action="version", version="ruleprobe " + __version__)
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("report", help="count detector hits over your transcripts")
    run_cmd.add_argument("--by", choices=list(BY), default="rule",
                         help="group by detector (default), by repository, or by stance")
    run_cmd.add_argument("--since", default=None, metavar="DATE",
                         help="a YYYY-MM-DD date, or a number of days back")
    run_cmd.add_argument("--root", default=None, metavar="DIR",
                         help="a directory of transcripts to read instead of the defaults")
    run_cmd.add_argument("--runtime", choices=["auto"] + sorted(RUNTIMES), default="auto",
                         help="which runtime wrote them (default: decide per file)")
    run_cmd.add_argument("--min-sessions", type=int, default=RULE_MIN_SESSIONS,
                         metavar="N", help="sessions needed before a note is printed")
    run_cmd.add_argument("--promote-share", type=float, default=RULE_PROMOTE_SHARE,
                         metavar="F", help="share of sessions that earns a promote? note")
    run_cmd.add_argument("--plugins", action="store_true",
                         help="also load detectors installed packages advertise")
    run_cmd.add_argument("--json", action="store_true",
                         help="print the measured rows as JSON instead of a table")
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
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text.isdigit() and len(text) <= 4 else text


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
    read_errors = []
    rows = [measure(session, registry=registry)
            for session in iter_sessions(root=args.root, runtime=args.runtime,
                                         since=_since(args.since), errors=read_errors)]
    unread = _read_errors_line(read_errors)
    if unread:
        sys.stderr.write(unread + "\n")
    if args.json:
        summary = bundle.summary()
        if summary:
            sys.stderr.write(summary + "\n")
        out.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        return 0
    if not rows:
        out.write("no transcripts found; pass --root to point at a directory of them\n")
        return 1
    scores = None
    if args.validity:
        try:
            scores = validity(registry=registry)
        except CorpusError as exc:
            sys.stderr.write("corpus: %s\n" % exc)
            return 2
    out.write(report(rows, by=args.by, min_sessions=args.min_sessions,
                     promote_share=args.promote_share, registry=registry,
                     validity=scores) + "\n")
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
        out.write("%-40s%-20s%s\n" % (detector.id, detector.event,
                                      "gated" if detector.gate is not None else ""))
    summary = bundle.summary()
    if summary:
        out.write("\n" + summary + "\n")
    return 0


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
    parser.print_help(out)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
