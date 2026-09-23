# BMad repository governance

This file is the single policy source loaded by this repository's BMad workflow customizations.
`AGENTS.md` remains authoritative where it is stricter.

- **Authority is split between the issue and its story file.**
  - The GitHub issue is the delivery authority. It holds state, discussion, a summary-depth writeup and
    the acceptance evidence.
  - The issue's story file, `_bmad-output/implementation-artifacts/<BMad ID>.md`, is the design
    authority. It holds:
    - context and acceptance criteria;
    - the design, with decisions and alternatives;
    - tasks;
    - dev notes that cite their sources;
    - the dev agent record;
    - review findings.
  - Keep the issue at summary depth and put the design depth in the story.
  - Create the issue before changing tracked files. Use one delivery issue per PR, and keep one concern in
    each PR.
- Run implementation in a worktree. Run BMad's installed scripts from the shared checkout and pass
  the implementation worktree as an explicit input.
- Public BMad artifacts live under `_bmad-output`; never redirect them to a private or central
  planning repository.
- Publish synthesized evidence and decisions, not raw conversations, tool logs, memory exports,
  secrets, private paths, real transcript content or irrelevant personal information.
- Label claims as implemented, validated, proposed, historical or unknown. A green suite or a 1.00
  corpus score is not evidence of field accuracy on real transcripts; say which one a claim rests on.
- Every managed work item has one immutable typed BMad ID and a bidirectional GitHub mapping.
  Reparenting never changes the ID; reconstructed history must say that it is reconstructed.
- File maintainer work with `python3 scripts/bmad_issue_sync.py new --title T --kind KIND
  --body-file F [--parent N] [--milestone M]`: it labels the issue and reserves its ID in one step.
  Refuse to start implementation for an issue absent from `_bmad-output/issue-map.json`; the
  required `issue-ownership` check fails a PR whose delivery issue is unmapped.
- Community issues can enter without BMad metadata. During triage, reserve an ID with
  `python3 scripts/bmad_issue_sync.py reserve --issue N --kind KIND [--parent N]`, then run `plan`
  and `apply` before implementation begins.
- Preserve issue and repository history. Add amendments rather than rewriting dated evidence, and
  do not replace original issue prose when maintaining traceability metadata.
- The package contract in `AGENTS.md` binds every plan: no runtime dependency, nothing sent off
  the machine by `report`, deterministic output, under-count rather than over-count.
- Before review, run the `## Gate` block in `AGENTS.md`. Never bypass hooks.
- Ordinary issues and PRs use the repository's own voice without generated framework footers.
  README and planning documentation may credit BMad explicitly.

## Route every operation through BMad

Before an SDLC step, read and follow the BMad skill for it. Never improvise a process a skill already
defines.

| When you | Run |
| --- | --- |
| Research a question a decision depends on | `bmad-deep-recon` |
| Change who the product serves or what it is for | `bmad-product-brief`, update intent |
| Add, change or retire a requirement | `bmad-prd`, update intent |
| Change a user-facing flow, output or copy pattern | `bmad-ux`, update intent |
| Change an invariant, a boundary or a dependency direction | `bmad-architecture`, update intent |
| Break new scope into work | `bmad-create-epics-and-stories`, then `scripts/bmad_issue_sync.py new` |
| Implement a work item | `bmad-build`, with the delivery story as its spec |
| Review a change | `bmad-code-review` |
| Change direction mid-flight | `bmad-correct-course` |
| Close an epic | `bmad-retrospective` |
| Check readiness or status | `bmad-sprint-planning` |

However a plan was produced and approved, write its detail into the delivery story's Design and Dev
notes at build time. The story is the durable record.

## Keep the corpus current in every change

Update the corpus in the same PR as the change that makes it stale:

- **New work.** File it with `scripts/bmad_issue_sync.py new`, which files the issue, reserves the ID and
  writes a typed story skeleton. Fill the story's required sections before the delivery PR merges. The
  `issue-ownership` check fails a typed delivery story that still holds placeholders.
- **Touching a legacy stub.** Run `scripts/bmad_issue_sync.py upgrade --id <BMad ID>` and fill the
  skeleton in the same PR.
- **Implementation.**
  - Keep the delivery story current: check off tasks, add the file list and references to the dev notes,
    and complete the dev agent record.
  - Record each review finding and how it was resolved.
  - Add a change-log line for every material change after the story was first written.
- **Changed requirements, invariants or flows.** No PRD, architecture spine or UX specification exists
  yet; once one does:
  - A changed requirement amends the PRD.
  - A changed invariant amends the architecture spine, either as an amended rule or a new AD.
  - A changed user-facing flow amends the UX specification.
  - Each amendment goes through the matching skill's update intent, with a memlog entry.
- **Sprint status is derived** from `issue-map.json` and the GitHub record; never edit it by hand.
