# Deferred work

Review findings that were real but not fixed in the pull request that found them. Each names its story;
the story's review findings hold the full reasoning.

## Deferred from: code review of RP-B002.md (2026-09-23)

- A release PR that leaves entries under `## Unreleased` passes CI, because the preflight refuses them
  only with `--tag`. The documented `--tag` runs in `docs/releasing.md` steps 2 and 3 refuse it before
  the tag, and `release.yml` after the push. Automatic enforcement, for example running the preflight
  with `--tag` in CI when a PR changes `__version__`, needs the maintainer's call.
  - Amended 2026-09-23: the maintainer chose CI enforcement; RP-C004 (#68) implements it.
- The Unreleased check matches only `- ` bullets under a literal `## Unreleased` heading; `* ` or `+ `
  bullets or a `[Unreleased]` heading would pass. Pre-existing; this repository writes neither.

## Found while running refresh for RP-B002 (2026-09-23)

- `scripts/bmad_issue_sync.py`'s `live_lifecycle` records every closed issue as `completed`, so the
  three closed as not planned (#28 RP-E009, #59 RP-D011, #60 RP-S020) read `completed`. Its lifecycle
  has two values; a `withdrawn` value would need the audit and the story files to accept it.

## Deferred from: code review of RP-B001.md (2026-09-23)

- AD-4 in the architecture spine lists the undecided reads as the `command`, `git` and `env` segment
  keys; a `text` read of `source: heredocs` is undecided over a skipped parse too, as the
  `ruleprobe/matchers.py` docstring says. Amend AD-4 through `bmad-architecture` update intent, for
  example with #36, which names the 0.2 break.
- `command: {unparsed: true}` beside a segment key is undecided on a skipped command and false on a
  parsed one, so it never fires and raises no error. Pre-existing since 0.1.0; a spec-time
  `DeclarativeError` would change the AD-7 vocabulary.

## Deferred from: code review of RP-C004.md (2026-09-23)

- `AGENTS.md`'s `## Gate` block says CI runs its commands, but the `test` check now also runs
  `release_preflight.py --base-init` on pull requests. A release branch should also run the preflight
  with `--tag v<version>` locally, as `docs/releasing.md` says. Amend the gate block when `AGENTS.md`
  is next edited.

## Deferred from: code review of RP-T002.md (2026-09-23)

- The envelope's import scan checks AD-8's list (`socket`, `urllib`, `http`, `subprocess`, model
  clients). `ssl`, `smtplib`, `ftplib`, `asyncio` connections, `multiprocessing` and `pty` pass it,
  and the run-time guard does not refuse `os.system`, `os.popen` or `os.spawn*`. Widening either
  amends AD-8's list, so it is the maintainer's call.
