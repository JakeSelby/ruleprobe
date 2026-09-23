---
bmad_id: "RP-SP003"
type: "spike"
title: "spike(readers): choose the third runtime, Cursor or Gemini CLI"
lifecycle: "active"
provenance: "authored"
github_issue: 54
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/54"
parent_bmad_id: "RP-E007"
parent_github_issue: 26
updated: "2026-09-23"
---

# RP-SP003 — spike(readers): choose the third runtime, Cursor or Gemini CLI

<!-- bmad-sync:begin -->
- **GitHub issue:** [#54](https://github.com/JakeSelby/ruleprobe/issues/54)
- **Primary parent:** [RP-E007](https://github.com/JakeSelby/ruleprobe/issues/26)
- **State:** active

The issue carries the summary, discussion and acceptance evidence; this file carries the design.

This work item was authored as part of the repository's committed BMad planning system.
<!-- bmad-sync:end -->

## Question

Which third runtime does ruleprobe read in 0.2: Cursor or Gemini CLI? This is PRD open question 1, and
it blocks FR-32, FR-33 and SM-6. The choice rests on which runtime's transcripts a detector can read.

## Experiment

For each candidate, from public documentation and a synthetic session, record:

- the transcript location and format;
- whether shell commands, file writes, tool-use ids and turns are recorded;
- the licence of any format documentation used.

Then, for the chosen runtime, list each file tool that maps exactly to a canonical name (`Write` with
`file_path` and `content`, `Edit` with `file_path` and `new_string`) and each that stays native
(AD-3). A native file tool matches no canonical detector and under-counts (AD-4); that gap is stated,
not closed by a lossy mapping.

## Exit criterion

- Both candidates have every field above recorded, or marked not recorded.
- The choice is stated with its trade-off.
- The chosen runtime's file tools are each listed as exact or native, so the part of FR-32 that holds
  is known before RP-S019.

## Result

Not yet run.

## Decision

Open: which candidate's transcripts record shell commands, file writes, tool-use ids and turns in a
form a reader can map under AD-3. The corpus records no recommendation. The result unblocks RP-S019.

## Dev notes

- Binds FR-32 (a third reader, Cursor or Gemini CLI), FR-33 (labelled third-runtime sessions at or
  above the floor), AD-3 (one tool vocabulary across runtimes), AD-10 (how a reader is added).
- No dependency. Files: this story file only. Tests: none.
- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1]
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#11. Open questions]
- [Source: _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md#AD-3]

## Change log

- 2026-09-23: written from the planning corpus before implementation.
