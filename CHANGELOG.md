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
- An extension point for declarative detectors: `register_compiler` and `from_spec`, with no
  compiler shipped yet.
