# SPDX-License-Identifier: MIT
"""The report: hits per detector, per repository, or per stance variant.

A row is one measured session: a dict carrying at least a `rules` map of detector id to hit
count. `measure()` builds one from a `Session`; a row read back out of a ledger file works
just as well, which is the point of keeping the report over rows rather than over sessions.

Only a row that carries a `rules` map is evidence. One written before a detector existed, or
one whose detectors could not be loaded, is absent from every count and from the
denominator: counting it as a session with no hit would turn a gap into a clean bill.
"""
from .registry import DEFAULT, run

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


def folded_rules(row, renamed):
    """One row's hits, with a renamed detector counted under its successor.

    A rename would otherwise split one measurement across two lines, and the older half
    would look like a detector that stopped firing. A stored row is never rewritten for it:
    the fold is done on every read instead.
    """
    out = {}
    for did, n in (row.get("rules") or {}).items():
        if not isinstance(did, str):
            continue
        try:
            count = int(n or 0)
        except (TypeError, ValueError):
            count = 0
        key = renamed.get(did, did)
        out[key] = out.get(key, 0) + count
    return out


def rule_ids(rows, registry):
    """Every detector id to report on: the registry's, so a detector with no hit is still a
    line, plus any id a row carries that the registry no longer defines - under its current
    name when the registry says it was renamed."""
    ids = set(registry.ids())
    for row in rows:
        ids.update(registry.renamed.get(k, k) for k in (row.get("rules") or {})
                   if isinstance(k, str))
    return sorted(ids)


def report(rows, by="rule", min_sessions=RULE_MIN_SESSIONS, promote_share=RULE_PROMOTE_SHARE,
           registry=DEFAULT, validity=None):
    """The report as text, ready to print.

    - `by="rule"` - one line per detector: hits, the sessions it fired in, the denominator,
      the share, and a note. `promote?` means the observable is common enough to be worth a
      look; `unobserved` means the detector has never fired in this window. Both are blank
      until there are `min_sessions` measured sessions, because a share over five sessions
      is noise.
    - `by="repo"` - one line per repository: sessions, hits, and its top three detectors.
    - `by="stance"` - the same, grouped by each `dimension=variant` a row ran under.

    `validity`, when a `{detector_id: Score}` mapping from `ruleprobe.validity` is passed,
    adds a column saying how good each detector is over the labelled corpus, so a hit rate
    is read as `p=0.96 r=0.91` and not as a fact. It is off by default because the table is
    meant to be read in a minute; `ruleprobe report --validity` turns it on.
    """
    if by not in BY:
        raise ValueError("unknown grouping %r; one of %s" % (by, ", ".join(BY)))
    rows = [r for r in rows if isinstance(r, dict)]
    lines = []
    measured = [r for r in rows
                if isinstance(r.get("rules"), dict) and not r.get("rules_errors")]
    legacy = sum(1 for r in rows
                 if not isinstance(r.get("rules"), dict) and not r.get("rules_error"))
    errored = sum(1 for r in rows if r.get("rules_error") or r.get("rules_errors"))
    if legacy or errored:
        lines.append("%d session(s) carry no rule data (%d unmeasured, %d errored)"
                     % (legacy + errored, legacy, errored))
    if not measured:
        lines.append("no measured sessions")
        return "\n".join(lines)
    counted = [(r, folded_rules(r, registry.renamed)) for r in measured]

    if by == "rule":
        total = len(counted)
        head = "%-38s%7s%10s%6s%8s  note" % ("detector", "hits", "sessions", "of", "share")
        width = len(head)
        if validity is not None:
            head = "%-*s  validity" % (width, head)
        lines.append(head)
        lines.append("-" * len(head))
        for did in rule_ids(measured, registry):
            hits = sum(hits_of.get(did, 0) for _, hits_of in counted)
            seen = sum(1 for _, hits_of in counted if hits_of.get(did, 0) > 0)
            share = seen / float(total) if total else 0.0
            note = ""
            if total >= min_sessions:
                note = "promote?" if share > promote_share else ("unobserved" if not hits else "")
            line = "%-38s%7d%10d%6d%8.0f%%  %s" % (did[:38], hits, seen, total,
                                                   share * 100, note)
            if validity is not None:
                line = "%-*s  %s" % (width, line.rstrip(), _validity_note(validity, did))
            lines.append(line.rstrip())
        return "\n".join(lines)

    if by == "stance":
        # A row whose stances were guessed after the fact would be filed under a variant the
        # session may never have run under, so it is excluded rather than misattributed.
        guessed = [r for r, _ in counted if r.get("stances_source") == "rescan"]
        if guessed:
            lines.append("%d rescanned session(s) excluded: stance not known at the time"
                         % len(guessed))
        counted = [(r, h) for r, h in counted if r.get("stances_source") != "rescan"]
        if not counted:
            lines.append("no sessions with a known stance")
            return "\n".join(lines)

    groups = {}
    for row, hits_of in counted:
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
    head = "%-42s%9s%7s  top detectors" % (by, "sessions", "hits")
    lines.append(head)
    lines.append("-" * len(head))
    for key in sorted(groups):
        sessions, counts = groups[key]
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        lines.append("%-42s%9d%7d  %s"
                     % (key[:42], sessions, sum(counts.values()),
                        ", ".join("%s %d" % (d, n) for d, n in top) or "-"))
    return "\n".join(lines)
