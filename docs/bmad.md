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

GitHub owns delivery state, discussion, the summary and acceptance evidence. BMad supplies the
typed ID and the story file that carries the design. `_bmad-output/issue-map.json` records each
mapping, its primary parent and the next ID of each kind; `_bmad-output/implementation-artifacts/RP-*.md`
is the story file and links back to the issue, and a generated Planning block in the issue links to
the artifact on `main`.

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

## Story files

The pattern comes from [agent-harness](https://github.com/JakeSelby/agent-harness), where story
files were first made the design record.

`new`, `reserve` and `bootstrap` write each story file from the template for its kind in
`scripts/bmad_story_templates/`: story, bug, spike, decision, epic, and one shared by task and
chore. The file opens with the nine linkage fields and `updated` as frontmatter, then the H1, then a
managed block between `<!-- bmad-sync:begin -->` and `<!-- bmad-sync:end -->` holding the issue
link, the parent, the state and the line that splits authority: the issue carries the summary,
discussion and acceptance evidence, and the file carries the design. Those three parts belong to the
tool. Everything after the end marker belongs to the people and agents who write the story, and the
tool never rewrites it. The block counts only where it opens, on the first non-blank line after
the H1, and it closes at the first end marker after that. The markers quoted anywhere else, in prose
or in a code fence, are ordinary text. Blank lines and whole-line HTML comments between the
frontmatter and the H1 are kept as they are; anything else there makes the file malformed. A
leading byte-order mark and CRLF line endings are kept on every rewrite.

Each template section holds a placeholder, `<!-- fill: what goes here -->`. A section counts as
filled when text remains once HTML comments, an unclosed one included, and `###` to `######`
sub-headings are taken out; any level 1 or 2 heading, ATX or setext, outside a comment or fence
ends a section, and a required heading that appears twice is a finding. These sections must be
filled:

- **story:** Story, Acceptance criteria, Design, Tasks, Dev notes
- **bug:** Reproduction, Root cause, Acceptance criteria, Design, Dev notes
- **spike:** Question, Experiment, Exit criterion, Result
- **decision:** Context, Options, Decision, Consequences
- **epic:** Goal, Scope and requirement coverage, Exit criteria
- **task and chore:** Goal, Acceptance criteria, Tasks

```sh
python3 scripts/bmad_issue_sync.py audit --delivery N
python3 scripts/bmad_issue_sync.py upgrade --check
python3 scripts/bmad_issue_sync.py upgrade --id RP-S123
python3 scripts/bmad_issue_sync.py refresh
```

`audit --delivery N` checks only issue N's story, and fails while any section its kind requires is
missing or unfilled. The required `issue-ownership` check runs it for the pull request's own
delivery issue, so an unfilled story elsewhere in the corpus never blocks an unrelated pull request.

A legacy stub is a file from before typed templates that opens with exactly the stub the tool
rendered for its item, ignoring `updated` and line endings; anything after that stub is carried
amendment text. Any other file without a well-formed managed block is malformed: `audit` reports
it, `refresh` refuses it, and `audit --delivery` fails it, so deleting a marker never skips the
depth check. The depth check passes a legacy stub with a notice, and `refresh` keeps rendering it
the old way. `upgrade` converts stubs to their kind's skeleton, carrying every byte after the old
stub, such as `## Amendment` sections, over verbatim at the end of the file, in the file's own line
endings. It refuses a stub that differs from the one the tool rendered, converts all the selected
files or none, restoring any it already wrote when a write fails, leaves a file already in the typed
format alone, and with `--check` reports without writing. Fill a skeleton in the same pull request
that upgrades it, so a file full of placeholders never lands on `main` on its own.

`refresh` copies GitHub's title and state into the manifest and its story files, and adopts a mapped
parent the manifest records as none. In a typed story file it rewrites only the frontmatter, the H1
and the managed block, and keeps the rest byte for byte. It checks every drifted artifact before
writing any of them, and refuses the whole run when a typed file's markers are missing or
duplicated, or when a legacy stub carries amendments; run `upgrade` on such a stub first. It never
touches GitHub.
