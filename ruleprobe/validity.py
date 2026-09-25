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

A corpus session is a native transcript read through the real readers, or an event-schema
file, `<name>.events.jsonl`, holding one event dict per line: the shape `ruleprobe label`
writes. `load_events` reads one without a runtime reader and takes each event's `turn` and
`final` as written, so a label keyed to turn 37 still names its event. The suffix is
reserved under `sessions/`: a native transcript named that way is never read by a reader.

The corpus also scores the rule binder, the text reading that binds a rule to a catalog
entry. `rules-zoo.json` beside `labels.yaml` holds synthetic rule sections, every line
labelled with the catalog detector it should bind, or null; `score_binding()` binds each
section as a rule file's section binds and compares. A false bind is a failure at any
count, because a rule bound to the wrong detector is measured wrongly. On the shipped zoo,
recall is also held by `BINDING_RECALL_FLOOR`, the recall the shipped binder measured, which
only goes up; any other zoo's recall is reported and holds nothing.
"""
import hashlib
import json
import os

from .declarative import DeclarativeError, load
from .events import Hit, Session  # noqa: F401  - Hit is named in the docstring's contract
from .readers import iter_file_sessions
from .registry import DEFAULT, fold_map, run
from . import rules as _rules

__all__ = ["CorpusError", "Score", "DEFAULT_FLOOR", "corpus_dir", "load_corpus",
           "load_events", "read_events", "score_corpus", "score_examples", "validity",
           "validity_table", "below_floor", "scores_as_dict"]

#: The floor `ruleprobe corpus` fails under. It is a CI gate for this repository, not a
#: runtime failure for a user: nothing in `ruleprobe report` reads it.
DEFAULT_FLOOR = 0.9

#: The corpus that ships with the package. `corpus_dir()` is how to find it.
CORPUS_DIRNAME = "corpus"
LABELS_FILE = "labels.yaml"
SESSIONS_DIRNAME = "sessions"
#: The suffix of an event-schema corpus session, read by `load_events` and never by a reader.
EVENTS_SUFFIX = ".events.jsonl"
#: The `runtime` a session read by `load_events` carries.
EVENTS_RUNTIME = "events"

_LABEL_KEYS = ("at", "fire", "near", "note")
_SESSION_KEYS = ("session", "note", "labels")

#: The rules zoo the binder is scored on, beside `LABELS_FILE`.
ZOO_FILE = "rules-zoo.json"
#: The binding recall the shipped binder measured on the shipped zoo, rounded down to two
#: places. `corpus` fails under it on that zoo alone, known by `SHIPPED_ZOO_SHA256`. It is a
#: ratchet, not a bar: a binder or catalog change that raises recall raises it in the same
#: change, and the suite says when it is stale.
BINDING_RECALL_FLOOR = 0.65
#: The sha256 of the shipped zoo's bytes. A zoo with other bytes - a corpus of your own, or
#: the shipped one edited - gets no recall floor; a change to the shipped zoo updates this.
SHIPPED_ZOO_SHA256 = "88da7e35438babf01e17fcd94ffae694ec684d77eb80fca23de8e20b69226ffc"
_ZOO_KEYS = ("about", "items")
_ITEM_KEYS = ("id", "kind", "heading", "heading_label", "lines")


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
    return _shipped_dir()


def _shipped_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CORPUS_DIRNAME)


def event_key(event):
    """The key a hit on `event` would carry. A tool use is keyed by its id; anything else
    by its turn alone, because a hit on the session does not name an event."""
    if event.get("kind") == "tool_use" and event.get("id"):
        return "%s:%s" % (event.get("turn", 0), event.get("id"))
    return "%s:-" % event.get("turn", 0)


def hit_key(hit):
    return "%s:%s" % (hit.turn, hit.tool_use_id or "-")


def read_events(text, path="<string>"):
    """The events in an event-schema session's text, one JSON object per non-blank line.

    Each is kept as written - `turn` and `final` are never re-derived - and only its shape is
    checked: an object with a string `kind` and an integer `turn`. Raises `CorpusError`, with
    the line, for anything else.
    """
    events = []
    for no, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise CorpusError("%s:%d: not JSON: %s" % (path, no, exc))
        if not isinstance(event, dict):
            raise CorpusError("%s:%d: an event is a JSON object" % (path, no))
        turn = event.get("turn")
        if not isinstance(event.get("kind"), str) or not isinstance(turn, int) \
                or isinstance(turn, bool):
            raise CorpusError("%s:%d: an event carries a string kind and an integer turn"
                              % (path, no))
        events.append(event)
    return events


def load_events(path):
    """One `<name>.events.jsonl` corpus session as a `Session`, its id the file name without
    the suffix and its runtime `EVENTS_RUNTIME`. Raises `CorpusError`."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusError("%s: cannot read: %s" % (path, exc))
    events = read_events(text, path)
    if not events:
        raise CorpusError("%s: holds no event" % path)
    name = os.path.basename(path)
    return Session(name[:-len(EVENTS_SUFFIX)], "", EVENTS_RUNTIME, events, path)


def _event_session_paths(sessions_dir):
    """Every `.events.jsonl` under `sessions_dir`, in path order, as the readers walk."""
    found = []
    for directory, _dirs, files in os.walk(sessions_dir, followlinks=True):
        for name in files:
            if name.endswith(EVENTS_SUFFIX):
                found.append(os.path.join(directory, name))
    return sorted(found)


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
    # An event-schema file ends in `.jsonl` too, so the readers see it; it is theirs to skip
    # and `load_events`' to read.
    # A label names its session by file name, so two files of one name in different
    # subdirectories are refused rather than one silently replacing the other, and two
    # files carrying one session id are both read.
    by_name = {}
    sessions = [s for s in iter_file_sessions(root=sessions_dir)
                if not s.path.endswith(EVENTS_SUFFIX)]
    sessions.extend(load_events(p) for p in _event_session_paths(sessions_dir))
    for session in sessions:
        name = os.path.basename(session.path)
        if name in by_name:
            raise CorpusError("%s: two session files are named %s under %s/"
                              % (path, name, SESSIONS_DIRNAME))
        by_name[name] = session
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
    folds = (registry.fold_map() if hasattr(registry, "fold_map")
             else fold_map(getattr(registry, "renamed", None)))
    labels = []
    for labelled in corpus:
        fire, near = _folded(labelled.fire, folds), _folded(labelled.near, folds)
        # A label may already give one id both lists at one key; only an overlap the fold
        # made is refused.
        before = set((folds.get(did, did), key)
                     for did in set(labelled.fire) & set(labelled.near)
                     for key in labelled.fire[did] & labelled.near[did])
        for detector_id in sorted(set(fire) & set(near)):
            both = set(key for key in fire[detector_id] & near[detector_id]
                       if (detector_id, key) not in before)
            if both:
                raise CorpusError(
                    "%s is labelled both fire and near at %s in %s once renamed ids are folded"
                    % (detector_id, ", ".join(sorted(both)), labelled.name))
        labels.append((labelled, fire, near))
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


# --- binding -----------------------------------------------------------------------------


class Binding(object):
    """The binder's tally over the rules zoo.

    `entries` is `{detector_id: Score}` for every catalog entry the binder can bind. Per
    labelled line, the heading one of them: a positive is the entry its label names, a true
    positive one a sentence starting on that line bound as labelled, a false positive one it
    bound unlabelled - a false bind - and a false negative a labelled one it did not bind.
    `false_binds` and `misses` name those as `(section id, detector id)` pairs, in zoo order. `outside` counts the labels naming a detector no
    catalog entry binds yet: no binder can meet them, so none is scored on them.
    `recall_floor` is `BINDING_RECALL_FLOOR` for the shipped zoo and None for any other.
    """

    __slots__ = ("entries", "false_binds", "misses", "sections", "labels", "outside",
                 "recall_floor")

    def __init__(self, entries, recall_floor=None):
        self.entries = entries
        self.false_binds = []
        self.misses = []
        self.sections = 0
        self.labels = 0
        self.outside = 0
        self.recall_floor = recall_floor

    @property
    def total(self):
        whole = total(self.entries)
        whole.source = "zoo"
        return whole


def load_zoo(directory=None):
    """The rules zoo's items, a list of sections, or None when a corpus directory of your
    own holds no `ZOO_FILE`. The shipped corpus always holds one, so its absence there is a
    `CorpusError`, as is anything in the file that is not a labelled section.

    An item is `{"id", "heading", "lines": [[text, label], ...]}`, with an optional
    `heading_label` when the heading states a rule itself and an optional `kind`; a label
    is a detector id or null.
    """
    loaded = _read_zoo(directory)
    return None if loaded is None else loaded[0]


def _read_zoo(directory=None):
    """`(items, sha256 of the file's bytes)` for `load_zoo`, or None."""
    base = corpus_dir(directory)
    path = os.path.join(base, ZOO_FILE)
    if not os.path.isfile(path):
        if os.path.normcase(base) == os.path.normcase(_shipped_dir()):
            raise CorpusError("%s: the shipped corpus has no rules zoo" % path)
        return None
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CorpusError("%s: cannot read: %s" % (path, exc))
    if not isinstance(document, dict) or not isinstance(document.get("items"), list):
        raise CorpusError("%s: expected an object with an items list" % path)
    _only(document, _ZOO_KEYS, path, "zoo")
    seen = set()
    for item in document["items"]:
        _check_item(item, seen, path)
    return document["items"], hashlib.sha256(raw).hexdigest()


def _check_item(item, seen, path):
    if not isinstance(item, dict):
        raise CorpusError("%s: a zoo item is an object" % path)
    _only(item, _ITEM_KEYS, path, "zoo item")
    ident = item.get("id")
    if not isinstance(ident, str) or not ident or ident in seen:
        raise CorpusError("%s: every zoo item has an id of its own; %r is not one"
                          % (path, ident))
    seen.add(ident)
    heading = item.get("heading")
    if not isinstance(heading, str) or not heading.strip() or "\n" in heading:
        raise CorpusError("%s: zoo item %s has no one-line heading" % (path, ident))
    lines = item.get("lines")
    if not isinstance(lines, list) or not lines or not all(
            isinstance(line, list) and len(line) == 2 and isinstance(line[0], str)
            and _is_label(line[1]) for line in lines):
        raise CorpusError("%s: zoo item %s needs lines of [text, detector id or null]"
                          % (path, ident))
    if not _is_label(item.get("heading_label")):
        raise CorpusError("%s: zoo item %s: heading_label is a detector id or null"
                          % (path, ident))


def _is_label(value):
    return value is None or (isinstance(value, str) and bool(value))


def _zoo_section(item):
    """`(heading, paragraphs)` for one zoo item, as `rules` parses the section it writes: a
    heading and the item's lines joined by newlines, so plain lines form one paragraph and
    a `- ` line is a list item."""
    body = "## %s\n\n%s\n" % (item["heading"], "\n".join(text for text, _l in item["lines"]))
    units = _rules._units(body)
    if len(units) != 1 or not units[0][2]:
        raise CorpusError("zoo item %s is not one rule section" % item["id"])
    return units[0][0], units[0][3]


def _attributed(item, heading, paragraphs):
    """`[set of detector ids]`, one per labelled unit of `item` - its heading, then each
    line - holding what the binder bound through a sentence starting there. The binds are
    the binder's own (`rules._binding`), each detector the entry lists placed by the
    paragraph and offset of the sentence that bound it, against each line's own normalized
    text found in turn in its paragraph's."""
    lines = [text for text, _label in item["lines"]]
    starts, cursor = {}, 0
    for index, paragraph in enumerate(paragraphs):
        text, offset = _rules._normalize(paragraph), 0
        while cursor < len(lines) and offset <= len(text):
            own = _rules._normalize(lines[cursor])
            if not own:
                cursor += 1
                continue
            found = text.find(own, offset)
            if found < 0:
                break
            starts.setdefault(index, []).append((found, cursor))
            offset, cursor = found + len(own), cursor + 1
    out = [set() for _unit in range(len(lines) + 1)]
    entry, binds = _rules._binding(item["id"], ZOO_FILE, heading, paragraphs)
    listed = set(entry.detectors) if entry.state == "measured" else set()
    for sentence, detector_id in binds:
        if detector_id not in listed:
            continue
        unit = 0
        if sentence.paragraph >= 0:
            placed = [line for start, line in starts.get(sentence.paragraph, [])
                      if start <= sentence.start]
            if not placed:
                raise CorpusError("zoo item %s: a bound sentence is on no line of it"
                                  % item["id"])
            unit = placed[-1] + 1
        out[unit].add(detector_id)
    unplaced = listed - set().union(*out)
    if unplaced:
        raise CorpusError("zoo item %s: the binder listed %s with no sentence to place"
                          % (item["id"], ", ".join(sorted(unplaced))))
    return out


def score_binding(directory=None, zoo=None):
    """The binder over the rules zoo (`load_zoo`), as a `Binding`, or None when there is no
    zoo. Each item binds as a section of a rule file binds, against the shipped catalog and
    fold map, and a label naming a retired id counts under its current one. Only the shipped
    zoo, known by its bytes, carries a recall floor; `zoo` passed as items carries none."""
    floor = None
    if zoo is None:
        loaded = _read_zoo(directory)
        if loaded is None:
            return None
        zoo, digest = loaded
        if digest == SHIPPED_ZOO_SHA256:
            floor = BINDING_RECALL_FLOOR
    items = zoo
    folds = fold_map()
    ids = [detector.id for detector in _rules.catalog_detectors(folds)]
    catalog = set(ids)
    binding = Binding(dict((i, Score(i, source="zoo")) for i in ids), floor)
    for item in items:
        heading, paragraphs = _zoo_section(item)
        units = [item.get("heading_label")] + [label for _text, label in item["lines"]]
        binding.sections += 1
        binding.labels += len(units) - ("heading_label" not in item)
        for label, bound in zip(units, _attributed(item, heading, paragraphs)):
            wanted = set([folds.get(label, label)]) if label else set()
            expected = wanted & catalog
            binding.outside += len(wanted - catalog)
            for detector_id in sorted(expected | bound):
                score = binding.entries[detector_id]
                if detector_id in expected:
                    score.positives += 1
                    if detector_id in bound:
                        score.tp += 1
                    else:
                        score.fn += 1
                        binding.misses.append((item["id"], detector_id))
                else:
                    score.fp += 1
                    binding.false_binds.append((item["id"], detector_id))
    return binding


def binding_failures(binding, recall_floor=None):
    """Why the binder fails the corpus gate, one line each, or `[]`: any false bind, and
    recall under `recall_floor`, the binding's own when not given, and none when that is
    None. No zoo is no failure, as an unscored detector is none."""
    if binding is None:
        return []
    if recall_floor is None:
        recall_floor = binding.recall_floor
    out = []
    if binding.false_binds:
        out.append("%d false bind(s): %s" % (len(binding.false_binds), ", ".join(
            "%s %s" % pair for pair in binding.false_binds)))
    whole = binding.total
    if recall_floor is not None and whole.recall < recall_floor:
        out.append("binding recall %.2f is under the recorded %.2f"
                   % (whole.recall, recall_floor))
    return out


def _binding_row(score):
    out = score.as_dict()
    out["precision"] = round(score.precision, 4) if score.tp + score.fp else None
    out["recall"] = round(score.recall, 4) if score.tp + score.fn else None
    out.pop("f1", None)
    out.pop("negatives", None)
    return out


def binding_as_dict(binding, recall_floor=None):
    """The binder's figures as plain data, for `corpus --json`, or None with no zoo. A
    precision or recall with nothing to divide is null rather than a number, and so is the
    recall floor of a zoo that has none."""
    if binding is None:
        return None
    if recall_floor is None:
        recall_floor = binding.recall_floor
    return {"zoo": ZOO_FILE, "sections": binding.sections, "labels": binding.labels,
            "outside_catalog": binding.outside, "recall_floor": recall_floor,
            "entries": dict((did, _binding_row(s)) for did, s in binding.entries.items()),
            "total": _binding_row(binding.total),
            "false_binds": [{"section": s, "detector": d} for s, d in binding.false_binds],
            "misses": [{"section": s, "detector": d} for s, d in binding.misses],
            "failures": binding_failures(binding, recall_floor)}


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


_BIND_HEAD = "%-38s%5s%5s%5s%5s%7s%8s  note"
_BIND_ROW = "%-38s%5d%5d%5d%5d%7s%8s  %s"


def binding_table(binding, recall_floor=None):
    """The binder section `ruleprobe corpus` prints under the detector table: one row per
    catalog entry, `pos` the zoo sections labelled with it, and a total held to no false
    bind and, on the shipped zoo, to its recall floor."""
    if binding is None:
        return "binder: this corpus has no %s, so binding is not scored" % ZOO_FILE
    if recall_floor is None:
        recall_floor = binding.recall_floor
    head = _BIND_HEAD % ("catalog entry", "pos", "tp", "fp", "fn", "prec", "recall")
    rule = "-" * len(head)
    lines = ["binder over the rules zoo: %d sections, %d labels"
             % (binding.sections, binding.labels), head, rule]
    for did in sorted(binding.entries):
        score = binding.entries[did]
        lines.append(_bind_row(did[:38], score, "false bind" if score.fp else ""))
    lines.append(rule)
    lines.append(_bind_row("total", binding.total, "no recall floor" if recall_floor is None
                           else "recall floor %.2f" % recall_floor))
    if binding.outside:
        lines.append("%d label(s) name a detector no catalog entry binds yet; not scored"
                     % binding.outside)
    return "\n".join(lines)


def _bind_row(name, score, note):
    precision = "%.2f" % score.precision if score.tp + score.fp else "-"
    recall = "%.2f" % score.recall if score.tp + score.fn else "-"
    return (_BIND_ROW % (name, score.positives, score.tp, score.fp, score.fn, precision,
                         recall, note)).rstrip()


def validity_note(scores, detector_id):
    """The one-line annotation `ruleprobe report --validity` puts beside a detector."""
    score = scores.get(detector_id) if scores else None
    if score is None:
        return "not in the corpus"
    if not score.scored:
        return "no examples"
    return "p=%.2f r=%.2f" % (score.precision, score.recall)
