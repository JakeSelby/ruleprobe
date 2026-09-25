---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/addendum.md
  - _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md
  - docs/bmad-governance.md
  - https://github.com/JakeSelby/ruleprobe/issues/19
title: "Epics and stories: ruleprobe 0.2.0"
issue: 15
bmad_id: RP-S006
parent: RP-E001 (#10)
milestone: v0.2.0
status: draft
created: 2026-09-23
updated: 2026-09-25
---

# ruleprobe - Epic Breakdown

## Overview

This document breaks the ruleprobe 0.2.0 requirements into epics and stories. It derives from the
[PRD](prds/prd-ruleprobe-2026-09-23/prd.md), its [addendum](prds/prd-ruleprobe-2026-09-23/addendum.md)
and the [architecture spine](architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md).
No UX document exists; the CLI output shapes are in the PRD's FRs.

Scope is what PRD §8 puts in 0.2.0 (planned, v0.2.0), plus Epic 7 for FR-34, which the maintainer withdrew on
2026-09-23 and moved to #21; it is kept as the record. The planning corpus epic RP-E001 (#10) is not part of 0.2. Every item here is
proposed until it is filed with `scripts/bmad_issue_sync.py new`. Inferences carry `[ASSUMPTION: ...]`.

Amended 2026-09-25: Epics 8 to 15 for 0.3.0 and 0.4.0 follow the 0.2 record, under [0.3.0 and 0.4.0](#030-and-040).

## Requirements Inventory

### Functional Requirements

Status as the PRD gives it. "In" means PRD §8 puts it in 0.2.0; "held" means implemented in 0.1.0 and
touched in 0.2 only where the contract versions it.

- FR-1: The CLI and library read Claude Code transcripts under `~/.claude/projects/`. Held (implemented, 0.1.0).
- FR-2: The CLI and library read Codex rollouts under `~/.codex/sessions/`. Held (implemented, 0.1.0).
- FR-3: Every reader emits the five event kinds with the fields `ruleprobe/events.py` documents. Held (implemented, 0.1.0).
- FR-4: A runtime is added by one module with `ROOT`, `transcripts(root)`, `read(path)` and one `RUNTIMES` entry. Held (implemented, 0.1.0).
- FR-5: One shared shell parse splits a command into compounds, pipelines and segments. Held (implemented, 0.1.0).
- FR-6: `Detector(id, rule, event, fn, gate=None)` and `Registry`. Held (implemented, 0.1.0); gains an optional `opportunities` attribute under AD-11.
- FR-7: Detectors ship through the `ruleprobe.detectors` entry point group. Held (implemented, 0.1.0).
- FR-8: Six generic detectors, with a declarative twin hit for hit. Held (implemented, 0.1.0).
- FR-9: A failing detector costs only itself. Held (implemented, 0.1.0); extends to `opportunities` under AD-11.
- FR-10: Declarative detectors in the YAML subset or JSON. Held (implemented, 0.1.0); gains `schema_version` under FR-27.
- FR-11: Discovery from `.ruleprobe/detectors.yaml`, user config and rule-file front matter. Held (implemented, 0.1.0).
- FR-12: Event, combinator and session matchers. Held (implemented, 0.1.0); negation, `any`, `all`, `order` and `absent` over skipped commands implemented under #19, unreleased, shipping in v0.2.0.
- FR-13: Per-file binding classes each rule file as measured, dark or unmeasured. Held (implemented, 0.1.0).
- FR-14: The report states the share of rules measured. In (partial; share planned, v0.2.0).
- FR-15: Section-level binding splits one rule file into many rules with stable ids, on headings only (Q2, decided 2026-09-23). In (planned, v0.2.0).
- FR-16: A shipped catalog of declarative detectors for common rule shapes, bound by one anchored pattern on an exact-one match; a small set of six to eight shapes (Q3, decided 2026-09-23). In (planned, v0.2.0).
- FR-17: `report` prints hits, sessions with a hit, measured sessions and share per detector. Held (implemented, 0.1.0); `promote?` becomes a neutral "frequent" marker in the break (Q11, decided 2026-09-23).
- FR-18: Grouping by rule, repository or stance, and a date window. Held (implemented, 0.1.0).
- FR-19: `report_data` and `--json` carry the same numbers as the table. Held (implemented, 0.1.0).
- FR-20: Only a row with a `rules` map is evidence. Held (implemented, 0.1.0).
- FR-21: Compliance per opportunity (`opportunities`, `followed`) beside hits per session, from `order` and `absent`. In (planned, v0.2.0).
- FR-22: No compliance rate below a minimum opportunity count, default 20, per printed group (Q7, decided 2026-09-23). In (planned, v0.2.0).
- FR-23: `ruleprobe corpus` scores precision and recall; `--floor 0.9` fails under it. Held (implemented, 0.1.0).
- FR-24: `examples:` with `fire` and `skip` cases on a declarative detector. Held (implemented, 0.1.0).
- FR-25: An explain path per hit, redacted, writing nothing. In (planned, v0.2.0).
- FR-26: One command turns a false positive into a labelled negative in a user-named corpus, redacted. In (planned, v0.2.0).
- FR-27: A schema version on every detector entry: an integer, `2` in 0.2.0 (Q9, decided 2026-09-23). In (planned, v0.2.0).
- FR-28: A schema version on every row and `report_data` result: an integer, `2` in 0.2.0. In (planned, v0.2.0).
- FR-29: Fold map. In for the persisted fold entries and the shipped-id rename test only (in-memory fold implemented, 0.1.0).
- FR-30: A declared public API covering every name, call shape and non-name dependency agent-harness uses, held by a contract test; other root names stay importable and undeclared (Q8, decided 2026-09-23). In (planned, v0.2.0).
- FR-31: Versioning policy: no incompatible change within a minor series; a later 0.x minor may break with notice (Q12, decided 2026-09-23). In (planned, v0.2.0).
- FR-32: A third reader, Gemini CLI (Q1, decided 2026-09-23). In (planned, v0.2.0).
- FR-33: Labelled Gemini CLI sessions in the corpus, at or above the floor. In (planned, v0.2.0).
- FR-34: A separate, opt-in command that drafts a declarative detector from a rule's text. Withdrawn (2026-09-23; moved to #21).

In scope for 0.2.0: 15 FRs (FR-14, FR-15, FR-16, FR-21, FR-22, FR-25 to FR-33). Withdrawn epic: FR-34 (moved to #21).

### NonFunctional Requirements

- NFR-1: Standard library only; `dependencies = []`. A test that fails on any addition is planned (v0.2.0).
- NFR-2: Python 3.9 floor; no syntax or call newer than 3.9.
- NFR-3: Deterministic output; byte-identical `--json` for the same inputs and flags.
- NFR-4: Under-count rather than over-count. Implemented: positive matchers in 0.1.0; negation, `any`, `all`, `order` and `absent` over skipped commands under #19, unreleased, shipping in v0.2.0.
- NFR-5: `report` writes and sends nothing. The enforcing test is planned (v0.2.0). Only FR-26's command writes.
- NFR-6: Corpus floor 0.9 in CI, never lowered to pass a detector.
- NFR-7: No model in measurement; no command in ruleprobe calls a model, and the core imports no model client.
- NFR-8: Local data only.
- NFR-9: `report --rules --since 30` inside sixty seconds over 500 sessions and 200 MB. No timing measured.

### Additional Requirements

From the architecture spine. Every AD binds; the ones below shape 0.2 stories directly.

- No starter template: this is a brownfield package at 0.1.0. Epic 1 starts from the existing code.
- AD-1: a new module takes a place in the dependency graph in the change that adds it, and the spine is updated.
- AD-3: the third reader maps its tools to the canonical names or leaves them native; no lossy mapping.
- AD-4: segment matchers return undecided over a skipped parse; `any`, `all`, `not` pass undecided through; `not`, `absent`, `order` treat it as no hit. Ships in the 0.2 break (#19).
- AD-6: labels keyed `"<turn>:<tool_use_id>"` or `"<turn>:-"`, built only by `hit_key` and `event_key`. The label command writes `<name>.events.jsonl`, loaded without a reader, `turn` and `final` taken as written.
- AD-7: the declarative subset and matcher vocabulary are closed; widening either is a contract change.
- AD-8: no new dependency, no network, no write except the label command, no model, explicit sorts. 0.2 adds the dependency test and the no-write, no-network `report` test.
- AD-9: `schema_version`, absent meaning 1, on entries (file-level `version` as default) and rows; one fold function over the union of the shipped map and `Registry(renamed=)`, chains resolved, cycles an error; `report_data` emits the effective map; shipped fold map and shipped ids as literals in `ruleprobe/contract_data.py`; one contract test module is the declared API and the README renders from it.
- AD-10: a reader lands with a labelled corpus session, near-misses included, and a README note of what the runtime does not record.
- AD-11: `Detector.opportunities`, keyword only, returns `(turn, tool_use_id, followed)` triples with `followed` True, False or None; rows gain `compliance` with `opportunities`, `followed`, `undecided`; `run()` unchanged; `measure()` isolates a raise.
- AD-12: `rules.py` owns binding and the rule id; section id is `<path>#<heading-slug>` with ordinal suffix; binding source own or catalog; precedence shipped, catalog, then discovery order.
- AD-13: `ruleprobe explain` and `ruleprobe label`; label refuses a session hit and refuses when redaction changes the matched field; one `redact` function beside `SECRET_PATTERNS`.
- AD-14: `DEFAULT` is never mutated after import; the catalog builds from `DEFAULT.copy()`.
- Inherited agent-harness AD-13 and AD-21: the harness vendors a pinned pure-Python wheel imported from a zip, and never forks detector logic.
- Existing bug #19 (RP-B001): negated matchers over skipped commands over-count. It is filed; it is placed, not re-created.

### UX Design Requirements

None. No UX document exists. CLI output shapes are carried by FR-14, FR-17, FR-21, FR-22 and FR-25.

### FR Coverage Map

Every in-scope FR maps to at least one story. Held FRs appear where a 0.2 story changes them.

- FR-6: Epic 2 (2.4) - `Detector` gains the keyword-only `opportunities` attribute.
- FR-9: Epic 2 (2.5) - a raising `opportunities` costs only its own figures.
- FR-10: Epic 1 (1.4) - declarative entries carry `schema_version`.
- FR-12: Epic 1 (1.7, #19) - negation and `absent` pass undecided through.
- FR-14: Epic 3 (3.3) - measured share in the coverage block.
- FR-15: Epic 3 (3.4) - section-level binding with stable ids.
- FR-16: Epic 3 (3.5) - shipped catalog and exact-one binding.
- FR-17: Epic 2 (2.6) - `promote?` renamed to a neutral "frequent" marker in the break.
- FR-21: Epic 2 (2.4, 2.5, 2.6) - opportunities and followed beside hits.
- FR-22: Epic 2 (2.6) - no rate below the minimum.
- FR-25: Epic 4 (4.1) - `ruleprobe explain`.
- FR-26: Epic 4 (4.2) - `ruleprobe label`.
- FR-27: Epic 1 (1.4) - schema version on detector entries.
- FR-28: Epic 1 (1.5) - schema version on rows and `report_data`.
- FR-29: Epic 1 (1.6) - persisted fold entries and the shipped-id rename test.
- FR-30: Epic 1 (1.8), Epic 6 (6.2) - declared API, contract test, re-derived before the tag.
- FR-31: Epic 1 (1.9) - versioning policy.
- FR-32: Epic 5 (5.2) - third reader.
- FR-33: Epic 5 (5.3) - third-runtime corpus sessions.
- FR-34: none. Withdrawn 2026-09-23 and moved to #21 (RP-E002); Epic 7 (7.2) is kept as the record, unbuilt.
- NFR-1, NFR-5: Epic 1 (1.10) - the enforcing tests AD-8 plans.
- NFR-4: Epic 1 (1.7, #19).
- NFR-9: Epic 3 (3.6) - measured, not assumed.

Coverage: 15 of 15 in-scope FRs (FR-14, FR-15, FR-16, FR-21, FR-22, FR-25 to FR-33), and FR-34 is
withdrawn (moved to #21). FR-1 to FR-5, FR-7, FR-8, FR-11, FR-13, FR-18 to FR-20, FR-23 and FR-24 are held unchanged
and get no story; the contract test (1.8) and the existing suites hold them.

## Epic List

Sequenced so the versioned contract lands first. Every later story writes rows and entries under
the schema version decision 1.1 fixes, and extends the contract test in the same change.

### Epic 1: A contract a downstream tool can pin
A tool built on ruleprobe, agent-harness first, pins 0.2 and knows what will not move under it: schema
versions on entries and rows, a fold map that persists, a declared API held by a test, and the
undecided rule (#19) that is part of the one break.
**FRs covered:** FR-10 (touched), FR-12 (touched), FR-27, FR-28, FR-29, FR-30, FR-31; NFR-1, NFR-4, NFR-5.

### Epic 2: Compliance per opportunity
A developer sees, for a rule that asks for something to be done, how many opportunities there were and
how many were followed, beside hits per session.
**FRs covered:** FR-6 (touched), FR-9 (touched), FR-17 (touched), FR-21, FR-22.

### Epic 3: A stranger's own rules measured in a minute
A developer with an unedited `CLAUDE.md` or `AGENTS.md` sees some of their own rules measured without
writing a detector or calling a model, and sees the share measured.
**FRs covered:** FR-14, FR-15, FR-16; NFR-9.

### Epic 4: Every hit explains itself, and a wrong hit becomes a label
A developer can see the event and detector behind any hit, and turn a false positive into a labelled
negative with one command.
**FRs covered:** FR-25, FR-26.

### Epic 5: A third runtime
A developer on a third runtime gets the same detectors, scored on labelled sessions from that runtime.
**FRs covered:** FR-32, FR-33.

### Epic 6: agent-harness pins 0.2.0
The release: the harness surface re-derived, the contract test current, the break named, the wheel
published for the harness to vendor.
**FRs covered:** FR-30 (re-derivation), FR-31 (changelog).

### Epic 7 (proposed, maintainer may drop): Draft a detector from a rule's text
A separate, opt-in command outside the core install drafts a declarative detector for a person to
review and commit. Withdrawn on 2026-09-23: the maintainer answered Q4 "nowhere in ruleprobe", and drafting moved to #21
(RP-E002). Kept as the record.
**FRs covered:** FR-34.

## How to read a story

Each item is proposed until filed. The title is the issue title. **Kind** is the `--kind` it is filed
with. **Binds** lists the FR, NFR and AD ids it must satisfy (AD ids are the ruleprobe spine's unless
prefixed "harness"). **Files** come from the spine's structure and the code at `12ababe`. **Depends on**
names earlier items by epic.story. Every story also runs the `## Gate` block in `AGENTS.md`, keeps the
3.9 floor (NFR-2), writes explicit sorts (NFR-3), and adds nothing to `dependencies` (NFR-1).

## Epic 1: A contract a downstream tool can pin

A tool built on ruleprobe pins 0.2 and knows what will not move under it. This is the one planned
break (PRD §6): schema versions, the persisted fold map, the declared API and the undecided rule land
together. Every later epic writes rows and entries against it.

### Story 1.1: `decision(contract): the schema version's type and the value 0.2.0 writes`

**Kind:** decision · **Binds:** FR-27, FR-28; AD-9 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** an integer; 0.2.0 writes `2`; an absent key means 1 (RP-D001, #29).

As a maintainer of a downstream ledger,
I want the schema version's type and the 0.2.0 value fixed before any code writes it,
So that every stored row and entry carries one value for good.

**Acceptance Criteria:**

1. **Given** PRD Q9, **When** the decision is recorded, **Then** it states the type and the value 0.2.0 writes, with the trade-off.
2. **Given** the decision, **When** it differs from the spine's working form, **Then** AD-9 is amended through `bmad-architecture` update intent in the same change.

**Files:** `_bmad-output/implementation-artifacts/<id>.md`; the spine if amended.
**Tests:** none; 1.4 and 1.5 prove it.

### Story 1.2: `decision(api): whether root __all__ names outside FR-30 join the declared API`

**Kind:** decision · **Binds:** FR-30, FR-31; AD-9 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** root `__all__` names outside FR-30 stay importable and undeclared; a name joins the declared API only with a contract test (RP-D002, #30).

As a downstream tool author,
I want to know whether names like `measure`, `load_corpus` and `Bundle` are promised,
So that I import only what will not move.

**Acceptance Criteria:**

1. **Given** PRD Q8 and the root `__all__` in `ruleprobe/__init__.py`, **When** the decision is recorded, **Then** each name outside FR-30's list is marked declared or importable-undeclared.
2. **Given** a name marked declared, **When** 1.8 lands, **Then** it has a contract test.

**Files:** story file only. **Tests:** none; 1.8 proves it.

### Story 1.3: `decision(contract): whether a 0.x minor may break again after 0.2.0`

**Kind:** decision · **Binds:** FR-31 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** a later 0.x minor may break the declared surface with notice: its changelog section opens with a Breaking heading naming the migration, and the contract test is updated in the same change (RP-D003, #31).

As a downstream tool author,
I want the break policy after 0.2.0 stated,
So that I know whether a 0.3 pin can break me.

**Acceptance Criteria:**

1. **Given** PRD Q12 and maintainer decision 4, **When** the decision is recorded, **Then** it states whether a later 0.x minor may break the declared surface, and what notice it owes.

**Files:** story file only. **Tests:** none; 1.9 states it in the README.

### Story 1.4: `feat(declarative): schema_version on detector entries`

**Kind:** story · **Binds:** FR-27, FR-10, FR-11; AD-7, AD-9 · **Depends on:** 1.1

As a maintainer of a rule set,
I want each detector entry to carry the schema it was written under,
So that a newer entry is refused loudly instead of loading wrong.

**Acceptance Criteria:**

1. **Given** an entry with no `schema_version` and a file with no top-level `version`, **When** it loads, **Then** it is read as schema 1.
2. **Given** a file whose top-level `version` is a known schema, **When** an entry omits the key, **Then** the entry takes the file's value; **and** an entry's own key wins over the file's.
3. **Given** a top-level `version` or an entry `schema_version` that is not a known schema version (above the highest known, `0`, a negative number, a string, a float or a boolean), **When** discovery loads it, **Then** it is a finding with file, line and reason, the entry (or, for a top-level `version`, every entry that takes it as default) does not load, and the rest of the file still loads. Each of those value shapes has its own test case. [ASSUMPTION: an entry with its own known `schema_version` still loads under a bad top-level `version`, since its own key wins]
4. **Given** `ruleprobe/detectors/common.yaml` (top-level `version: 1`), **When** `tests/test_equivalence.py` runs, **Then** it still matches `common.py` hit for hit.

**Files:** `ruleprobe/matchers.py` (`ENTRY_KEYS`, `compile_detector`), `ruleprobe/rules.py` (`_entries`, `_compile_entries`), `ruleprobe/detectors/common.yaml`, `README.md` (Writing a detector).
**Tests:** `tests/test_declarative.py`, `tests/test_matchers.py`, `tests/test_rules.py`, `tests/test_equivalence.py`.

### Story 1.5: `feat(report): schema_version on rows and report_data`

**Kind:** story · **Binds:** FR-28, FR-19, FR-20; AD-9, AD-8 · **Depends on:** 1.1

As a downstream tool storing rows,
I want each row and each `report_data` result to say which schema wrote it,
So that a later reader never counts a row under the wrong schema.

**Acceptance Criteria:**

1. **Given** a session, **When** `measure()` runs, **Then** the row carries `schema_version` with the 1.1 value.
2. **Given** a row with no `schema_version`, **When** it is reported, **Then** it is read as schema 1 and counted as today.
3. **Given** a row above the highest known version, **When** it is reported, **Then** it is excluded from every count and denominator and reported as excluded, as FR-20 excludes a row with no `rules` map.
4. **Given** any rows, **When** `report_data` returns, **Then** the result carries `schema_version`, and `--json` output is byte-identical across two runs.

**Files:** `ruleprobe/report.py` (`measure`, `report_data`, `report`), `ruleprobe/cli.py`.
**Tests:** `tests/test_report.py`, `tests/test_cli.py`.

### Story 1.6: `feat(registry): persisted fold map and a shipped-id rename test`

**Kind:** story · **Binds:** FR-29, FR-31; AD-9, AD-1, AD-14, harness AD-13 · **Depends on:** none

As a downstream tool with a ledger written under an older release,
I want renamed detector ids to fold without my process having built the registry,
So that a rename never drops my history.

**Acceptance Criteria:**

1. **Given** `ruleprobe/contract_data.py` holding the shipped fold map and the list of every shipped detector id, **When** a test parses it, **Then** it holds only literals. [ASSUMPTION: module name from AD-9]
2. **Given** a shipped map and a consumer `Registry(renamed=...)`, **When** ids are resolved, **Then** one function uses the union, the consumer wins a clash, a chain resolves to its end, and a cycle raises when the registry is built.
3. **Given** rows stored under a retired id, **When** `report`, `report_data` or validity reads them, **Then** they count under the current id through that one function.
4. **Given** `report_data` output saved as JSON, **When** it is read by a process with no registry, **Then** it carries the effective fold map beside its rows.
5. **Given** an id on the shipped list that is neither registered in `DEFAULT` nor a fold-map key, **When** the suite runs, **Then** it fails.
6. **Given** a `Registry` is built or `report_data` runs, **When** file access is traced, **Then** no file is read.

**Files:** `ruleprobe/contract_data.py` (new), `ruleprobe/registry.py`, `ruleprobe/report.py` (`folded_rules`), `ruleprobe/validity.py`, the spine's AD-1 graph (new module, amended in the same change).
**Tests:** `tests/test_registry.py`, `tests/test_report.py`, `tests/test_validity.py`, `tests/test_contract_data.py` (new).

### Story 1.7: existing bug #19 (RP-B001), `fix(matchers): not and absent fire on a Bash command the shell parse skipped`

**Kind:** bug (filed as [#19](https://github.com/JakeSelby/ruleprobe/issues/19); not re-created) · **Binds:** NFR-4, FR-12, FR-5; AD-4, AD-9 · **Depends on:** none

Placed here because AD-9 puts the undecided rule in the 0.2 break: it changes counts for user detector
files that use `not` or `absent`. The issue's "Done when" (undecided over a skipped command, and
regression tests for `command` and `git` under `not` and `absent`) is kept and not restated. It covers
only part of AD-4, so the criteria below cover the rest; the maintainer widens #19's issue body to
match. It lands before 2.4, because compiled opportunities read undecided straight through these
combinators and count it separately.

**Acceptance Criteria** (AD-4's truth table; each is a regression test over a command the shell parse
skipped, as `Parsed.skipped` marks it):

1. **Given** #19's "Done when", **When** the story closes, **Then** every item of it holds.
2. **Given** each `env` key, **When** it matches a skipped command, **Then** it returns undecided, as the `command` and `git` segment matchers do; **and** `command.regex` and `command.unparsed` are exempt and keep their 0.1.0 result.
3. **Given** `not` over an undecided matcher, **When** evaluated, **Then** it is undecided, never true.
4. **Given** `any`, **When** evaluated, **Then** it is true on any true child, else undecided on any undecided child, else false; one test per branch.
5. **Given** `all`, **When** evaluated, **Then** it is false on any false child, else undecided on any undecided child, else true; one test per branch.
6. **Given** a `when` that evaluates to undecided, **When** the detector runs, **Then** it produces no hit.
7. **Given** an `order` detector, **When** `first` or `then` is undecided, **Then** it produces no hit; a hit needs both true.
8. **Given** an `absent` scope holding an undecided candidate and no true one, **When** the detector runs, **Then** it produces no hit, for `scope: turn` and `scope: session` both.
9. **Given** every shipped declarative detector, **When** `tests/test_equivalence.py` and `ruleprobe corpus --floor 0.9` run, **Then** both still pass.

**Files:** `ruleprobe/matchers.py`, `_bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md` (NFR-4 status), the spine (AD-4 status), `CHANGELOG.md`.
**Tests:** `tests/test_matchers.py`, `tests/test_equivalence.py`.

### Story 1.8: `feat(api): declare the public API and hold it with a contract test`

**Kind:** story · **Binds:** FR-30, FR-6, FR-31; AD-9, AD-5, AD-14, harness AD-13, harness AD-21 · **Depends on:** 1.2, 1.4, 1.5, 1.6

As a downstream tool author,
I want every name, call shape and non-name dependency the harness uses declared and tested,
So that a pinned 0.2 wheel cannot break me silently.

**Acceptance Criteria:**

1. **Given** the contract test module, **When** it runs, **Then** it imports each FR-30 name at its declared path, including the eight 0.1.0 names and every harness import.
2. **Given** a detector function built as `fn(events, ctx)`, **When** `run(events, stances, registry=Registry([...]), strict=..., errors=...)` calls it, **Then** it reads `ctx.bash` (each a `Parsed` with `.event`, `.command`, `.heredocs`) and `ctx.finals`, and returns `(turn, tool_use_id)` pairs.
3. **Given** `Detector` built positionally with five arguments and subclassed with `__slots__ = ()`, **When** the test reads `.id`, `.rule`, `.event`, `.fn` and `.gate` on it and on each `common.DETECTORS` item, **Then** each is present.
4. **Given** `hit(event)`, `hit(event, tool_use_id=False)`, `git_calls(parsed, ("commit",))`, `MARKER_RE.match`, `declarative.load(path)`, `score_corpus(registry=, directory=)` and the `Score` attributes, **When** exercised, **Then** each returns the declared shape.
5. **Given** `ruleprobe/detectors/common.py`, **When** it is parsed with `ast`, **Then** `SECRET_PATTERNS` is a plain `ast.Assign` of a literal list.
6. **Given** the built wheel, **When** it is placed on `sys.path` as a zip, **Then** the package imports and `run` works without installation, the file is named `ruleprobe-<version>-py3-none-any.whl`, and it carries `ruleprobe/corpus/`.
7. **Given** the README's public API section, **When** a test compares it with the contract list, **Then** they match, and the "six names" count (PRD Q13) is gone. [ASSUMPTION: a test checks the README against the list rather than generating it]
8. **Given** any removal or signature change of a declared item, **When** the suite runs, **Then** it fails. This holds only for what the test exercises, so AC9 to AC11 make the test walk FR-30's whole list.
9. **Given** an event from each of the five kinds, **When** the test reads the fields the harness reads (`kind`, `turn`, `id`, `name`, `input`, `text`, `final`, `tool_use_id`, `tool_name`) through `.get`, **Then** each is present on the kinds `ruleprobe/events.py` documents it for.
10. **Given** FR-30's call shapes not covered above, **When** exercised, **Then** each returns the declared shape: `gate` accepts `None` and a `(dimension, variants_or_None)` pair; `MARKER_RE.match(value)` group 1 is an index into `Parsed.heredocs`; `input_of(event)`, `text_of(value)` and `normalise(command)` return their documented types; `below_floor(scores, floor)`, `scores_as_dict(scores, floor)` and `validity_table(scores, floor)` accept those positional arguments; `Score(detector_id)` exposes `.add`, `.scored`, `.precision`, `.recall` and `.detector`; `score_corpus` raises `CorpusError` on a broken corpus; `ctx.events` is present beside `ctx.bash` and `ctx.finals`.
11. **Given** the wheel imported from a zip, **When** the test resolves `os.path.dirname(ruleprobe.__file__)`, **Then** `corpus/` is found beside it, as the harness finds it. [ASSUMPTION: the test unpacks the corpus from the zip or points `RULEPROBE_CORPUS` at it, as AD-9 says a zip caller does, and asserts only that the path resolves and `corpus/labels.yaml` is in the archive under it]
12. **Given** FR-30's list, **When** the contract test module is read, **Then** every bullet of that list maps to at least one named test, and a comment in the module names the FR-30 bullet each test covers.

**Files:** `tests/test_contract.py` (new) [ASSUMPTION: name], `README.md` (public API section), `.github/workflows/ci.yml` (zip-import step if not covered by the wheel job).
**Tests:** `tests/test_contract.py`.

### Story 1.9: `docs(contract): state the versioning policy and name the 0.2 break`

**Kind:** task · **Binds:** FR-31, FR-29; AD-9 · **Depends on:** 1.3, 1.8

As a downstream tool author,
I want the versioning policy and the 0.2 break written where I will read them,
So that I know what a 0.2.x bump can and cannot do.

**Acceptance Criteria:**

1. **Given** the README, **When** read, **Then** it states that within a minor series no declared name, call shape, row schema or entry schema changes incompatibly, and states the 1.3 decision.
2. **Given** `CHANGELOG.md` Unreleased, **When** read, **Then** it names each part of the break: schema versions, persisted fold map, declared API, the undecided rule (#19), and the result-shape change of the coverage block moving from stderr into `--json` output (3.3; today `ruleprobe/cli.py` writes it to stderr).
3. **Given** a detector rename in a 0.2.x change, **When** the suite runs without a fold entry, **Then** 1.6's shipped-id test fails.
4. **Given** a 0.2.x release candidate, **When** `scripts/release_preflight.py` runs, **Then** it fails if the contract test drops a name the v0.2.0 tag declared. [ASSUMPTION: a preflight check is the mechanism for "a 0.2.x passes the 0.2.0 contract test unchanged"]

**Files:** `README.md`, `CHANGELOG.md`, `docs/releasing.md`, `scripts/release_preflight.py`.
**Tests:** `tests/test_release.py`.

### Story 1.10: `test(envelope): fail on a new dependency, a network call or a write from report`

**Kind:** task · **Binds:** NFR-1, NFR-5, NFR-7; AD-8 · **Depends on:** none

As a developer running `ruleprobe report` on private transcripts,
I want the package's promises enforced by tests, not by review,
So that no change can quietly add a dependency, a network call or a write.

**Acceptance Criteria:**

1. **Given** `pyproject.toml`, **When** the suite runs, **Then** it fails if `dependencies` is not empty.
2. **Given** every module in `ruleprobe/`, **When** scanned with `ast`, **Then** none imports `socket`, `urllib`, `http`, `subprocess` or a model client.
3. **Given** `report` over the corpus sessions, **When** socket creation and any write-mode `open` raise, **Then** `report` succeeds and prints its table.

**Files:** `tests/test_envelope.py` (new) [ASSUMPTION: name].
**Tests:** that file.

## Epic 2: Compliance per opportunity

For a rule that asks for something to be done, the report says how many opportunities there were and
how many were followed, beside hits per session (maintainer decision 3).

### Story 2.1: `decision(report): the minimum opportunity count`

**Kind:** decision · **Binds:** FR-22; AD-11 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** 20, per printed group (RP-D004, #38).

As a developer reading a compliance figure,
I want a floor under which no rate is shown,
So that I never act on a rate from three opportunities.

**Acceptance Criteria:**

1. **Given** PRD Q7 and the working default of 20, **When** the decision is recorded, **Then** it names the default and whether it is per rule or per group under `--by`.

**Files:** story file only. **Tests:** none; 2.6 proves it.

### Story 2.2: `decision(registry): how a Python detector declares an opportunity`

**Kind:** decision · **Binds:** FR-21, FR-6, FR-30; AD-11 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** the keyword-only `opportunities` callable of AD-11 (RP-D005, #39).

As a downstream tool with Python detectors,
I want the opportunity hook fixed before it is declared,
So that my `fn(events, ctx)` detectors keep working and can opt in.

**Acceptance Criteria:**

1. **Given** PRD Q10 and AD-11's keyword-only `opportunities` callable returning `(turn, tool_use_id, followed)` triples, **When** the decision is recorded, **Then** it confirms or replaces that form, and the positional five-argument `Detector` and `fn` shape stay unchanged either way.

**Files:** story file; the spine if AD-11 changes. **Tests:** none; 2.4 proves it.

### Story 2.3: `decision(report): what promote? becomes`

**Kind:** decision · **Binds:** FR-17; maintainer decision 1 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** `promote?` is renamed to a neutral "frequent" marker with no advice; the parameter names follow in the break (RP-D006, #40).

As a developer reading the report,
I want the threshold marker to describe, not advise,
So that the report stays an instrument.

**Acceptance Criteria:**

1. **Given** PRD Q11 and its recommendation, **When** the decision is recorded, **Then** it chooses keep, reword or drop.

**Files:** story file only. **Tests:** none; 2.6 proves it.

### Story 2.4: `feat(matchers): opportunities for order and absent detectors`

**Kind:** story · **Binds:** FR-21, FR-6, FR-12, NFR-4; AD-11, AD-4, AD-7, AD-9 · **Depends on:** 1.7, 1.8, 2.2

As a maintainer of a rule set,
I want `order` and `absent` detectors to report opportunities and whether each was followed,
So that a rule's compliance can be counted without a new detector.

**Acceptance Criteria:**

1. **Given** `Detector`, **When** built positionally with five arguments, **Then** it behaves as in 0.1.0; **and** `opportunities` can be set by keyword only.
2. **Given** an `absent` detector with `scope: turn`, **When** compiled, **Then** each turn in the event list is one opportunity, followed when `of` matched in that turn.
3. **Given** an `order` detector, **When** compiled, **Then** each `first` match opens one opportunity, followed when `then` matched within `within`.
4. **Given** an `absent` detector with `scope: session`, **When** compiled, **Then** it defines no opportunity.
5. **Given** an opportunity whose `followed` is undecided (AD-4), or whose `first` is undecided, **When** counted, **Then** it is `undecided`, never not-followed. [ASSUMPTION from AD-11, `first` undecided counts as undecided]
6. **Given** every compiled detector over the corpus, **When** tested, **Then** hits = opportunities - followed for `absent` and hits = followed for `order`, as AD-11 writes it. `opportunities` excludes undecided: AD-11 leaves an undecided opportunity out of both `opportunities` and `followed`, and under AD-4 an undecided `absent` turn yields no hit, so undecided is not subtracted again.
7. **Given** the contract test, **When** this lands, **Then** it covers the keyword `opportunities` attribute in the same change.

**Files:** `ruleprobe/registry.py` (`Detector`), `ruleprobe/matchers.py` (`order`, `absent` compilers, docstring misses), `tests/test_contract.py`.
**Tests:** `tests/test_matchers.py`, `tests/test_registry.py`, `tests/test_contract.py`.

### Story 2.5: `feat(report): rows carry compliance for detectors that define opportunities`

**Kind:** story · **Binds:** FR-21, FR-9, FR-28; AD-11, AD-9 · **Depends on:** 1.5, 2.4

As a downstream tool storing rows,
I want each row to carry opportunity counts beside hit counts,
So that compliance can be reported from stored rows without re-reading transcripts.

**Acceptance Criteria:**

1. **Given** a session and a detector with `opportunities`, **When** `measure()` runs, **Then** the row carries `compliance[detector_id] = {"opportunities": N, "followed": M, "undecided": U}`, where `N` excludes `U` (AD-11): an undecided opportunity is counted in `U` only.
2. **Given** a detector with no `opportunities`, **When** `measure()` runs, **Then** it has no `compliance` entry.
3. **Given** a detector gated off by the run's stances, **When** `measure()` runs, **Then** its `opportunities` is not called.
4. **Given** an `opportunities` callable that raises, **When** `measure()` runs, **Then** the raise is recorded in `rules_errors` against that detector and every other figure stands.
5. **Given** `run()`, **When** called as in 0.1.0, **Then** its arguments and return are unchanged.

**Files:** `ruleprobe/report.py` (`measure`).
**Tests:** `tests/test_report.py`.

### Story 2.6: `feat(report): compliance per opportunity for order and absent detectors`

**Kind:** story · **Binds:** FR-21, FR-22, FR-17, FR-18, FR-19; AD-11, AD-8 · **Depends on:** 2.1, 2.3, 2.5

As a developer with rules,
I want the report to show opportunities and followed beside hits per session,
So that I can say how often a rule was followed when it applied.

**Acceptance Criteria:**

1. **Given** a fixture session with N opportunities of which M are followed, **When** `report_data` runs, **Then** it gives `opportunities: N`, `followed: M` and `undecided`, and the table prints the same numbers beside hits per session, not in place of them.
2. **Given** a detector with no opportunity, **When** reported, **Then** it prints hits per session only and no compliance figure.
3. **Given** fewer opportunities than the minimum (`min_opportunities`, a parameter of `report` and `report_data`, default from 2.1), **When** reported, **Then** counts print and no rate does; in `report_data` the rate field `compliance_rate` (`followed / opportunities`) is `null` and the table prints the same absence, so the table and `report_data` agree (FR-19). [ASSUMPTION: the field name `compliance_rate`, and `null` rather than an absent key]
4. **Given** `--by repo` or `--by stance`, **When** reported, **Then** compliance is grouped the same way as hits.
5. **Given** the 2.3 decision, **When** the table prints, **Then** the threshold marker uses the decided wording and carries no advice.
6. **Given** the same rows, **When** reported twice, **Then** `--json` is byte-identical.
7. **Given** rows whose `compliance` map is keyed by a retired detector id and rows keyed by its current id, **When** `report_data` runs, **Then** `compliance` folds through the same fold function 1.6 uses for `rules`, and `opportunities`, `followed` and `undecided` sum under the current id, so a rename never splits compliance while hits merge (AD-9, AD-11).

**Files:** `ruleprobe/report.py` (`report_data`, `report`, `folded_rules` or the one fold function), `ruleprobe/cli.py` (flag), `README.md` (report section).
**Tests:** `tests/test_report.py`, `tests/test_cli.py`.

### Story 2.7: `decision(report): compliance by position stays out of 0.2.0`

**Kind:** decision · **Binds:** FR-21; PRD §8 · **Depends on:** none · **Sequenced before:** 6.2

**Decided 2026-09-23 by the maintainer:** compliance by position is out of 0.2.0 (RP-D007, #44).

As the maintainer,
I want PRD Q5 confirmed before 0.2.0 scope freezes,
So that compliance by position in the session neither slips in nor is dropped by default.

**Acceptance Criteria:**

1. **Given** PRD Q5 and §8's Out line, **When** the decision is recorded, **Then** it confirms that compliance by position stays out of 0.2.0, or names the story that brings it in.

**Files:** story file only. **Tests:** none.

## Epic 3: A stranger's own rules measured in a minute

A developer with an unedited `CLAUDE.md` or `AGENTS.md` sees some of their own rules measured, with no
detector written and no model (maintainer decision 7).

### Story 3.1: `decision(rules): the section split unit`

**Kind:** decision · **Binds:** FR-15; AD-12 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** headings only for 0.2 (RP-D008, #45).

As a developer with a long rule file,
I want the split unit fixed,
So that my file becomes the rules I would name.

**Acceptance Criteria:**

1. **Given** PRD Q2 and the addendum's trade-off, **When** the decision is recorded, **Then** it chooses headings, list items or both, and how a list-item rule's id is formed if chosen.

**Files:** story file; the spine if AD-12's id form changes. **Tests:** none; 3.4 proves it.

### Story 3.2: `decision(detectors): the catalog's first shapes and how many`

**Kind:** decision · **Binds:** FR-16, SM-1; AD-6, AD-12 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** a small set of six to eight shapes, each with `examples:` that clear the 0.9 floor, binding by exact-one match (AD-12). The starting list: run the tests before finishing (`order` or `absent`); never skip pre-commit hooks with `--no-verify` (event, `git`); never force-push the default branch (event, `git`); use the named package manager, not another (event, `command`); do not read a whole file into context (event, `command`, as the shipped `whole-file-cat`); Conventional Commit subjects (event, `git` message) `[ASSUMPTION: subject parsing fits a matcher]`; never commit a secret-shaped file (event, `git add` path) (RP-D009, #46).

As a first-time user,
I want the catalog to hold the rule shapes most files state,
So that at least one of my own rules is measured.

**Acceptance Criteria:**

1. **Given** PRD Q3, **When** the decision is recorded, **Then** it lists the named shapes for 0.2.0, each with its detector kind (`order`, `absent`, event matcher) and its anchored pattern's intent.
2. **Given** SM-1's counter, **When** a shape is listed, **Then** it can be written with `examples:` that clear the floor.

**Files:** story file only. **Tests:** none; 3.5 proves it.

### Story 3.3: `feat(rules): print the measured share in the coverage block`

**Kind:** story · **Binds:** FR-14, harness FR-67 · **Depends on:** none

As a developer with rules,
I want the share of my rules that are measured,
So that I can see how much of my file anything checks.

**Acceptance Criteria:**

1. **Given** a rules directory with measured, dark and unmeasured rules, **When** `report --rules` runs, **Then** the coverage block prints the three counts and the measured share.
2. **Given** zero rules, **When** it runs, **Then** no share is printed and nothing divides by zero.
3. **Given** `--json`, **When** it runs, **Then** the same counts and share appear in the output. [ASSUMPTION: the coverage block is carried in `--json`]

**Files:** `ruleprobe/rules.py` (`Bundle` coverage), `ruleprobe/cli.py`.
**Tests:** `tests/test_rules.py`, `tests/test_cli.py`.

### Story 3.4: `feat(rules): split a rule file into one rule per section`

**Kind:** story · **Binds:** FR-15, FR-13; AD-12 · **Depends on:** 3.1, 3.3

As a developer with a `CLAUDE.md` of twelve rules,
I want twelve entries in the coverage block,
So that each rule is measured, dark or unmeasured on its own.

**Acceptance Criteria:**

1. **Given** a fixture file with three rule sections and one section holding only a fenced example, **When** read, **Then** it yields three rules and the coverage block counts three.
2. **Given** a unit that is only a heading, a fenced block, a table or a blockquote, **When** read, **Then** it is not a rule and is in no state.
3. **Given** a section rule, **When** its id is formed, **Then** it is `<path>#<heading-slug>`, and it is unchanged after a section above it is edited.
4. **Given** two sections with the same slug, **When** read, **Then** the second takes `-2` in document order; a collision that remains is a finding.
5. **Given** a file bound in front matter (FR-13), **When** read, **Then** it keeps one rule with its 0.1.0 id and state.

**Files:** `ruleprobe/rules.py` (`read_rule_file`, `load_rules_dir`), `tests/fixtures/` (rule files).
**Tests:** `tests/test_rules.py`.

### Story 3.5: `feat(detectors): a shipped catalog of common rule shapes, bound by exact-one match`

**Kind:** story · **Binds:** FR-16, FR-23, FR-24, NFR-4, NFR-6, NFR-7; AD-6, AD-7, AD-9, AD-12, AD-14 · **Depends on:** 1.4, 1.6, 2.4, 3.2, 3.4

As a first-time user,
I want my own rules bound to shipped detectors by what they say,
So that I get a measured answer without writing a detector.

**Acceptance Criteria:**

1. **Given** each catalog entry, **When** CI runs `ruleprobe corpus --floor 0.9`, **Then** it carries `examples:` and scores at or above the floor.
2. **Given** a named fixture rule file whose sections each follow one catalog shape, **When** `report --rules` runs, **Then** each section binds that entry and is reported measured and catalog-bound.
3. **Given** a rule whose text matches no entry's anchored pattern, or more than one, **When** bound, **Then** it stays unmeasured.
4. **Given** a user detector with a catalog id, **When** the bundle builds, **Then** the rule is reported bound to the user's own (AD-12 precedence), and `DEFAULT` is unchanged (AD-14).
5. **Given** the catalog loaded from a wheel on `sys.path` as a zip, **When** a bundle builds, **Then** it loads with no file read beside `__file__`, and a test asserts `ruleprobe/detectors/catalog.py` holds only literals. Catalog entries are Python literals in that module, compiled with `compile_detector` (AD-9, amended 2026-09-23).
6. **Given** each catalog id, **When** the shipped-id test runs, **Then** it is on the shipped-id list.
7. **Given** binding, **When** it runs, **Then** it reads rule text with no model.

**Files:** `ruleprobe/detectors/catalog.py` (new; a Python literal module under AD-9, placed in AD-1's graph with `rules` importing it and it importing `matchers`), `ruleprobe/rules.py` (binding, source own or catalog), `ruleprobe/contract_data.py`, `tests/fixtures/` (catalog rule file), `README.md` (Sixty seconds on a rule of your own), the spine's AD-1 graph and AD-9 catalog line (amended in planning on 2026-09-23; the story checks the code matches and amends the spine again if it does not).
**Tests:** `tests/test_rules.py`, `tests/test_validity.py`, `tests/test_detectors.py`.

### Story 3.6: `spike(report): time the sixty-second path on a reference volume`

**Kind:** spike · **Binds:** NFR-9, SM-1 · **Depends on:** 3.5

As the maintainer,
I want one measured timing of `report --rules --since 30`,
So that NFR-9 rests on a number, not an assumption.

**Acceptance Criteria:**

1. **Given** a synthetic reference volume of 500 sessions and 200 MB, **When** timed, **Then** the result, the command and the machine class are recorded in the story file, and the exit is "within 60 s" or "not".
2. **Given** "not", **When** the spike closes, **Then** it files a follow-up rather than fixing inside the spike.

**Files:** story file; a generator script under `scripts/` if needed [ASSUMPTION]. **Tests:** none.

## Epic 4: Every hit explains itself, and a wrong hit becomes a label

Field validity over corpus validity (maintainer decision 6).

### Story 4.1: `feat(cli): ruleprobe explain prints the event behind every hit, redacted`

**Kind:** story · **Binds:** FR-25, NFR-5, NFR-3; AD-13, AD-6, AD-8 · **Depends on:** 1.5, 1.8

As a developer surprised by a hit,
I want to see the event and detector behind it,
So that I can judge whether the hit is right.

**Acceptance Criteria:**

1. **Given** a report run over transcripts, **When** `ruleprobe explain` runs, **Then** every hit prints the session, turn, tool-use id, detector id and the matched field, keyed with `hit_key`.
2. **Given** an event holding a known secret shape, **When** explained, **Then** the shape never appears in the output; a single `redact` beside `SECRET_PATTERNS` is the only path, and `SECRET_PATTERNS` stays a plain literal assignment.
3. **Given** a stored row, **When** explained, **Then** the output says the row carries counts only and names the rerun over that row's runtime and session id. [ASSUMPTION: a library function takes the row; the CLI has no stored-row input]
4. **Given** explain runs, **When** the file system and report figures are checked, **Then** nothing is written and no report number changes.
5. **Given** the CLI form `ruleprobe explain [--session ID] [--detector ID] [--key KEY]` plus `report`'s source options (`--root`, `--runtime`, `--since`) and the shared detector options (`--rules`, `--detectors`, `--no-config`), **When** run with no filter, **Then** it prints every hit; each filter narrows the output and a filter that matches nothing prints nothing and exits 0. [ASSUMPTION: this CLI form; AD-13 fixes only the subcommand names]
6. **Given** a hit, **When** printed, **Then** its address is the session (`<runtime>:<Session.id>`) plus the `hit_key`, because a key `"<turn>:<tool_use_id>"` is unique only within a session; the printed address is exactly what `ruleprobe label` takes. [ASSUMPTION: `Session.id` is unique within a runtime, so the runtime prefix makes it unique across runtimes]

**Files:** `ruleprobe/cli.py` (`explain`), `ruleprobe/report.py`, `ruleprobe/detectors/common.py` (`redact`), `README.md`.
**Tests:** `tests/test_cli.py`, `tests/test_report.py`, `tests/test_detectors.py`, `tests/test_contract.py` (literal check still passes).

### Story 4.2: `feat(cli): ruleprobe label turns a false positive into a labelled negative`

**Kind:** story · **Binds:** FR-26, FR-23, NFR-5, NFR-6; AD-6, AD-8, AD-13 · **Depends on:** 4.1

As a developer who found a wrong hit,
I want one command to record it as a labelled negative,
So that the detector's score reflects the field, not only the corpus.

**Acceptance Criteria:**

1. **Given** a hit key from explain and a corpus directory the user names, **When** `ruleprobe label` runs, **Then** it writes one `<name>.events.jsonl` holding only that event and one `near` label for the detector's key, and nothing else anywhere.
2. **Given** that directory, **When** `ruleprobe corpus` reruns over it, **Then** the new negative counts in that detector's score; the loader takes `turn` and `final` as written.
3. **Given** a session hit (`"<turn>:-"`), **When** label runs, **Then** it refuses and says why.
4. **Given** an event holding a known secret shape, **When** labelled, **Then** the shape appears in no written file.
5. **Given** redaction changes the field the detector matched, **When** label runs, **Then** it refuses and says why.
6. **Given** `report`, **When** run after this lands, **Then** 1.10's no-write test still passes.
7. **Given** the CLI form `ruleprobe label --session <runtime>:<ID> --detector ID --key KEY --corpus DIR --name NAME`, with `report`'s source options and the shared detector options, **When** it runs, **Then** it re-reads the transcripts, selects the one session with that runtime and id, reruns the detector over it, and takes the event whose `event_key` equals KEY. It refuses, and says why, when no session or more than one matches, when the detector has no hit at KEY (only a hit can be a false positive), or when `DIR/sessions/NAME.events.jsonl` already exists. [ASSUMPTION: this CLI form; AD-13 fixes only the subcommand name]
8. **Given** `DIR/labels.yaml` does not exist, **When** label runs, **Then** it creates it with `version: 1` and a `sessions` list holding the one new entry (`session: NAME.events.jsonl`, `labels: [{at: KEY, near: [DETECTOR]}]`). **Given** it exists, **When** label runs, **Then** it parses it with `declarative.load`, refuses if `NAME.events.jsonl` is already named or `sessions` is not the last top-level key, appends the new entry's text at the end of the file so existing comments and entries are untouched, re-parses the whole file, and refuses and restores the original if the result is not the old document plus that one entry. [ASSUMPTION: append rather than rewrite, to keep a hand-written file's comments]
9. **Given** the package has a YAML reader and no writer, **When** label writes YAML, **Then** it uses a minimal emitter in `ruleprobe/declarative.py` for the same closed subset the reader accepts (mappings, sequences, plain and quoted scalars), and a round-trip test asserts `parse(emit(value)) == value` for every value shape the label entry uses, including keys that need quoting such as `"1:tu-c1"`. [ASSUMPTION: a minimal emitter for the closed subset is the default; AD-7 keeps the subset closed, so the emitter adds no syntax the reader lacks]

**Files:** `ruleprobe/cli.py` (`label`), `ruleprobe/validity.py` (`.events.jsonl` loader, `event_key`), `ruleprobe/declarative.py` (minimal emitter), `README.md` (How good are the detectors?).
**Tests:** `tests/test_cli.py`, `tests/test_validity.py`, `tests/test_declarative.py` (emitter round trip).

### Story 4.3: `spike(validity): field precision per shipped detector from hand-sampled hits`

**Kind:** spike · **Binds:** FR-26, SM-8, NFR-6; AD-6 · **Depends on:** 3.5, 4.1, 4.2 · **Sequenced before:** 6.2

**Confirmed by the maintainer on 2026-09-23:** the spike runs before the 0.2.0 release notes (6.2) (RP-SP002, #53).

As the maintainer,
I want each shipped detector's precision measured on real hits,
So that the release says what corpus agreement does not.

**Acceptance Criteria:**

1. **Given** a developer's own transcripts, **When** 50 to 100 hits per shipped detector are hand-sampled through `ruleprobe explain`, **Then** precision per detector and the sample size are recorded, labelled as field precision on one developer's transcripts, not as field accuracy.
2. **Given** each false positive, **When** found, **Then** it goes through `ruleprobe label` into a corpus, and the story file lists the resulting negatives by detector.
3. **Given** the public-only rule, **When** the result is published, **Then** it carries figures and synthetic stand-ins only; no transcript content.
4. **Given** a detector with fewer than 50 hits available, **When** sampled, **Then** it is reported with its actual count, not padded.

**Files:** story file; corpus additions from 4.2. **Tests:** `ruleprobe corpus --floor 0.9` still passes.

## Epic 5: A third runtime

Runtime-neutral becomes a fact (maintainer decision 5).

### Story 5.1: `spike(readers): choose the third runtime, Cursor or Gemini CLI`

**Kind:** spike · **Binds:** FR-32, FR-33; AD-3, AD-10 · **Depends on:** none

**Runtime chosen by the maintainer on 2026-09-23:** Gemini CLI. The spike still runs to confirm Gemini CLI's transcript location and format and to list its file-tool mappings; if it finds Gemini CLI cannot be read reliably, it reports back rather than switching runtime (RP-SP003, #54).

As the maintainer,
I want evidence of what each candidate's transcripts record,
So that the choice rests on which one a detector can read.

**Acceptance Criteria:**

1. **Given** each candidate, **When** examined from public documentation and a synthetic session, **Then** the story file records the transcript location, format, whether shell commands, file writes, tool-use ids and turns are recorded, and the licence of any format documentation used.
2. **Given** the evidence, **When** the spike closes, **Then** it states the choice (PRD Q1) with the trade-off.
3. **Given** FR-32 says file tools reach detectors under the shared names, and AD-3 lets a tool with no exact canonical twin stay native, **When** the spike closes, **Then** it lists, for the chosen runtime, each file tool that maps exactly and each that stays native, so the part of FR-32 that holds is known before 5.2. A native file tool matches no canonical detector and under-counts (AD-4); that gap is stated, not closed by a lossy mapping.

**Files:** story file only. **Tests:** none.

### Story 5.2: `feat(readers): read the third runtime's transcripts into the event schema`

**Kind:** story · **Binds:** FR-32, FR-3, FR-4; AD-2, AD-3, AD-10, AD-1 · **Depends on:** 5.1

As a developer on the third runtime,
I want `ruleprobe report` to read my sessions,
So that the same detectors measure my rules.

**Acceptance Criteria:**

1. **Given** `--runtime <name>`, **When** run, **Then** that runtime's sessions are read, and `auto` includes them.
2. **Given** its shell tool, **When** read, **Then** it reaches detectors as `Bash` with `command`; file tools map to the canonical names or stay native, never lossily.
3. **Given** a malformed line, an unreadable file and a missing `ROOT`, **When** read, **Then** the line is skipped, the file lands in `errors`, and the missing root yields nothing and no error.
4. **Given** `turn` and `final`, **When** derived, **Then** they follow AD-2 exactly as the other readers do.
5. **Given** the reader lands, **Then** at least one labelled synthetic session from the runtime is in the corpus, and the README names the runtime and what its transcripts do not record.

**Files:** `ruleprobe/readers/<runtime>.py` (new), `ruleprobe/readers/__init__.py` (`RUNTIMES`), `ruleprobe/corpus/sessions/`, `ruleprobe/corpus/labels.yaml`, `tests/fixtures/`, `README.md`.
**Tests:** `tests/test_readers.py`, `tests/test_validity.py`.

### Story 5.3: `test(corpus): labelled third-runtime sessions with near-misses, at the floor`

**Kind:** story · **Binds:** FR-33, NFR-6, SM-6; AD-6, AD-10 · **Depends on:** 5.2, 3.5

As a contributor adding a runtime,
I want every applicable detector scored on that runtime's sessions,
So that "runtime-neutral" is a measured claim.

**Acceptance Criteria:**

1. **Given** the corpus, **When** listed, **Then** it holds at least one labelled session from each runtime read.
2. **Given** each detector that applies to the third runtime, catalog entries included, **When** CI scores it on those sessions, **Then** it is at or above 0.9.
3. **Given** the third runtime's sessions, **When** reviewed, **Then** they carry near-misses as well as positives.

**Files:** `ruleprobe/corpus/sessions/`, `ruleprobe/corpus/labels.yaml`.
**Tests:** `tests/test_validity.py`; CI `corpus` job.

## Epic 6: agent-harness pins 0.2.0

### Story 6.1: `decision(release): the success targets and window for 0.2.0`

**Kind:** decision · **Binds:** SM-1 to SM-8 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** every SM target is kept as written; the window becomes six months from the 0.2.0 release, replacing 2027-03-23 (RP-D010, #57).

As the maintainer,
I want the targets and the 2027-03-23 window confirmed,
So that the release is judged against numbers I set.

**Acceptance Criteria:**

1. **Given** PRD Q6, **When** the decision is recorded, **Then** each SM target and the window is kept or changed, and a change amends the PRD through `bmad-prd` update intent.

**Files:** story file; the PRD if amended. **Tests:** none.

### Story 6.2: `chore(release): re-derive the harness surface and cut 0.2.0`

**Kind:** task · **Binds:** FR-30, FR-31, harness AD-13 · **Depends on:** every in-scope item in Epics 1 to 5, 6.1, and 4.3 if the maintainer confirms it

As a downstream tool,
I want a 0.2.0 wheel whose contract matches what I import on the day it ships,
So that I bump my pin with no code change.

**Acceptance Criteria:**

1. **Given** agent-harness `main` on the release day, **When** its ruleprobe imports, call shapes and non-name dependencies are re-derived, **Then** the contract test is updated in the same change and passes, and the commit read is recorded.
2. **Given** `CHANGELOG.md`, **When** the version section is cut, **Then** it names the break (1.9).
3. **Given** `scripts/release_preflight.py`, **When** run in a fresh clone, **Then** it is clean, and the wheel is published by the release workflow.

**Files:** `tests/test_contract.py`, `CHANGELOG.md`, `README.md`, `ruleprobe/__init__.py` (`__version__`, which `pyproject.toml` reads), `docs/releasing.md`.
**Tests:** full suite, corpus floor, preflight.

## Epic 7 (proposed, maintainer may drop): Draft a detector from a rule's text

**Withdrawn 2026-09-23 by the maintainer (7.1, RP-D011):** drafting from prose needs a model, so it moves
to the judge library tracked in [#21](https://github.com/JakeSelby/ruleprobe/issues/21) (RP-E002). The two
items below are kept as the record and are not built in ruleprobe.

### Story 7.1: `decision(draft): whether the drafting command belongs in 0.2.0, a later minor or nowhere`

**Kind:** decision · **Binds:** FR-34; AD-8 · **Depends on:** none

**Decided 2026-09-23 by the maintainer:** nowhere in ruleprobe. Drafting moves to the judge library tracked in #21 (RP-E002), because it needs a model; FR-34 is withdrawn and NFR-7 loses its exception (RP-D011, #59). Withdrawn with its epic.

As the maintainer,
I want the drafting command's place decided before 0.2.0 scope freezes,
So that it neither slips in nor blocks the release.

**Acceptance Criteria:**

1. **Given** PRD Q4, **When** the decision is recorded, **Then** it states 0.2.0, a later minor or nowhere, and, if built, whether it is an optional extra or a separate package.

**Files:** story file only. **Tests:** none.

### Story 7.2: `feat(draft): an opt-in command that drafts a detector from a rule's text`

**Kind:** story (proposed) · **Binds:** FR-34, NFR-1, NFR-7; AD-8 · **Depends on:** 7.1, 1.4, 1.10

**Withdrawn 2026-09-23 by the maintainer (7.1):** moved to #21 (RP-E002); kept here as the record, not built in ruleprobe (RP-S020, #60).

As a maintainer of a rule set,
I want a draft detector with `examples:` from a rule's prose,
So that I can review and commit it instead of writing it from nothing.

**Acceptance Criteria:**

1. **Given** the core install, **When** 1.10's tests run, **Then** no core module imports the drafting code or a model client, and `dependencies` is still empty.
2. **Given** the user names the command and supplies model access, **When** it runs, **Then** it prints, or writes to a path the user names, one entry with `schema_version` and `examples:` that `compile_detector` accepts.
3. **Given** a run, **When** it finishes, **Then** no registry, corpus or rule file changed.
4. **Given** `report`, `detectors` and `corpus`, **When** run with the command installed, **Then** they make no model call.

**Files:** outside the core install [ASSUMPTION: a separate distribution in this repository]. **Tests:** its own suite, and 1.10.

Out of scope and not given stories: a judge, tracked as a future capability under RP-E002 (see Beyond
0.2 below); compliance by position (PRD Q5, decision 2.7).

## Open questions

1. Closed 2026-09-23: PRD Q1, third runtime: Gemini CLI; spike 5.1 still confirms its format.
2. Closed 2026-09-23: PRD Q2, split unit: headings only for 0.2 (3.1).
3. Closed 2026-09-23: PRD Q3, catalog: a small set of six to eight shapes (3.2).
4. Closed 2026-09-23: PRD Q4, drafting command: nowhere in ruleprobe; moved to #21 (7.1).
5. Closed 2026-09-23: PRD Q5, compliance by position: out of 0.2.0 (2.7).
6. Closed 2026-09-23: PRD Q6, targets kept; the window is six months from the 0.2.0 release (6.1).
7. Closed 2026-09-23: PRD Q7, minimum opportunity count: 20, per printed group (2.1).
8. Closed 2026-09-23: PRD Q8, root `__all__` names: importable and undeclared (1.2).
9. Closed 2026-09-23: PRD Q9, schema version: an integer; 0.2.0 writes `2`; absent means 1 (1.1).
10. Closed 2026-09-23: PRD Q10, Python opportunity hook: AD-11's keyword-only `opportunities` callable (2.2).
11. Closed 2026-09-23: PRD Q11, `promote?`: a neutral "frequent" marker with no advice (2.3).
12. Closed 2026-09-23: PRD Q12, later 0.x breaks: allowed with notice, a Breaking changelog heading and the contract test updated in the same change (1.3).
13. Closed 2026-09-23: the catalog is a Python literal module, `ruleprobe/detectors/catalog.py`, under AD-9, and sits in AD-1's graph (spine amended; readiness M1).
14. Closed 2026-09-23: AD-11 already places `undecided` outside both `opportunities` and `followed`, so its identity holds as written. 2.4 AC6 and 2.5 AC1 follow it (readiness H1).
15. Closed 2026-09-23: the maintainer confirmed the field-precision spike (4.3); it runs before 6.2.
16. Closed 2026-09-23: Epic 7 is withdrawn and drafting moved to #21 (7.1).
17. FR-29 says a fold entry persists "with the rows". AD-9 reads that as `report_data` emitting the effective map, and 1.6 AC4 follows. A ledger of `measure()` rows, which UJ-3 stores, carries none; shipped renames still fold through `contract_data.py`. Confirm the spine's reading, or add the map to rows (readiness L1).
18. 1.8 AC7 has a test compare the README with the contract list, where AD-9 says the README "renders from" it. Accept the test, or amend AD-9 (readiness L8).
19. FR-32 says file tools reach detectors under the shared names; AD-3 lets a tool with no exact twin stay native. 5.1 AC3 records the gap. Amend FR-32 to match AD-3, or keep it and accept the gap (readiness L4).

## Validation (step 4)

- **FR coverage:** 15 of 15 in-scope FRs bound by at least one story; FR-34 withdrawn (moved to #21), its epic kept as the record.
- **Starter template:** none; brownfield package at 0.1.0.
- **Forward dependencies:** none within an epic. Cross-epic dependencies point only at earlier epics.
- **File churn:** `ruleprobe/report.py` changes in Epics 1, 2 and 4, and `ruleprobe/rules.py` in 1 and 3.
  Consolidation was considered and rejected: the brief sequences the contract first so every later
  row and entry is written against it, and each epic delivers a separate user outcome.
- **Items:** 33 (15 stories, 3 tasks, 3 spikes, 11 decisions, 1 existing bug). Epic 7's two items were
  withdrawn on 2026-09-23 (moved to #21); spike 4.3 was confirmed on 2026-09-23. Decision 2.7 was added on
  2026-09-23 from the implementation readiness report (L5).
- **Readiness:** the findings of `implementation-readiness-2026-09-23.md` (gate CONCERNS) are applied
  here on 2026-09-23; L7 was open question 15, closed on 2026-09-23, and L1, L4 and L8 need the maintainer (open
  questions 17 to 19).

## Beyond 0.2

A judge is tracked as a future capability under RP-E002
([#21](https://github.com/JakeSelby/ruleprobe/issues/21)): a model-free verdict-source seam in ruleprobe,
proposed for 0.3, and later a separate, provider-neutral judge library that depends on ruleprobe and
never the reverse. PRD FR-35 and the PRD's §8 "Beyond 0.2" note describe it. It has no stories here and
is not scheduled.

# 0.3.0 and 0.4.0

Added 2026-09-25 under #127 (RP-T009), from the roadmap the maintainer approved that day. Epic 7 above is
withdrawn but keeps its number and its issue (#28), so these epics start at 8. Every item is proposed.
Epic issues are filed with `scripts/bmad_issue_sync.py new` (#128 to #135, RP-E010 to RP-E017); story issues are filed when each epic
starts, and until then a story's title is its proposed issue title. Stories follow "How to read a story"
above; AD ids are the ruleprobe spine's.

## Requirements Inventory, 0.3 and 0.4

### Functional Requirements

- FR-35: Judge receipts: a versioned JSONL verdict format with provenance, a judge scored as one more
  rater, judge-human agreement in `corpus`. Amended 2026-09-25 (proposed, v0.4.0, #21).
- FR-36: Per-sentence binding, with exception and condition words scoped to their sentence, negated
  markers recognised, and catalog patterns for the four unbound defaults. Proposed, v0.3.0.
- FR-37: The binder scored like a detector on a synthetic zoo of about 60 rule sentences. Proposed,
  v0.3.0.
- FR-38: Rule discovery with no `--rules`, naming the nearest catalog entry and the blocking word, and
  saying the rule text is today's. Proposed, v0.3.0.
- FR-39: A version hash on every detector. Proposed, v0.3.0.
- FR-40: `ruleprobe audit` samples hits and near-misses for judging. Proposed, v0.3.0.
- FR-41: Content-free validity cards pooled into a shipped field figure, per source. Proposed, v0.3.0.
- FR-42: Wilson and session-clustered bounds on every rate; notes read from bounds. Proposed, v0.3.0.
- FR-43: Opt-in `snapshot DIR`, `report --rows`, and the `cleanupPeriodDays` warning. Proposed, v0.3.0.
- FR-44: A deciding event for session-level and compliance hits (#112). Proposed, v0.3.0.
- FR-45: Reader health counts. Proposed, v0.3.0.
- FR-46: `ruleprobe compare` with Newcombe intervals, minimum detectable effect, controls and
  confound warnings. Proposed, v0.4.0.
- FR-47: A dark-rule slice as the judge's calibration set. Proposed, v0.4.0.
- FR-48: `ruleprobe merge`. Proposed, v0.4.0.
- FR-49: JSON Schemas for rows, cards, snapshots and verdicts. Proposed, v0.4.0.
- FR-50: A mutation-tested corpus, at least 80% of mutants caught per detector. Proposed, v0.4.0.
- FR-51: A binding corpus of at least 200 sections, precision at least 0.95. Proposed, v0.4.0.

### NonFunctional Requirements

- NFR-3: Deterministic output gains a two-hash-seed, reversed-order test and a seeded parse fuzz test.
- NFR-5: `audit` and `snapshot` write, each only under a directory the user names.
- NFR-10: The default-set field floor: point estimate at least 0.90, Wilson lower bound at least 0.80,
  on at least 20 judged hits from at least 2 developers.
- NFR-11: CI on ubuntu, macOS and Windows, on Python 3.9 and 3.x.

### Additional Requirements

- AD-15: cards and snapshot rows hold counts only, built from an allow-list.
- AD-16: one detector hash function; no declared version means no hash, and `compare` refuses.
- AD-17: one standard-library statistics module owns every interval.
- AD-18: the sentence is the binding unit inside AD-12's section rule, under AD-4.

### FR Coverage Map

| FR | Stories |
| --- | --- |
| FR-35 | 15.1 |
| FR-36 | 8.1, 8.3, 8.4 |
| FR-37 | 8.1, 8.2 |
| FR-38 | 8.5 |
| FR-39 | 10.1 |
| FR-40 | 10.2 |
| FR-41 | 10.3, 10.4 |
| FR-42 | 11.1 |
| FR-43 | 11.2, 11.3 |
| FR-44 | 11.4 (#112) |
| FR-45 | 12.2 |
| FR-46 | 14.1, 14.2, 14.3 |
| FR-47 | 15.2 |
| FR-48 | 15.3 |
| FR-49 | 15.4 |
| FR-50 | 15.5 |
| FR-51 | 15.6 |
| NFR-3 | 12.3, 12.4 |
| NFR-10 | 9.5 |
| NFR-11 | 12.1 |

## Epic List, 0.3 and 0.4

Milestone v0.3.0 holds Epics 8 to 13; v0.4.0 holds Epics 14 and 15. The field floor, rule discovery and
history ship first, and five testers are recruited before `compare` is built. Housekeeping #121 and
#124 lands before Epic 8 starts.

### Epic 8: a first run with no configuration (#128, RP-E010)
A stranger runs `ruleprobe report` with no flags and sees their own rules found, bound per sentence and
measured inside a minute, with the binder scored like a detector.
**FRs covered:** FR-36, FR-37, FR-38; AD-18, AD-12.

### Epic 9: a field floor for the default detectors (#129, RP-E011)
Every default detector has field evidence behind it or leaves the defaults. Existing items: #110, #111,
#113 and #114.
**FRs covered:** FR-8 (amended), NFR-10.

### Epic 10: audit and validity cards (#130, RP-E012)
Anyone can judge a sample of a detector's hits and near-misses locally and hand back a card that holds
counts and no content; the cards become the shipped field figure.
**FRs covered:** FR-39, FR-40, FR-41; AD-15, AD-16.

### Epic 11: honest numbers and history (#131, RP-E013)
Every rate carries a bound, and history outlives Claude Code's 30-day deletion. Existing item: #112.
**FRs covered:** FR-42, FR-43, FR-44; AD-15, AD-17.

### Epic 12: robustness on three operating systems (#132, RP-E014)
The same transcripts give the same bytes on ubuntu, macOS and Windows, and the readers say what they set
aside.
**FRs covered:** FR-45, NFR-3, NFR-11.

### Epic 13: the 0.3 beta and launch (#133, RP-E015)
Five outside developers try a release candidate, 0.3.0 is tagged, agent-harness pins it (#27, alongside
this epic), and the launch goes out with every public text approved first.
**FRs covered:** SM-1, SM-2 (evidence); FR-31 (the Breaking heading).

### Epic 14: compare, before and after (#134, RP-E016)
A developer asks whether a rule change changed behaviour and gets detected, inconclusive or confounded.
**FRs covered:** FR-46; AD-17, AD-16.

### Epic 15: team roll-up, schemas and corpus proof (#135, RP-E017)
Reports pool across a team without session keys, the formats are published, and the corpus is proven
to catch a broken detector. #21 covers the judge receipts and the dark-rule slice; #115 records the
judge's package boundary.
**FRs covered:** FR-35, FR-47, FR-48, FR-49, FR-50, FR-51.

## Epic 8: a first run with no configuration

**Issue:** [#128](https://github.com/JakeSelby/ruleprobe/issues/128) (RP-E010).

A developer with an unedited rule file sees rules measured with no flags. Binding is per sentence and
under-counts (AD-18). Runs after housekeeping #121 and #124.

### Story 8.1: `spike(rules): score the section binder and a per-sentence binder on a rules zoo`

**Kind:** spike · **Binds:** FR-36, FR-37; AD-18, AD-4 · **Depends on:** none

As the maintainer,
I want both binders scored on labelled rule sentences before either ships,
So that per-sentence binding is chosen on a number, not a hunch.

**Acceptance Criteria:**

1. **Given** a synthetic zoo of about 60 labelled rule sentences in common phrasings, with near-misses for conditions, exceptions and contrasts, **When** both binders run on it, **Then** the spike records each one's recall and false binds.
2. **Given** the exit criterion, **When** the result is recorded, **Then** it says whether per-sentence binding reaches recall of at least 0.70 with zero false binds, and what blocks it if not.
3. **Given** the zoo, **When** it is written, **Then** it holds no real transcript or rule-file text.

**Files:** spike story file; zoo draft under `tests/fixtures/`. **Tests:** none; 8.2 makes the zoo a gate.

### Story 8.2: `feat(corpus): score rule binding in ruleprobe corpus`

**Kind:** story · **Binds:** FR-37, NFR-6; AD-6, AD-18 · **Depends on:** 8.1

As a contributor changing the binder,
I want `corpus` to score binding like a detector,
So that a binding regression fails CI.

**Acceptance Criteria:**

1. **Given** the zoo shipped under `ruleprobe/corpus/`, **When** `ruleprobe corpus` runs, **Then** it prints a binder section with binding precision and recall.
2. **Given** a false bind in the zoo, **When** `corpus --floor 0.9` runs, **Then** it exits non-zero.
3. **Given** `--json`, **When** it runs, **Then** the binder figures appear beside the detector figures.

**Files:** `ruleprobe/validity.py`, `ruleprobe/corpus/`. **Tests:** `tests/test_validity.py`.

### Story 8.3: `feat(rules): bind rules per sentence`

**Kind:** story · **Binds:** FR-36, NFR-4; AD-18, AD-12 · **Depends on:** 8.2

As a developer with dense rule files,
I want each sentence to bind its own detector,
So that a section mixing several rules is measured rather than dropped.

**Acceptance Criteria:**

1. **Given** a section whose two sentences each match a different catalog entry, **When** it binds, **Then** it binds both, and the rule id is still AD-12's section id.
2. **Given** a sentence matching no entry or several, **When** it binds, **Then** that sentence binds nothing.
3. **Given** "unless" in one sentence, **When** the section binds, **Then** only that sentence is unbound.
4. **Given** "admit no exception" or "without exception", **When** the sentence binds, **Then** the marker does not unbind it.
5. **Given** the zoo, **When** `corpus` runs, **Then** binding recall is at least 0.70 with zero false binds.

**Files:** `ruleprobe/rules.py`, `ruleprobe/detectors/catalog.py`. **Tests:** `tests/test_rules.py`, the zoo.

### Story 8.4: `feat(detectors): catalog patterns for the four unbound default detectors`

**Kind:** story · **Binds:** FR-36, FR-16; AD-12, AD-6 · **Depends on:** 8.3

As a developer whose rules mention compaction, model switching, secrets or `find`,
I want those rules bound to the shipped detectors,
So that the defaults measure my own rules.

**Acceptance Criteria:**

1. **Given** a rule sentence in the shape of each of `compact`, `model-switch`, `secret-in-write` and `unfiltered-find`, **When** it binds, **Then** it binds that detector, catalog-bound.
2. **Given** a near-miss sentence for each, **When** it binds, **Then** it stays unbound.
3. **Given** `secret-in-write` outside the defaults (Epic 9), **When** its rule binds, **Then** the coverage block says which detector it bound and that the detector is not a default.

**Files:** `ruleprobe/detectors/catalog.py`, the zoo. **Tests:** `tests/test_rules.py`.

### Story 8.5: `feat(rules): find the rule files with no --rules`

**Kind:** story · **Binds:** FR-38, NFR-5, NFR-9; AD-18, AD-8 · **Depends on:** 8.3

As a first-time user,
I want `ruleprobe report` to find my rule files itself,
So that my first run needs no flags.

**Acceptance Criteria:**

1. **Given** no `--rules`, **When** `report` runs, **Then** it reads `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md` and the project rule files at each session's recorded working directory.
2. **Given** an unmeasured section, **When** the coverage block prints, **Then** it names the nearest catalog entry and the word that blocked the bind.
3. **Given** any discovered run, **When** the coverage block prints, **Then** it says the rule text is today's, not the text in force when an older session ran.
4. **Given** a fixture home with one bindable rule, **When** `report` runs with no flags, **Then** that rule is measured inside 60 seconds.
5. **Given** a discovered run, **When** it finishes, **Then** no file was written.

**Files:** `ruleprobe/rules.py`, `ruleprobe/cli.py`, `ruleprobe/report.py`. **Tests:** `tests/test_rules.py`, `tests/test_cli.py`.

## Epic 9: a field floor for the default detectors

**Issue:** [#129](https://github.com/JakeSelby/ruleprobe/issues/129) (RP-E011).

The default set is the detectors that clear NFR-10. Four existing items fix what the 0.2.0 field
reading found; 9.5 sets the gate once Epic 10's field figure and Epic 11's bounds exist.

### Story 9.1: #114 `decision(readers): whether a cancelled or errored tool call counts as a tool use`

**Kind:** decision (existing, RP-D012) · **Binds:** FR-3; AD-2, AD-4 · **Depends on:** none

Its story file holds the design. It is listed here so the epic's scope is whole.

### Story 9.2: #110 `fix(detectors): secret-in-write stops counting text about secrets`

**Kind:** bug (existing, RP-B009) · **Binds:** FR-8, NFR-10; AD-4 · **Depends on:** 9.1

Redesigns `secret-in-write` to count an action that writes a secret-shaped value, not text that mentions
secrets: the action-versus-mention principle. Until it clears the floor, `secret-in-write` is out of the
defaults.

### Story 9.3: #111 `fix(detectors): whole-file-cat skips a cat inside a redirected group`

**Kind:** bug (existing, RP-B010) · **Binds:** FR-8; AD-5, AD-4 · **Depends on:** none

### Story 9.4: #113 `fix(readers): --runtime gemini and auto read the same Gemini files under a root`

**Kind:** bug (existing, RP-B012) · **Binds:** FR-32; AD-10 · **Depends on:** none

### Story 9.5: `feat(validity): hold the default set to the field floor`

**Kind:** story · **Binds:** NFR-10, FR-8, FR-31; AD-15, AD-17 · **Depends on:** 9.1 to 9.4, 10.3, 11.1

As a developer trusting the defaults,
I want every default detector to carry field evidence,
So that a default number is never a synthetic 1.00 alone.

**Acceptance Criteria:**

1. **Given** the shipped `field.json`, **When** the suite runs, **Then** a test fails for any default detector whose field precision is under 0.90, whose Wilson lower bound is under 0.80, or that has fewer than 20 judged hits from 2 developers.
2. **Given** a detector under the floor, **When** the release is prepared, **Then** it leaves the defaults and `CHANGELOG.md` names it under a Breaking heading.
3. **Given** the README's detector section, **When** it is read, **Then** it states the floor and each default's field figure.
4. **Given** `secret-in-write` before #110 clears the floor, **When** the defaults load, **Then** it is not among them.

**Files:** `ruleprobe/detectors/`, `README.md`, `CHANGELOG.md`. **Tests:** a new floor test reading `field.json`.

## Epic 10: audit and validity cards

**Issue:** [#130](https://github.com/JakeSelby/ruleprobe/issues/130) (RP-E012).

Evidence capture that never copies content (AD-15), keyed to a detector's version (AD-16).

### Story 10.1: `feat(registry): a version hash on every detector`

**Kind:** story · **Binds:** FR-39; AD-16 · **Depends on:** none

As someone pooling figures,
I want each figure tied to the detector version that produced it,
So that a changed detector never inherits an old figure.

**Acceptance Criteria:**

1. **Given** the same detector definition, **When** it is hashed on each CI platform and Python version, **Then** the hash is the same.
2. **Given** a change to a detector's matching, **When** it is hashed, **Then** the hash changes; a change only to `examples:` leaves it.
3. **Given** a Python detector that declares no version, **When** it is hashed, **Then** it has no hash.
4. **Given** `ruleprobe detectors`, **When** it runs, **Then** each detector's hash is printed.

**Files:** `ruleprobe/registry.py`, `ruleprobe/declarative.py`. **Tests:** `tests/test_registry.py`.

### Story 10.2: `feat(audit): sample a detector's hits and near-misses for judging`

**Kind:** story · **Binds:** FR-40, NFR-5; AD-13, AD-15, AD-8 · **Depends on:** 10.1

As a developer checking a detector,
I want a seeded sample of its hits and near-misses to judge,
So that I can say how often it is right on my own transcripts.

**Acceptance Criteria:**

1. **Given** `ruleprobe audit --detector <id> --sample N --seed S`, **When** it runs twice on the same transcripts, **Then** it draws the same sample.
2. **Given** an event that failed exactly one clause of the detector, **When** sampling runs, **Then** it can be drawn as a near-miss.
3. **Given** an item with a known secret shape, **When** it is shown, **Then** the shape never appears.
4. **Given** a verdict of right, wrong or unsure, **When** it is recorded, **Then** it is written only under the directory the user named.

**Files:** `ruleprobe/cli.py`, `ruleprobe/validity.py`. **Tests:** `tests/test_validity.py`, `tests/test_cli.py`.

### Story 10.3: `feat(audit): content-free validity cards and the shipped field figure`

**Kind:** story · **Binds:** FR-41, NFR-10; AD-15, AD-16 · **Depends on:** 10.2

As someone contributing field evidence,
I want a card I can share without sharing a transcript,
So that my verdicts count toward the field figure.

**Acceptance Criteria:**

1. **Given** `audit --card`, **When** it runs, **Then** the card holds exactly AD-15's keys.
2. **Given** sessions holding known strings, **When** a card is written, **Then** none of them, no session id and no path appear in it.
3. **Given** cards from several sources, **When** they pool into `ruleprobe/validity/field.json`, **Then** figures are shown per source with contributor counts.
4. **Given** an excluded source, **When** the figure prints, **Then** the exclusion and its stated reason are shown.
5. **Given** a card whose detector hash differs from the shipped one, **When** the figure prints, **Then** it is flagged stale and does not count toward NFR-10.

**Files:** `ruleprobe/validity.py`, `ruleprobe/validity/field.json`, `pyproject.toml` package data. **Tests:** `tests/test_validity.py`.

### Story 10.4: `task(validity): retake the pre-fix figures and publish agent-human agreement`

**Kind:** task · **Binds:** FR-41, NFR-10 · **Depends on:** 10.3, 9.2, 9.3

As the maintainer,
I want the field figures current and their judges checked,
So that a published figure says who judged it and how well they agree.

**Acceptance Criteria:**

1. **Given** the four figures that predate their fixes, **When** they are retaken, **Then** the new cards carry the fixed detectors' hashes.
2. **Given** every sample, **When** it is judged, **Then** at least a fifth of it is human-judged.
3. **Given** at least 30 agent verdicts re-judged by a human, **When** agreement is computed, **Then** kappa is published beside the figures.

**Files:** `ruleprobe/validity/field.json`, `README.md`. **Tests:** 9.5's floor test.

## Epic 11: honest numbers and history

**Issue:** [#131](https://github.com/JakeSelby/ruleprobe/issues/131) (RP-E013).

Bounds from one statistics module (AD-17) and count-only history (AD-15).

### Story 11.1: `feat(report): Wilson and session-clustered bounds on every rate`

**Kind:** story · **Binds:** FR-42, FR-17, FR-21, NFR-3; AD-17 · **Depends on:** none

As a developer reading a share,
I want its bound beside it,
So that 3 of 20 and 300 of 2,000 no longer look the same.

**Acceptance Criteria:**

1. **Given** any share or field precision, **When** the report prints, **Then** it carries a Wilson 95% bound, in the table and in `report_data`.
2. **Given** a compliance rate, **When** it prints, **Then** it carries a session-clustered bound; below FR-22's minimum it carries none.
3. **Given** `unobserved` and `frequent`, **When** they are decided, **Then** they read a bound, not the point estimate.
4. **Given** `--validity`, **When** it prints, **Then** the field figure comes before the corpus figure.
5. **Given** the golden rows, **When** the suite runs, **Then** they carry the bounds and match byte for byte.

**Files:** `ruleprobe/stats.py` (new), `ruleprobe/report.py`. **Tests:** `tests/test_stats.py`, `tests/test_report.py`.

### Story 11.2: `feat(snapshot): save count-only rows and read them with report --rows`

**Kind:** story · **Binds:** FR-43, NFR-5; AD-15, AD-16, AD-8 · **Depends on:** 10.1

As a developer who will want to compare later,
I want to save count-only history now,
So that a rule change can be tested after the transcripts are gone.

**Acceptance Criteria:**

1. **Given** `ruleprobe snapshot DIR`, **When** it runs, **Then** it writes rows keyed by runtime, session key and detector hash, only under `DIR`.
2. **Given** a saved row, **When** it is read, **Then** it holds no transcript text and no path.
3. **Given** a session saved twice, **When** `report --rows` reads both files, **Then** it counts once.
4. **Given** `report` with no `snapshot`, **When** it runs, **Then** it writes nothing.

**Files:** `ruleprobe/cli.py`, `ruleprobe/report.py`. **Tests:** `tests/test_report.py`, `tests/test_cli.py`.

### Story 11.3: `feat(readers): warn when Claude Code history stops at about 30 days`

**Kind:** story · **Binds:** FR-43 · **Depends on:** 11.2

As a first-time user,
I want to know my transcripts are being deleted,
So that I can keep them or snapshot them before a comparison needs them.

**Acceptance Criteria:**

1. **Given** Claude Code transcripts whose oldest session is about 30 days old, **When** the first run reports, **Then** it warns and names `cleanupPeriodDays`.
2. **Given** history older than that, **When** it reports, **Then** no warning prints.
3. **Given** the warning, **When** it prints, **Then** it names `ruleprobe snapshot` as the way to keep counts.

**Files:** `ruleprobe/readers/claude_code.py`, `ruleprobe/report.py`. **Tests:** `tests/test_readers.py`. [ASSUMPTION: the reader module name]

### Story 11.4: #112 `fix(explain): show the deciding event for session-level and compliance hits`

**Kind:** bug (existing, RP-B011) · **Binds:** FR-44, FR-25; AD-13 · **Depends on:** none

Every corpus hit explains itself, session-level and compliance hits included.

## Epic 12: robustness on three operating systems

**Issue:** [#132](https://github.com/JakeSelby/ruleprobe/issues/132) (RP-E014).

### Story 12.1: `ci: run the suite on ubuntu, macOS and Windows`

**Kind:** chore · **Binds:** NFR-11, NFR-2 · **Depends on:** none

As a developer on Windows or macOS,
I want CI to prove ruleprobe runs where I do,
So that a platform bug is caught before release.

**Acceptance Criteria:**

1. **Given** a pull request, **When** CI runs, **Then** the suite runs on ubuntu, macOS and Windows, each on Python 3.9 and 3.x, and all pass.
2. **Given** the required checks, **When** the matrix lands, **Then** the ruleset names the new jobs.

**Files:** `.github/workflows/`. **Tests:** the matrix itself.

### Story 12.2: `feat(readers): count dropped lines, unknown record types and CLI versions`

**Kind:** story · **Binds:** FR-45; AD-10, AD-2 · **Depends on:** none

As a developer reading a quiet report,
I want to know what the readers set aside,
So that a quiet number is not mistaken for a clean one.

**Acceptance Criteria:**

1. **Given** a fixture with one malformed line and one unknown record type, **When** it is read, **Then** each is counted once.
2. **Given** a run, **When** the coverage block and `--json` print, **Then** both carry the three counts, with the agent CLI versions seen.
3. **Given** any reader, **When** it drops a line, **Then** the line is counted.

**Files:** `ruleprobe/readers/`, `ruleprobe/report.py`. **Tests:** `tests/test_readers.py`.

### Story 12.3: `test: identical bytes under two hash seeds and reversed file order`

**Kind:** task · **Binds:** NFR-3; AD-8 · **Depends on:** 12.1

**Acceptance Criteria:**

1. **Given** the suite's report fixture, **When** it runs under two `PYTHONHASHSEED` values and with file order reversed, **Then** the output bytes are identical, on all three operating systems.

**Files:** `tests/`. **Tests:** the new determinism test.

### Story 12.4: `test(shell): seeded fuzzing of the shell parse`

**Kind:** task · **Binds:** NFR-3, NFR-4; AD-5 · **Depends on:** none

**Acceptance Criteria:**

1. **Given** a fixed seed, **When** the fuzz test feeds generated commands to the shell parse, **Then** it never raises and each input parses the same way twice.
2. **Given** the fuzz test, **When** it runs, **Then** it uses the standard library only and finishes within the suite's normal time. [ASSUMPTION: a time budget set in the story]

**Files:** `tests/test_shell.py`. **Tests:** the fuzz test.

## Epic 13: the 0.3 beta and launch

**Issue:** [#133](https://github.com/JakeSelby/ruleprobe/issues/133) (RP-E015).

#27 (RP-E008) sits alongside this epic: agent-harness bumps to 0.3, including its detector-count test,
and checks what it measures after the default set changes.

### Story 13.1: `chore(release): publish 0.3.0rc1`

**Kind:** chore · **Binds:** FR-31 · **Depends on:** Epics 8 to 12

**Acceptance Criteria:**

1. **Given** the release procedure in `docs/releasing.md`, **When** `v0.3.0rc1` is tagged, **Then** the tag workflow publishes it and nothing is uploaded by hand.

**Files:** `ruleprobe/__init__.py`, `CHANGELOG.md`. **Tests:** the release preflight.

### Story 13.2: `task(beta): five outside developers try the no-flags first run`

**Kind:** task · **Binds:** FR-38, FR-41, SM-1, NFR-9 · **Depends on:** 13.1

As the maintainer,
I want strangers to try the first run before launch,
So that the headline claim is observed, not assumed.

**Acceptance Criteria:**

1. **Given** five developers outside the project, **When** they run the release candidate with no flags, **Then** at least three see one of their rules measured inside 60 seconds.
2. **Given** the testers, **When** they report, **Then** at least two return a validity card.
3. **Given** each tester's volume, **When** `report` is timed, **Then** only a run past 60 seconds is acted on.
4. **Given** the reports, **When** they are recorded, **Then** the story holds synthesized findings, never transcript content or names.

**Files:** story file. **Tests:** none.

### Story 13.3: `chore(release): tag 0.3.0`

**Kind:** chore · **Binds:** FR-31, NFR-10 · **Depends on:** 13.2

**Acceptance Criteria:**

1. **Given** what the testers hit, **When** it is fixed, **Then** each fix has its own issue and pull request.
2. **Given** the changelog, **When** 0.3.0 is folded, **Then** the default-set change sits under a Breaking heading.
3. **Given** the tag, **When** it is pushed, **Then** #27's agent-harness bump follows.

**Files:** `CHANGELOG.md`, `ruleprobe/__init__.py`. **Tests:** the release preflight.

### Story 13.4: `docs(launch): the field scan and the launch kit`

**Kind:** task · **Binds:** SM-2 · **Depends on:** 13.3

As the maintainer,
I want the launch to position ruleprobe honestly against its neighbours,
So that it is found by the people it serves.

**Acceptance Criteria:**

1. **Given** claude-md-doctor and RuleReceipt, **When** the field scan is written, **Then** it positions ruleprobe on determinism, privacy and measured validity, and says whether the ATIF and Inspect routes hold.
2. **Given** the kit, **When** it is drafted, **Then** it holds a front-door README, list submissions and posts.
3. **Given** any public text, **When** it is ready, **Then** the maintainer approves it before it goes out.

**Files:** `README.md`, story file. **Tests:** none.

## Epic 14: compare, before and after

**Issue:** [#134](https://github.com/JakeSelby/ruleprobe/issues/134) (RP-E016).

### Story 14.1: `feat(stats): Newcombe intervals and the minimum detectable effect`

**Kind:** story · **Binds:** FR-46; AD-17 · **Depends on:** 11.1

**Acceptance Criteria:**

1. **Given** two proportions, **When** their difference is computed, **Then** it carries Newcombe's hybrid score interval, checked against published worked examples.
2. **Given** two sides' sizes and a pooled rate, **When** the minimum detectable effect is computed, **Then** it uses a two-sided alpha of 0.05 and 80% power.
3. **Given** compliance rates, **When** they are compared, **Then** the interval is built from the session-clustered bounds.

**Files:** `ruleprobe/stats.py`. **Tests:** `tests/test_stats.py`.

### Story 14.2: `feat(compare): compare two windows or two groups`

**Kind:** story · **Binds:** FR-46, FR-21; AD-17, AD-16 · **Depends on:** 14.1, 11.2

As a developer who changed a rule,
I want before and after side by side with an honest interval,
So that I know whether the change did anything.

**Acceptance Criteria:**

1. **Given** `--split-at DATE`, or two groups by stance, model or runtime, **When** `compare` runs, **Then** each detector shows the difference, its Newcombe interval and the minimum detectable effect.
2. **Given** an interval spanning zero, **When** it prints, **Then** the detector reads `inconclusive`.
3. **Given** detectors whose rules did not change, **When** it prints, **Then** they appear as controls.
4. **Given** a detector that defines opportunities, **When** it is compared, **Then** its rate uses opportunities.
5. **Given** a detector hash that differs between the sides, **When** `compare` runs, **Then** it refuses that detector and says why.
6. **Given** saved rows, **When** `compare` reads them through `--rows`, **Then** they count as transcripts would.

**Files:** `ruleprobe/cli.py`, `ruleprobe/report.py`. **Tests:** `tests/test_compare.py`.

### Story 14.3: `feat(compare): confound warnings and git-aware windows`

**Kind:** story · **Binds:** FR-46, FR-38; AD-17 · **Depends on:** 14.2

**Acceptance Criteria:**

1. **Given** a model mix that shifts between the sides, **When** `compare` runs, **Then** it warns and the fixture reads `confounded`.
2. **Given** a rule edit that followed a bad stretch, **When** `compare` runs, **Then** it warns about regression to the mean.
3. **Given** the opt-in `git log` window on a rule file, **When** it is chosen, **Then** the split falls at that file's last change.
4. **Given** fixtures with an effect, with none and with a model shift, **When** `compare` runs, **Then** they read detected, inconclusive and confounded.

**Files:** `ruleprobe/cli.py`, `ruleprobe/report.py`. **Tests:** `tests/test_compare.py`.

## Epic 15: team roll-up, schemas and corpus proof

**Issue:** [#135](https://github.com/JakeSelby/ruleprobe/issues/135) (RP-E017).

#21 (RP-E002) covers 15.1 and 15.2; ruleprobe still calls no model. #115 (RP-T007) records the judge as
a separate package.

### Story 15.1: `feat(validity): judge receipts`

**Kind:** story · **Binds:** FR-35, NFR-7; AD-8, AD-17 · **Depends on:** 10.3

**Acceptance Criteria:**

1. **Given** a versioned JSONL file of verdicts with provider, model and pack version, **When** `corpus` reads it, **Then** the judge is scored as one more rater.
2. **Given** items judged by a human and the judge, **When** `corpus` runs, **Then** it prints judge-human agreement on the shared items.
3. **Given** the core package, **When** it is imported, **Then** no model client is imported and no model is called.

**Files:** `ruleprobe/validity.py`. **Tests:** `tests/test_validity.py`.

### Story 15.2: `feat(corpus): a dark-rule slice`

**Kind:** story · **Binds:** FR-47 · **Depends on:** 15.1

**Acceptance Criteria:**

1. **Given** 10 to 20 common rules no detector can see, **When** the slice ships, **Then** each has hand-labelled followed and not-followed synthetic sessions.
2. **Given** the slice, **When** `corpus` runs, **Then** it scores judges on it and no detector.

**Files:** `ruleprobe/corpus/`. **Tests:** `tests/test_validity.py`.

### Story 15.3: `feat(merge): roll reports up across a team`

**Kind:** story · **Binds:** FR-48, NFR-8; AD-15 · **Depends on:** 11.1

**Acceptance Criteria:**

1. **Given** three JSON reports, **When** `merge` runs, **Then** the result equals the report over the union of their rows.
2. **Given** the merged report, **When** it is written, **Then** it holds no session key.
3. **Given** `merge`, **When** it runs, **Then** it reads only the files named and sends nothing.

**Files:** `ruleprobe/cli.py`, `ruleprobe/report.py`. **Tests:** `tests/test_report.py`.

### Story 15.4: `feat(schemas): publish JSON Schemas for rows, cards, snapshots and verdicts`

**Kind:** story · **Binds:** FR-49, FR-31; AD-15 · **Depends on:** 15.1, 15.3

**Acceptance Criteria:**

1. **Given** each golden output, **When** the suite runs, **Then** it validates against its published schema.
2. **Given** the package contract, **When** schemas are checked, **Then** no runtime dependency is added. [ASSUMPTION: a standard-library check of the schema subset used]

**Files:** schema files, `tests/`. **Tests:** a schema test.

### Story 15.5: `test(corpus): mutation-test every declarative detector's corpus`

**Kind:** story · **Binds:** FR-50, NFR-1; AD-6, AD-7 · **Depends on:** none

**Acceptance Criteria:**

1. **Given** each declarative detector, **When** mutants are generated (a flipped operator, a dropped clause), **Then** its corpus fails at least 80% of them.
2. **Given** the tool, **When** it runs, **Then** it uses the standard library only.

**Files:** `ruleprobe/validity.py` or `scripts/`. **Tests:** the mutation run in CI.

### Story 15.6: `feat(corpus): a binding corpus of at least 200 sections`

**Kind:** story · **Binds:** FR-51; AD-18 · **Depends on:** 8.2

**Acceptance Criteria:**

1. **Given** a census of public rule files collected outside the package after a licensing review, **When** the corpus is written, **Then** only paraphrases ship.
2. **Given** at least 200 labelled sections, **When** `corpus` scores the binder, **Then** precision is at least 0.95.
3. **Given** a release, **When** its notes are written, **Then** they publish the binding rate.

**Files:** `ruleprobe/corpus/`. **Tests:** 8.2's binder section.

## Validation, 0.3 and 0.4

- **FR coverage:** FR-35 to FR-51, NFR-10 and NFR-11 each bound by at least one story (the map above).
- **Forward dependencies:** one crosses epics forward: 9.5 depends on 10.3 and 11.1, because the floor
  needs the field figure and its bound. Epic 9's four fixes land first; 9.5 closes the epic after them.
  10.4 depends on 9.2 and 9.3 for the same reason.
- **Existing items:** #110, #111, #113 and #114 under Epic 9; #112 under Epic 11; #27 alongside Epic
  13; #21 over 15.1 and 15.2; #115 beside Epic 15. None is re-filed.
- **Items:** 35 (21 stories, 5 tasks, 3 chores, 4 bugs, 1 spike, 1 decision), 5 of them existing issues.
