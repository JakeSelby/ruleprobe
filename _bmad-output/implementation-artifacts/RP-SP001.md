---
bmad_id: "RP-SP001"
type: "spike"
title: "spike(report): time the sixty-second path on a reference volume"
lifecycle: "active"
provenance: "authored"
github_issue: 50
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/50"
parent_bmad_id: "RP-E005"
parent_github_issue: 24
updated: "2026-09-23"
---

# RP-SP001 — spike(report): time the sixty-second path on a reference volume

<!-- bmad-sync:begin -->
- **GitHub issue:** [#50](https://github.com/JakeSelby/ruleprobe/issues/50)
- **Primary parent:** [RP-E005](https://github.com/JakeSelby/ruleprobe/issues/24)
- **State:** active

The issue carries the summary, discussion and acceptance evidence; this file carries the design.

This work item was authored as part of the repository's committed BMad planning system.
<!-- bmad-sync:end -->

## Question

Does `ruleprobe report --rules --since 30` finish within sixty seconds over the reference volume of
500 sessions and 200 MB of transcripts? NFR-9 states this bound, but no timing has been measured and
the bound is derived from SM-1, not from a benchmark. The answer decides whether NFR-9 holds as
written or needs a follow-up for performance before SM-1's cohort runs.

## Experiment

- Build a synthetic reference volume: 500 sessions, about 200 MB, in a native runtime's transcript
  format, with no real transcript content (AD-6). A generator script under `scripts/` if needed.
  [ASSUMPTION: from epics.md Story 3.6]
- Run on a build with the catalog (RP-S016) and section-level binding (RP-S015) in place, over a
  sectioned rule file.
- Time `ruleprobe report --rules <dir> --since 30 --root <volume>` wall-clock, cold and warm.
  [ASSUMPTION: several runs and the worst taken; the corpus names one timing]
- Record the exact command and the machine class.

## Exit criterion

Within 60 s wall-clock on the reference volume: "within 60 s". Over 60 s: "not". A "not" files a
follow-up issue rather than fixing inside the spike.

## Result

Not yet run.

## Decision

Pending the result. "Within 60 s" confirms NFR-9 as written. "Not" opens a follow-up for the slow path.
Whether to publish the machine the timing came from is a publishing question for the maintainer
(NFR-9).

## Dev notes

- Binds NFR-9 Time to first answer and SM-1 Sixty-second test.
- `report` has no default window; `--since` defaults to none (`ruleprobe/cli.py`), so the command names
  the flag.
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#5 NFR-9]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.6]

## Change log

- 2026-09-23: written from the planning corpus before implementation.
