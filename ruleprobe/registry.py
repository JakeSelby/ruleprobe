# SPDX-License-Identifier: MIT
"""Detectors, the registry that holds them, and `run()`.

A detector is one rule, one observable, one function over a session's events and the parse
of its shell commands. `run()` is the whole engine: it parses once, calls each detector, and
returns `{detector_id: [Hit, ...]}` with the detectors that found nothing omitted.

A detector that raises is skipped, so one bad pattern cannot cost a session its record.
`run(..., strict=True)` re-raises instead, which is how a corpus is tested.
"""
from .events import Hit
from .shell import analyse

#: The contract's schema version: what 0.2.0 writes, and every version it can read (AD-9).
SCHEMA_VERSION = 2
KNOWN_SCHEMA_VERSIONS = (1, 2)

__all__ = ["Detector", "Registry", "DEFAULT", "run", "register_compiler", "from_spec"]

#: The shapes of transcript a detector reads. A registry entry naming anything else is a
#: typo, not a new kind, so `Registry.add` refuses it.
EVENT_KINDS = frozenset(("bash", "write", "agent-brief", "assistant-final", "session",
                         "tool_use", "assistant_text"))


class Detector(object):
    """One rule, one observable, one function over the event list and its parse.

    - `id` - stable, `rule/observable`; it is what a ledger row is written under.
    - `rule` - the rule the observable belongs to, with no slash in it.
    - `event` - which shape of transcript it reads, one of `EVENT_KINDS`. Advisory: every
      detector is handed the whole event list either way.
    - `fn` - `fn(events, ctx) -> [(turn, tool_use_id), ...]`.
    - `gate` - when the detector only applies under some configuration: either a
      `(dimension, allowed_variants_or_None)` pair read against the `stances` dict, or a
      callable taking that dict and returning a bool. `None` is always on.
    - `examples` - optional, an `Examples(fire, skip)` of minimal cases the detector says
      it should and should not fire on, scored by `ruleprobe.validity`. A declarative
      detector fills this from its `examples:` block; `None` means nobody said.
    """

    __slots__ = ("id", "rule", "event", "fn", "gate", "examples")

    def __init__(self, id, rule, event, fn, gate=None, examples=None):
        self.id = id
        self.rule = rule
        self.event = event
        self.fn = fn
        self.gate = gate
        self.examples = examples

    def enabled(self, stances):
        if self.gate is None:
            return True
        if callable(self.gate):
            return bool(self.gate(stances or {}))
        dimension, allowed = self.gate
        variant = (stances or {}).get(dimension)
        if not variant or variant == "off":
            return False
        return allowed is None or variant in allowed

    def __repr__(self):
        return "Detector(%r, rule=%r, event=%r)" % (self.id, self.rule, self.event)


class Registry(object):
    """An ordered set of detectors, keyed by id, plus the renames folded on read.

    A registry is mutable and cheap: build your own rather than mutating `DEFAULT` when you
    want the six generic detectors left alone.
    """

    def __init__(self, detectors=None, renamed=None):
        self._order = []
        self._by_id = {}
        self.renamed = dict(renamed or {})
        for detector in detectors or ():
            self.add(detector)

    def add(self, detector):
        """Register `detector` and return it. An id already present is replaced in place, so
        a later registration overrides an earlier one without reordering the report."""
        if not isinstance(detector, Detector):
            raise TypeError("not a Detector: %r" % (detector,))
        if not detector.id or not detector.rule or "/" in detector.rule:
            raise ValueError("a detector needs an id and a slash-free rule: %r" % (detector,))
        if detector.event not in EVENT_KINDS:
            raise ValueError("unknown event kind %r; one of %s"
                             % (detector.event, ", ".join(sorted(EVENT_KINDS))))
        if not callable(detector.fn):
            raise TypeError("detector %s has no callable fn" % detector.id)
        if detector.id in self._by_id:
            self._order[self._order.index(self._by_id[detector.id])] = detector
        else:
            self._order.append(detector)
        self._by_id[detector.id] = detector
        return detector

    def extend(self, detectors):
        for detector in detectors:
            self.add(detector)
        return self

    def rename(self, old_id, new_id):
        """Record that `old_id` became `new_id`, and drop `old_id` if it is still here.

        A stored row is never rewritten for a rename; a report folds this map on every read
        instead, so one measurement stays one line and one series across it. Leaving the old
        detector registered as well would double every hit into the successor and keep the
        old id on the table for ever as an `unobserved` line, so the rename removes it.
        """
        self.renamed[old_id] = new_id
        if old_id != new_id:
            self.remove(old_id)
        return self

    def get(self, detector_id):
        return self._by_id.get(detector_id)

    def ids(self):
        return [d.id for d in self._order]

    def remove(self, detector_id):
        detector = self._by_id.pop(detector_id, None)
        if detector is not None:
            self._order.remove(detector)
        return detector

    def copy(self):
        return Registry(self._order, self.renamed)

    def __iter__(self):
        return iter(list(self._order))

    def __len__(self):
        return len(self._order)

    def __contains__(self, detector_id):
        return detector_id in self._by_id

    def __repr__(self):
        return "Registry(%d detectors)" % len(self._order)

    @classmethod
    def from_entry_points(cls, group="ruleprobe.detectors", base=None):
        """A registry of `base` (default: the shipped detectors) plus everything installed
        packages advertise under `group`.

        An entry point may load a `Detector`, an iterable of them, or a callable taking the
        registry and registering whatever it likes. One that raises is skipped: a broken
        third-party plugin costs its own detectors and nothing else.
        """
        registry = (base or DEFAULT).copy()
        for entry in _entry_points(group):
            try:
                loaded = entry.load()
            except Exception:
                continue
            try:
                if isinstance(loaded, Detector):
                    registry.add(loaded)
                elif callable(loaded):
                    loaded(registry)
                else:
                    registry.extend(loaded)
            except Exception:
                continue
        return registry


def _entry_points(group):
    """`group`'s entry points, across the two importlib.metadata APIs (3.9 and 3.10+)."""
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - Python 3.7 and earlier
        return []
    try:
        found = metadata.entry_points()
    except Exception:  # pragma: no cover - a broken distribution on the path
        return []
    if hasattr(found, "select"):
        return list(found.select(group=group))
    return list(found.get(group, []))


#: The detectors that ship with the package: generic enough to mean the same thing in any
#: repository. Anything about one project's own rules belongs in that project's registry.
DEFAULT = Registry()


# --- extension point: declarative detectors -----------------------------------------
#
# A detector written as data rather than as Python - a pattern, a tool name and a rule id in
# a config file - arrives here: a compiler registered per spec `kind` turns a dict into a
# `Detector`, and nothing else in this module knows what the dict holds.
# `ruleprobe.matchers` registers the `declarative` kind, and a caller may register another.

COMPILERS = {}


def register_compiler(kind, compiler):
    """Teach `from_spec` how to turn a `{"kind": kind, ...}` dict into a `Detector`."""
    COMPILERS[kind] = compiler
    return compiler


def from_spec(spec):
    """A `Detector` from a declarative spec dict, via its registered compiler."""
    kind = (spec or {}).get("kind")
    compiler = COMPILERS.get(kind)
    if compiler is None and kind is None:
        from . import matchers  # noqa: F401  - registers the default compiler
        compiler = COMPILERS.get(matchers.SPEC_KIND)
    if compiler is None:
        raise NotImplementedError(
            "no compiler for detector spec kind %r; the shipped one is %r, and a caller "
            "may register another with register_compiler()" % (kind, "declarative"))
    return compiler(spec)


def run(events, stances=None, *, registry=DEFAULT, strict=False, errors=None):
    """Every enabled detector over one session's events.

    Returns `{detector_id: [Hit, ...]}`, omitting the detectors that found nothing.
    `stances` is a dimension to variant dict, e.g. `{"commits": "conventional"}`, read by
    gated detectors only. `errors`, when a list is passed, collects
    `{"detector": id, "error": exception name}` for every detector that raised.
    """
    try:
        ctx = analyse(events)
    except Exception as exc:  # pragma: no cover - analyse() defends its own input
        if strict:
            raise
        if errors is not None:
            errors.append({"detector": "analysis", "error": type(exc).__name__})
        return {}  # a session keeps its record even when its transcript is odd
    out = {}
    for detector in registry:
        if not detector.enabled(stances):
            continue
        try:
            raw = detector.fn(ctx.events, ctx)
        except Exception as exc:
            if strict:
                raise
            if errors is not None:
                errors.append({"detector": detector.id, "error": type(exc).__name__})
            continue
        if raw:
            out[detector.id] = [Hit(detector.id, turn, tool_use_id)
                                for turn, tool_use_id in raw]
    return out


# Imported last, and by the module that owns the registry rather than the other way round,
# so `from ruleprobe.registry import DEFAULT` is always a populated registry.
from .detectors import common as _common  # noqa: E402

_common.register(DEFAULT)
