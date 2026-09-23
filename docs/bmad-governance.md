# BMad repository governance

This file is the single policy source loaded by this repository's BMad workflow customizations.
`AGENTS.md` remains authoritative where it is stricter.

- GitHub issues are the delivery authority. Create the issue before changing tracked files, use
  one delivery issue per PR, and keep one concern in each PR.
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
