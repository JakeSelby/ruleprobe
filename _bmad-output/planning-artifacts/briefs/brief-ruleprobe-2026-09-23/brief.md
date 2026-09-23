---
title: "Product Brief: ruleprobe"
status: final
created: 2026-09-23
updated: 2026-09-23
issue: 12
bmad_id: RP-S003
inputs:
  - _bmad-output/planning-artifacts/research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md
  - README.md
  - AGENTS.md
  - https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/product-briefs/brief-agent-harness-2026-09-23/brief.md
open_questions:
  - "Third reader for 0.2: Cursor or Gemini CLI?"
  - "Section-level binding: split a rule file on headings, on list items, or on both?"
  - "How many rule shapes must the shipped catalog hold before the sixty-second test can pass?"
  - "Re-derive the exact import list from the harness source before the 0.2 public API is fixed."
  - "Does the separate, opt-in command that drafts a detector from prose belong in 0.2, a later minor, or nowhere?"
  - "Should the report also break compliance down by position in the session, as the research's recommendation 4 suggests?"
  - "Are the success targets and the 2027-03-23 window the right ones?"
  - "Is 20 opportunities the right minimum before a compliance figure is shown?"
---

# Product Brief: ruleprobe

## Executive summary

Developers write rules for their coding agents in `CLAUDE.md`, `AGENTS.md` and house-style
files. Nobody knows whether those rules change what the agent does. ruleprobe answers that from
the transcripts the agent already wrote, with deterministic detectors, no model in the loop, and
nothing sent off the machine (implemented, 0.1.0). Release 0.1.0 is on PyPI and reads Claude Code
and Codex (implemented, 0.1.0).

ruleprobe is **the measurement engine for agent rules, not a doctor.** It counts and reports.
It does not diagnose causes, prescribe fixes or block the agent. It stays a narrow library and
CLI that other tools build on, agent-harness first among them.

0.2 does three things (planned, v0.2.0). It reports compliance per opportunity, not only hits
per session. It versions the contract that downstream tools depend on. It closes the
sixty-second gap for a stranger's own rules without a model.

## The problem

The whole field is guessing at one question: do written rules change agent behaviour? Several
single-lab preprints report low compliance when it is measured from what the agent did rather
than from what the file says ([research](../../research/competitive-rule-measurement-neighbours-of-ruleprobe-2026-09-23/research.md), refs 21, 23 (due for re-check), 24 and 25; rated medium and unverified there).
A controlled study, a single preprint, found no detectable effect of file size, placement or
design after correction, and found compliance falling with each additional function the agent
writes (ref 22). That per-function decline is what the research's recommendation 4 rests on.
Rules still get written, kept and argued over on intuition.

The cost is the rule nobody checks. It sits in the always-loaded prefix every session, and
nobody learns whether it fired, was ignored, or guards against something that never happens.

## What 0.1 does not do for a stranger's own rules

This is the gap 0.2 exists to close.

- The six shipped detectors are generic. They say nothing about the reader's own rules (implemented, 0.1.0; README, "What it actually covers").
- Binding is per file. A `CLAUDE.md` with twelve rules is one rule in the coverage block, and it is unmeasured until someone writes a detector for it (implemented, 0.1.0).
- Measuring a rule of your own means writing a detector, as data or as Python (implemented, 0.1.0). The README's worked example shows it takes no Python, but a stranger has to learn the detector format before they get a first answer about their own rules.
- The report says how often a shape happened, not how often the rule was followed when it applied (implemented, 0.1.0). There is no opportunity count yet (planned, v0.2.0).
- The validity corpus is six synthetic sessions (implemented, 0.1.0). A 1.00 there is not field accuracy, and a user's own detector is scored only if it carries `examples:`.

A stranger who runs `uvx ruleprobe report` today learns about six generic habits and gets one
unmeasured line for their own rule file.

## The solution

ruleprobe reads transcripts, turns them into one event schema, runs detectors over it and reports
per rule. The same transcript always gives the same report. For 0.2 (planned, v0.2.0):

1. **Compliance per opportunity.** For a rule that asks for something to be done, the report says how many opportunities there were and how many were followed, beside hits per session.
2. **A versioned contract.** A schema version on detector entries and report rows, a fold map for renamed detectors, and a declared public API that includes every name agent-harness imports today. This is the 0.2 breaking change, taken once.
3. **A third reader**, Cursor or Gemini CLI, so runtime-neutral is a fact and not a claim resting on two runtimes.
4. **Field validity.** An explain path for every hit, and one command that turns a false positive into a labelled negative in the corpus.
5. **The sixty-second gap, closed without a model.** Section-level binding turns one instruction file into many rules. A shipped catalog of common rule shapes gives a stranger measured rules they did not write detectors for.

## What makes this different

Credit first. **claude-md-doctor** and **RuleReceipt** already measure rule compliance from
transcripts and report per rule (research refs 1, 2). ruleprobe is not first, and does not say so.

What ruleprobe can claim, bounded to the research:

- **It reads two runtimes** (implemented, 0.1.0). Both neighbours read Claude Code only (refs 1, 2). No tool was found measuring rule compliance from Codex rollouts as of 2026-09-23. That is absence of evidence from one import and one targeted search, so it is thin (ref 9, rated low), and the claim carries its date.
- **Its detectors are committed data**, scored against a labelled corpus with a CI floor of 0.9 (implemented, 0.1.0). The same detectors give the same answer next month. claude-md-doctor's skill has the model write the rulebook at every checkup (step 4b) and fix a matcher when a sampled fire is a false positive (step 4d). Its engine then replays that model-authored rulebook deterministically ([SKILL.md](https://github.com/agent-clinic/claude-md-doctor/blob/main/skills/claude-md-doctor/SKILL.md), [`scripts/backtest.py`](https://github.com/agent-clinic/claude-md-doctor/blob/main/skills/claude-md-doctor/scripts/backtest.py), verified 2026-09-23). Nothing in the skill holds the matchers fixed between checkups.
- **It is a library first.** Other tools import it, not just run it (implemented, 0.1.0).

Deterministic-first is not the pitch. The literature recommends it (refs 26, 27), and the
research's staleness map already lists ref 26 as stale, due a re-check since 2026-07-16. Both
neighbours already do it (refs 1, 2). It is the price of being credible.

The honest risk: platforms already hold the data. Langfuse and LangSmith ingest Claude Code and
Codex transcripts (refs 17, 19), and Anthropic's /insights reads local transcripts to suggest rules
(ref 15). None was found scoring existing rules. That finding is due for a re-check by 2026-12-23.

## Who this serves

- **First:** a developer with a `CLAUDE.md` or `AGENTS.md` and a few weeks of transcripts, who wants to know which rules do anything. They will not write Python. They need a first answer in a minute and a number they can trust.
- **Second:** tools and researchers that build on the library. agent-harness binds its own rules to ruleprobe detectors; its spine AD-13 says it never forks detector logic ([agent-harness planning corpus](https://github.com/JakeSelby/agent-harness/tree/main/_bmad-output/planning-artifacts)). Researchers get reproducible counts they can publish beside their method.

ruleprobe owes the harness a stable contract and nothing else. A ruleprobe release means a harness
version bump (agent-harness PRD 2026-09-23, FR-21). The harness vendors a pinned 0.1.0 wheel today
at `lib/vendor/` in its repository, implemented on its side.

## Alternatives, and their honest case

- **claude-md-doctor** (MIT, local). It decomposes a `CLAUDE.md` into per-rule matchers, replays them, and reports followed, ignored and never-used rules (ref 1). For a stranger's own rules it does today what ruleprobe cannot. Choose it on Claude Code if you want a diagnosis.
- **RuleReceipt** (source-available, bars competing commercial offerings). Deterministic checks over git commands and file operations, with judgment rules left UNCLEAR unless you opt into an LLM grader (ref 2). Strong where your rules are about git and files.
- **Anthropic /insights.** First-party and zero-install; suggests `CLAUDE.md` additions from 30 days of transcripts (refs 15, 16). It answers what to write, not whether what you wrote works. It is a first-party absorption path, from secondary sources.
- **Codex Code Review.** Applies `AGENTS.md` rules to pull-request diffs (ref 31). It judges the output at merge, not the session. For many teams that is where a rule matters.
- **Do nothing.** Keep writing rules on intuition. Free, and what most developers do.

Detail is in the [addendum](addendum.md).

## Success criteria

Baseline on 2026-09-23: 0 stars, no known outside user. Targets are for 2027-03-23. [ASSUMPTION: the window and every number below are inferred for review, not set by the maintainer.]

- **Sixty-second test.** Four of five first-time testers with an unedited `CLAUDE.md` or `AGENTS.md` see at least one of their own rules measured within a minute, with no detector written. The bar mirrors the harness's first-minute criterion ([agent-harness brief](https://github.com/JakeSelby/agent-harness/blob/main/_bmad-output/planning-artifacts/product-briefs/brief-agent-harness-2026-09-23/brief.md)).
- **Outside use.** Five people outside the project report a run, file an issue or open a PR. Evidence: issues and PRs on `JakeSelby/ruleprobe` whose authors are outside the project.
- **Built on.** One consumer besides agent-harness imports the library. Evidence: GitHub's dependents graph for the repository, or a public code search for `import ruleprobe`.
- **Compliance per opportunity shown.** For every rule whose detector defines an opportunity, `ruleprobe report` and `report_data` give an opportunity count and a followed count beside hits per session.
- **Contract held.** Zero agent-harness breakages across 0.2.x; the harness pins 0.2 with no fork. Every detector entry and report row carries a schema version, and a test folds a row stored under a renamed detector id onto its new id through the fold map.
- **Runtime-neutral is a fact.** The third reader's sessions are in the validity corpus, and the detectors that apply to them score at or above the 0.9 floor in CI.
- **Every hit explains itself.** The explain path returns, for any hit in a report, the transcript event it came from and the detector that matched it.
- **Field validity grows.** At least ten corpus negatives that came from real false positives, through the one-command route. The floor stays at 0.9.

**Counter-criteria**, which mean winning the wrong way:

- A model call appears anywhere in `ruleprobe report`, or a runtime dependency appears.
- The same transcript gives a different report.
- A catalog detector ships without `examples:`, or scores below the 0.9 floor. Loose binding that raises measured-rule share on rules nobody would recognise shows up here.
- Stars or downloads rise with no outside run reported. Attention is recorded, not targeted.
- A compliance figure is shown over fewer than 20 opportunities. [ASSUMPTION: 20 mirrors the report's existing `min_sessions=20`; the maintainer sets the number.]

## Scope

**In for 0.2 (planned, v0.2.0):** the five items under The solution.

**Out, deliberately:** prescriptions and fixes, HTML report cards, cause triage, hooks or guards
that block an agent, anything hosted, and any model call inside `ruleprobe report`.

**Proposed only:** a separate, opt-in command that drafts a detector from a rule's prose and emits
data a person reviews and commits. It is not a commitment and never runs inside `report`.

**Risks carried** (maintainer notes, unpublished, 2026-09-21, post-build position): a second
release cadence beside the harness's; the measurement contract drifting silently until 0.2 versions it;
and a position resting on a handful of detectors while opted-out rules stay dark.

## Vision

ruleprobe becomes the instrument people cite when they claim a rule works or does not. A developer
runs it over any major agent's transcripts and gets a reproducible, per-rule compliance figure they
can defend. Tools like agent-harness build governance on top; researchers publish with it. It
stays narrow. It measures, and others decide what to do about it.
