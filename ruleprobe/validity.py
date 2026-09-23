# SPDX-License-Identifier: MIT
"""How good a detector is: precision and recall over a labelled corpus.

Every hit rate a report prints is a rate of *the detector*, not of the behaviour, until
somebody says what the detector should have found. This module is that: a corpus of
synthetic, hand-labelled transcript sessions ships inside the package at
`ruleprobe/corpus/`, and `score_corpus()` runs every registered detector over it and
compares what fired with what the labels say should have fired.

    from ruleprobe import score_corpus, validity_table

    scores = score_corpus()
    print(validity_table(scores))

A label is keyed by the same pair a `Hit` carries - the turn and the tool use id, written
`"<turn>:<tool_use_id>"`, or `"<turn>:-"` for a hit on the session rather than on a tool
use. The labels for one session are the whole truth about every detector they name: a hit at
a key the labels do not give such a detector is a false positive, and a label the detector
did not produce is a false negative. A detector the corpus never names is not scored by it. `near` marks a deliberate near-miss and is what the negative count is
counting; it is documentation of intent, not arithmetic.

A detector with no corpus label and no `examples:` block of its own is *unscored* - the
report says "no examples" rather than inventing a number - and the floor gate passes over
it, because an unmeasured detector is a gap to see, not a failure to fix.
"""
import os

from .declarative import DeclarativeError, load
from .events import Hit  # noqa: F401  - named in the docstring's contract
from .readers import iter_sessions
from .registry import DEFAULT, fold_map, run

__all__ = ["CorpusError", "Score", "DEFAULT_FLOOR", "corpus_dir", "load_corpus",
           "score_corpus", "score_examples", "validity", "validity_table",
           "below_floor", "scores_as_dict"]

#: The floor `ruleprobe corpus` fails under. It is a CI gate for this repository, not a
#: runtime failure for a user: nothing in `ruleprobe report` reads it.
DEFAULT_FLOOR = 0.9

#: The corpus that ships with the package. `corpus_dir()` is how to find it.
CORPUS_DIRNAME = "corpus"
LABELS_FILE = "labels.yaml"
SESSIONS_DIRNAME = "sessions"

_LABEL_KEYS = ("at", "fire", "near", "note")
_SESSION_KEYS = ("session", "note", "labels")


class CorpusError(Exception):
    """The corpus itself is wrong - a label pointing at no event, two labels on one key, a
    session file that is not there. Unlike a detector file, this is fatal: the corpus is the
    measuring instrument and a broken one may not quietly produce a number."""


class Score(object):
    """One detector's tally over the corpus.

    `positives` and `negatives` are what the labels asked for; `tp`, `fp` and `fn` are what
    happened. A detector nobody labelled is `scored == False` and has no rates.
    """

    __slots__ = ("detector", "positives", "negatives", "tp", "fp", "fn", "source")

    def __init__(self, detector, positives=0, negatives=0, tp=0, fp=0, fn=0, source=""):
        self.detector = detector
        self.positives = positives
        self.negatives = negatives
        self.tp = tp
        self.fp = fp
        self.fn = fn
        self.source = source or "corpus"

    @property
    def scored(self):
        return bool(self.positives or self.negatives or self.tp or self.fp or self.fn)

    @property
    def precision(self):
        """Of the hits it produced, the share that should have happened. No hit and no
        miss is a precision of 1.0; no hit and a miss is 0.0, because a detector that never
        fires has no claim to being right."""
        if self.tp + self.fp:
            return self.tp / float(self.tp + self.fp)
        return 1.0 if not self.fn else 0.0

    @property
    def recall(self):
        """Of the events that should have fired, the share that did."""
        if self.tp + self.fn:
            return self.tp / float(self.tp + self.fn)
        return 1.0

    @property
    def f1(self):
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def add(self, other):
        self.positives += other.positives
        self.negatives += other.negatives
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        return self

    def as_dict(self):
        out = {"detector": self.detector, "source": self.source, "scored": self.scored,
               "positives": self.positives, "negatives": self.negatives,
               "tp": self.tp, "fp": self.fp, "fn": self.fn}
        if self.scored:
            out.update({"precision": round(self.precision, 4),
                        "recall": round(self.recall, 4), "f1": round(self.f1, 4)})
        return out

    def __repr__(self):
        return "Score(%r, tp=%d, fp=%d, fn=%d)" % (self.detector, self.tp, self.fp, self.fn)


# --- loading the corpus ----------------------------------------------------------------


class LabelledSession(object):
    """One corpus session and the labels over it."""

    __slots__ = ("session", "name", "note", "fire", "near")

    def __init__(self, session, name, note="", fire=None, near=None):
        self.session = session
        self.name = name
        self.note = note
        #: `{detector_id: set(keys)}`, both ways round from the file's per-event shape,
        #: because scoring is a set comparison per detector.
        self.fire = fire or {}
        self.near = near or {}


def corpus_dir(directory=None):
    """Where the corpus is. `directory`, else `$RULEPROBE_CORPUS`, else the one inside the
    package - which is how it reaches a user, since it is package data and not a file in the
    repository root."""
    if directory:
        return os.path.abspath(os.path.expanduser(directory))
    from_env = os.environ.get("RULEPROBE_CORPUS")
    if from_env:
        return os.path.abspath(os.path.expanduser(from_env))
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CORPUS_DIRNAME)


def event_key(event):
    """The key a hit on `event` would carry. A tool use is keyed by its id; anything else
    by its turn alone, because a hit on the session does not name an event."""
    if event.get("kind") == "tool_use" and event.get("id"):
        return "%s:%s" % (event.get("turn", 0), event.get("id"))
    return "%s:-" % event.get("turn", 0)


def hit_key(hit):
    return "%s:%s" % (hit.turn, hit.tool_use_id or "-")


def load_corpus(directory=None):
    """Every labelled session in the corpus, in the order the labels file names them.

    Raises `CorpusError` for anything wrong with the corpus: a missing file, a label whose
    `at` names no event, a duplicate label, an unknown key.
    """
    base = corpus_dir(directory)
    path = os.path.join(base, LABELS_FILE)
    try:
        document, _lines = load(path)
    except DeclarativeError as exc:
        raise CorpusError("%s" % exc)
    if not isinstance(document, dict) or not isinstance(document.get("sessions"), list):
        raise CorpusError("%s: expected a mapping with a sessions list" % path)
    sessions_dir = os.path.join(base, SESSIONS_DIRNAME)
    by_name = dict((os.path.basename(s.path), s)
                   for s in iter_sessions(root=sessions_dir))
    out = []
    seen = set()
    for entry in document["sessions"]:
        out.append(_labelled(entry, by_name, path))
        seen.add(out[-1].name)
    unlabelled = sorted(set(by_name) - seen)
    if unlabelled:
        raise CorpusError("%s: no labels for %s" % (path, ", ".join(unlabelled)))
    return out


def _labelled(entry, by_name, path):
    if not isinstance(entry, dict):
        raise CorpusError("%s: a session entry is a mapping" % path)
    _only(entry, _SESSION_KEYS, path, "session")
    name = entry.get("session")
    if not isinstance(name, str) or name not in by_name:
        raise CorpusError("%s: no session file named %r under %s/"
                          % (path, name, SESSIONS_DIRNAME))
    session = by_name[name]
    keys = set(event_key(e) for e in session.events)
    fire, near, at_seen = {}, {}, set()
    for label in entry.get("labels") or []:
        if not isinstance(label, dict):
            raise CorpusError("%s: a label is a mapping" % path)
        _only(label, _LABEL_KEYS, path, "label")
        at = label.get("at")
        if not isinstance(at, str) or at not in keys:
            raise CorpusError("%s: label %r in %s points at no event"
                              % (path, at, name))
        if at in at_seen:
            raise CorpusError("%s: two labels at %r in %s" % (path, at, name))
        at_seen.add(at)
        for key, into in (("fire", fire), ("near", near)):
            for detector_id in _ids(label.get(key), path, name, at, key):
                into.setdefault(detector_id, set()).add(at)
    return LabelledSession(session, name, entry.get("note") or "", fire, near)


def _ids(value, path, name, at, key):
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise CorpusError("%s: %s at %r in %s is a list of detector ids"
                          % (path, key, at, name))
    return tuple(value)


def _only(mapping, allowed, path, what):
    for key in mapping:
        if key not in allowed:
            raise CorpusError("%s: unknown %s key %r; one of %s"
                              % (path, what, key, ", ".join(allowed)))


# --- scoring ----------------------------------------------------------------------------


def score_corpus(registry=DEFAULT, directory=None, corpus=None):
    """`{detector_id: Score}` for every detector in `registry`, over the corpus.

    Only a detector the corpus *names* somewhere - in a `fire` list or a `near` one - is
    scored against it. A detector nobody labelled is returned unscored rather than omitted,
    so the gap is visible in the table; scoring it anyway would call every hit it produced a
    false positive, which would punish a detector of yours for firing on a session written
    before it existed.

    A label naming a retired detector id counts under its current id, folded through
    `registry`'s fold map as a report folds a stored row.
    """
    corpus = load_corpus(directory) if corpus is None else corpus
    scores = dict((d.id, Score(d.id)) for d in registry)
    folds = fold_map(getattr(registry, "renamed", None))
    labels = [(labelled, _folded(labelled.fire, folds), _folded(labelled.near, folds))
              for labelled in corpus]
    named = set()
    for _labelled, fire, near in labels:
        named.update(fire)
        named.update(near)
    for labelled, fire, near in labels:
        hits = run(labelled.session.events, registry=registry, strict=True)
        for detector_id, score in scores.items():
            if detector_id not in named:
                continue
            found = [hit_key(h) for h in hits.get(detector_id, [])]
            if len(set(found)) != len(found):
                raise CorpusError(
                    "%s fires twice at one key in %s; give the events separate turns"
                    % (detector_id, labelled.name))
            found = set(found)
            wanted = fire.get(detector_id, set())
            score.positives += len(wanted)
            score.negatives += len(near.get(detector_id, set()))
            score.tp += len(found & wanted)
            score.fp += len(found - wanted)
            score.fn += len(wanted - found)
    return scores


def _folded(labels, folds):
    """`{detector_id: keys}` with each retired id's keys merged under its current id. A new
    mapping, so a corpus passed in is not changed by scoring it."""
    out = {}
    for detector_id, keys in labels.items():
        out.setdefault(folds.get(detector_id, detector_id), set()).update(keys)
    return out


def score_examples(detectors):
    """`{detector_id: Score}` from the `examples:` blocks detectors carry themselves.

    A `fire` case counts one positive and is a true positive when the detector produced any
    hit over it; a `skip` case counts one negative and is a false positive when it did.
    A detector with no examples gets an unscored `Score`.
    """
    from .registry import Registry

    scores = {}
    for detector in detectors:
        score = Score(detector.id, source="examples")
        scores[detector.id] = score
        examples = getattr(detector, "examples", None)
        if not examples:
            continue
        one = Registry([detector])
        for _note, events in examples.fire:
            score.positives += 1
            if run(events, registry=one, strict=True).get(detector.id):
                score.tp += 1
            else:
                score.fn += 1
        for _note, events in examples.skip:
            score.negatives += 1
            if run(events, registry=one, strict=True).get(detector.id):
                score.fp += 1
    return scores


def validity(registry=DEFAULT, directory=None, corpus=None):
    """The scores a report or the corpus command reads: the shipped corpus for the
    detectors it labels, and a detector's own `examples:` block for the rest."""
    scores = score_corpus(registry, directory, corpus)
    for detector_id, score in score_examples(registry).items():
        if score.scored and not scores.get(detector_id, Score(detector_id)).scored:
            scores[detector_id] = score
    return scores


def total(scores):
    """One `Score` over every scored detector."""
    out = Score("total")
    for score in scores.values():
        if score.scored:
            out.add(score)
    return out


def below_floor(scores, floor=DEFAULT_FLOOR):
    """The scored detectors whose precision or recall is under `floor`, in id order."""
    return sorted(did for did, s in scores.items()
                  if s.scored and (s.precision < floor or s.recall < floor))


def scores_as_dict(scores, floor=DEFAULT_FLOOR):
    """The whole result as plain data, for `--json`."""
    return {"floor": floor,
            "detectors": dict((did, s.as_dict()) for did, s in scores.items()),
            "total": total(scores).as_dict(),
            "below_floor": below_floor(scores, floor)}


# --- the table ---------------------------------------------------------------------------

_HEAD = "%-38s%5s%5s%5s%5s%5s%7s%8s%7s  note"
_ROW = "%-38s%5d%5d%5d%5d%5d%7.2f%8.2f%7.2f  %s"
_UNSCORED = "%-38s%5s%5s%5s%5s%5s%7s%8s%7s  %s"


def validity_table(scores, floor=DEFAULT_FLOOR):
    """The table `ruleprobe corpus` prints, and the one the README quotes."""
    head = _HEAD % ("detector", "pos", "neg", "tp", "fp", "fn", "prec", "recall", "f1")
    lines = [head, "-" * len(head)]
    failing = set(below_floor(scores, floor))
    for did in sorted(scores):
        score = scores[did]
        if not score.scored:
            lines.append((_UNSCORED % (did[:38], "-", "-", "-", "-", "-", "-", "-", "-",
                                       "no examples")).rstrip())
            continue
        note = "below floor" if did in failing else ""
        lines.append((_ROW % (did[:38], score.positives, score.negatives, score.tp,
                              score.fp, score.fn, score.precision, score.recall,
                              score.f1, note)).rstrip())
    whole = total(scores)
    lines.append("-" * len(head))
    lines.append((_ROW % ("total", whole.positives, whole.negatives, whole.tp, whole.fp,
                          whole.fn, whole.precision, whole.recall, whole.f1,
                          "floor %.2f" % floor)).rstrip())
    return "\n".join(lines)


def validity_note(scores, detector_id):
    """The one-line annotation `ruleprobe report --validity` puts beside a detector."""
    score = scores.get(detector_id) if scores else None
    if score is None:
        return "not in the corpus"
    if not score.scored:
        return "no examples"
    return "p=%.2f r=%.2f" % (score.precision, score.recall)
