# SPDX-License-Identifier: MIT
"""`ruleprobe` on the command line.

    ruleprobe report [--by rule|repo|stance] [--since DATE] [--root DIR] [--runtime NAME]
    ruleprobe detectors

Nothing is written anywhere and nothing leaves the machine: the transcripts are read, the
detectors are run over them in memory, and a table is printed.
"""
import argparse
import json
import sys

from . import __version__
from .readers import RUNTIMES, iter_sessions
from .registry import DEFAULT, Registry
from .report import BY, RULE_MIN_SESSIONS, RULE_PROMOTE_SHARE, measure, report


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

    sub.add_parser("detectors", help="list the detectors that would run")
    return parser


def _since(value):
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text.isdigit() and len(text) <= 4 else text


def cmd_report(args, out):
    registry = Registry.from_entry_points() if args.plugins else DEFAULT
    rows = [measure(session, registry=registry)
            for session in iter_sessions(root=args.root, runtime=args.runtime,
                                         since=_since(args.since))]
    if args.json:
        out.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        return 0
    if not rows:
        out.write("no transcripts found; pass --root to point at a directory of them\n")
        return 1
    out.write(report(rows, by=args.by, min_sessions=args.min_sessions,
                     promote_share=args.promote_share, registry=registry) + "\n")
    return 0


def cmd_detectors(args, out):
    registry = Registry.from_entry_points()
    for detector in registry:
        out.write("%-40s%-20s%s\n" % (detector.id, detector.event,
                                      "gated" if detector.gate is not None else ""))
    return 0


def main(argv=None, out=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = sys.stdout if out is None else out
    if args.command == "report":
        return cmd_report(args, out)
    if args.command == "detectors":
        return cmd_detectors(args, out)
    parser.print_help(out)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
