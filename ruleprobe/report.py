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
alone - one broken third-party detector may not erase every other detector's evidence. The
older singular spelling, `rules_error`, names no detector, so a row carrying it is still
dropped whole: an error nobody attributed cannot be attributed here either.

Every row and every `report_data` result carries `schema_version`, an integer; a row without
one was written by 0.1 and is schema 1. A row whose version this package does not know - one
written by a newer release, or a value that is not a known version at all - is excluded from
every count and denominator and counted apart, as a row with no `rules` map is: its hits may
not mean what this release's hits mean.
"""
from .registry import DEFAULT, KNOWN_SCHEMA_VERSIONS, SCHEMA_VERSION, run

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


def measure(session, stances=None, registry=DEFAULT):
    """One report row from one `Session`: its identity and its hit counts."""
    errors = []
    hits = run(session.events, stances, registry=registry, errors=errors)
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
    "this session has no evidence at all". `renamed` is read as `folded_rules` reads it.
    """
    out = set()
    for entry in (row.get("rules_errors") or ()):
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
