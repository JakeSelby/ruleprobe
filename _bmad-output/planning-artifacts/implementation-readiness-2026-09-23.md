---
title: 'Implementation readiness: ruleprobe 0.2.0'
type: implementation-readiness
skill: bmad-sprint-planning (intent readiness, headless)
created: '2026-09-23'
gate: CONCERNS
inputs:
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md
  - _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/epics.md (draft, first independent read)
  - docs/bmad-governance.md
  - https://github.com/JakeSelby/ruleprobe/issues/19
code_read_at: 12ababe
---

# Implementation readiness: ruleprobe 0.2.0

**Gate: CONCERNS.** The plan is buildable in shape. Every in-scope FR has a story, every open PRD
question but one has a decision item that gates the work it blocks, and dependencies are acyclic.
Two acceptance criteria would bake the wrong semantics into the one planned break, and four gaps
would make a builder invent a decision. Fix them in `epics.md` before filing; no spine or PRD
rewrite is needed except where noted.

No sprint-status file was generated (readiness intent only). No UX document exists by design; no
story needs one beyond the CLI shapes noted in M3.

## Inventory

- PRD 2026-09-23 with addendum and validation report (proposed, 0.2.0 scope in §8).
- Architecture spine 2026-09-23, status final, AD-1 to AD-14, with three reviews and a validation
  report.
- Brief 2026-09-23 and competitive research 2026-09-23 (context, not traced here).
- Epics draft: 7 epics, 32 items (15 stories, 3 tasks, 3 spikes, 10 decisions, 1 existing bug).
- Code at `12ababe`: every file, function and test module the stories cite exists
  (`ENTRY_KEYS`, `compile_detector`, `_entries`, `_compile_entries`, `read_rule_file`,
  `load_rules_dir`, `measure`, `folded_rules`, `corpus --corpus DIR`, `near` labels,
  `tests/test_release.py`, `CHANGELOG.md`, `scripts/release_preflight.py`).

## What passes

- **FR coverage.** 15 of 15 in-scope FRs map to at least one story. FR-34 sits in a proposed epic
  gated by decision 7.1.
- **Decisions before what they gate.** 1.1 before 1.4 and 1.5; 1.2 before 1.8; 1.3 before 1.9;
  2.1 and 2.3 before 2.6; 2.2 before 2.4; 3.1 before 3.4; 3.2 before 3.5; 5.1 before 5.2; 6.1 and
  7.1 before what they gate.
- **Dependencies.** Acyclic. No forward dependency within an epic; cross-epic edges point only at
  earlier epics.
- **Envelope.** No story adds a model call to `report`, a prescription, a report card, triage, a
  hook or anything hosted. 7.2 lives outside the core install, and 1.10 makes the no-dependency,
  no-network, no-write promises tests.
- **AD-9 package data.** 1.6 puts the fold map and shipped ids in `ruleprobe/contract_data.py` as
  literals, with a literal-only test and a no-file-read test.
- **AD-11 undecided count.** 2.5 carries `undecided` in the row; 2.6 prints it. The count exists;
  its arithmetic is wrong (H1).

## Findings

Counts: 2 high, 4 medium, 8 low.

### High

**H1. Story 2.4 AC6 contradicts AD-11 on where `undecided` sits.**
AD-11 says an opportunity whose `followed` is undecided "is left out of both counts and counted as
`undecided`". Both counts are `opportunities` and `followed`. So `opportunities` excludes undecided,
and AD-11's identity `hits = opportunities - followed` holds as written: under AD-4 an undecided
`absent` turn yields no hit. AC6 instead asserts `hits = opportunities - followed - undecided`,
which is true only if `opportunities` includes undecided. Built to AC6, the row either
double-subtracts or deflates the rate by counting undecided in the denominator, which is the
over-count AD-4 forbids. The row's `compliance` shape is frozen for the 0.2 series (FR-31), so
this cannot be fixed later without a break. Open question 14 in `epics.md` says AD-11 is silent on
this; it is not.
*Fix:* restate 2.4 AC6 as AD-11's identity with `opportunities` excluding undecided, and state in
2.5 AC1 that `N` excludes `U`. Close epics OQ14. Skill: `bmad-create-epics-and-stories` (edit).

**H2. Story 1.7 proves less than AD-4 requires, and 2.4 depends on the rest.**
1.7 adopts issue #19's "Done when" as its acceptance criteria. #19 asks for undecided over a
skipped command and regression tests for `command` and `git` under `not` and `absent`. AD-4 asks
for more, all of it part of the one break: `env` keys as segment matchers and `regex` and
`unparsed` exempt; three-valued `any` and `all`; `not` of undecided is undecided; an undecided
`when` yields no hit; `order` needs `first` and `then` both true; an `absent` scope with an
undecided candidate and no true one yields no hit. None of that is proven by an AC. 2.4's compiled
opportunities read undecided straight through these combinators, so a gap here surfaces as wrong
compliance counts.
*Fix:* give 1.7 ACs of its own that cite AD-4's truth table, with tests for `env`, `any`, `all`,
`order` and an undecided `when`. Leave #19's prose untouched and add the extra criteria in the
story file. Skill: `bmad-create-epics-and-stories` (edit).

### Medium

**M1. Story 3.5 adds a module without the AD-1 update.**
`ruleprobe/detectors/catalog.py` is new, and `rules` would import it (and it `matchers`). AD-1
says a new module takes its place in the graph in the change that adds it, with the spine updated.
1.6 does this for `contract_data.py`; 3.5's file list omits it. The catalog's literal form is
sound: AD-9 forbids a file read when a `Registry` is built, and `Bundle.registry` builds one, so a
YAML catalog read at bundle time would breach it. But the spine should say so rather than leave it
to a story assumption (epics OQ13).
*Fix:* add the spine's AD-1 graph, and one line under AD-9 or AD-12 on catalog storage, to 3.5's
files. Skill: `bmad-architecture` (update) for the spine line.

**M2. The compliance map does not fold under renames.**
1.6 routes `rules` through the one fold function. 2.5 and 2.6 key `compliance` by detector id and
never say it folds. A renamed detector with opportunities would split its compliance across two
ids while its hits merge.
*Fix:* add an AC to 2.6 (or 1.6) that `compliance` folds through the same function and sums.

**M3. `explain` and `label` have no recorded inputs.**
AD-13 fixes the subcommand names; nothing fixes their arguments. 4.2 starts from "a hit key from
explain", but a key `"<turn>:<tool_use_id>"` is unique only within a session, and label must
re-read the transcript to recover the event. 4.2 also does not say how the `near` label joins a
`labels.yaml` that already exists in the named directory, and the package has a YAML parser but no
writer. A builder would invent the session selector, the file name and the merge rule.
*Fix:* record the CLI form (session id, detector id, key, `--corpus DIR`, name) and the
labels-file rule (create, or append in the closed subset) in 4.1 and 4.2. The spine's AD-13
already marks the CLI form as an assumption.

**M4. Story 1.8's criteria cover a subset of FR-30's declared call shapes.**
Named in FR-30 but absent from every 1.8 AC: the event fields the harness reads (`kind`, `turn`,
`id`, `name`, `input`, `text`, `final`, `tool_use_id`, `tool_name`); `gate` as `None` or a
`(dimension, variants_or_None)` pair; `MARKER_RE` group 1 as an index into `.heredocs`; the shapes
of `input_of`, `text_of`, `normalise`, `below_floor`, `scores_as_dict` and `validity_table`; and
`ruleprobe.__file__` locating `corpus/` from a zip. AC8's "any removal or signature change fails"
holds only for what the test exercises. SM-4's target is zero breakages.
*Fix:* one AC per missing item, or one AC that walks FR-30's list verbatim.

### Low

- **L1.** FR-29 says a fold entry persists "with the rows". AD-9 reads that as `report_data`
  emitting the map, and 1.6 AC4 follows. A ledger of `measure()` rows, which is what UJ-3 stores,
  carries none. Shipped renames still fold through `contract_data.py`. Confirm the spine's reading.
- **L2.** AD-9 says any top-level `version` that is not a known schema version is a finding. 1.4
  AC3 covers only a value above the highest known, not `0`, a string or a float.
- **L3.** The epic list says later stories write "schema version 2" before decision 1.1 has fixed
  the type or the value (PRD Q9).
- **L4.** FR-32 says file tools reach detectors under the shared names. AD-3 lets a tool with no
  exact twin stay native, and 5.2 AC2 follows the spine. The PRD consequence is only partly
  provable; amend FR-32 or note the gap in 5.1.
- **L5.** PRD Q5 (compliance by position stays out) has no decision item. It must be confirmed
  before scope freezes; add it to 6.1 or a one-line decision.
- **L6.** Output shape: FR-19 requires table numbers to equal `report_data` fields, but no story
  names the rate field FR-22 suppresses. 3.3 AC3 moves the coverage block into `--json`, where
  today it goes to stderr (`ruleprobe/cli.py:193`); that is a result-shape change and belongs in
  1.9's break list.
- **L7.** Spike 4.3 traces to maintainer decision 6 and SM-8, not to an FR. It is marked proposed
  and, if confirmed, gates the release on hand sampling. Confirm or drop before 6.2 (epics OQ15).
- **L8.** 1.8 AC7 has a test compare the README with the contract list; AD-9 says the README
  "renders from" it. Tagged as an assumption; accept it or amend AD-9.

## Next

1. Edit `epics.md` for H1, H2, M2, M3, M4 and L2, L3, L6.
2. Run `bmad-architecture` update for M1's spine line and, if accepted, L1 and L8.
3. Rerun this gate. On PASS, run `bmad-sprint-planning` with the sprint-planning intent.

The shared rules ask for a memlog line per decision; this run was limited to writing this one file,
so none was written.
