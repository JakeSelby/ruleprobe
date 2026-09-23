---
name: 'ruleprobe'
type: architecture-spine
purpose: build-substrate
altitude: feature
paradigm: 'pipes-and-filters, batch per session: readers -> event list -> one shell parse -> detectors -> rows -> report'
scope: 'The ruleprobe package: readers, event schema, shell parse, registry, matchers, declarative format, rule binding, report, validity and CLI. 0.1.0 as built, and the v0.2.0 PRD.'
status: final
created: '2026-09-23'
updated: '2026-09-23'
binds: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27, FR-28, FR-29, FR-30, FR-31, FR-32, FR-33, FR-34, NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-6, NFR-7, NFR-8, NFR-9, agent-harness AD-13, agent-harness AD-21]
sources:
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/validation-report.md
  - ruleprobe/ (module docstrings at ae84ac3)
  - _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/validation-report.md
  - https://github.com/JakeSelby/ruleprobe/issues/19
  - ruleprobe/corpus/labels.yaml
  - ruleprobe/detectors/common.yaml
  - tests/test_equivalence.py
  - pyproject.toml
  - .github/workflows/
  - https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/architecture-spines/architecture-agent-harness-2026-09-23/ARCHITECTURE-SPINE.md
companions: []
---

# Architecture Spine: ruleprobe

Every rule below is tagged. `[ADOPTED]` means the 0.1.0 code already does it (implemented, 0.1.0).
`[PROPOSED]` means the rule binds v0.2.0 work that does not exist yet (planned, v0.2.0). Inferences carry
`[ASSUMPTION: ...]`. Rationale is in `.memlog.md` beside this file.

## Design Paradigm

**Pipes and filters, batch per session.** `iter_sessions` streams sessions. Inside a session the event
list is materialised, parsed once, and handed whole to every detector, because session matchers
(`order`, `absent`, `change`) read the whole list. A detector is a filter from that list to hits. A row is
a session's hits reduced to counts. The report and the validity scorer are two sinks over the same
filters.

```mermaid
flowchart LR
  T[(transcripts on disk)] --> R[readers<br/>one per runtime]
  R -->|Session with event list| A[shell.analyse<br/>once per session]
  A -->|events, Context| D[detectors<br/>Python or compiled data]
  D -->|Hit list| M[report.measure]
  M -->|row| P[report / report_data]
  C[(corpus: sessions + labels)] --> R2[same readers]
  R2 --> A2[same analyse] --> D2[same detectors] --> V[validity: precision, recall, floor]
```

| Layer | Modules |
| --- | --- |
| Schema (leaf) | `ruleprobe/events.py` |
| Format (leaf) | `ruleprobe/declarative.py` |
| Parse | `ruleprobe/shell.py` |
| Engine | `ruleprobe/registry.py`, `ruleprobe/detectors/` |
| Compilers | `ruleprobe/matchers.py` |
| Binding | `ruleprobe/rules.py` |
| Sources | `ruleprobe/readers/` |
| Sinks | `ruleprobe/report.py`, `ruleprobe/validity.py` |
| Shell | `ruleprobe/cli.py`, `ruleprobe/__main__.py`, `ruleprobe/__init__.py` (re-exports) |

## Inherited Invariants

| Inherited | From parent | Binds here |
| --- | --- | --- |
| AD-13: detector logic lives in `ruleprobe` | [agent-harness spine](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/architecture-spines/architecture-agent-harness-2026-09-23/ARCHITECTURE-SPINE.md) | The harness vendors a pinned wheel and never forks detector logic. A ruleprobe release means a harness bump. Declarative detectors are read through this engine. Here: AD-9 declares what the harness imports; no ruleprobe change may require the harness to copy detector code. |
| AD-21: dependencies | same | Standard library first, on a Python 3.9 floor. Third-party code enters the harness only as a pinned wheel loaded by path. Here: AD-10; the wheel stays pure Python and importable from a zip. |

Read-only. A local AD that weakens either is a conflict to surface, not an override.

## Invariants & Rules

### AD-1: Dependency direction [ADOPTED]

- **Binds:** all modules.
- **Prevents:** a reader that imports a detector, a detector that imports a reader, or an import cycle
  that breaks the zip import the harness relies on.
- **Rule:**
  - Imports point down the graph below. Nothing imports `cli`.
  - Three upward imports are sanctioned, each inside a function or at the module's tail, and no
    others: `registry.from_spec` imports `matchers`; `report._validity_note` imports `validity`;
    `registry` imports `detectors.common` at its tail to populate `DEFAULT`.
  - A new module takes a place in this graph in the change that adds it, and the spine is updated.
  - `detectors.catalog` (planned, v0.2.0, story 3.5) is a Python literal module under AD-9's package
    data rule. `rules` imports it; it imports `matchers` to compile its entries and nothing else.

```mermaid
flowchart TD
  cli --> report
  cli --> registry
  cli --> rules
  cli --> validity
  cli --> readers
  validity --> readers
  validity --> registry
  validity --> declarative
  validity --> events
  report --> registry
  rules --> matchers
  rules --> registry
  rules --> declarative
  rules --> detectors_catalog[detectors.catalog]
  detectors_catalog --> matchers
  matchers --> registry
  matchers --> shell
  matchers --> declarative
  matchers --> events
  detectors_common[detectors.common] --> registry
  detectors_common --> shell
  detectors_common --> events
  registry --> shell
  registry --> events
  shell --> events
  readers --> events
```

### AD-2: The event schema is the one contract between readers and detectors [ADOPTED]

- **Binds:** FR-1, FR-2, FR-3, FR-4, FR-32; every detector and matcher.
- **Prevents:** a reader adding a field a detector then depends on for one runtime only, or a detector
  that works on one runtime and silently not on another.
- **Rule:**
  - `ruleprobe/events.py`'s module docstring is the schema: five kinds (`assistant_text`, `tool_use`,
    `tool_result`, `user_prompt`, `compact`), each with `turn` and the fields listed there. A reader
    emits nothing else.
  - `turn` increments on every `user_prompt`. `final` is derived by the reader: the last
    `assistant_text` before the next `user_prompt` or the end. Every reader derives both the same way.
  - A detector reads fields through `input_of`, `text_of` and `.get`, never by index, and never
    branches on the runtime. `Session.runtime` exists for rows, not for detectors.
  - A new kind or field is added in `events.py` first, in the same change as the reader that emits it.
    Adding one is a minor change; renaming, removing or changing the meaning of one is a breaking
    change under AD-9.

### AD-3: One tool vocabulary across runtimes [ADOPTED for Bash and Agent; PROPOSED for file tools]

- **Binds:** FR-2, FR-3, FR-32.
- **Prevents:** two readers mapping the same action to different names, so one detector counts it on
  one runtime and misses it on another.
- **Rule:**
  - Claude Code's tool names and input keys are canonical: `Bash` with `command`, `Agent` and `Task`,
    `Write` with `file_path` and `content`, `Edit` with `file_path` and `new_string`. The list grows
    only with a shipped detector that reads the new name or key.
  - A reader translates at read time, in one module-level table in its own module.
    `ruleprobe/readers/codex.py` maps `exec_command` to `Bash` and `spawn_agent` to `Agent`. A
    translated input keeps the native key beside the canonical one, as `cmd` sits beside `command`.
  - A native tool with no exact canonical twin keeps its native name. It then matches no canonical
    detector, which under-counts (AD-4). A lossy mapping is never made to gain a hit.
  - The third reader to map is Gemini CLI (PRD Q1, decided 2026-09-23). Spike RP-SP003 lists each of
    its file tools as exact or native before its reader is built; a native one stays native.
  - [ASSUMPTION: the canonical file-tool list above is what `ruleprobe/detectors/common.py` reads
    today; Gemini CLI's file tools are mapped to it or left native, decided in its story]

### AD-4: Detectors under-count rather than over-count [ADOPTED; negation implemented under #19, ships in v0.2.0]

- **Binds:** NFR-4, FR-5, FR-12, FR-16, FR-21; every detector and matcher.
- **Prevents:** a new matcher or detector that guesses on input it cannot read, so a report shows a
  hit that did not happen.
- **Rule:**
  - Undecidable input yields no hit: a missing or wrongly typed field, a command the shell parse
    skipped, or a command inside a substitution. `Parsed.skipped` marks a skipped command as
    unparsed, empty or over `MAX_COMMAND`.
  - Negation must not turn an undecidable input into a hit. In 0.1.0 it does
    ([#19](https://github.com/JakeSelby/ruleprobe/issues/19)): a segment matcher returns false for a
    skipped parse, so both `not` over it and `absent` of it fire (historical, 0.1.0; implemented
    under #19, unreleased, shipping in v0.2.0).
  - The segment matchers are every `command` key except `regex` and `unparsed`, every `git` key and
    every `env` key. Over a command the parse skipped, a segment matcher returns undecided.
  - `any`, `all` and `not` pass undecided through: `not` of undecided is undecided; `any` is true on
    any true, else undecided on any undecided; `all` is false on any false, else undecided on any
    undecided. A `when` that is undecided produces no hit.
  - `not`, `absent` and `order` treat undecided as no hit. An `absent` scope holding any undecided
    candidate and no true one yields no hit; an `order` hit needs `first` and `then` both true.
  - The undecided rule changes counts for user detectors that use `not` or `absent`, so it ships as part of the 0.2
    break (AD-9).
  - A new matcher lands with `fire` and `skip` examples, at least one `skip` a deliberate near-miss,
    and its known misses listed in the `ruleprobe/matchers.py` docstring.
  - A new Python detector lists its known misses in its docstring, as `ruleprobe/shell.py` does.

### AD-5: The shared shell parse is the only Bash decomposition [ADOPTED]

- **Binds:** FR-5, FR-6, FR-12, FR-30.
- **Prevents:** two detectors splitting the same command differently, so `command` matchers and Python
  detectors disagree about which segment a word is in.
- **Rule:**
  - `run()` calls `shell.analyse(events)` once per session. Detectors read `ctx.bash`, a list of
    `Parsed`. Matchers read the same `Parsed` through their environment.
  - No detector, matcher or reader tokenises a command itself. A `regex` over the raw command text
    is a text read, not a decomposition, and is allowed.
  - The parse never runs, resolves or opens anything. A new shell capability lands in
    `ruleprobe/shell.py` with its test in `tests/test_shell.py`, and its misses in the module docstring.

### AD-6: The labelled corpus is the validity contract, and the floor is 0.9 [ADOPTED; third-runtime sessions PROPOSED]

- **Binds:** FR-23, FR-24, FR-26, FR-33, NFR-6, FR-16.
- **Prevents:** a label keyed differently from a hit, a detector shipped unscored, or a floor lowered
  to let a detector through.
- **Rule:**
  - A label is keyed exactly as a `Hit`: `"<turn>:<tool_use_id>"`, or `"<turn>:-"` for a session hit.
    `ruleprobe/validity.py`'s `hit_key` and `event_key` are the only functions that build it; explain
    and label use them too.
  - The labels for a session are the whole truth for every detector they name.
  - Shipped corpus sessions are synthetic, hand-authored native-runtime transcripts read through the
    real readers, so the corpus tests readers as well as detectors. No real transcript content.
  - A session written by the FR-26 label command is an event-schema file, `<name>.events.jsonl`, one
    event dict per line, which `validity` loads without a runtime reader. It is the only other corpus
    session format. The loader takes each event's `turn` and `final` as written and never re-derives
    them, so a label keyed to turn 37 still matches. [ASSUMPTION: a native transcript cannot be
    rebuilt from one event]
  - Every detector the package ships, catalog entries included, is scored by labels or `examples:`
    and meets the floor in CI. An unscored third-party detector is shown as unscored and passes.
  - The floor stays 0.9. A detector under it is fixed or removed, with a changelog entry.
  - Only the FR-26 label command writes into a corpus, and only under a directory the user names.

### AD-7: The declarative format is a closed YAML subset with JSON as its equal [ADOPTED]

- **Binds:** FR-8, FR-10, FR-11, FR-12, FR-16, FR-27.
- **Prevents:** a detector file that two parsers read differently, a YAML dependency, or a matcher key
  that loads and never fires.
- **Rule:**
  - `ruleprobe/declarative.py` is the only parser. The subset in its docstring is closed: anchors,
    aliases, tags, block scalars, directives, merge keys, multi-document files, `yes`/`no`/`on`/`off`
    and leading-zero numbers are refused with a line number.
  - A document parses to the same objects from YAML or JSON.
  - The matcher vocabulary in `ruleprobe/matchers.py` is closed: an unknown key is a
    `DeclarativeError` with a line number.
  - Widening the subset or the vocabulary is a contract change under AD-9, with tests in
    `tests/test_declarative.py` or `tests/test_matchers.py`.
  - A shipped Python detector that the matcher set can express keeps a declarative twin in
    `ruleprobe/detectors/common.yaml`, and `tests/test_equivalence.py` asserts hit-for-hit equality.
    Catalog detectors are declarative only.

### AD-8: The package envelope: no dependency, no network, no write, no model, deterministic [ADOPTED; enforcing tests implemented under #37, ships in v0.2.0]

- **Binds:** NFR-1, NFR-2, NFR-3, NFR-5, NFR-7, NFR-8; all modules.
- **Prevents:** one feature quietly adding a dependency, a network call, a file write or an
  order-dependent count.
- **Rule:**
  - `dependencies = []`. Standard library only, no syntax or call newer than Python 3.9.
  - No module in the package imports `socket`, `urllib`, `http`, `subprocess` or a model client.
    No command anywhere in ruleprobe calls a model. Drafting a detector from prose (FR-34) was
    withdrawn on 2026-09-23 and moved to the judge library tracked in #21, so ruleprobe has no
    drafting command and no boundary for one (PRD Q4).
  - `open()` is for reading. The one write in the package is the FR-26 label command, under a
    directory the user names. `report`, `detectors`, `corpus` and the explain path write nothing.
  - The clock is read only to resolve `--since`, in `ruleprobe/readers/__init__.py`.
  - Every ordering in output comes from an explicit sort. Path lists are sorted before reading, as the
    readers do today. No count depends on dict, set or filesystem order.
  - 0.2 adds tests that fail on a new dependency and that run `report` with network and writes denied.

### AD-9: The contract is versioned, once, in 0.2.0 [PROPOSED; fold on read ADOPTED]

- **Binds:** FR-27, FR-28, FR-29, FR-30, FR-31; agent-harness AD-13.
- **Prevents:** a stored row or a detector file read under the wrong schema, a renamed detector
  dropping its history, and a silent break in the harness.
- **Rule:**
  - **Schema version.** The key is `schema_version`; absent means 1. It sits on each detector entry
    and on each row and `report_data` result. A detector file's top-level `version` sets the default
    for its entries, and an entry's own key wins. 0.1.0 ignores the top-level `version` that
    `common.yaml` already carries; from 0.2 it is read, and a value that is not a known schema version
    is a finding. An entry above the highest version the package knows is a finding; a row above it is
    excluded from counts and reported, as FR-20 excludes a row with no `rules` map. The value is an
    integer, and 0.2.0 writes `2` (PRD Q9, decided 2026-09-23). [ASSUMPTION: key name and file-level
    default]
  - **The 0.2 break** carries the schema version, the fold map, the declared API below, and AD-4's
    undecided rule for `not` and `absent`, which changes counts for existing user detector files.
  - **Fold map.** One function resolves renamed ids for `report`, `report_data` and validity. It reads
    the union of the shipped map and the consumer's `Registry(renamed=)` map; the consumer's entry
    wins on a clash. Chains resolve to their end; a cycle is an error when the registry is built.
    `report_data` emits the effective map beside its rows, so stored JSON folds without the registry.
    The same function folds a row's `compliance` map (AD-11): a retired id's `opportunities`,
    `followed` and `undecided` sum under the current id, as its hits do.
    [ASSUMPTION: this is the persistence FR-29 asks for]
  - **Shipped ids.** A list of every detector id any release has shipped. A test fails when a listed
    id is neither registered nor folded.
  - **Package data.** The shipped fold map and the shipped-id list are Python literals in one module,
    as `SECRET_PATTERNS` is, never a data file read beside `__file__`. A module literal loads through
    the import system the same way from a directory, a wheel or a zip on `sys.path` on 3.9, and the
    import system loads it once per process, so building a `Registry` adds no file I/O. A test asserts
    the module holds only literals. [ASSUMPTION: the module is `ruleprobe/contract_data.py`]
  - **Catalog.** The shipped catalog's entries are Python literals in `ruleprobe/detectors/catalog.py`
    under the same rule, compiled with `compile_detector`, never a data file read when a bundle builds
    a `Registry` (planned, v0.2.0).
  - **Corpus.** The corpus stays a directory, read only by validity and `ruleprobe corpus`, never at
    import or registry build. A caller that imports from a zip sets `RULEPROBE_CORPUS` or unpacks it,
    as the harness does. [ADOPTED]
  - **Declared API.** One contract test module is the list: every name and call shape in PRD FR-30,
    including `fn(events, ctx)`, `Context`, `Parsed`, `hit`, `git_calls` 3-tuples, positional
    `Detector(id, rule, event, fn, gate)`, `Registry(list)`, the validity helpers and
    `declarative.load` returning `(document, lines)`. The README renders from it. A name joins only
    with its test. Root `__all__` names outside FR-30's list stay importable and undeclared (PRD Q8,
    decided 2026-09-23). The list is re-derived from agent-harness `main` before each release.
  - **Non-name dependencies.** `SECRET_PATTERNS` stays a plain module-level assignment of a literal
    list in `ruleprobe/detectors/common.py`. The wheel is pure Python, named
    `ruleprobe-<version>-py3-none-any.whl`, carries `corpus/`, and imports from a zip on `sys.path`:
    no import-time file read, and no file read when a `Registry` is built or `report_data` runs.
  - Within a minor series none of the above changes incompatibly (FR-31).
  - **Later breaks.** A later 0.x minor may break the declared surface, with notice: its changelog
    section opens with a Breaking heading naming the migration, and the contract test is updated in the
    same change (PRD Q12, decided 2026-09-23).

### AD-10: How a reader is added [ADOPTED]

- **Binds:** FR-4, FR-32, FR-33.
- **Prevents:** a third reader that differs in turn, final, error or ordering behaviour from the first
  two.
- **Rule:**
  - One module in `ruleprobe/readers/` with `ROOT`, `transcripts(root)` returning sorted paths, and
    `read(path)` returning a `Session`; one entry in `RUNTIMES`. It imports `ruleprobe.events` only.
  - It owns its tool-name table (AD-3) and derives `turn` and `final` as AD-2 says.
  - A malformed line is skipped and the file still reads; an unreadable file lands in `errors` with its
    path; a missing `ROOT` yields nothing and no error.
  - It lands with a labelled corpus session from that runtime, near-misses included, and a README
    note of what that runtime's transcripts do not record.

### AD-11: Opportunity and compliance travel beside hits, never inside them [PROPOSED]

- **Binds:** FR-9, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-28, FR-30.
- **Prevents:** matchers, Python detectors and the report each inventing their own opportunity shape,
  a compliance rate that comes out inverted, or the harness's `fn(events, ctx)` changing to carry one.
- **Rule:**
  - `Detector` gains one optional attribute, `opportunities`, set by keyword only: a callable over
    `(events, ctx)` returning `(turn, tool_use_id, followed)` triples, where `followed` is `True`,
    `False` or `None` for undecided. `fn`, its return shape and the positional five-argument
    constructor do not change.
  - Polarity comes from the matchers' code. `absent`'s `of` is the action the rule asks for, and
    `absent` has no trigger key.
  - `absent` with `scope: turn` compiles `opportunities`. Each turn present in the event list is one opportunity;
    it is followed when `of` matched in that turn. A hit is an opportunity not followed.
  - `order` compiles `opportunities`. Each event `first` matches opens one opportunity; it is followed when `then`
    matched within `within`. A hit is a followed opportunity.
  - `absent` with `scope: session` defines no opportunity; its hit per session is already the rate.
  - The compiler derives `followed` from the same evaluation that yields the hit. A test asserts, for
    every compiled detector on the corpus, hits = opportunities - followed for `absent` and
    hits = followed for `order`.
  - Under AD-4, an opportunity whose `followed` is undecided is left out of both counts and counted
    as `undecided`. It is never recorded as not followed. [ASSUMPTION: an event whose `first` is
    undecided is counted as `undecided` too]
  - A Python detector may set `opportunities` by hand.
  - A row carries `compliance`: detector id to `{"opportunities": N, "followed": M, "undecided": U}`,
    only for detectors that define one. `report` and `report_data` show `undecided` beside the other
    two, apply the minimum of 20 `opportunities` to each printed group, as `min_sessions` is applied
    (PRD Q7, decided 2026-09-23), and never replace hits per session.
  - `run()` and its return are unchanged. `measure()` calls each enabled detector's `opportunities`,
    behind the same `enabled(stances)` gate and the same isolation as `run()`: a raise is recorded in
    `rules_errors` against that detector and costs only its own figures.
  - A Python detector declares opportunities through this keyword-only callable, not a second return
    value (PRD Q10, decided 2026-09-23).

### AD-12: Rule binding and rule ids [ADOPTED per file; PROPOSED per section and catalog]

- **Binds:** FR-13, FR-14, FR-15, FR-16.
- **Prevents:** two parts of the package computing a rule's id differently, or a catalog entry that
  binds loosely.
- **Rule:**
  - `ruleprobe/rules.py` owns binding and the rule id. The report reads its `Bundle` and never binds.
  - A rule is `measured`, `dark` or `unmeasured` (`STATES`), and a binding records its source: own or
    catalog.
  - A file bound in its front matter (FR-13) keeps one rule, whose id is the file's path relative to
    `--rules`. A section rule's id is that path, `#`, and a slug of its heading text, so it survives an
    edit above it. A slug repeated in one file takes an ordinal suffix in document order
    (`CLAUDE.md#testing`, `CLAUDE.md#testing-2`); a collision that remains is a finding.
    The split unit is the heading only, for 0.2 (PRD Q2, decided 2026-09-23); list items are not split,
    so a section of bullet rules is one rule.
  - Detector precedence is fixed: shipped, then catalog, then the three discovery places in
    `load_bundle`'s order; a later id replaces an earlier one (`Registry.add`). A rule bound to a
    catalog id the user replaced is reported as bound to the user's own.
  - A catalog entry carries one anchored pattern. A rule binds an entry only when exactly one entry
    matches; none or several leaves it unmeasured. Binding reads text; no model.
  - The 0.2 catalog is a small set of six to eight shapes, each with `examples:` at the floor, listed
    with their detector kinds in PRD FR-16 (PRD Q3, decided 2026-09-23).

### AD-13: Explain, label and redaction [PROPOSED]

- **Binds:** FR-25, FR-26, NFR-5.
- **Prevents:** a secret printed by explain or written into a corpus, or the row widened to carry hit
  keys.
- **Rule:**
  - `ruleprobe explain` reruns detectors over transcripts and prints from `Hit` keys: session, turn,
    tool-use id, detector id, matched field. It changes no report number. Over a stored row it prints
    that the row holds counts only, and the rerun that would explain it.
  - `ruleprobe label` writes one `.events.jsonl` session (AD-6) and one `near` label under a directory
    the user names. It refuses a session hit (`"<turn>:-"`) and says why, because one event cannot
    reproduce an `absent` or `order` hit. [ASSUMPTION: refusing, rather than writing the whole turn
    window]
  - `label` refuses to write, and says why, when redaction changes the field the detector matched,
    because the written negative would then pass trivially.
  - One `redact` function, beside `SECRET_PATTERNS` in `ruleprobe/detectors/common.py`, is the only
    path for text that explain prints or label writes. Each has a test that a known secret shape never
    appears.
  - [ASSUMPTION: the subcommand names; the PRD left the CLI form to the spine]

### AD-14: Shared registry state is never mutated after import [ADOPTED]

- **Binds:** FR-6, FR-7, FR-11, FR-16, FR-30.
- **Prevents:** one caller's loaded detectors leaking into another caller's `DEFAULT` in the same
  process, as when the harness and the CLI share an interpreter.
- **Rule:**
  - `DEFAULT` holds the shipped detectors, registered once at import by `registry.py`'s tail. Package
    code never adds to it afterwards; a bundle, the catalog or entry points build a new registry from
    `DEFAULT.copy()`, as `Bundle.registry` does (`ruleprobe/rules.py:53`, the copy at `:57`).
  - `COMPILERS` is written only by `register_compiler` at import time.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Detector id | `rule/observable`, lower-case, hyphenated. A rule name holds no slash. |
| Hit and label key | `"<turn>:<tool_use_id>"`, or `"<turn>:-"` for a session hit. |
| Row | A dict with `session_id`, `repo`, `runtime`, `started`, `ended`, `stances`, `rules` (id to count); 0.2 adds `schema_version` and `compliance` (id to `opportunities`, `followed`, `undecided`). |
| Errors | FR-9. Detector failures `{"detector": id, "error": ExceptionName}` in `rules_errors`; reader failures `{"path": ..., "error": ...}` in `errors`; spec failures a `DeclarativeError` or finding with file, line and reason. Nothing fails a whole run for one bad input. |
| Contracts | Each module's docstring states its contract and known misses; it is the reference a reviewer checks. |
| Spelling | British in identifiers already shipped (`analyse`, `normalise`); new names follow. |
| Tests | `tests/test_<module>.py`, `unittest`, run on 3.9 and 3.x. |
| Output | Tables for people; `--json` and `report_data` carry the same numbers. |

## Stack

Verified against the repository files at `ae84ac3`, not the web.

| Name | Version |
| --- | --- |
| Python (floor) | `>=3.9` (`pyproject.toml`); CI runs 3.9 and 3.x |
| setuptools (build backend) | `>=61` |
| build (CI and release) | `1.6.1` |
| actions/checkout | v7.0.1, SHA-pinned |
| actions/setup-python | v7.0.0, SHA-pinned |
| actions/upload-artifact | v7.0.1, SHA-pinned |
| actions/download-artifact | v8.0.1, SHA-pinned |
| pypa/gh-action-pypi-publish | v1.14.2, SHA-pinned |
| Runtime dependencies | none |
| Licence | MIT |

Amended 2026-09-23: the build backend floor is `setuptools>=77`, for the SPDX licence expression (#6)

## Structural Seed

```text
ruleprobe/
  events.py declarative.py shell.py registry.py matchers.py rules.py report.py validity.py cli.py
  contract_data.py  # 0.2: shipped fold map and shipped ids, as literals (AD-9)
  readers/     # one module per runtime, plus RUNTIMES and iter_sessions
  detectors/   # common.py (reference), common.yaml (twin); 0.2: catalog data
  corpus/      # labels.yaml and synthetic sessions/, shipped in the wheel
tests/         # test_<module>.py; 0.2: the contract test (AD-9)
```

```mermaid
flowchart LR
  src[ruleprobe source] -->|CI: compileall, unittest 3.9 and 3.x, corpus floor, wheel install| gh[GitHub Actions]
  gh -->|tag: preflight, build, publish| pypi[(PyPI wheel)]
  pypi --> uvx[uvx / pip: CLI on a developer machine]
  pypi -->|pinned wheel, vendored| harness[agent-harness lib/vendor, imported from zip]
  uvx -->|reads| local[(local transcripts)]
```

No service, no hosted component, no environment beyond a developer machine and CI.

## Capability → Architecture Map

| Capability | Lives in | Governed by |
| --- | --- | --- |
| FR-1 to FR-4, FR-32 readers and schema | `readers/`, `events.py` | AD-2, AD-3, AD-10 |
| FR-5 shell parse | `shell.py` | AD-5, AD-4 |
| FR-6 to FR-9 registry, entry points, six detectors, failure isolation | `registry.py`, `detectors/` | AD-1, AD-4, AD-7 |
| FR-10 to FR-12 declarative format and matchers | `declarative.py`, `matchers.py` | AD-7, AD-4 |
| FR-13 to FR-16 binding, share, sections, catalog | `rules.py`, `detectors/` | AD-12, AD-6 |
| FR-17 to FR-22 report and compliance | `report.py` | AD-11, AD-8, AD-9 |
| FR-23, FR-24, FR-33 corpus and floor | `validity.py`, `corpus/` | AD-6 |
| FR-25, FR-26 explain and label | `cli.py`, `report.py`, `validity.py` | AD-13, AD-8 |
| FR-27 to FR-31 versioned contract | `registry.py`, `report.py`, `declarative.py`, contract test | AD-9 |
| FR-34 drafting (withdrawn 2026-09-23; moved to #21) | not in ruleprobe | AD-8 |
| NFR-1 to NFR-8 | all | AD-8, AD-4, AD-6 |

## Deferred

- **Compliance by position** (PRD Q5). Out of 0.2.0 (decided 2026-09-23); a candidate beyond 0.2. Needs
  AD-11 first.
- **A trigger key for `absent`.** Without one, every turn is an opportunity for `scope: turn`
  (AD-11). Adding one is an AD-7 vocabulary change. Revisit when the catalog's first `absent` rule
  shows a rate diluted by turns where the rule could not apply.
- **Performance** (NFR-9). No timing exists; the batch-per-session shape bounds memory per session.
  A measured timing decides whether anything needs fixing here.
- **Concurrency.** Single process, one session at a time. Parallel reading is not planned.
- **Release operations.** Owned by `scripts/release_preflight.py` and `.github/workflows/release.yml`;
  nothing here a unit could diverge on.
