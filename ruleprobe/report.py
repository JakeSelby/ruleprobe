# SPDX-License-Identifier: MIT
"""The report: hits per detector, per repository, or per stance variant.

A row is one measured session: a dict carrying at least a `rules` map of detector id to hit
count. `measure()` builds one from a `Session`; a row read back out of a ledger file works
just as well, which is the point of keeping the report over rows rather than over sessions.

Only a row that carries a `rules` map is evidence. One written before a detector existed, or
one whose detectors could not be loaded, is absent from every count and from the
denominator: counting it as a session with no hit would turn a gap into a clean bill.

A detector that raised costs its own denominator and nobody else's. The row stays measured,
and the session is subtracted from the denominator of the detector named in `rules_errors`
alone - one broken third-party detector may not erase every other detector's evidence. An
entry tagged `"hook": "opportunities"` is the exception: its `fn` ran, so it touches no hit
figure and costs the detector only its `compliance` entry. The older singular spelling,
`rules_error`, names no detector, so a row carrying it is still dropped whole: an error
nobody attributed cannot be attributed here either.

A row may also carry `compliance`, detector id to `{"opportunities", "followed",
"undecided"}`, for each enabled detector that defines `opportunities`; `measure()` below
says how it is counted.

Every row and every `report_data` result carries `schema_version`, an integer; a row without
one was written by 0.1 and is schema 1. A row whose version this package does not know - one
written by a newer release, or a value that is not a known version at all - is excluded from
every count and denominator and counted apart, as a row with no `rules` map is: its hits may
not mean what this release's hits mean.
"""
from .registry import DEFAULT, KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION, _run

#: Above this share of measured sessions, an observable is common enough that the rule it
#: belongs to is worth stating more loudly - or is wrong. Either way it wants a look.
RULE_PROMOTE_SHARE = 0.30
#: Below this many measured sessions, no share means anything and the note is left blank.
RULE_MIN_SESSIONS = 20

BY = ("rule", "repo", "stance")


def _validity_note(scores, detector_id):
    """Imported late: `ruleprobe.validity` reads the transcript readers, and a report over
    stored rows should not pay for that unless it asked for the column."""
    from .validity import validity_note

    return validity_note(scores, detector_id)


class MalformedOpportunities(TypeError):
    """An `opportunities` result that is not `(turn, tool_use_id, followed)` triples with
    `followed` exactly `True`, `False` or `None`. Its name is what a row records, so a
    malformed result reads apart from a callable that raised a `TypeError` of its own."""


def _tally(triples):
    """`{"opportunities", "followed", "undecided"}` from one `opportunities` result.

    An undecided triple counts in `undecided` alone, never as an opportunity not followed.
    A malformed result - a `turn` that is not an integer, a `tool_use_id` neither a string
    nor `None`, a `followed` not exactly a bool or `None`, or one `(turn, tool_use_id)`
    point twice - raises `MalformedOpportunities`: it is the detector's error, never a guess
    at what it meant.
    """
    if triples is None or isinstance(triples, (str, bytes, dict)):
        raise MalformedOpportunities("opportunities returned %s, not a list of triples"
                                     % type(triples).__name__)
    try:
        triples = iter(triples)
    except TypeError:
        raise MalformedOpportunities("opportunities returned %s, not a list of triples"
                                     % type(triples).__name__)
    tally = {"opportunities": 0, "followed": 0, "undecided": 0}
    points = set()
    for triple in triples:
        if not isinstance(triple, (tuple, list)) or len(triple) != 3:
            raise MalformedOpportunities("not a (turn, tool_use_id, followed) triple: %r"
                                         % (triple,))
        turn, tool_use_id, followed = triple
        if isinstance(turn, bool) or not isinstance(turn, int):
            raise MalformedOpportunities("turn is %r, not an integer" % (turn,))
        if tool_use_id is not None and not isinstance(tool_use_id, str):
            raise MalformedOpportunities("tool_use_id is %r, not a string or None"
                                         % (tool_use_id,))
        if (turn, tool_use_id) in points:
            raise MalformedOpportunities("the point (%r, %r) is repeated"
                                         % (turn, tool_use_id))
        points.add((turn, tool_use_id))
        if followed is None:
            tally["undecided"] += 1
        elif followed is True or followed is False:
            tally["opportunities"] += 1
            tally["followed"] += followed
        else:
            raise MalformedOpportunities("followed is %r, not True, False or None"
                                         % (followed,))
    return tally


def _compliance(ctx, enabled, errors):
    """`{detector_id: tally}` for every detector in `enabled` that defines `opportunities`,
    or `None` when none does. Each is handed the `ctx` its `fn` was, so a compiled detector
    counts from the evaluation that gave its hits. A raise or a malformed result is appended
    to `errors` against that detector, tagged `"hook": "opportunities"` so the report's hit
    figures ignore it, and the detector gets no entry."""
    defining = sorted((d for d in enabled if getattr(d, "opportunities", None) is not None),
                      key=lambda d: d.id)
    if ctx is None or not defining:
        return None
    out = {}
    for detector in defining:
        try:
            out[detector.id] = _tally(detector.opportunities(ctx.events, ctx))
        except Exception as exc:
            errors.append({"detector": detector.id, "error": type(exc).__name__,
                           "hook": "opportunities"})
    return out


def measure(session, stances=None, registry=DEFAULT):
    """One report row from one `Session`: its identity, its hit counts and its compliance.

    `compliance` maps each enabled detector that defines `opportunities` to
    `{"opportunities": N, "followed": M, "undecided": U}`, where `N` leaves the undecided
    out. The key is absent when no enabled detector defines one, and when the session could
    not be analysed at all (`rules_errors` then names `analysis`). `opportunities` is called
    here rather than in `run()`, so `run()` and its return keep their shape.
    """
    errors = []
    hits, ctx, enabled = _run(session.events, stances, registry, False, errors)
    compliance = _compliance(ctx, enabled, errors)
    row = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session.id,
        "repo": session.repo,
        "runtime": session.runtime,
        "started": session.started,
        "ended": session.ended,
        "stances": dict(stances or {}),
        "rules": dict((did, len(found)) for did, found in hits.items()),
    }
    if compliance is not None:
        row["compliance"] = compliance
    if errors:
        row["rules_errors"] = errors
    return row


def _current(detector_id, renamed):
    """`detector_id` followed to the end of its chain in `renamed`, and in nothing else: on
    a map `Registry.fold_map()` returned this is one lookup."""
    seen = {detector_id}
    while renamed.get(detector_id, detector_id) != detector_id:
        detector_id = renamed[detector_id]
        if detector_id in seen:
            raise ValueError("the fold map has a cycle through %r" % detector_id)
        seen.add(detector_id)
    return detector_id


def folded_rules(row, renamed):
    """One row's hits, with a renamed detector counted under its successor.

    A rename would otherwise split one measurement across two lines, and the older half
    would look like a detector that stopped firing. A stored row is never rewritten for it:
    the fold is done on every read instead. Each id follows its chain within `renamed` and
    nowhere else: the shipped renames apply only when `renamed` is `Registry.fold_map()`,
    and are never merged in here, so an override in that map stands.
    """
    out = {}
    for did, n in (row.get("rules") or {}).items():
        if not isinstance(did, str):
            continue
        try:
            count = int(n or 0)
        except (TypeError, ValueError):
            count = 0
        key = _current(did, renamed)
        out[key] = out.get(key, 0) + count
    return out


def errored_detectors(row, renamed):
    """The detector ids that raised on `row`, under their current names.

    A session an entry names is subtracted from that detector's denominator and from no
    other's, which is the whole difference between "this detector has no evidence here" and
    "this session has no evidence at all". An entry tagged `"hook": "opportunities"` is not
    counted: it costs the detector its compliance entry, not its hits. `renamed` is read as
    `folded_rules` reads it.
    """
    out = set()
    for entry in (row.get("rules_errors") or ()):
        if isinstance(entry, dict) and entry.get("hook") == "opportunities":
            continue  # its `fn` ran, so its hits stand; only its compliance entry is gone
        if isinstance(entry, dict) and isinstance(entry.get("detector"), str):
            out.add(_current(entry["detector"], renamed))
    return out


def _row_schema_version(row):
    """The schema `row` was written under: its `schema_version`, or 1 when it has none. A
    null is read as none, since a store with a nullable column writes one for every 0.1 row."""
    version = row.get("schema_version")
    return 1 if version is None else version


def _is_known_schema(row):
    """Whether this release can count `row`. A boolean is not a version, though Python
    would compare `True` equal to 1."""
    version = _row_schema_version(row)
    return (isinstance(version, int) and not isinstance(version, bool)
            and version in KNOWN_SCHEMA_VERSIONS)


def rule_ids(rows, registry, folds=None):
    """Every detector id to report on: the registry's, so a detector with no hit is still a
    line, plus any id a row carries that the registry no longer defines - under its current
    name when the registry says it was renamed. `folds` is the resolved fold map to use, by
    default `registry.fold_map()`."""
    folds = registry.fold_map() if folds is None else folds
    ids = set(registry.ids())
    for row in rows:
        ids.update(folds.get(k, k) for k in (row.get("rules") or {})
                   if isinstance(k, str))
    return sorted(ids)


def report_data(rows, by="rule", min_sessions=RULE_MIN_SESSIONS,
                promote_share=RULE_PROMOTE_SHARE, registry=DEFAULT, validity=None):
    """The report as data: the same numbers `report()` prints, in the same order.

    `report()` renders this and `ruleprobe report --json` dumps it, so the table and the
    JSON cannot disagree about a denominator, a fold or a note. The shape is:

    - `schema_version` - the schema this result is written under.
    - `by`, `measured`, `unmeasured`, `unknown_schema`, `unattributed`, `errors`,
      `min_sessions`, `promote_share` - what was counted and under which settings.
    - `notes` - the preamble lines, in order.
    - `renamed` - the effective fold map the counts were read through, `{retired_id:
      current_id}`, resolved once for this call. It is complete: a stored result folds a
      retired id by applying it as it stands, and it is never re-merged with the shipped map
      of a later release, which would undo a consumer's override.
    - `detectors` - one entry per detector when `by="rule"`: `detector`, `hits`,
      `sessions`, `of`, `share`, `note`, and `validity` when scores were passed.
    - `groups` - one entry per repository or stance otherwise: `key`, `sessions`, `hits`,
      `top`.
    """
    if by not in BY:
        raise ValueError("unknown grouping %r; one of %s" % (by, ", ".join(BY)))
    rows = [r for r in rows if isinstance(r, dict)]
    renamed = registry.fold_map()
    measured, unmeasured, unknown_schema, unattributed = [], 0, 0, 0
    for row in rows:
        if not _is_known_schema(row):
            # Checked first: a newer schema may shape even its `rules` map differently.
            unknown_schema += 1
        elif not isinstance(row.get("rules"), dict):
            unmeasured += 1
        elif row.get("rules_error") and not row.get("rules_errors"):
            # The legacy spelling names no detector, so there is nobody to charge the loss
            # to and the row is dropped whole rather than misattributed.
            unattributed += 1
        else:
            measured.append(row)
    errors, errored_rows = {}, 0
    for row in measured:
        found = errored_detectors(row, renamed)
        errored_rows += 1 if found else 0
        for did in found:
            errors[did] = errors.get(did, 0) + 1
    notes = []
    if unmeasured:
        notes.append("%d session(s) carry no rule data" % unmeasured)
    if unknown_schema:
        notes.append("%d session(s) carry a schema_version this release does not know"
                     " (highest known: %d) and are excluded"
                     % (unknown_schema, max(KNOWN_SCHEMA_VERSIONS)))
    if unattributed:
        notes.append("%d session(s) carry an error naming no detector and are dropped whole"
                     % unattributed)
    if errors:
        named = ", ".join("%s (%d)" % (d, n) for d, n in sorted(errors.items())[:5])
        more = "" if len(errors) <= 5 else ", and %d more" % (len(errors) - 5)
        notes.append("%d detector(s) raised in %d session(s): %s%s"
                     % (len(errors), errored_rows, named, more))
        notes.append("each is out of its own denominator for those sessions, and no other's")
    data = {"schema_version": SCHEMA_VERSION, "by": by, "measured": len(measured),
            "unmeasured": unmeasured, "unknown_schema": unknown_schema,
            "unattributed": unattributed, "errors": dict(errors),
            "min_sessions": min_sessions, "promote_share": promote_share,
            "notes": notes, "renamed": dict(renamed), "detectors": [], "groups": []}
    if not measured:
        notes.append("no measured sessions")
        return data
    counted = [(r, folded_rules(r, renamed), errored_detectors(r, renamed))
               for r in measured]

    if by == "rule":
        for did in rule_ids(measured, registry, renamed):
            rows_for = [(h, e) for _r, h, e in counted if did not in e]
            total = len(rows_for)
            hits = sum(h.get(did, 0) for h, _e in rows_for)
            seen = sum(1 for h, _e in rows_for if h.get(did, 0) > 0)
            share = seen / float(total) if total else 0.0
            note = ""
            if total >= min_sessions:
                note = "promote?" if share > promote_share else ("unobserved" if not hits
                                                                 else "")
            entry = {"detector": did, "hits": hits, "sessions": seen, "of": total,
                     "share": share, "note": note}
            if validity is not None:
                entry["validity"] = _validity_note(validity, did)
            data["detectors"].append(entry)
        return data

    if by == "stance":
        # A row whose stances were guessed after the fact would be filed under a variant the
        # session may never have run under, so it is excluded rather than misattributed.
        guessed = [r for r, _h, _e in counted if r.get("stances_source") == "rescan"]
        if guessed:
            notes.append("%d rescanned session(s) excluded: stance not known at the time"
                         % len(guessed))
        counted = [x for x in counted if x[0].get("stances_source") != "rescan"]
        if not counted:
            notes.append("no sessions with a known stance")
            return data

    groups = {}
    for row, hits_of, _errored in counted:
        if by == "stance":
            stances = row.get("stances") if isinstance(row.get("stances"), dict) else {}
            keys = ["%s=%s" % (k, v) for k, v in sorted(stances.items())] or ["(no stances)"]
        else:
            keys = [row.get("repo") or "(no repo)"]
        for key in keys:
            acc = groups.setdefault(key, [0, {}])
            acc[0] += 1
            for did, n in hits_of.items():
                acc[1][did] = acc[1].get(did, 0) + n
    for key in sorted(groups):
        sessions, counts = groups[key]
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        data["groups"].append({"key": key, "sessions": sessions,
                               "hits": sum(counts.values()),
                               "top": [[did, n] for did, n in top]})
    return data


def report(rows, by="rule", min_sessions=RULE_MIN_SESSIONS, promote_share=RULE_PROMOTE_SHARE,
           registry=DEFAULT, validity=None):
    """The report as text, ready to print.

    - `by="rule"` - one line per detector: hits, the sessions it fired in, the denominator,
      the share, and a note. `promote?` means the observable is common enough to be worth a
      look; `unobserved` means the detector has never fired in this window. Both are blank
      until there are `min_sessions` measured sessions, because a share over five sessions
      is noise. A detector that raised in a session is out of its own `of` column for that
      session and out of nobody else's.
    - `by="repo"` - one line per repository: sessions, hits, and its top three detectors.
    - `by="stance"` - the same, grouped by each `dimension=variant` a row ran under.

    `validity`, when a `{detector_id: Score}` mapping from `ruleprobe.validity` is passed,
    adds a column saying how good each detector is over the labelled corpus, so a hit rate
    is read as `p=0.96 r=0.91` and not as a fact. It is off by default because the table is
    meant to be read in a minute; `ruleprobe report --validity` turns it on.

    `report_data()` is the same thing as a dict, and is what `--json` prints.
    """
    data = report_data(rows, by=by, min_sessions=min_sessions,
                       promote_share=promote_share, registry=registry, validity=validity)
    lines = list(data["notes"])
    if not data["detectors"] and not data["groups"]:
        return "\n".join(lines)

    if data["by"] == "rule":
        head = "%-38s%7s%10s%6s%8s  note" % ("detector", "hits", "sessions", "of", "share")
        width = len(head)
        if validity is not None:
            head = "%-*s  validity" % (width, head)
        lines.append(head)
        lines.append("-" * len(head))
        for entry in data["detectors"]:
            line = "%-38s%7d%10d%6d%8.0f%%  %s" % (
                entry["detector"][:38], entry["hits"], entry["sessions"], entry["of"],
                entry["share"] * 100, entry["note"])
            if validity is not None:
                line = "%-*s  %s" % (width, line.rstrip(), entry.get("validity", ""))
            lines.append(line.rstrip())
        return "\n".join(lines)

    head = "%-42s%9s%7s  top detectors" % (data["by"], "sessions", "hits")
    lines.append(head)
    lines.append("-" * len(head))
    for group in data["groups"]:
        lines.append("%-42s%9d%7d  %s"
                     % (group["key"][:42], group["sessions"], group["hits"],
                        ", ".join("%s %d" % (did, n) for did, n in group["top"]) or "-"))
    return "\n".join(lines)


#: The most of one event's text explain prints; the rest is cut and counted.
MAX_EXPLAINED = 4000

# Every control character but a newline and a tab, and the line and paragraph separators:
# printed raw, one in a transcript could rewrite the reader's terminal. Every Unicode format
# character (category Cf: zero-width characters, U+061C, the bidi marks) is escaped too, since
# one can make a printed line read as something it is not.
_CONTROL = r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]"


def _hit_key(hit):
    """Imported late: `ruleprobe.validity` sits above this module in the import graph, and
    a label and a hit are keyed by the one function it owns."""
    from .validity import hit_key

    return hit_key(hit)


def _redact(text):
    """`detectors.common.redact`, the one path for text printed from a transcript, with
    every control character but a newline and a tab, both line separators and every Unicode
    format character written as its `\\xNN`, `\\uNNNN` or `\\UNNNNNNNN` escape."""
    import re
    import unicodedata

    from .detectors.common import redact

    text = re.sub(_CONTROL, lambda found: _escape(found.group(0)), redact(text))
    if text.isascii():
        return text
    return "".join(_escape(c) if unicodedata.category(c) == "Cf" else c for c in text)


def _escape(char):
    code = ord(char)
    if code <= 0xff:
        return "\\x%02x" % code
    return "\\u%04x" % code if code <= 0xffff else "\\U%08x" % code


def _capped(text):
    if len(text) <= MAX_EXPLAINED:
        return text
    return "%s\n[%d more character(s) cut]" % (text[:MAX_EXPLAINED],
                                               len(text) - MAX_EXPLAINED)


def session_address(runtime, session_id):
    """`<runtime>:<session id>`: a session id is unique within the runtime that wrote it,
    and a hit key only within its session, so this plus the key names one hit anywhere."""
    return "%s:%s" % (runtime or "", session_id or "")


def _turn_order(turn):
    return (0, turn, "") if isinstance(turn, int) and not isinstance(turn, bool) \
        else (1, 0, str(turn))


def _event_field(event):
    """The name and text of what a hit on `event` matched: a Bash command, or any other
    tool's whole input as sorted JSON, since a hit does not say which of its fields fired."""
    import json

    data = event.get("input") if isinstance(event.get("input"), dict) else {}
    if event.get("name") == "Bash" and isinstance(data.get("command"), str):
        return "command", data["command"]
    try:
        return "input", json.dumps(data, sort_keys=True, default=str)
    except (TypeError, ValueError):  # keys of mixed types, or an input that holds itself
        return "input", repr(data)


def _tool_use_positions(events):
    """`{(turn, tool use id): index}` for the first tool use at each pair: a hit names its
    event by both, since an id is only promised unique within its turn's key."""
    position = {}
    for index, event in enumerate(events or ()):
        if not isinstance(event, dict) or event.get("kind") != "tool_use":
            continue
        try:
            position.setdefault((event.get("turn", 0), event.get("id")), index)
        except TypeError:  # an unhashable turn or id names no hit either
            continue
    return position


def _redacted_strings(mapping):
    """`mapping` with every value but None and an integer turned to a string and redacted:
    a transcript field may be any shape, and a list or tuple holds text as well as a string
    does."""
    out = {}
    for name, value in mapping.items():
        if value is None or (isinstance(value, int) and not isinstance(value, bool)):
            out[name] = value
        else:
            out[name] = _redact(value if isinstance(value, str) else str(value))
    return out


def explain(sessions, stances=None, registry=DEFAULT, errors=None, session=None,
            detector=None, key=None):
    """Every hit `measure()` would count over `sessions`, one dict each, with the event
    behind it.

    Each dict carries `session` (the `session_address`), `key` (the hit's
    `"<turn>:<tool_use_id>"`, or `"<turn>:-"` for a hit that names no tool use), `detector`,
    `turn`, `tool_use_id`, `tool`, `field` and `value`. Every string among them has been through
    `_redact`, and `value` is cut at `MAX_EXPLAINED` characters; a hit that names no tool use
    has no event, so its `tool`, `field` and `value` are None. Sessions keep the order given;
    within one, hits are by turn, a hit naming no tool use ahead of the tool uses, those in
    transcript order, then by detector id. `errors`, when a list is passed, collects what
    `run()` collects, with the session address added and its strings through `_redact`.
    `session` (an address or a bare id), `detector` and `key` keep only what equals them,
    compared with the values before redaction, so an id holding a control character or a secret
    shape can still be picked. Nothing is written and no row is built, so no report number can
    move.
    """
    wanted_session = session
    for session in sessions:
        address = session_address(session.runtime, session.id)
        if wanted_session is not None and wanted_session not in (address, session.id):
            continue
        events = session.events
        position = _tool_use_positions(events)
        found = []
        session_errors = [] if errors is not None else None
        hits = run(events, stances, registry=registry, errors=session_errors)
        for detector_id in sorted(hits):
            if detector is not None and detector_id != detector:
                continue
            for one in hits[detector_id]:
                if key is not None and _hit_key(one) != key:
                    continue
                at = -1
                if one.tool_use_id:
                    try:
                        at = position.get((one.turn, one.tool_use_id), -1)
                    except TypeError:
                        at = -1
                found.append(((_turn_order(one.turn), at, detector_id), one))
        for entry in session_errors or ():
            errors.append(_redacted_strings(dict(entry, session=address)))
        found.sort(key=lambda pair: pair[0])
        for (_order, at, _did), one in found:
            item = {"session": address, "key": _hit_key(one), "detector": one.id,
                    "turn": one.turn, "tool_use_id": one.tool_use_id, "tool": None,
                    "field": None, "value": None}
            if at >= 0:
                event = events[at]
                field, value = _event_field(event)
                item.update(tool=event.get("name"), field=field, value=value)
            item = _redacted_strings(item)
            if item["value"] is not None:
                item["value"] = _capped(item["value"])
            yield item


def explain_text(item):
    """One `explain()` dict as the block `ruleprobe explain` prints, redacted whole."""
    lines = ["session   %s" % item["session"],
             "key       %s" % item["key"],
             "detector  %s" % item["detector"],
             "turn      %s" % item["turn"]]
    if item["field"] is not None:
        lines.append("tool use  %s (%s)" % (item["tool_use_id"], item["tool"]))
        body = "\n          ".join((item["value"] or "").split("\n"))
        lines.append("%-9s %s" % (item["field"], body))
    elif item["tool_use_id"]:
        lines.append("tool use  %s (not an event in this session)" % item["tool_use_id"])
    else:
        lines.append("tool use  -  (the hit names no tool use, only turn %s)" % item["turn"])
    return _redact("\n".join(lines))


def explain_row(row, runtimes=()):
    """What explain can say about a stored row: that it carries counts only, and the rerun
    over its runtime and session id that would explain each hit.

    `runtimes` is the runtime names `--runtime` accepts, such as `readers.RUNTIMES`. For a
    runtime among them the rerun names `--runtime` and the `<runtime>:<id>` address; for
    any other, or none, it names the bare session id, since no reader emits that address.
    By default no runtime is known. Each value is shell-quoted.
    """
    import shlex

    row = row if isinstance(row, dict) else {}
    runtime = row.get("runtime") if isinstance(row.get("runtime"), str) else ""
    session_id = row.get("session_id") if isinstance(row.get("session_id"), str) else ""
    shown = session_address(runtime, session_id) if runtime else (session_id or "(no id)")
    if not isinstance(row.get("rules"), dict):
        return _redact("session %s: this row carries no rule counts, so there is no hit "
                       "to explain" % shown)
    known = bool(runtime) and runtime in runtimes
    rerun = ["ruleprobe", "explain"]
    if known:
        rerun += ["--runtime", runtime]
    if session_id:
        rerun += ["--session", session_address(runtime, session_id) if known
                  else session_id]
    hits = sum(folded_rules(row, {}).values())
    return _redact("session %s: this row carries counts only (%d hit(s)), not the events "
                   "behind them; rerun `%s` over its transcripts to see each hit"
                   % (shown, hits, " ".join(shlex.quote(part) for part in rerun)))
