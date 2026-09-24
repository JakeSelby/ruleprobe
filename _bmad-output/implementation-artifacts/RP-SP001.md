---
bmad_id: "RP-SP001"
type: "spike"
title: "spike(report): time the sixty-second path on a reference volume"
lifecycle: "completed"
provenance: "authored"
github_issue: 50
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/50"
parent_bmad_id: "RP-E005"
parent_github_issue: 24
updated: "2026-09-24"
---

# RP-SP001 — spike(report): time the sixty-second path on a reference volume

<!-- bmad-sync:begin -->
- **GitHub issue:** [#50](https://github.com/JakeSelby/ruleprobe/issues/50)
- **Primary parent:** [RP-E005](https://github.com/JakeSelby/ruleprobe/issues/24)
- **State:** completed

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

**Within 60 s.** Every run on the reference volume finished in under 1.5 s; the worst, 1.48 s, was
on the Python 3.9 floor. A denser variant of the same size finished in under 3 s. Both are more than
twenty times inside the bound.

- **Build:** first run at `9ca5651`, which carries the catalog (RP-S016), section-level binding
  (RP-S015), the subagent-session reader (#86) and the Gemini reader. The branch was then rebased
  onto `5464b32`, which adds #87's copied-session pre-scan, and every series below the first table
  ran on that reader.
- **Machine:** Apple M5 Pro (`sysctl -n machdep.cpu.brand_string`), 15 cores, 24 GiB
  (`hw.memsize` 25769803776), macOS 26.5, internal SSD. Python 3.14.5; the floor run on 3.9.25.
- **Command:** from the repository root,
  `python3 -m ruleprobe report --rules tests/fixtures/catalog/team --since 30 --root <volume>`, and
  the same with `--json`. The rule file binds seven catalog entries by section, and the report
  measured all seven.
- **Timing:** wall-clock by `/usr/bin/time -p`, with each run in a new process and exit 0 every
  time. A cold run started with an empty bytecode cache (`PYTHONPYCACHEPREFIX` set to a new temporary
  directory), and a warm run reused one. Dropping the file cache needs root, which the run did not
  have, so "cold" means a cold interpreter over a volume the OS had just written.

**First series, at `9ca5651`,** on a volume the generator wrote before review (seed 50,
`--anchor 2026-09-24`): 500 transcripts, 75 of them subagent files, 206.2 MB and 74,131 lines.
`--since 30` kept 429 sessions holding 60,490 events. The dense variant came from the same generator
with its tool output patched to short outputs during the session: 212 MB and 276,628 lines.

| Series | Runs (s) | Worst (s) |
| --- | --- | --- |
| Text, cold | 1.07, 0.96, 0.95 | 1.07 |
| Text, warm | 0.95, 0.86, 0.85 | 0.95 |
| `--json`, cold | 0.95, 1.02, 0.96 | 1.02 |
| `--json`, warm | 0.88, 0.86, 0.90 | 0.90 |
| Python 3.9.25, text, cold | 1.48, 1.09, 1.11 | 1.48 |
| Dense variant, text, cold | 2.87, 2.68, 2.62 | 2.87 |
| Dense variant, text, warm | 2.52, 2.57, 2.52 | 2.57 |
| Dense variant, `--json`, warm | 2.52, 2.56, 2.54 | 2.56 |

The first cold text figure was taken by `perf_counter` around the command, because its
`/usr/bin/time` output had not yet been set up. Every other figure is `/usr/bin/time`'s `real`. The
text and `--json` outputs were byte-identical across runs, and the 3.9 text output matched 3.14's.

**Re-run after #87,** at `5464b32`'s reader, on the same pre-review volume, cold as above: text
1.46, 1.09 and 1.03 s, worst 1.46 s; `--json` 1.06, 1.02 and 1.14 s, worst 1.14 s. The pre-scan
leaves the verdict unchanged.

**Final generator, at `5464b32`,** which is the script this branch ships. Its volumes differ from the
pre-review ones: timestamps are capped at the anchor day, and long outputs are capped to the file's
remaining budget. The reference volume has 500 transcripts, 202.3 MB and 91,243 lines, and
`--since 30` kept 433 sessions holding 75,132 events. The `--short-outputs` dense variant has 202.3
MB and 276,853 lines, and kept 432 sessions holding 225,938 events.

| Series | Runs (s) | Worst (s) |
| --- | --- | --- |
| Text, cold | 1.24, 1.19, 1.21 | 1.24 |
| `--json`, cold | 1.15, 1.15, 1.13 | 1.15 |
| Text, warm | 1.10, 1.06, 1.06 | 1.10 |
| Python 3.9.25, text, cold | 1.35, 1.34, 1.36 | 1.36 |
| Dense, text, cold | 2.79, 2.65, 2.71 | 2.79 |
| Dense, `--json`, cold | 2.69, 2.69, 2.70 | 2.70 |
| Dense, text, warm | 2.61, 2.58, 2.60 | 2.61 |

- **Sensitivity:** most of the reference volume's bytes are in a few long tool outputs, which parse
  cheaply. The dense variant has about three times as many lines in the same bytes. Its time grew
  with lines rather than bytes, and it stayed under 3 s.
- **Evidence:** the raw `/usr/bin/time` output, the report outputs and the volumes lived in a session
  scratch folder and were not kept; the figures above are transcribed from them. To regenerate the
  final volumes from the repository root, run
  `python3 scripts/reference_volume.py <volume> --anchor 2026-09-24` and
  `python3 scripts/reference_volume.py <dense> --anchor 2026-09-24 --short-outputs`. Seed 50 is the
  default. The bytes are the same on one Python version (3.14.5 here), and `--since 30` counts from
  the day of the run. To time a run, use
  `PYTHONPYCACHEPREFIX=$(mktemp -d) /usr/bin/time -p python3 -m ruleprobe report --rules
  tests/fixtures/catalog/team --since 30 --root <volume>`.

## Decision

**Within 60 s: NFR-9 holds as written.** No follow-up for the slow path is filed. Whether to publish
the machine the timing came from is a publishing question for the maintainer (NFR-9).

## Dev notes

- Binds NFR-9 Time to first answer and SM-1 Sixty-second test.
- `report` has no default window; `--since` defaults to none (`ruleprobe/cli.py`), so the command names
  the flag.
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#5 NFR-9]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.6]

## Dev agent record

- **status:** review
- **baseline_commit:** `5464b32` (first cut from `9ca5651`, then rebased)
- **Model:** Claude Opus 5.5, as the `builder` role.
- **Completion notes:** `scripts/reference_volume.py` writes the volume in Claude Code's native
  JSONL, deterministic from its seed and `--anchor`: Bash calls, reads, edits, writes and searches,
  streamed responses repeating a message id, compaction boundaries, a share of subagent files under
  `<session>/subagents/`, and about 85% of parent sessions inside the last 29 days, with no timestamp
  past the anchor day. `--short-outputs` writes the dense variant. `main` refuses a bad
  `--subagent-share`, a non-empty directory and an existing file with exit 2. Every word comes
  from a fixed list. The volumes were written under the session scratchpad, outside the repository,
  and never staged.
- **Files:** `scripts/reference_volume.py`, `tests/test_reference_volume.py`, `MANIFEST.in` (the
  new test imports `scripts/`, so the sdist leaves it out like the other four), `AGENTS.md` (the
  layout note's count and its `scripts/` bullet), this file.

## Change log

- 2026-09-23: written from the planning corpus before implementation.
- 2026-09-24: run; the result, the decision and the dev agent record filled: within 60 s.
- 2026-09-24: after review, rebased onto `5464b32`; a cold re-run after #87, the shipped
  `--short-outputs` dense variant, final-generator timings and regeneration commands recorded.
