---
bmad_id: "RP-SP002"
type: "spike"
title: "spike(validity): field precision per shipped detector from hand-sampled hits"
lifecycle: "active"
provenance: "authored"
github_issue: 53
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/53"
parent_bmad_id: "RP-E006"
parent_github_issue: 25
updated: "2026-09-23"
---

# RP-SP002 — spike(validity): field precision per shipped detector from hand-sampled hits

<!-- bmad-sync:begin -->
- **GitHub issue:** [#53](https://github.com/JakeSelby/ruleprobe/issues/53)
- **Primary parent:** [RP-E006](https://github.com/JakeSelby/ruleprobe/issues/25)
- **State:** active

The issue carries the summary, discussion and acceptance evidence; this file carries the design.

This work item was authored as part of the repository's committed BMad planning system.
<!-- bmad-sync:end -->

## Question

What is each shipped detector's precision on real hits, as opposed to its agreement with the
synthetic corpus? The release notes for 0.2.0 (story 6.2) wait on it, so the release can say what
corpus agreement does not.

The maintainer confirmed this spike on 2026-09-23. It runs before the 0.2.0 release notes
(story 6.2).

## Experiment

- Run `ruleprobe explain` over one developer's own transcripts.
- Hand-sample 50 to 100 hits per shipped detector and judge each right or wrong.
- Record precision per detector and the sample size, labelled as field precision on one developer's
  transcripts, not as field accuracy.
- Put each false positive through `ruleprobe label` into a corpus, and list the resulting negatives
  by detector.
- A detector with fewer than 50 hits available is reported with its actual count, not padded.

## Exit criterion

- Every shipped detector has a recorded precision and sample size, with at least 50 sampled hits or
  its full available count.
- `ruleprobe corpus --floor 0.9` still passes after the new negatives are added.
- [ASSUMPTION: the corpus sets no precision threshold per detector for this spike; the result is a
  measurement for the release, not a pass or fail per detector]

## Result

Not yet run.

## Decision

Confirmed by the maintainer on 2026-09-23. Open: the measured figures. The result feeds the
0.2.0 release text (story 6.2) and adds field negatives toward SM-8 (at least ten from real false
positives). Published figures carry numbers and synthetic stand-ins only, no transcript content.

## Dev notes

- Binds FR-26 (one command turns a false positive into a labelled negative), SM-8 (field validity
  grows), NFR-6 (corpus floor 0.9 in CI), and AD-6 (the labelled corpus is the validity contract).
- Depends on story 3.5, RP-S017 and RP-S018; sequenced before 6.2.
- Files: this story file; corpus additions from RP-S018.
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3]
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#SM-8]

## Change log

- 2026-09-23: written from the planning corpus before implementation.
- 2026-09-23: confirmed by the maintainer; runs before the 0.2.0 release notes.
