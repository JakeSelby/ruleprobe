# ruleprobe

A standalone Python package that measures which of a coding agent's rules actually fire, by
running deterministic detectors over the transcripts the agent already wrote. Standard library
only, Python 3.9 and newer, MIT. This file carries what is true of this repository.

## For other repositories

- ruleprobe is a standalone Python package with no runtime dependencies. A release is a tag, which publishes it.
- Changes land through one squash-merged pull request per issue.
- Its README at the released tag is ruleprobe-site's landing copy: change it here and release.

Before changing anything here from a session started in another folder, read
`.claude/rules/working-here.md`. Claude Code loads it by itself only in sessions started in this
repository, on their first file read; every other session and tool must read it.

## Gate

```sh
python3 -m compileall -q ruleprobe tests scripts
python3 -m unittest discover -s tests
python3 -m ruleprobe corpus --no-config --floor 0.9
python3 scripts/bmad_issue_sync.py audit
python3 scripts/release_preflight.py
```

CI runs these as the required `test`, `floor`, `corpus` and `package` checks, plus
`issue-ownership` on every pull request.

## The package contract

- **No runtime dependency.** `dependencies = []` is a promise in the README. Anything that
  needs a third-party library is a development tool, never an import under `ruleprobe/`.
- **Nothing leaves the machine.** `ruleprobe report` sends nothing, asks no model and writes
  nothing to disk. A feature that needs any of those is a separate, opt-in command.
- **Deterministic.** The same transcript gives the same report. No clock in the output, no
  iteration over an unordered set in a place the output depends on.
- **Under-count rather than over-count.** A missed hit is a quieter report; a false hit is a
  wrong one. A new detector ships with corpus labels or `examples:` and a near-miss beside
  each positive.
- **The public API is what the README lists.** Changing a name in it is a breaking change.
- **The corpus is synthetic.** No real transcript content, home paths or personal names ever
  enter `ruleprobe/corpus/`, `tests/fixtures/` or `docs/`.

## `AGENTS.md` and `CLAUDE.md` are one file

`CLAUDE.md` is a symlink to this file. Edit `AGENTS.md`.
