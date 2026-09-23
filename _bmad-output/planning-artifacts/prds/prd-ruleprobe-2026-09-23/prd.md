---
title: "PRD: ruleprobe"
status: final
created: 2026-09-23
updated: 2026-09-23
issue: 13
bmad_id: RP-S004
milestone: v0.2.0
inputs:
  - _bmad-output/planning-artifacts/briefs/brief-ruleprobe-2026-09-23/brief.md
  - _bmad-output/planning-artifacts/research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md
  - README.md
  - https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/prds/prd-agent-harness-2026-09-23/prd.md
  - https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/architecture-spines/architecture-agent-harness-2026-09-23/ARCHITECTURE-SPINE.md
---

# PRD: ruleprobe

## 0. Document purpose

This PRD is for the maintainer, for contributors, and for the architecture spine (#14) and the 0.2
epics (#15) that build on it. It turns the
[product brief](../../briefs/brief-ruleprobe-2026-09-23/brief.md) into requirements. It does not
re-decide the brief. Terms in the Glossary (§3) are used exactly. Features are grouped in §4 with FR ids
numbered globally from FR-1. The package contract is §5. Every claim about what exists carries a status:
implemented (version), partial, planned (milestone) or proposed. Inferences are tagged `[ASSUMPTION]` and
indexed in §12. Rejected alternatives and technical depth are in the [addendum](addendum.md).

## 1. Vision

Developers write rules for their coding agents and cannot tell whether the rules change what the agent
does. ruleprobe answers that from the transcripts the agent already wrote. It reads them locally, turns
them into one event schema, runs deterministic detectors over them, and reports per rule. The same
transcript always gives the same report (implemented, 0.1.0).

ruleprobe is the measurement engine for agent rules, not a doctor. It counts and reports. It does not
diagnose, prescribe or block. It stays a narrow library and CLI that other tools build on.

0.2.0 does three things (planned, v0.2.0). The report gives compliance per opportunity beside hits per
session. The contract that downstream tools import is versioned. A stranger gets a first measured answer
about their own rules in a minute, without a model and without writing a detector.

### 1.1 Positioning

**Category.** A local, deterministic instrument that measures agent rules from coding-agent transcripts.
It is a library first and a CLI second.

**The bounded claim.** ruleprobe is not the first tool that measures rule compliance from transcripts.
claude-md-doctor and RuleReceipt already do
([research](../../research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md),
refs 1 and 2). What ruleprobe claims, and only this:

- It reads two runtimes, Claude Code and Codex (implemented, 0.1.0). Both neighbours read Claude Code
  only (refs 1, 2). No other tool was found measuring rule compliance from Codex rollouts as of
  2026-09-23. That is absence of evidence from one import and one targeted search, rated low (ref 9),
  and the claim always carries its date.
- Its detectors are committed data, scored against a labelled corpus with a CI floor of 0.9
  (implemented, 0.1.0). claude-md-doctor's matchers are authored by the model at each checkup and
  verified by sampling; nothing in its skill holds them fixed between checkups (its
  [SKILL.md](https://github.com/agent-clinic/claude-md-doctor/blob/main/skills/claude-md-doctor/SKILL.md)
  steps 4b and 4d, verified 2026-09-23).
- It is a library that other tools import (implemented, 0.1.0; agent-harness vendors it).

Deterministic-first is not a differentiator. The literature recommends it (refs 26, 27) and both
neighbours already do it (refs 1, 2). It is the price of being credible.

**Alternatives, credited by name.**

- **claude-md-doctor** (MIT, local). Decomposes a rule file into per-rule matchers and reports followed,
  ignored and never-used rules on Claude Code (ref 1). For a stranger's own rules on Claude Code it does
  today what ruleprobe 0.1.0 cannot. Choose it for a diagnosis.
- **RuleReceipt** (source-available; its licence bars competing commercial offerings). Deterministic
  checks over git commands and file operations, with an opt-in model grader (ref 2).
- **Anthropic /insights.** Suggests `CLAUDE.md` additions from local transcripts (refs 15, 16, secondary
  sources). It answers what to write, not whether what you wrote works.
- **Codex Code Review.** Applies `AGENTS.md` rules to pull-request diffs (ref 31). It judges the diff, not
  the session.
- **Doing nothing.** Rules kept on intuition. Free, and the common case.

**Claims ruleprobe never makes.**

- That a model is involved in measurement. `ruleprobe report` calls no model.
- That anything leaves the machine.
- That a rule should be kept, rewritten or deleted. ruleprobe prescribes nothing.
- That it supports every runtime. It names the runtimes it reads.
- Any accuracy figure it has not measured. Corpus agreement is reported as corpus agreement, never as
  field accuracy.

## 2. Target user

### 2.1 Jobs to be done

- **Developer with rules.** "I have a `CLAUDE.md` or `AGENTS.md` and weeks of transcripts. Tell me which
  rules do anything, in a minute, with a number I can defend." Will not write Python.
- **Maintainer of a rule set.** "When I add a rule, let me add a detector for it as data, label what it
  should and should not catch, and see its precision before I trust its counts."
- **Downstream tool.** "Let me import the engine, bind my own rules to its detectors, and pin a version
  whose contract does not move under me." agent-harness is the first such tool
  ([AD-13](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/architecture-spines/architecture-agent-harness-2026-09-23/ARCHITECTURE-SPINE.md)).
- **Researcher.** "Give me reproducible counts I can publish beside my method."
- **Contributor.** "Let me add a runtime by writing one reader, and know when it is good enough."

### 2.2 Non-users

- Anyone who wants the tool to fix, rewrite or suggest rules. claude-md-doctor and /insights serve them.
- Anyone who wants an agent blocked in the moment. Hooks and guards belong to other tools.
- Anyone who wants a hosted dashboard or team aggregation.

### 2.3 Key user journeys

- **UJ-1. Ines measures her own rules in sixty seconds.**
  - **Persona and context:** Ines keeps an unedited 200-line `AGENTS.md` and three weeks of Codex and
    Claude Code sessions. She has never heard of a detector.
  - **Entry state:** a terminal in her repository; `uv` installed; nothing else.
  - **Path:** she runs `uvx ruleprobe report --rules .`. The report splits her file into rules by
    section (FR-15), matches the sections it recognises against the shipped catalog (FR-16), and prints
    each rule as measured, dark or unmeasured.
  - **Climax:** within a minute she sees three of her own rules measured, one with 31 opportunities and
    12 followed (FR-21), and a list of the rules nothing measures. The figures are illustrative, not
    measured.
  - **Resolution:** she opens the explain path on one surprising hit (FR-25) and sees the command the
    agent ran, with any secret redacted. `[ASSUMPTION: the explain path's CLI form is for the architecture
    spine]`
  - **Edge case:** a hit is wrong. One command records it as a labelled negative (FR-26). The detector came
    from the catalog, so she opens a pull request with the label.
- **UJ-2. Tomas adds a detector with labels.**
  - **Persona and context:** Tomas maintains his team's house-style rules and wants one of them measured.
  - **Path:** he writes a declarative detector in the rule file's front matter (FR-10), adds `examples:`
    with cases it should fire on and skip (FR-24), and runs `ruleprobe corpus`.
  - **Climax:** the corpus scores his detector at precision 1.00 and recall 0.75 over his examples, and
    names the missed case. The figures are illustrative, not measured.
  - **Resolution:** he fixes the matcher, the score clears the 0.9 floor (FR-23), and he commits the
    detector as data.
- **UJ-3. Noor builds a governance tool on the library.**
  - **Persona and context:** Noor maintains a tool that binds its own rules to ruleprobe detectors, the
    way agent-harness does.
  - **Path:** she vendors a pinned 0.2.0 wheel, imports only names in the declared public API (FR-30),
    and stores report rows in her own ledger.
  - **Climax:** a later 0.2.x renames a detector. Her stored rows fold onto the new id through the fold
    map (FR-29), and her contract tests still pass.
  - **Resolution:** she bumps the pin with no code change.
- **UJ-4. Kofi adds a reader.**
  - **Persona and context:** Kofi uses a runtime ruleprobe does not read.
  - **Path:** he writes one reader module with `ROOT`, `transcripts(root)` and `read(path)` (FR-4), maps
    the runtime's tool names onto the shared vocabulary, and adds labelled sessions from that runtime to
    the corpus.
  - **Climax:** the detectors that apply to his runtime score at or above the floor on those sessions
    (FR-33).
  - **Resolution:** the README lists the runtime, with its known gaps.

## 3. Glossary

- **Transcript**: the file a runtime writes for one session. Claude Code JSONL, Codex rollout.
- **Reader**: a module that turns one runtime's transcripts into sessions of events.
- **Session**: one transcript as read, with an id, a repository and a list of events.
- **Event**: one entry in the event schema, one of `assistant_text`, `tool_use`, `tool_result`,
  `user_prompt` or `compact`, each with a `turn`. These five are the event's `kind`.
- **Shell parse**: the shared parse of a Bash command into pipelines and segments.
- **Detector**: one rule, one observable, one function over a session's events. Has an id of the form
  `rule/observable`.
- **Detector input shape**: the `event` field of a detector. It is one of the registry's `EVENT_KINDS`:
  `bash`, `write`, `agent-brief`, `assistant-final`, `session`, `tool_use` or `assistant_text`
  (`ruleprobe/registry.py:18`). It says which shape of transcript the detector reads. It is advisory:
  every detector is handed the whole event list. It is not an event's `kind`.
- **Declarative detector**: a detector written as data and compiled to the same detector.
- **Matcher**: the data form of a detector's condition.
- **Registry**: the set of detectors a run uses.
- **Rule**: one instruction a person wrote for an agent. In 0.1.0 a rule file is one rule.
- **Rule file**: a markdown file holding one or more rules.
- **Binding**: the link between a rule and a detector, or a reason for having none.
- **Measured / dark / unmeasured**: a rule with a detector; a rule opted out with a reason; a rule
  with neither.
- **Catalog**: the shipped set of declarative detectors for common rule shapes.
- **Row**: one measured session, holding at least a `rules` map of detector id to hit count.
- **Hit**: one match of a detector, keyed by turn and tool-use id.
- **Opportunity**: a point in a session where a rule applies. Defined by the detector.
- **Followed**: an opportunity where the action the rule asks for happened inside the opportunity's
  window. For an `order` detector, a `then` match inside `within` of the `first` match that opened the
  opportunity. For an `absent` detector with `scope: turn`, a turn in which the `of` matcher, the
  action the rule asks for, matched; a turn in which it did not is a hit.
- **Compliance per opportunity**: opportunities, and how many were followed, for one rule.
- **Corpus**: the labelled sessions that ship in the package.
- **Floor**: the minimum precision and recall a detector must score on the corpus. Default 0.9.
- **Schema version**: an integer on each detector entry and each row naming the contract it was written
  under. 0.2.0 writes `2`; an absent key means 1.
- **Fold map**: a mapping from a retired detector id to its current id. Each consumer supplies its own
  through `Registry(renamed=...)` or `Registry.rename`.
- **Declared public API**: the names the project promises not to change within a minor series.

## 4. Features

### 4.1 Readers and the event schema

**Description:** A reader finds a runtime's transcripts and emits sessions of events. Every detector reads
the same schema whatever the runtime. Realizes UJ-1 and UJ-4.

#### FR-1: Claude Code reader
The CLI and library read Claude Code transcripts under `~/.claude/projects/`. **Status:** implemented
(0.1.0).

**Consequences (testable):**
- `iter_sessions(runtime="claude-code")` yields one session per transcript file.
- A line that does not parse is skipped, and the rest of the file still reads.
- A file that cannot be read is recorded in `errors` with its path, not dropped silently.

#### FR-2: Codex reader
The CLI and library read Codex rollouts under `~/.codex/sessions/`. **Status:** implemented (0.1.0).

**Consequences (testable):**
- Codex `exec_command` reaches a detector as `Bash`, and `spawn_agent` as `Agent`.
- A subagent thread's inherited `session_meta` does not change the rollout's own session id.

#### FR-3: One event schema
Every reader emits the five event kinds with the fields `ruleprobe/events.py` documents. **Status:**
implemented (0.1.0).

**Consequences (testable):**
- A detector that runs on one runtime's session runs unchanged on another runtime's session.
- `turn` increments on every `user_prompt`.
- `input_of` and `text_of` return an empty value, not an exception, for a malformed field.

#### FR-4: Reader contract
A contributor adds a runtime by adding one module with `ROOT`, `transcripts(root)` and `read(path)`, and
one entry in `RUNTIMES`. **Status:** implemented (0.1.0).

**Consequences (testable):**
- `--runtime NAME` accepts every key in `RUNTIMES`, and `auto` reads all of them.
- A reader whose `ROOT` does not exist yields no sessions and no error.

### 4.2 The shell parse

**Description:** One parse of Bash commands serves every detector and every `command` matcher, so a
command is read the same way everywhere.

#### FR-5: Shared shell parse
The system splits a command into compounds, pipelines and segments, strips heredocs, and marks
substitutions. **Status:** implemented (0.1.0).

**Consequences (testable):**
- `sudo pip install x && ls` yields two segments, and a `starts_with: [sudo, pip]` matcher matches the
  first only.
- A command inside `$( )` is not visible to a segment matcher. This is a documented miss, and it
  under-counts.
- A command longer than `MAX_COMMAND` is not parsed, and yields no hit.

### 4.3 The registry and Python detectors

**Description:** A detector is a function over a session's events. The registry holds the set a run uses.
Python is the escape hatch for shapes a matcher cannot say.

#### FR-6: Detector and Registry
A developer registers a detector as `Detector(id, rule, event, fn, gate=None)`. **Status:** implemented
(0.1.0).

**Consequences (testable):**
- `Registry.add` with an id already present replaces that detector in place.
- `Registry.add` rejects a rule name containing a slash, and rejects a detector input shape (§3)
  outside `EVENT_KINDS`.
- A detector whose `gate` is not satisfied by the run's stances produces no hit.

#### FR-7: Detectors from entry points
A package can ship detectors through the `ruleprobe.detectors` entry point group. **Status:** implemented
(0.1.0).

**Consequences (testable):**
- `Registry.from_entry_points("ruleprobe.detectors")` loads every detector an installed package declares.

#### FR-8: Six generic detectors
The package ships six detectors that mean the same in every repository: `whole-file-cat`,
`unfiltered-find`, `no-verify`, `secret-in-write`, `compact` and `model-switch`. **Status:** implemented
(0.1.0).

**Consequences (testable):**
- `ruleprobe/detectors/common.yaml` produces hit for hit what `ruleprobe/detectors/common.py` produces
  over the corpus.

#### FR-9: A failing detector costs only itself
A detector that raises is recorded against its own id, and every other detector's result stands.
**Status:** implemented (0.1.0).

**Consequences (testable):**
- A row naming a detector in `rules_errors` is subtracted from that detector's denominator only.
- With `strict=True`, `run` raises instead of recording.

### 4.4 The declarative format and matchers

**Description:** A detector written as data compiles to the same `Detector` a Python one is. It lives in a
repository, in user config, or in a rule file's front matter. Realizes UJ-2.

#### FR-10: Declarative detectors
A developer writes a detector as five keys, `id`, `rule`, `event`, `when` and an optional `gate`, in the
YAML subset or JSON. **Status:** implemented (0.1.0).

**Consequences (testable):**
- `compile_detector(spec)` returns a `Detector` whose hits equal those of the equivalent Python detector.
- A misspelt key is a `DeclarativeError` with a line number, never a detector that never fires.

#### FR-11: Discovery from three places
The CLI reads `.ruleprobe/detectors.yaml` found by walking up from the working directory,
`~/.config/ruleprobe/detectors.yaml`, and rule-file front matter under `--rules`. **Status:**
implemented (0.1.0).

**Consequences (testable):**
- `--no-config` reads neither config file.
- A bad entry is a finding with a file, a line and a reason, and the rest of the file still loads.

#### FR-12: Matchers
The format offers the event matchers `tool`, `arg`, `command`, `git`, `env`, `text`, `message` and
`kind`, the combinators `any`, `all` and `not`, and the session matchers `order`, `absent` and `change`.
**Status:** implemented (0.1.0).

**Consequences (testable):**
- The keys of one `command` block all hold for the same pipeline segment.
- `order`, `absent` and `change` are rejected anywhere but as the whole `when` of a `session` detector.
- `path_glob` matches a relative pattern at any path-component boundary of an absolute path.

### 4.5 Rule binding

**Description:** A rule file binds to a detector, opts out with a reason, or is listed as unmeasured, so
the gap is visible. 0.2.0 splits one file into many rules and ships detectors for common shapes, so a
stranger's file is measured without writing one. Realizes UJ-1.

#### FR-13: Per-file binding
Given `--rules <dir>`, the report classes each rule file as measured, dark or unmeasured. **Status:**
implemented (0.1.0).

**Consequences (testable):**
- A file with a `detector:` block is measured.
- A file with `opt_out: <reason>` is dark, and the reason is kept with it.
- A file with neither is listed as unmeasured.

#### FR-14: Measured share
The report states the share of rules measured. **Status:** partial. 0.1.0 prints the three counts as
`rules: N measured, N dark, N unmeasured` and no share (`ruleprobe/rules.py:74`); the share is planned
(v0.2.0). The harness's FR-67 asks for the share.

**Consequences (testable):**
- The coverage block prints measured, dark and unmeasured counts and the measured share.

#### FR-15: Section-level binding
The system splits one rule file into many rules, so a `CLAUDE.md` with twelve rules is twelve entries in
the coverage block. **Status:** planned (v0.2.0). The split unit is the heading, for 0.2 (§11, Q2,
decided 2026-09-23). List items are not split units in 0.2.

**Consequences (testable):**
- A file with twelve rule sections yields twelve rules, each with its own measured, dark or unmeasured
  state.
- Each rule's id is stable when a section above it is edited. It derives from the heading text, not the
  position.
- A heading section is a rule when its body holds at least one line of text outside a fenced code
  block, a table and a blockquote. A unit that is only a heading, only a fenced block, only a table or
  only a blockquote is not a rule, and is not counted in any of the three states.
  `[ASSUMPTION: this definition; the research's ref 3 says most of a public CLAUDE.md is not rules]`
- A section holding several bullet rules is one rule.
- A fixture rule file with three rule sections and one section holding only a fenced example yields
  three rules, and the coverage block counts three.
- Per-file binding (FR-13) gives the same result as before for a file with one rule.

#### FR-16: Catalog of common rule shapes
The package ships declarative detectors for common rule shapes, bound to a rule by what the rule says, so
a stranger's rules are measured without a detector written. **Status:** planned (v0.2.0). The catalog is a
small set of six to eight shapes (§11, Q3, decided 2026-09-23). The starting list, with each detector
kind:

1. Run the tests before finishing: `order` or `absent`.
2. Never skip pre-commit hooks with `--no-verify`: event matcher on `git`.
3. Never force-push the default branch: event matcher on `git`.
4. Use the named package manager, not another: event matcher on `command`.
5. Do not read a whole file into context: event matcher on `command`, as the shipped `whole-file-cat`.
6. Conventional Commit subjects: event matcher on the `git` commit message.
   `[ASSUMPTION: subject parsing fits a matcher]`
7. Never commit a secret-shaped file: event matcher on the `git add` path.

**Consequences (testable):**
- Every catalog detector carries `examples:` and scores at or above the floor in CI.
- A named fixture rule file ships with the tests. Each of its sections is written in the shape of one
  named catalog entry, and a test asserts that each section binds that entry and is reported as
  measured and catalog-bound.
- A catalog binding is shown as catalog-bound, not as the user's own detector.
- The binding rule: each catalog entry carries one anchored text pattern. A rule binds an entry only
  when its text matches exactly one entry's pattern. A rule that matches none, or more than one, stays
  unmeasured. Binding under-counts. The pattern form is fixed by the spine (AD-12).
- Binding reads the rule text with no model.

### 4.6 The report

**Description:** The report counts over rows. Today it gives hits per session. 0.2.0 adds compliance per
opportunity for rules that ask for something to be done. Realizes UJ-1 and UJ-3.

#### FR-17: Hits per session
`ruleprobe report` prints, per detector, hits, sessions with a hit, measured sessions and share.
**Status:** implemented (0.1.0); the marker's rename is planned (v0.2.0).

**Consequences (testable):**
- A detector with zero hits in the window is listed, not omitted.
- `unobserved` and the threshold marker stay blank until `min_sessions` (default 20) measured sessions.
- The marker appears above the share threshold (default 0.30). In 0.2.0 it is a neutral "frequent"
  marker with no advice, replacing 0.1.0's `promote?`, and the parameter and flag names
  (`promote_share`, `--promote-share`) follow in the 0.2 break (§11, Q11, decided 2026-09-23).

#### FR-18: Grouping and window
The report groups by rule, by repository or by stance variant, and filters by date. **Status:**
implemented (0.1.0).

**Consequences (testable):**
- `--by repo` prints one block per repository.
- `--by stance` groups on the values passed with `--stance DIM=VARIANT`.
- `--since 30` counts only sessions in the last thirty days.

#### FR-19: The report as data
`report_data` and `--json` return the same numbers the table prints, with the rows. **Status:**
implemented (0.1.0).

**Consequences (testable):**
- Every number in the table equals the matching field in `report_data` for the same rows.

#### FR-20: Denominator rules
Only a row carrying a `rules` map is evidence. **Status:** implemented (0.1.0).

**Consequences (testable):**
- A row with no `rules` map is absent from every count and every denominator.
- A row carrying the older `rules_error` is dropped whole.

#### FR-21: Compliance per opportunity
For a rule that asks for something to be done, the report gives the opportunity count and the followed
count beside hits per session. **Status:** planned (v0.2.0).

**Consequences (testable):**
- A detector that defines an opportunity gets two more fields in `report_data`: `opportunities` and
  `followed`.
- The table prints them beside hits per session, not in place of them.
- A detector that defines no opportunity reports hits per session only, and prints no compliance figure.
- The `order` and `absent` session matchers can define an opportunity.
  `[ASSUMPTION: compliance per opportunity starts from these two shapes, as the brief's addendum says]`
- A fixture session with N opportunities, of which M are followed (§3), yields `opportunities: N` and
  `followed: M` in `report_data`, and the table prints the same two numbers.

#### FR-22: Minimum opportunities
No compliance figure is shown below a minimum opportunity count. **Status:** planned (v0.2.0).

**Consequences (testable):**
- Below the minimum, the report prints the counts and no rate.
- The minimum is a parameter of `report` and `report_data`, default 20, applied to each printed group,
  as `min_sessions` is (§11, Q7, decided 2026-09-23).
- A `--by repo` block with fewer than 20 opportunities of its own prints the counts and no rate.

### 4.7 Detector validity

**Description:** A count is a rate of the detector until someone says what it should have found. The
corpus says it. 0.2.0 adds field validity: every hit explains itself, and a wrong hit becomes a label.
Realizes UJ-1 and UJ-2.

#### FR-23: Corpus score and floor
`ruleprobe corpus` scores every registered detector's precision and recall against the labelled corpus,
and `--floor 0.9` fails when a detector is under it. **Status:** implemented (0.1.0).

**Consequences (testable):**
- A hit at a key the labels do not give its detector is a false positive; a label the detector did not
  produce is a false negative.
- `ruleprobe corpus --floor 0.9` exits non-zero when any scored detector is under 0.9.
- A detector with no label and no `examples:` is shown as unscored and does not fail the floor.

#### FR-24: Examples on a detector
A declarative detector may carry `examples:` with `fire` and `skip` cases, and the corpus command scores
them. **Status:** implemented (0.1.0).

**Consequences (testable):**
- A `fire` case the detector misses is a false negative in its score.
- `ruleprobe report` never runs examples.

#### FR-25: Explain path per hit
For any hit in a report run over transcripts, the user can see the event it came from and the detector
that matched it. **Status:** planned (v0.2.0).

A stored row keeps only `{detector_id: hit_count}` (`ruleprobe/report.py:37`, `measure`), with no turn or
tool-use id. A report over stored rows cannot explain a hit, and the row schema is not widened to carry
hits.

**Consequences (testable):**
- For every hit in a report run over transcripts, the explain output names the session, the turn, the
  tool-use id and the detector id.
- For a hit counted from a stored row, the explain path says the row carries counts only, and names the
  re-run that would explain it: `ruleprobe report` over that row's runtime and session id.
- The explain output quotes the event's matched field, such as the command.
- Printed text is redacted with the shipped `SECRET_PATTERNS` (`ruleprobe/detectors/common.py:19`)
  before it is printed. A test feeds an event holding a known secret shape and asserts the shape never
  appears in the output.
- The explain path prints locally and writes nothing.
- Running it does not change any number in the report.

#### FR-26: False positive to labelled negative
One command turns a hit the user says is wrong into a labelled negative in a corpus. **Status:** planned
(v0.2.0).

**Consequences (testable):**
- The command writes a minimal labelled session holding the event, and a label marking the detector's
  key as a negative.
- Rerunning `ruleprobe corpus` counts the new negative in that detector's score.
- The command writes only under a corpus directory the user names. `report` still writes nothing (NFR-5).
- The command never copies transcript content outside the event it was given.
- Text written into the corpus session and its label is redacted with the shipped `SECRET_PATTERNS`
  first. A test feeds an event holding a known secret shape and asserts the shape never appears in any
  written file. A person reviewing the file is not the control.

### 4.8 The versioned contract and public API

**Description:** Downstream tools store rows, bind rules to detector ids and import names. 0.2.0 versions
all three once, as its one breaking change (maintainer decision 4, 2026-09-23). Realizes UJ-3.

#### FR-27: Schema version on detector entries
Every declarative detector entry carries a schema version. **Status:** planned (v0.2.0).

**Consequences (testable):**
- 0.2.0 writes the integer `2` (§11, Q9, decided 2026-09-23).
- An entry with no schema version is read as the 0.1 schema, version 1.
- An entry with a schema version newer than the package knows is a finding, not a silent load.

#### FR-28: Schema version on rows
Every row and every `report_data` result carries a schema version. **Status:** planned (v0.2.0).

**Consequences (testable):**
- `measure()` writes the version into the row: the integer `2` in 0.2.0.
- A row with no version is read as the 0.1 schema, version 1.

#### FR-29: Fold map
A renamed detector id folds onto its new id when rows are reported. **Status:** partial. Implemented
(0.1.0) in memory via `Registry(renamed=)` and report folding. Planned (v0.2.0): fold entries that
persist with rows, and a test that detects an unfolded rename.

In 0.1.0, `Registry(detectors=None, renamed=None)` and `Registry.rename(old_id, new_id)`
(`ruleprobe/registry.py:70,101`) hold the map, and `folded_rules` (`ruleprobe/report.py:55`) applies it
on every read. Each consumer supplies its own fold map through `Registry`. The map lives only in the
process that built the registry.

**Consequences (testable):**
- A report folds a row stored under a retired id onto its current id, and counts it under the current
  id. (Implemented, 0.1.0.)
- A fold entry persists with the rows it applies to, so a reader that did not build the registry still
  folds them. (Planned, v0.2.0.)
- The repository commits a list of every detector id any release has shipped. A test compares it with
  the default registry: an id on the list that is neither registered nor a key of the fold map fails
  the suite. (Planned, v0.2.0.)

#### FR-30: Declared public API
The README declares the public API, and it includes every name agent-harness imports today. **Status:**
planned (v0.2.0); eight names declared in 0.1.0.

**Consequences (testable):**
- The declaration lists the README's eight 0.1.0 names: `iter_sessions`, `run`, `Registry`,
  `report`, `report_data`, `validity`, `load_bundle`, `compile_detector`.
- It lists every name the harness imports, re-derived from harness `main` at `1307113` on 2026-09-23
  (the four files are unchanged since `991b13e`):
  - root: `Registry`, `analyse`, `counts`, `run`
    ([`policy/hooks/rule-detectors.py`](https://github.com/JakeSelby/agent-harness/blob/main/policy/hooks/rule-detectors.py));
  - `ruleprobe.detectors.common`: `SECRET_PATTERNS`, `DETECTORS` (same file);
  - `ruleprobe.events`: `hit`, `input_of`, `text_of` (same file);
  - `ruleprobe.registry`: `Detector` (same file) and `Registry`
    ([`scripts/detector_corpus.py`](https://github.com/JakeSelby/agent-harness/blob/main/scripts/detector_corpus.py));
  - `ruleprobe.shell`: `MAX_COMMAND`, `MARKER_RE`, `SUB_PLACEHOLDER`, `git_calls`, `has_redirect`,
    `normalise`, `operands`, `pipelines`, `strip_heredocs` (`policy/hooks/rule-detectors.py`);
  - `ruleprobe.declarative`: `load` (`scripts/detector_corpus.py`);
  - `ruleprobe.validity`: `Score`, `CorpusError`, `DEFAULT_FLOOR`, `below_floor`, `score_corpus`,
    `scores_as_dict`, `validity_table` (`scripts/detector_corpus.py`).
- It declares the four dependencies that are not import names:
  - `SECRET_PATTERNS` stays a plain module-level assignment of a literal list at
    `ruleprobe/detectors/common.py`, which the harness reads by syntax tree without importing. It matches
    only a plain `ast.Assign`, so an annotated assignment would break it silently
    ([`policy/hooks/decisions.py`](https://github.com/JakeSelby/agent-harness/blob/main/policy/hooks/decisions.py));
  - the wheel is pure Python and named `ruleprobe-<version>-py3-none-any.whl` (both harness hook files);
  - the package imports and runs from the wheel placed on `sys.path` as a zip, without installation;
  - the corpus ships inside the wheel at `ruleprobe/corpus/` (`scripts/detector_corpus.py`).
- It declares every call shape and attribute the harness uses, and the types `Context` and `Parsed`:
  - the detector function `fn(events, ctx)`, returning a list of `(turn, tool_use_id)` pairs
    (`ruleprobe/registry.py:239,248`); about ten harness detectors depend on it;
  - `ctx` is a `Context` with `.events`, `.bash` (a list of `Parsed`) and `.finals` (the final
    `assistant_text` events) (`ruleprobe/shell.py:485`); the harness reads `ctx.bash` and `ctx.finals`;
  - `Parsed` with `.event`, `.command` and `.heredocs` (`ruleprobe/shell.py:444`), all read by the
    harness; `MARKER_RE.match(value)` with group 1 an index into `.heredocs`
    (`ruleprobe/shell.py:34`);
  - `hit(event)` and `hit(event, tool_use_id=False)`, returning `(turn, id or None)`
    (`ruleprobe/events.py:63`);
  - `git_calls(parsed, subcommands)`, yielding `(segment, subcommand, args)` 3-tuples
    (`ruleprobe/shell.py:426`);
  - `input_of(event)`, `text_of(value)` and `normalise(command)`;
  - the event fields the harness reads: `kind`, `turn`, `id`, `name`, `input`, `text`, `final`,
    `tool_use_id` and `tool_name` (`ruleprobe/events.py:4`);
  - `Detector` built positionally as `(id, rule, event, fn, gate)` and subclassable with
    `__slots__ = ()` (`ruleprobe/registry.py:38,40`); `gate` as `None` or a
    `(dimension, allowed_variants_or_None)` pair (`ruleprobe/registry.py:48`);
  - reads of `.id`, `.rule`, `.event`, `.fn` and `.gate` on each item of `common.DETECTORS`
    (`policy/hooks/rule-detectors.py`), and of `.rule` by `bin/harness` on the harness's own
    `Detector` subclass;
  - `Registry(<list of detectors>)` positionally (`ruleprobe/registry.py:70`);
  - `run(events, stances, registry=, strict=, errors=)` (`ruleprobe/registry.py:218`);
  - `score_corpus(registry=, directory=)` raising `CorpusError`; `below_floor(scores, floor)`,
    `scores_as_dict(scores, floor)` and `validity_table(scores, floor)` (`ruleprobe/validity.py:239,
    323,329,344`); `Score(detector_id)` with `.add`, `.scored`, `.precision`, `.recall` and `.detector`
    (`ruleprobe/validity.py:56`);
  - `declarative.load(path)` returning `(document, lines)` (`ruleprobe/declarative.py:126`);
  - `ruleprobe.__file__`, used to find `corpus/` beside it (`scripts/detector_corpus.py`).
- Root `__all__` names outside this list stay importable and undeclared: the README says they are not
  covered by FR-31. A name joins the declared API only with a contract test (§11, Q8, decided
  2026-09-23).
- A contract test exercises each declared name and each call shape and attribute above, including a
  detector function called as `fn(events, ctx)` that reads `ctx.bash`, `ctx.finals` and `Parsed.event`.
  It fails on any removal or signature change.
- The list is re-derived from harness `main` immediately before the 0.2.0 tag, and before every later
  release, and the contract test is updated in the same change.

`bin/harness` imports nothing from ruleprobe directly. It loads the harness's projected
`rule-detectors.py`, so it depends on the same surface.

#### FR-31: Versioning policy
Within a minor series, a declared name, a declared call shape, the row schema and the detector-entry
schema do not change incompatibly. **Status:** planned (v0.2.0).

**Consequences (testable):**
- A 0.2.x release passes the 0.2.0 contract test unchanged.
- A detector rename in 0.2.x ships a fold map entry (FR-29).
- A breaking change needs a new minor and a changelog entry naming it.
- A later 0.x minor may break the declared surface, with notice: its changelog section opens with a
  Breaking heading naming the migration, and the contract test is updated in the same change (§11,
  Q12, decided 2026-09-23).

### 4.9 The third reader

**Description:** A third runtime makes runtime-neutral a fact, not a claim resting on two runtimes.
Realizes UJ-4.

#### FR-32: Third reader
The system reads Gemini CLI's transcripts into the event schema. **Status:** planned (v0.2.0). The
maintainer chose Gemini CLI on 2026-09-23 (§11, Q1). Spike RP-SP003 confirms its transcript location and
format and lists its file-tool mappings; if Gemini CLI cannot be read reliably, it reports back rather
than switching runtime.

**Consequences (testable):**
- `--runtime <name>` reads Gemini CLI's sessions, and `auto` includes it.
- The runtime's shell and file tools reach detectors under the shared names (`Bash`, and the file tools).
- The README names the runtime and lists what its transcripts do not record.

#### FR-33: Third reader in the corpus
Labelled Gemini CLI sessions join the corpus. **Status:** planned (v0.2.0).

**Consequences (testable):**
- The corpus holds at least one labelled session from each runtime the package reads.
- Every detector that applies to Gemini CLI scores at or above 0.9 on its sessions in CI.

### 4.10 Model-assisted detector drafting (withdrawn)

**Description:** A separate command could read a rule's prose and draft a declarative detector for a person
to review and commit. The maintainer withdrew it from ruleprobe on 2026-09-23 (§11, Q4): it needs a
model, so it moves into the scope of the future judge library tracked in
[#21](https://github.com/JakeSelby/ruleprobe/issues/21) (RP-E002). The text below is kept as the record.

#### FR-34: Opt-in drafting command
A user can run a separate, opt-in command that drafts a declarative detector from a rule's text.
**Status:** withdrawn (2026-09-23; moved to #21).

**Consequences (testable):**
- The command only runs when the user names it and supplies the model access.
- Its output is a detector entry with `examples:`, printed or written to a path the user names.
- It never changes a registry, a corpus or a rule file by itself.
- `ruleprobe report`, `detectors` and `corpus` make no model call, whether or not the command exists.
- The package keeps no runtime dependency for it.

**Non-goals of FR-34:** it does not bind rules at report time; it does not score detectors; it does not
make a drafted detector count before a person commits it; it does not ship with the core install.

### 4.11 Verdict-source seam (proposed, 0.3)

**Description:** Some rules no transcript shape can decide, such as voice or conciseness; the report
shows them as dark. A judge outside ruleprobe could give a verdict on them. ruleprobe would own only a
model-free seam: the shape of a judged verdict, and scoring a judge on the corpus like a detector
(maintainer decision, 2026-09-23; [#21](https://github.com/JakeSelby/ruleprobe/issues/21), RP-E002).

#### FR-35: Verdict-source seam
A judge installed beside ruleprobe can emit verdicts into the row shape and be scored on the labelled
corpus. **Status:** proposed (0.3, #21).

**Consequences (testable):**
- A judged verdict is marked as judged and carries its provider, model id and pack version.
- `ruleprobe corpus` scores a judge with the same precision, recall and floor as a detector.
- `ruleprobe report` calls no model, with or without a judge installed (NFR-7).

## 5. The package contract (cross-cutting NFRs)

These bind every feature. Each is tested.

- **NFR-1 Standard library only.** `pyproject.toml` declares no runtime dependency (implemented, 0.1.0).
  Bound: `dependencies = []`. A test that fails the build on any addition: planned (v0.2.0).
- **NFR-2 Python 3.9 floor.** The package runs on CPython 3.9 and every later release CI tests
  (implemented, 0.1.0). Bound: `requires-python = ">=3.9"`; no syntax or standard-library call newer
  than 3.9.
- **NFR-3 Deterministic output.** The same transcripts, detectors and flags give byte-identical
  `--json` output (implemented, 0.1.0). Bound: no clock, randomness, locale or dict-order effect in any
  count. `[ASSUMPTION: --since is the one input read against the clock, and a fixed date removes it]`
- **NFR-4 Under-count rather than over-count.** When a detector or the shell parse cannot decide, it
  produces no hit (implemented: positive matchers in 0.1.0; negation, `any`, `all`, `order` and
  `absent` over skipped commands under #19, unreleased, shipping in v0.2.0). Bound: every documented
  miss is a miss, not a guess; a catalog binding that is unsure leaves the rule unmeasured (FR-16).
- **NFR-5 `report` writes and sends nothing.** `ruleprobe report` opens no network connection and writes
  no file (implemented, 0.1.0). Bound: a test runs `report` with network access and file writes denied,
  and `report` succeeds (planned, v0.2.0). Only FR-26's command writes, and only where the user says.
- **NFR-6 Corpus floor 0.9 in CI.** CI runs `ruleprobe corpus --floor 0.9` and fails under it
  (implemented, 0.1.0). Bound: the floor is not lowered to pass a detector; a detector under it is
  fixed or removed.
- **NFR-7 No model in measurement.** No command in ruleprobe calls a model, and 0.1.0 has none
  (implemented, 0.1.0). Bound: the core package imports no model client.
- **NFR-8 Local data only.** Transcripts are read where the runtime wrote them or where `--root`
  points (implemented, 0.1.0).
- **NFR-9 Time to first answer.** `report --rules --since 30` finishes inside the sixty-second budget of
  SM-1 over a reference volume of 500 sessions and 200 MB of transcripts. `report` has no default
  window (`--since` defaults to none, `ruleprobe/cli.py:44`), so the bound names the flag.
  `[ASSUMPTION: the reference volume; no timing has been measured, and the bound is derived from SM-1,
  not from a benchmark]` When a timing exists, whether to publish the machine it came from is a
  publishing question for the maintainer.

## 6. Public surface, versioning and dependencies

- **Surfaces.** The CLI (`report`, `detectors`, `corpus`), the library's declared public API (FR-30),
  the declarative format (FR-10 to FR-12), the row schema (FR-28), and the corpus format (FR-23).
- **Breaking change policy.** 0.2.0 is the one planned break: schema versions, the fold map and the
  declared API land together (maintainer decision 4). After it, FR-31 governs.
- **Distribution.** A pure-Python wheel on PyPI, runnable with `uvx` and vendorable as a zip (FR-30).
- **Downstream bump.** A ruleprobe release means an agent-harness version bump
  ([harness PRD FR-21](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/prds/prd-agent-harness-2026-09-23/prd.md),
  AD-13). ruleprobe owes the harness a stable contract and nothing else (maintainer decision 8).
- **Licence.** MIT (implemented, 0.1.0). Nothing is borrowed from source-available neighbours.

## 7. Non-goals

From the maintainer's decisions of 2026-09-23:

- No prescriptions or fixes. ruleprobe never says to keep, rewrite or delete a rule.
- No HTML report cards.
- No cause triage. ruleprobe does not say why a rule was ignored.
- No hooks or guards that block an agent.
- Nothing hosted: no service, no upload, no team aggregation.
- No model call inside `ruleprobe report`.
- No universal runtime claim. The README lists the runtimes read.
- No fork of detector logic into a consumer; consumers import it (AD-13).

## 8. Scope for 0.2.0

**In (planned, v0.2.0):** FR-14, FR-15, FR-16 (section-level binding, catalog, measured share); FR-21 and
FR-22 (compliance per opportunity); FR-25 and FR-26 (field validity); FR-27 to FR-31 (versioned contract;
FR-29's persisted fold entries and rename test only); FR-32 and FR-33 (third reader).

**Held (implemented, 0.1.0):** FR-1 to FR-13, FR-17 to FR-20, FR-23 and FR-24, unchanged except where
the contract work versions them.

**Withdrawn:** FR-34 (2026-09-23; moved to #21).

**Out:** §7, and compliance by position in the session (research recommendation 4), kept out of 0.2.0 by
the maintainer on 2026-09-23 (§11, Q5).

**Beyond 0.2:** FR-35's seam is proposed for 0.3 (#21). A separate, provider-neutral judge library is
future and unscheduled. It would own judging and depend on ruleprobe's seam, never the reverse. It is
carved out of agent-harness's decision layer when three signals hold: developers outside the project ask
to measure dark rules with their own model; the judge needs nothing from the harness except ruleprobe's
seam; and the judge has a validity figure on the corpus that the provider's terms allow to be published.
Non-goal: no model client, credential or vendor adapter enters ruleprobe.

## 9. Success metrics

**Baseline, 2026-09-23:** 0 GitHub stars; 0 known outside users. Unless stated otherwise, the
window runs for six months from the 0.2.0 release. The maintainer kept every target as written and set
this window on 2026-09-23 (§11, Q6).

- **SM-1 Sixty-second test.** Cohort: five first-time testers outside the project, each with an unedited
  `CLAUDE.md` or `AGENTS.md` and their own transcripts. Target: four of five see at least one of their own
  rules measured within a minute, timed by observation, with no detector written. Validates FR-15, FR-16,
  FR-13, NFR-9. The bar mirrors the harness's SM-1.
  - Counter: catalog precision. No catalog detector ships without `examples:` or under the floor. Loose
    binding that lifts the measured share on rules nobody would recognise shows here.
- **SM-2 Outside use.** Cohort: people outside the project. Target: five who report a run, file an issue
  or open a pull request on `JakeSelby/ruleprobe`. Baseline 0.
  - Counter: stars and downloads. Recorded, never targeted; a rise with no outside run is not success.
- **SM-3 Built on.** Cohort: public repositories. Target: one consumer besides agent-harness imports the
  library, found through GitHub's dependents graph or a public code search for `import ruleprobe`.
  Validates FR-30.
  - Counter: forks of detector logic. A consumer that copies detector code instead of importing it does
    not count.
- **SM-4 Contract held.** Cohort: agent-harness and any SM-3 consumer. Window: every 0.2.x release.
  Target: zero breakages; the harness pins 0.2 with no fork. Validates FR-27 to FR-31.
  - Counter: declared-surface growth. A name joins the declared API only with a contract test; the list
    is not grown to avoid a break.
- **SM-5 Compliance per opportunity shown.** Cohort: every rule whose detector defines an opportunity.
  Target: 100% show opportunities and followed in `report` and `report_data`. Validates FR-21.
  - Counter: thin figures. Zero compliance rates are shown over fewer opportunities than the FR-22
    minimum.
- **SM-6 Runtime-neutral is a fact.** Cohort: the third reader's labelled corpus sessions. Target: every
  applicable detector at or above 0.9 in CI. Validates FR-32, FR-33.
  - Counter: easy sessions. The third runtime's sessions carry near-misses as well as positives.
- **SM-7 Every hit explains itself.** Cohort: every hit in a report run over transcripts. Target: 100%
  return the event and detector through the explain path. A hit counted from a stored row is outside
  the cohort; it gets the counts-only message and the re-run it needs. Validates FR-25.
  - Counter: report drift. The explain path changes no report number.
- **SM-8 Field validity grows.** Cohort: corpus negatives. Target: at least ten that came from real false
  positives through FR-26. Validates FR-26.
  - Counter: floor erosion. The floor stays at 0.9, and no detector is deleted to pass it without a
    changelog entry.

**Global counter-metrics:** a model call anywhere in `report`, a runtime dependency, or the same
transcript giving a different report. Any one is a failure regardless of the other metrics.

## 10. Risks

- **Second release cadence.** Each ruleprobe release forces a harness bump (unpublished maintainer
  notes, 2026-09-21, post-build position). Mitigation: few, batched releases; FR-31.
- **Silent contract drift until 0.2.0.** The harness imports far more than the README declares (FR-30).
  Mitigation: the contract test lands with the declaration.
- **A position resting on few detectors.** Six generic detectors, and opted-out rules stay dark. Mitigation:
  FR-15, FR-16.
- **Absorption.** Langfuse and LangSmith already hold Claude Code and Codex transcripts, and /insights
  reads local transcripts (research refs 15, 17, 19). None was found scoring existing rules. Re-check
  due 2026-12-23.
- **Stale evidence.** The research's staleness map lists ref 26 as already stale. The positioning cites
  it for parity only.

## 11. Open questions

1. **Third reader: Cursor or Gemini CLI?** Closed 2026-09-23: Gemini CLI. The spike RP-SP003 still
   confirms its format and reports back if it cannot be read reliably (RP-SP003, #54).
2. **Section-level binding: split on headings, list items, or both?** Closed 2026-09-23: headings only
   for 0.2 (RP-D008, #45).
3. **How many rule shapes must the catalog hold before SM-1 can pass?** Closed 2026-09-23: a small set
   of six to eight shapes, listed in FR-16, each clearing the floor (RP-D009, #46).
4. **Does the drafting command belong in 0.2.0, a later minor, or nowhere?** Closed 2026-09-23: nowhere
   in ruleprobe; FR-34 is withdrawn and drafting moves to the judge library tracked in #21 (RP-D011,
   #59).
5. **Should the report also break compliance down by position in the session (research recommendation
   4)?** Closed 2026-09-23: out of 0.2.0 (RP-D007, #44).
6. **Are the targets and the 2027-03-23 window right?** Closed 2026-09-23: targets kept as written; the
   window becomes six months from the 0.2.0 release (RP-D010, #57).
7. **Is 20 the right minimum opportunity count?** Closed 2026-09-23: 20, per printed group (RP-D004,
   #38).
8. **Do the root `__all__` names outside FR-30's list join the declared API, or stay importable and
   undeclared?** Closed 2026-09-23: importable and undeclared; a name joins only with a contract test
   (RP-D002, #30).
9. **Is the schema version an integer, and does 0.2.0 write `2`?** Closed 2026-09-23: yes; an absent
   key means 1 (RP-D001, #29).
10. **How does a Python detector declare an opportunity?** Closed 2026-09-23: through the keyword-only
    `opportunities` callable of AD-11 (RP-D005, #39).
11. **What does `promote?` become?** Closed 2026-09-23: a neutral "frequent" marker with no advice;
    the parameter names follow in the break (RP-D006, #40).
12. **May a 0.x minor break again after 0.2.0?** Closed 2026-09-23: yes, with notice: a Breaking
    changelog heading naming the migration, and the contract test updated in the same change (RP-D003,
    #31).
13. **README count of declared names.** The README says "six names" but lists seven lines plus two
    (`README.md:339`); FR-30's count of eight is right. A docs fix for the 0.2 stories, not a PRD
    change.

## 12. Assumptions index

- §2.3 UJ-1: the explain path's CLI form is left to the architecture spine.
- §4.5 FR-15: what counts as a rule within a split unit.
- §4.5 FR-16: Conventional Commit subject parsing fits a matcher.
- §4.6 FR-21: compliance per opportunity starts from the `order` and `absent` shapes.
- §5 NFR-3: `--since` is the one clock-dependent input.
- §5 NFR-9: the reference volume; no timing measured, and the bound is SM-1's minute.
