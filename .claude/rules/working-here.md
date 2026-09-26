---
paths:
  - "**/*"
---

# Working in ruleprobe

## Commands

```sh
python3 -m unittest discover -s tests                      # the suite
uv run --python 3.9 python -m unittest discover -s tests   # the floor the package claims
python3 -m ruleprobe corpus --no-config --floor 0.9        # the detector-validity gate
python3 -m ruleprobe report --root docs --rules docs/rules # the worked example, end to end
python3 scripts/bmad_issue_sync.py audit                   # the issue map is consistent
python3 scripts/release_preflight.py                       # version and changelog agree
```

**Expected clean-tree output:** `OK` from unittest with no skipped tests, `total … floor 0.90`
with no detector under it, `audit: N issue(s), 0 finding(s)`, and
`release preflight: <version> is ready`.

## BMad planning

BMad Method 6.12.0 with the `bmm` module is this repository's public planning system. Its
authored corpus lives in `_bmad-output/`; the installed runtime and the skill projections are
local and ignored. The pinned install command and the version-control boundary are in
`docs/bmad.md`; the policy every BMad workflow loads is `docs/bmad-governance.md`. Run planning
workflows from the shared checkout and implementation from a worktree.

Every SDLC step routes to its BMad skill, and every PR keeps the corpus current: the issue keeps a
summary, its story file carries the design. The routing map, the currency rule and the story-file
contract are in `docs/bmad-governance.md`, which every BMad workflow loads.

## How work lands

- **Every change lands through a pull request.** The `main` ruleset requires the checks above
  on an up-to-date branch, resolved review threads and a squash merge; there is no direct push.
- **One delivery issue per PR, one PR per delivery issue.** File the issue before changing
  files, including docs, with `scripts/bmad_issue_sync.py new`, or `reserve` an existing one;
  `issue-ownership` fails a PR whose issue has no BMad ID in `_bmad-output/issue-map.json`.
  Put `Closes #N` in the PR body. Split separately delivered work into child issues.
- **Conventional Commits.** The PR title becomes the squash commit, so it is the commit message.
- **Code changes carry a test.** A detector change carries corpus labels or `examples:`.
- **A user-visible change adds a line under `## Unreleased` in `CHANGELOG.md`** in the same PR.

## Issues, milestones and releases

- **Every issue carries one `type::*` label**, and the `v<next>` milestone when it is meant for
  the next release. Create that milestone when the first issue is filed against it.
- **Releases are cut by milestone.** Merge freely; propose a release when the milestone empties
  or a user-visible unreleased change is seven days old. A regression fix releases at once as a
  patch.
- **Number by what changed.** Fixes only is a patch; added or changed user-visible behaviour is
  a minor. Before 1.0, a breaking change to the CLI, the detector format or the public API is a
  minor and says so at the top of its changelog section.
- **A release is a tag.** `docs/releasing.md` holds the procedure: fold the changelog, bump
  `__version__`, run the preflight, tag `v<version>`. The tag workflow publishes to PyPI and
  GitHub and advances `stable`; nothing is uploaded by hand.

## Layout

- `ruleprobe/` — the package: readers, the shell parse, the registry, the declarative format,
  matchers, rules binding, report, and the shipped detectors and corpus as package data.
- `tests/` — the suite. The five `test_*` files for `scripts/` stay out of the sdist.
- `docs/` — the worked example and the repository's process docs.
- `scripts/` — repository tooling: the BMad issue map, the release preflight and notes, the
  `stable` branch, and the reference-volume generator for timing `report`. Never imported by the
  package.
- `_bmad/custom/`, `_bmad-output/` — BMad configuration and the public planning corpus.
