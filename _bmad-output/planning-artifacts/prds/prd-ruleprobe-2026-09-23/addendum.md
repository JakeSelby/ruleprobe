---
title: "PRD addendum: ruleprobe"
created: 2026-09-23
updated: 2026-09-23
---

# Addendum: ruleprobe PRD

Depth the PRD points at and does not carry: rejected alternatives, the harness surface in detail, and
mechanism notes for the architecture spine (#14). Reference numbers point at the source appendix of the
[research artifact](../../research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md).

## Rejected alternatives

- **A model inside `ruleprobe report`.** Rejected (maintainer decision 2, 2026-09-23). It would end
  deterministic output (NFR-3) and put a third-party judgment inside every number. The literature
  demotes a model judge to an advisor behind a deterministic layer (refs 26, 27). No model path remains
  in ruleprobe: FR-34's drafting command was withdrawn on 2026-09-23 and moved to the judge library
  tracked in #21.
- **Closing the sixty-second gap with a model.** Rejected (maintainer decision 7). Section-level binding
  and a catalog do it deterministically. The trade-off: a catalog binds fewer rules than a model would,
  and the unbound ones stay visibly unmeasured.
- **A deprecation path for harness imports instead of declaring them.** Rejected (maintainer decision 4;
  brief review finding 1). Every name the harness imports is declared. The cost is a wider declared
  surface than a library of this size would choose; the alternative is a silent break in the one
  consumer that exists.
- **Leading with a Codex reader in 0.2.** Not needed. 0.1.0 already reads Codex rollouts
  (`ruleprobe/readers/codex.py`), which meets research recommendation 2. The 0.2 answer is a third
  reader, so the lead does not rest on a runtime the platforms already ingest (refs 17, 19).
- **Compliance by position in the session for 0.2.** Deferred (research recommendation 4; PRD §11 Q5).
  The strongest controlled result says position matters and file structure does not (ref 22, a single
  preprint). Compliance per opportunity comes first because position needs an opportunity to be
  positioned.
- **HTML report cards, cause triage, fixes, blocking hooks, hosted service.** Out (maintainer decision
  2). Each moves ruleprobe from instrument to doctor or platform, and each is served elsewhere.
- **Claiming first or only.** Rejected (maintainer decision 9; research recommendation 1).
  claude-md-doctor and RuleReceipt disprove it (refs 1, 2).

## The harness surface, re-derived

Read from `JakeSelby/agent-harness` `main` at `991b13e` on 2026-09-23 through the GitHub API, and read
again at `1307113` the same day for the PRD update; the four files are unchanged between them. A local
read-only checkout was behind `main`, so it was not used for this list. PRD FR-30 carries the declared
form with ruleprobe file references; it is re-derived before every release.

- [`policy/hooks/rule-detectors.py`](https://github.com/JakeSelby/agent-harness/blob/main/policy/hooks/rule-detectors.py)
  - Puts `lib/vendor/ruleprobe-0.1.0-py3-none-any.whl` on `sys.path` and imports from the zip.
  - `from ruleprobe import Registry, analyse, counts, run`. `analyse` and `counts` are re-exported.
  - `from ruleprobe.detectors import common`, then reads `common.SECRET_PATTERNS` and iterates
    `common.DETECTORS`, reading `.id`, `.rule`, `.event`, `.fn` and `.gate`.
  - `from ruleprobe.events import hit, input_of, text_of`.
  - `from ruleprobe.registry import Detector`, subclassed with `__slots__ = ()` and two properties,
    and constructed positionally with five arguments. `gate` is passed as a `(dimension, variants)`
    pair.
  - About ten detector functions of the form `fn(events, ctx)`. They read `ctx.bash` (each a `Parsed`,
    read for `.event`, `.command` and `.heredocs`) and `ctx.finals`, and iterate `events` for the
    fields `kind`, `turn`, `id`, `name`, `input`, `text`, `final`, `tool_use_id` and `tool_name`.
  - `hit(event)` and `hit(event, tool_use_id=False)`; one detector builds the
    `(turn, tool_use_id)` pair by hand.
  - `git_calls(parsed, ("commit",))` and `git_calls(parsed, ("add",))`, unpacked as 3-tuples;
    `MARKER_RE.match(value)` with group 1 indexing `parsed.heredocs`; `normalise(command)`.
  - `from ruleprobe.shell import MAX_COMMAND, MARKER_RE, SUB_PLACEHOLDER, git_calls, has_redirect,
    normalise, operands, pipelines, strip_heredocs`.
  - Calls `run(events, stances, registry=Registry(...), strict=..., errors=...)`, with the registry
    built as `Registry(<list>)` and no `renamed=`.
  - Defines its own `RENAMED` map. It does not pass it to `Registry`.
- [`policy/hooks/decisions.py`](https://github.com/JakeSelby/agent-harness/blob/main/policy/hooks/decisions.py)
  - Names the wheel file `ruleprobe-0.1.0-py3-none-any.whl`.
  - Opens it as a zip and reads `SECRET_PATTERNS` out of `ruleprobe/detectors/common.py` by syntax
    tree, to avoid the import cost inside a hook. A non-literal list, a moved module or a renamed name
    makes the harness stop sampling, which is its safe direction but still a break.
- [`scripts/detector_corpus.py`](https://github.com/JakeSelby/agent-harness/blob/main/scripts/detector_corpus.py)
  - `from ruleprobe.registry import Registry`, built from a list of detectors.
  - `ruleprobe.__file__`, to find `ruleprobe/corpus/` inside the wheel and extract it.
  - `from ruleprobe.declarative import load`, unpacked as `(document, lines)`.
  - `from ruleprobe.validity import Score, CorpusError, DEFAULT_FLOOR, below_floor, score_corpus,
    scores_as_dict, validity_table`; `Score(detector_id)` with `.add`, `.scored`, `.precision`,
    `.recall`, `.detector`; `score_corpus(registry=..., directory=...)`.
- [`bin/harness`](https://github.com/JakeSelby/agent-harness/blob/main/bin/harness) imports nothing from
  ruleprobe. It loads the harness's projected `rule-detectors.py` and takes the secret list from it. It
  reads `.rule` on each `DETECTORS` value. It folds renamed ids with its own `folded_rules`, reading the
  module's `RENAMED`, not ruleprobe's `report.folded_rules`. The validation report's statement that the
  harness passes `RENAMED` through `Registry` does not hold at `1307113`: the harness reimplements the
  fold instead. Folding is report logic, not detector logic, so AD-13 is not breached, but it is a second
  copy the persisted fold entries of FR-29 could replace.

Against the list recorded before this run, the re-derivation adds `ruleprobe.registry.Registry`, the
in-wheel corpus path, the positional `Detector` constructor and the zip import. The README's eight
declared names already cover the root `Registry` and `run`.

## Mechanism notes for the spine

These are candidate shapes, not decisions. The spine decides them.

- **Opportunity.** A declarative detector could name an `opportunity:` matcher beside `when:`. For
  `order` (`first`, `then`, `within`), each `first` match is an opportunity and a `then` inside the
  window is followed. For `absent` with `scope: turn`, each turn a trigger matches is an opportunity.
  A Python detector would need a second return value or a second function (PRD §11 Q10).
- **Schema version.** An integer key on each detector entry and each row, absent meaning 1, is the
  smallest form (PRD §11 Q9).
- **Fold map.** Implemented in memory in 0.1.0: `Registry(renamed=)` and `Registry.rename` hold it, and
  `report.folded_rules` applies it on read. The planned part is persistence: fold entries stored with
  the rows, so a ledger written under 0.1 still counts in a reader that did not build the registry. It
  may chain: a retired id may map to one that was itself renamed. The rename test compares a committed
  list of every shipped detector id with the default registry and its fold map.
- **Section-level binding.** Heading sections are the simpler split and match how most rule files are
  written; list items catch the one-line rules the RuleReceipt author's parse suggests are a minority
  of a file (ref 3, low). Both are open (PRD §11 Q2).
- **False positive to label.** The command takes a hit's key from the explain path and writes a
  one-session corpus file with that event and a `near` label. Every written string passes through
  `SECRET_PATTERNS` redaction first; review by a person is not the control.
- **Explain over stored rows.** A row holds counts only. The explain path names the re-run instead:
  `ruleprobe report` over the row's runtime and session id. Widening the row to carry hit keys was
  rejected in the update of 2026-09-23: it grows every stored ledger for a debugging path.

## Harness requirements that touch ruleprobe

From the [agent-harness PRD 2026-09-23](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/prds/prd-agent-harness-2026-09-23/prd.md)
§4.4: FR-19 (a detector or a reason for every rule), FR-20 (per-rule hit rate by repository and
variant), FR-21 (standalone instrument and a vendored pinned wheel), FR-22 (corpus floor in CI; corpus
agreement is not field accuracy), FR-67 (detectors for a developer's own rules without code; the share
of rules measured; proposing a detector from prose is planned (unscheduled) there). UJ-3 (Sam finds out
which rules fire) and SM-1 (four of five testers within a minute) are the harness-side mirror of this
PRD's UJ-1 and SM-1. AD-13 in its
[spine](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/architecture-spines/architecture-agent-harness-2026-09-23/ARCHITECTURE-SPINE.md)
fixes the relationship: the harness binds rules to detectors, vendors a pinned wheel and never forks.

This PRD maps them: FR-19 and FR-67 to FR-13 to FR-16; FR-20 to FR-17 and FR-18; FR-21 to NFR-5 and
FR-30; FR-22 to FR-23 and NFR-6.
