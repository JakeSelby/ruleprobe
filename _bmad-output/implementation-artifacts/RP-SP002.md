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

Run 2026-09-24 over one developer's own transcripts (Claude Code and Codex, on one machine).
**Field precision is not field accuracy:** these are right-or-wrong verdicts on sampled hits, from
one developer's work, and they say nothing of what the detectors miss.

**Who judged.** The maintainer delegated the judgment on 2026-09-24. Each hit was judged by an
agent (Claude subagents) from the hit's redacted `ruleprobe explain` block, against the detector's
own stated claim; the session-level detectors (`compact`, `model-switch`) and
`testing/test-after-change`, whose blocks show no deciding event, were judged from a script's
evidence: the compaction event at the hit turn, the models either side of it, and the later command
the detector's own `then` matcher matched. `right` and `wrong` count; `unsure` is counted apart.
Samples are seeded (seed 53), at most 50 per detector, every hit when fewer; hits that repeated a
session and key were counted once.

**Two rounds.** The first sampled the six shipped detectors before two reader fixes this spike
found (below); the second, after them, sampled the catalog detectors bound through a rule file that
binds all seven shapes, and drew a new `whole-file-cat` sample now that subagent work is read.

| Detector | Hits available | Sampled (distinct) | Right | Wrong | Unsure | Precision |
| --- | --- | --- | --- | --- | --- | --- |
| `cache-hygiene/compact` | 38 (22 distinct) | 22 | 22 | 0 | 0 | 1.00 |
| `cache-hygiene/model-switch` | 98 (72 after the reader fixes) | 43 | 42 | 0 | 1 | 1.00 |
| `secrets/secret-in-write` | 40 (73 after) | 23 | 1 | 20 | 2 | 0.05 |
| `transcript-hygiene/whole-file-cat`, round 1 | 1,521 | 48 | 45 | 1 | 2 | 0.98 |
| `transcript-hygiene/whole-file-cat`, round 2 | 5,131 | 50 | 49 | 1 | 0 | 0.98 |
| `verification/no-verify` | 12 (6 distinct) | 6 | 1 | 5 | 0 | 0.17 before #88 |
| `transcript-hygiene/unfiltered-find` | 1 | 1 | 0 | 1 | 0 | 0.00 before #98 |
| `commits/non-conventional-subject` | 84 | 50 | 48 | 0 | 2 | 1.00 |
| `git-safety/force-push-default` | 3 | 3 | 3 | 0 | 0 | 1.00 |
| `package-manager/pip-install` | 18 | 18 | 18 | 0 | 0 | 1.00 |
| `testing/test-after-change` | 5,228 (of 10,118 opportunities) | 50 | 44 | 0 | 6 | 1.00 |
| `secrets/secret-file-add` | 0 | 0 | - | - | - | no hits |

Every detector has a recorded precision and sample size: at least 50 sampled hits, or every hit
there was.

**What the sample found, beyond the figures.**

- **Subagent work was never measured (#86, fixed).** Newer Claude Code marks every line of a
  subagent's own transcript as a sidechain line, and the reader skipped them: 5,002 of the 5,510
  sessions read were empty shells, so subagent tool calls went unmeasured and every share's
  denominator counted the shells.
- **Copied sessions counted twice (#87, fixed).** Project folders copied or renamed left the same
  session in several files; after #86, 2,307 of 5,524 sessions read were extra copies.
- **`no-verify` counted hooks turned on (#88).** Five of its six distinct hits were
  `git -c core.hooksPath=<tracked hooks dir> commit`, which runs every hook. With #88 the five
  labelled real negatives score as true negatives.
- **The shared parse split an escaped parenthesis (#98).** `find … \( -name … \) | head` parsed as
  three segments, the only `unfiltered-find` hit. With #98 its labelled real negative scores as a
  true negative.
- **`secret-in-write` fires on writing about secrets:** environment-variable names, pattern sources,
  placeholders and redaction code. Its redesign is a follow-up after 0.2.0 (maintainer, 2026-09-24),
  and the release notes carry the 0.05.
- **`whole-file-cat` counts a `cat` inside a `{ … }` group whose output is redirected** (both of its
  wrong hits). A follow-up; precision stays 0.98.

**Field negatives (SM-8).** Every false positive went through `ruleprobe label` into a local field
corpus kept off the repository, since it holds real transcript content: eight were written
(whole-file-cat 2, no-verify 5, unfiltered-find 1). All twenty `secret-in-write` false positives
were refused, as `label` is built to: redacting the written event removes exactly what the detector
matched, so the negative would pass trivially. A secret detector's field negatives need synthetic
stand-ins written by hand. Synthetic stand-ins from real false positives ship in the corpus with
#88 (a tracked hooks directory) and #98 (grouped `find` predicates); `ruleprobe corpus --floor 0.9`
passes with both. SM-8's ten is not yet reached.

**Evidence.** The sample sheets, verdicts and field corpus stay on the measuring machine, since they
hold redacted but real transcript text; the figures above carry numbers only.

## Decision

Confirmed by the maintainer on 2026-09-23; the judgment delegated to an agent on 2026-09-24.
Measured: see Result. Two follow-ups after 0.2.0: `secret-in-write`'s redesign and
`whole-file-cat`'s redirected group. The maintainer confirmed on 2026-09-24 that the 0.2.0
release text publishes the table above, labelled as agent-judged field precision on one
developer's transcripts. The result feeds the
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
- 2026-09-24: run, agent-judged under the maintainer's delegation; Result recorded with the four
  reader, detector and parse fixes it found (#86, #87, #88, #98).
