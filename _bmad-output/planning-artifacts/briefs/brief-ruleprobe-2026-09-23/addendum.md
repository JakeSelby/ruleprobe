---
title: "Product Brief addendum: ruleprobe"
created: 2026-09-23
updated: 2026-09-23
---

# Addendum: ruleprobe product brief

Depth that belongs to the PRD and architecture runs, kept out of the brief to hold it near two
pages. Reference numbers point at the source appendix of the
[research artifact](../../research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md).

## How the research recommendations land

1. **Bound the novelty claim.** Taken. The brief credits claude-md-doctor and RuleReceipt and dates the two-runtime claim.
2. **Ship a Codex rollout reader in 0.2.** Already met: ruleprobe 0.1.0 reads Codex rollouts (`ruleprobe/readers/codex.py`, implemented, 0.1.0), as the artifact's project note records. The 0.2 answer is a third reader, so the lead does not rest on a runtime the platforms already ingest (refs 17, 19).
3. **Deterministic verdicts, evidence quoted, model judgment separable.** Taken as a constraint. The explain path per hit is the evidence-quoting half. Any model path stays a separate opt-in command (proposed).
4. **Report compliance against in-session position.** Not taken for 0.2; left as an open question. Compliance per opportunity comes first.
5. **Name the alternatives.** Taken, below and in the brief.

## Alternatives in more detail

- **claude-md-doctor** (ref 1). Reads `CLAUDE.md` or `AGENTS.md` with Claude Code transcripts. Replays model-authored regex matchers deterministically and sample-verifies results before they count. Reports followed, ignored and never-used rules. Frames itself against /insights: it answers whether what you wrote is doing anything. What it has that ruleprobe lacks: rule decomposition from prose, an opportunity denominator, diagnosis. What ruleprobe has that it lacks: a second runtime, and detectors committed as data and scored against a labelled corpus. claude-md-doctor's matchers are authored by the model at each checkup and verified by sampling (its [SKILL.md](https://github.com/agent-clinic/claude-md-doctor/blob/main/skills/claude-md-doctor/SKILL.md) steps 4b and 4d, and the docstring of [`scripts/backtest.py`](https://github.com/agent-clinic/claude-md-doctor/blob/main/skills/claude-md-doctor/scripts/backtest.py), verified 2026-09-23). Nothing in the skill holds them fixed between checkups.
- **RuleReceipt** (refs 2, 3). TypeScript. Deterministic checks over git commands and file operations; judgment rules report UNCLEAR unless `--llm` grades them with the user's key. The plain check makes no network calls. Source-available, and the licence bars competing commercial offerings, so ruleprobe borrows nothing from it. Its author's parse of 559 public `CLAUDE.md` files argues most of their content is not rules, which bears on how section-level binding should treat prose that is not a rule.
- **Anthropic /insights** (refs 15, 16; implemented there as of 2026-09-23, secondary sources). Reads 30 days of local transcripts and suggests `CLAUDE.md` additions. No source shows it scoring existing rules; that is an absence claim.
- **Codex Code Review** (ref 31; implemented there as of 2026-09-23). Applies `AGENTS.md` rules to pull-request diffs. Judges the diff, not the session.
- **Platforms** (refs 13, 14, 17 to 20; implemented there as of 2026-09-23). Anthropic's OpenTelemetry export and analytics carry usage only. Langfuse and LangSmith ingest several runtimes' transcripts and ship no rule evaluator. Generic eval vendors offer custom scorers, not a packaged adherence evaluator.
- **Static tooling** (refs 10 to 12; implemented there as of 2026-09-23). agnix, ctxlint and rulesync lint or convert rule files. None measures behaviour. They are complements.
- **Spend analyzers** (refs 6 to 9; implemented there as of 2026-09-23). ccusage and similar read many runtimes for tokens and cost. The README's "Origins and neighbours" names one; none reports compliance.

## The 0.1 gap mapped to 0.2

| 0.1 gap for a stranger | 0.2 answer (planned, v0.2.0) |
| --- | --- |
| Shipped detectors are generic | Catalog of common rule shapes |
| One file is one rule | Section-level binding |
| Hits per session only | Compliance per opportunity |
| Six synthetic corpus sessions | Explain path; false positive to labelled negative |
| Contract unversioned | Schema version, fold map, declared public API |
| Two runtimes | Third reader |

The `absent` and `order` session matchers already express an opportunity for ordering rules
(implemented, 0.1.0). The report does not yet present them that way.
[ASSUMPTION: compliance per opportunity can start from those two shapes.]

## The contract surface agent-harness depends on

The declaration is the README's "public API" section, which names eight: `iter_sessions`, `run`,
`Registry`, `report`, `report_data`, `validity`, `load_bundle` and `compile_detector` (implemented,
0.1.0). The root `__all__` exports 33 names at `984c830`, but it is an export list, not a declared
contract. agent-harness also depends on names the README does not declare: the root `analyse` and
`counts` (both in `__all__`); names from `detectors.common`, `events`, `registry`, `shell`,
`declarative` and `validity`; `SECRET_PATTERNS`, which it reads out of the wheel; and the wheel
file name, which its own code names. The root `Registry` and `run` it imports are already declared. [ASSUMPTION: this list reflects the harness's main branch on
2026-09-23; the PRD run re-derives it from the harness source before the 0.2 public API is fixed.]
Any of those changing shape breaks the harness, so the 0.2 contract work declares each one
(maintainer decision 4, 2026-09-23).

## Harness requirements that touch ruleprobe

From the agent-harness PRD 2026-09-23, §4.4 ([planning corpus](https://github.com/JakeSelby/agent-harness/tree/main/_bmad-output/planning-artifacts)):
FR-19 (a detector or a reason for every rule), FR-20 (per-rule hit rate by repo and variant),
FR-21 (standalone instrument and vendored pinned wheel), FR-22 (corpus floor in CI; corpus agreement
is not field accuracy), FR-67 (detectors for a developer's own rules without code; proposing one from
prose is planned (unscheduled) there).
This brief keeps a drafting command a proposal on ruleprobe's side.
