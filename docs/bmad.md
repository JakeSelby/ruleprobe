# BMad in this repository

ruleprobe uses the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) (MIT) as its public
planning system: product brief, PRD, architecture, epics and stories are written with it, and each
GitHub issue carries an immutable BMad ID. The framework's files are installed locally and never
committed; only this repository's configuration and the planning corpus it authors are.

## Install

BMad Method 6.12.0 with the `bmm` module, Claude Code and Codex projections, and compatibility
shims. From the shared checkout, not a worktree:

```sh
BMAD_VERSION=6.12.0
npx --yes bmad-method@"$BMAD_VERSION" install --directory . --modules bmm \
  --tools claude-code,codex --user-name <your name> --communication-language English \
  --document-output-language English --output-folder _bmad-output --shims --yes
```

Upgrade by changing the pinned version here in its own pull request, reinstalling, and checking
that every tracked file under `_bmad/custom/` still resolves.

## The version-control boundary

### Commit

- `_bmad/custom/config.toml` and the `bmad-*.toml` workflow customizations, each of which loads
  `docs/bmad-governance.md` as a persistent fact.
- `_bmad-output/planning-artifacts/**`: brief, PRD, architecture, epics, decisions, readiness.
- `_bmad-output/implementation-artifacts/**`: one `RP-*.md` per mapped issue, stories, sprint
  state and retrospectives.
- `_bmad-output/issue-map.json`, the mapping between BMad IDs and GitHub issues.

### Do not commit

- The installed `_bmad` runtime outside `_bmad/custom`, and every `*.user.toml`.
- The generated `.agents/skills`, `.claude/skills` or `.github/agents` projections.
- Installer caches, logs, raw conversations, memory exports, secrets or private paths.

A clean reinstall must leave tracked files unchanged.

## GitHub traceability

GitHub owns scope, discussion, delivery state and acceptance evidence. BMad supplies the typed ID
and the public artifact. `_bmad-output/issue-map.json` records each mapping, its primary parent
and the next ID of each kind; `_bmad-output/implementation-artifacts/RP-*.md` links back to the
issue, and a generated Planning block in the issue links to the artifact on `main`.

| Kind | Prefix | Example |
| --- | --- | --- |
| epic | `RP-E` | `RP-E001` |
| story | `RP-S` | `RP-S001` |
| task | `RP-T` | `RP-T001` |
| bug | `RP-B` | `RP-B001` |
| chore | `RP-C` | `RP-C001` |
| spike | `RP-SP` | `RP-SP001` |
| decision | `RP-D` | `RP-D001` |

```sh
python3 scripts/bmad_issue_sync.py new --title T --kind KIND --body-file F [--parent N] [--milestone M]
python3 scripts/bmad_issue_sync.py reserve --issue N --kind KIND [--parent N]
python3 scripts/bmad_issue_sync.py audit            # offline consistency; CI runs it
python3 scripts/bmad_issue_sync.py audit --live     # against GitHub; the daily workflow runs it
python3 scripts/bmad_issue_sync.py plan             # what apply would change
python3 scripts/bmad_issue_sync.py apply            # write Planning blocks, labels and parents
```

The exact `type::*` label is the authoritative type, because native issue types are
organization-managed and this is a personal-account repository. Native sub-issues carry the
hierarchy.
