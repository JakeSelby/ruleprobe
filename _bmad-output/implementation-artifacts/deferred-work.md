# Deferred work

Review findings that were real but not fixed in the pull request that found them. Each names its story;
the story's review findings hold the full reasoning.

## Deferred from: code review of RP-B002.md (2026-09-23)

- A release PR that leaves entries under `## Unreleased` passes CI, because the preflight refuses them
  only with `--tag`. The documented `--tag` runs in `docs/releasing.md` steps 2 and 3 refuse it before
  the tag, and `release.yml` after the push. Automatic enforcement, for example running the preflight
  with `--tag` in CI when a PR changes `__version__`, needs the maintainer's call.
- The Unreleased check matches only `- ` bullets under a literal `## Unreleased` heading; `* ` or `+ `
  bullets or a `[Unreleased]` heading would pass. Pre-existing; this repository writes neither.
