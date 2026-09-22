# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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

### Changed

- A malformed detector entry is a finding with a file, a line and a reason, printed under the
  report; the entry is skipped and every other detector still runs.
