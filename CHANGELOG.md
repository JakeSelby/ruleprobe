# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Breaking

0.2.0 versions the contract and takes its break here, in seven parts: the undecided rule for `not`
and `absent`; schema versions, on detector entries (below) and on rows and the `report_data` result
(under Added); the persisted fold map for renamed detector ids; the declared public API; the
coverage block, which now also appears in `report --json` as `coverage`; section rules; and the
report's `frequent` marker, with its threshold renamed. Each part has its entry below, the row
schema's under Added. From 0.2.0 nothing declared breaks within a minor series, and a later 0.x
minor may break only under a Breaking heading like this one; the README's Versioning section states
the policy.

- A declarative matcher no longer counts a Bash command the shell parse skipped - empty or missing,
  longer than 16,384 characters, or one that does not tokenize or parse - as a match for `not` or
  `absent` ([#19](https://github.com/JakeSelby/ruleprobe/issues/19)). Over such a command every
  `command` key but `regex` and `unparsed`, every `git` key, every `env` key and a `text` read of
  `source: heredocs` is undecided; `not`, `any` and `all` pass undecided through, and an undecided
  `when`, an `order` endpoint or an `absent` candidate is no hit. A detector file using `not` or
  `absent` may count fewer hits; no edit is needed, and a rule that wants those commands asks for
  `command: {unparsed: true}`. A predicate from `compile_matcher` may now return a falsy undecided
  value: a Python caller who negates a predicate itself reads it as false and can over-count, and
  should test it with `is_undecided` or compose through the declarative `not`, `any` and `all`
  instead.
- A detector file's top-level `version`, ignored in 0.1, is now read as its entries' schema version,
  and an entry may carry its own `schema_version`, which wins
  ([#32](https://github.com/JakeSelby/ruleprobe/issues/32)). A schema version this release does not
  know - above 2, `0`, negative or not an integer - is a finding, and only the entries that would
  read it are skipped; a top-level `schema_version` is a finding too, since the file-level key is
  `version`. A 0.1 detector file whose top-level `version` is anything but 1 or 2 loses the entries
  without a key of their own until it is corrected.
- `report --rules` prints the measured share in the coverage block, as in `rules: 2 measured, 1
  dark, 1 unmeasured (50% measured)`, floored so a file with a rule unmeasured never shows 100%
  ([#47](https://github.com/JakeSelby/ruleprobe/issues/47)); and `report --json` now carries the
  block as a top-level `coverage` key, where it was printed to stderr only. The key counts rules,
  not sessions.
- The README declares the public API: every name, call shape and non-name promise a downstream tool
  may pin, each held by a contract test that CI also runs against the built wheel imported as a zip
  ([#35](https://github.com/JakeSelby/ruleprobe/issues/35)). A name outside that list is importable
  but may change in any release.
- A retired detector id folds onto its current id through one fold map: the renames the package
  ships, with a consumer's own `Registry(renamed=)` laid over them
  ([#34](https://github.com/JakeSelby/ruleprobe/issues/34)). Chains resolve to their end, and a
  cycle raises `ValueError` when a `Registry` is built or a rename would close one. `report_data`
  and `--json` carry the effective map as `renamed`, and corpus labels fold the same way. A test
  fails when a detector id any release shipped is neither registered nor folded.
- An unbound rule file with headings now splits into one rule per section, with the id
  `<path>#<heading-slug>` and an ordinal suffix for a repeated slug, so the coverage block counts
  rules, not files ([#48](https://github.com/JakeSelby/ruleprobe/issues/48)). A section holding only
  a heading, a fenced or indented code block, a table, a quote or a comment is not a rule. A file
  with no heading, a file bound in its front matter, and a headed file with no rule section stay one
  rule with their 0.1.0 id. The findings line now reads `findings: N (everything else still
  loaded)`.
- The `report` table marks a detector whose share of measured sessions passes the threshold
  `frequent`, where 0.1 printed `promote?`, and the marker advises nothing about the rule
  ([#43](https://github.com/JakeSelby/ruleprobe/issues/43)). The threshold is renamed with it:
  `frequent_share=` on `report` and `report_data`, the `--frequent-share` option, the
  `frequent_share` key in `report_data` and `--json`, and the `RULE_FREQUENT_SHARE` constant, where
  0.1 had `promote_share`, `--promote-share` and `RULE_PROMOTE_SHARE`.

### Added

- Rows and the `report_data` result carry `schema_version`, which this release writes as 2
  ([#33](https://github.com/JakeSelby/ruleprobe/issues/33)). A row with no version, or a null one,
  reads as 1; a row with a version this release does not know is left out of every count, tallied
  in `unknown_schema`, and noted by `report`.
- `is_undecided(value)`, exported from the package root, tells the undecided result of a
  `compile_matcher` predicate from a false one
  ([#35](https://github.com/JakeSelby/ruleprobe/issues/35)).
- `Detector` takes an optional keyword-only `opportunities`: a callable over `(events, ctx)`
  returning `(turn, tool_use_id, followed)` triples, with `followed` true, false or None for
  undecided ([#41](https://github.com/JakeSelby/ruleprobe/issues/41)). Declarative `order` and
  turn-scoped `absent` detectors set it from the same evaluation as their hits; the positional
  constructor and `fn(events, ctx)` are unchanged.
- A row from `measure()` carries `compliance`: for each enabled detector that defines
  opportunities, `{"opportunities": N, "followed": M, "undecided": U}`, with undecided points
  counted apart and never as not followed ([#42](https://github.com/JakeSelby/ruleprobe/issues/42)).
  A raising or malformed `opportunities` is recorded in `rules_errors` tagged `"hook":
  "opportunities"` and costs only that detector's compliance, not its hit figures.
- `ruleprobe explain` reruns the detectors over your transcripts and prints the event behind every
  hit: the session address, turn, tool-use id, detector id and the matched command or input,
  filtered by `--session`, `--detector` and `--key`
  ([#51](https://github.com/JakeSelby/ruleprobe/issues/51)). It changes no report number, sends
  nothing and writes nothing. Every line it prints passes through `redact` in
  `ruleprobe.detectors.common`, which hides the shipped secret shapes and a set of common
  credential forms; other credentials can still print, so read the output before sharing it.
- `report` and `report_data` carry compliance beside hits for every detector a row has a tally
  for: `opportunities`, `followed`, `undecided` and `compliance_rate`, which is `followed /
  opportunities` and null below `min_opportunities`
  ([#43](https://github.com/JakeSelby/ruleprobe/issues/43)). They group under `--by repo` and
  `--by stance` as hits do, and the table prints them as four columns only when some row carries
  compliance. `--min-opportunities`, defaulting to `RULE_MIN_OPPORTUNITIES` (20), is the fewest
  opportunities a rate is printed for. `report_data` also counts `opportunity_errors`,
  `malformed_compliance` and `unreadable_compliance`, and `report` notes each: a detector whose
  `opportunities` raised, a tally that cannot be read, or a compliance map that names no
  detector. Each costs only compliance figures for those sessions; hits stand.

### Changed

- The package declares its licence as the SPDX expression `MIT`, with `LICENSE` as its licence
  file, in place of the deprecated table form and classifier
  ([#6](https://github.com/JakeSelby/ruleprobe/issues/6)). Building ruleprobe from source now
  needs setuptools 77 or newer.
- The `report` table's share header is one column wider, so the note and validity columns start
  under their headers ([#43](https://github.com/JakeSelby/ruleprobe/issues/43)).

## 0.1.0 (2026-09-22)

### Added

- The measurement engine: `run()` over a session's events, a `Registry` of `Detector`
  objects, and `report()` over the rows it produces.
- Readers for Claude Code transcripts and Codex rollouts, behind one event schema and one
  `iter_sessions(root, runtime, since)`.
- The Bash decomposition every shell detector shares: compounds, pipelines, heredocs,
  substitutions and continuations, parsed once per command.
- Six generic detectors: whole-file cat, unfiltered find, no-verify, secret in a write,
  compaction, and a model switch mid-session.
- A `ruleprobe report` command, grouping by detector, by repository or by stance.
- An extension point for declarative detectors: `register_compiler` and `from_spec`.
- A declarative detector format, so a rule can be measured without writing Python: one entry
  of `id`, `rule`, `event`, `when` and an optional `gate`, compiled by `ruleprobe/matchers.py`
  into the same `Detector` a Python detector builds.
- Matchers for a tool name, an argument, a Bash command through the shared parse, a `git`
  call, an environment assignment, a text body, an assistant message and a raw event kind,
  composed with `any`, `all` and `not`; and three that read a whole session, `order`,
  `absent` and `change`.
- `ruleprobe/declarative.py`: a strict, minimal YAML subset with a line number and a reason
  on every refusal, and the same objects from a `.json` file. No third-party dependency.
- Detector files found without a flag: `.ruleprobe/detectors.yaml` at the root of the
  repository you are in, and `~/.config/ruleprobe/detectors.yaml` for the user. `--detectors`
  names one, `--no-config` skips discovery.
- `ruleprobe report --rules <dir>`: markdown rule files bind to the detectors in their front
  matter, and the report says which rules are measured, which are dark by `opt_out`, and
  which are **unmeasured** - the gap an author cannot otherwise see.
- `ruleprobe/detectors/common.yaml`: the six shipped detectors written as data, with a test
  asserting they produce identical hits to the Python reference over the corpus and the
  fixture transcripts.
- A worked example that runs from a clone: `docs/rules/` and `docs/example-session.jsonl`.
- A labelled corpus, shipped as package data at `ruleprobe/corpus/`: six synthetic sessions
  in both transcript shapes, every interesting event labelled by hand in `labels.yaml` with
  the detectors that should fire on it, and a deliberate near-miss beside each - a `cat` of
  a range, a filtered `find`, a push after the gate ran, a heredoc with `rm -rf` in its body
  as text. Every shipped detector carries at least five positives and five negatives.
- `ruleprobe corpus`, and `ruleprobe.validity()` behind it: per-detector precision, recall
  and F1 with their counts, a total, `--json`, `--corpus DIR` for a corpus of your own, and
  a non-zero exit under `--floor 0.9`. The floor is this repository's CI gate, not a runtime
  failure: nothing in `ruleprobe report` reads it.
- `ruleprobe report --validity`: each detector's corpus precision and recall beside its row.
  Off by default, because the two numbers belong to the detector rather than to the run.
- An optional `examples:` block on a declarative detector - `fire:` and `skip:` lists of
  minimal cases, each `bash:`, `event:` or `events:` - so a detector of your own can be
  scored without a corpus. A detector with neither says `no examples` rather than a number,
  and the floor steps over it.
- `.github/workflows/ci.yml`: the unit tests on 3.9 and the newest 3.x, `compileall`, and
  `ruleprobe corpus --floor 0.9`.

### Changed

- A malformed detector entry is a finding with a file, a line and a reason, printed under the
  report; the entry is skipped and every other detector still runs.
- The README no longer says detector validity is unmeasured; it prints the corpus table
  instead, and a test asserts the README quotes it byte for byte.

### Fixed

Every finding of the pre-release review, [#2](https://github.com/JakeSelby/ruleprobe/issues/2),
each with the reviewer's own input as a regression test in `tests/test_findings.py`.

- **The shell parse.** `cat <<\EOF` is a heredoc header, so its body is no longer parsed as
  commands and no longer yields a false `unfiltered-find` hit; a heredoc terminator must be
  the delimiter alone, as bash has it, and only `<<-` may have it indented; a command that
  does not tokenize is `unparsed` rather than invisible to every matcher.
- **The denominator.** A detector that raises leaves the denominator of that detector only,
  instead of taking the whole row out of every other detector's evidence, and a row is never
  counted twice in the preamble.
- **Errors are counted.** `iter_sessions(errors=[...])` collects every transcript that
  raised or held no session, and `ruleprobe report` prints the count. The directory walks
  follow symlinks.
- **Matchers.** `arg: {equals: ...}` no longer raises on a list-valued field; `absent` over
  a session with no events is not a hit; `command: {contains: ...}` is a substring;
  a list of `command: {regex: ...}` patterns is alternatives; `order: {within: N}` does not
  spend its budget on `tool_result` events; `path_glob` is matched as a path, with `*`
  stopping at a `/`, `**` crossing one, and a relative pattern matching an absolute
  `file_path`.
- **The parser.** An escaped quote inside a double-quoted string no longer truncates it at a
  `#`; `[a: b]` is a one-key mapping and not a tuple; `yes`, `no`, `on`, `off` and a
  leading-zero number are refused with a line and a reason rather than read one way here and
  another by YAML.
- **The readers.** A runtime is chosen by parsing the first line, not by searching it for
  `"session_meta"`; a streamed partial text block is one message that grows, not two; a
  Codex user message is a `user_prompt` and `final` is derived there as it is on Claude Code,
  so a detector means the same thing on both.

### Changed

- `iter_sessions` takes an `errors` list; `measure`, `run`, `report`, `Registry` and
  `iter_sessions` are otherwise unchanged in signature.
- `report_data(rows, ...)` is new and is what `report()` renders and `ruleprobe report
  --json` prints, so the table and the JSON cannot disagree about a denominator, a fold or a
  note. `--json` now prints that object with the rows under `rows`, and exits non-zero on an
  empty root as the table does.
- `ruleprobe report --stance dimension=variant`, repeatable: a `gate:` block was unreachable
  from the command line, so a gated detector never fired and `--by stance` could only print
  `(no stances)`. `ruleprobe detectors` names the stance each gate is waiting for.
- `--since 2024` is refused rather than silently read as 2024 days back.
- `Registry.rename` removes the detector it renamed.
- A `user_prompt` event carries the prompt's `text` on both runtimes.
- `README.md` and `ruleprobe/detectors/common.yaml` no longer claim the shipped detector
  file uses every matcher; they name the ten it uses and the four it does not.
