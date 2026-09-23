---
title: "Validation review: ruleprobe product brief 2026-09-23"
reviewed: brief.md, addendum.md, .memlog.md
created: 2026-09-23
---

# Validation review: ruleprobe product brief

```json
{
  "status": "complete",
  "intent": "validate",
  "offer_to_update": true,
  "findings": {"high": 2, "medium": 4, "low": 9}
}
```

Checked against the ruleprobe README and code at `984c830`, the research artifact under
`_bmad-output/planning-artifacts/research/`, the agent-harness public planning corpus on its `main`
branch, the shared maintainer decisions of 2026-09-23, and the repository on GitHub.

## High

1. **Maintainer decision 4 is re-decided.** (frontmatter `open_questions` line 17; addendum
   "The contract surface agent-harness depends on", lines 53 and 54.) Decision 4 says the 0.2 public
   API *includes every name agent-harness actually imports today*. The open question asks which of
   those names become public API "and which get a deprecation path instead". The addendum says the
   work "either declares each one or gives it a deprecation path". Both reopen a closed decision.
   **Fix:** drop the deprecation alternative. Rewrite the open question as "re-derive the exact import
   list from the harness source before the API is fixed".
2. **A differentiator depends on an unverified guess about a named competitor.** (What makes this
   different, line 83; addendum line 23.) The `[ASSUMPTION]` says claude-md-doctor has a model write
   its matchers on every run, so two runs may differ. Research [1] says only that it "replays
   model-authored regex matchers deterministically", and that their results are "sample-verified
   before they count". It says nothing about per-run authoring, and its wording points the other way.
   A published brief should not make an unverified reproducibility claim against a named project.
   **Fix:** verify the claim from the claude-md-doctor repository, or delete the sentence and its
   copy in the addendum.

## Medium

3. **Success criteria miss the operative clause of three 0.2 items.** (Success criteria, lines
   115 to 119, against The solution, items 1, 3 and 4.) No criterion tests that the report gives an
   opportunity count and a followed count. None tests that the third reader makes runtime-neutral
   true, for example its sessions scored in the corpus at the 0.9 floor. None tests the explain path
   per hit. The schema version and the fold map have nothing beyond "zero agent-harness breakages".
   **Fix:** add one testable consequence for each item.
4. **Two counter-criteria cannot be tested.** (Lines 125 and 127.) "Too few opportunities to mean
   anything" has no threshold. "Bind loosely and fire on nothing a person would call that rule" has
   no instrument. The report's existing `min_sessions=20` is a precedent (README, public API).
   **Fix:** set a minimum opportunity count. Require every catalog detector to carry `examples:` and
   to pass the 0.9 floor.
5. **The addendum misstates FR-67's status in the harness PRD.** (Addendum line 62, "with its
   milestone disputed".) The public PRD says "planned (unscheduled)", with an `[ASSUMPTION]` about the
   v0.15.0 loop work. It does not say "disputed". Memlog line 25 already removed a sentence like this
   one because its source was the unpublished evidence pack.
   **Fix:** write "planned (unscheduled) there".
6. **Several claims about what exists have no status label.** (Line 29 "nothing sent off the
   machine"; gap bullets on lines 57 to 59; line 82 "It reads two runtimes"; lines 98 and 99; addendum
   lines 25 to 29.) The shared style rule requires a label on every claim about what exists.
   **Fix:** add `implemented (0.1.0)` or the right label to each.

## Low

7. **The literature claim is stated more strongly than its sources support.** (Lines 42 to 44.)
   The research rates refs 21 and 23 to 25 "medium, unverified, one lab each", and verified only 7 of
   its 28 claims. **Fix:** write "several single-lab preprints report".
8. **The citation of ref 22 leaves out its limits.** (Line 45.) The brief drops "after correction"
   and "single preprint", and omits the per-function decline behind research recommendation 4.
   **Fix:** add all three.
9. **The Codex-gap method is misdescribed.** (Line 82, "one search pass (ref 9)".) The research
   says "one import and one targeted search", and rates ref 9 low. **Fix:** match the research wording.
10. **"Largest absorption path" is not in the research.** (Line 105.) The research rates the
    /insights evidence medium and sources it from secondary blogs only. **Fix:** write "a first-party
    absorption path, from secondary sources".
11. **"Choose it ... if you want a diagnosis and a fix" is unsupported.** (Line 103.) Ref 1 shows a
    per-rule backtest. It does not show fixes. **Fix:** delete "and a fix".
12. **The contract-surface list miscounts.** (Addendum lines 48 to 50.) `Registry` and `run` are
    already among the README's declared names, so "imports more" overstates. Also, the root
    `__all__` exports about 31 names, so "declared" is ambiguous. **Fix:** list only the undeclared
    names, and say whether the README or `__all__` is the declaration.
13. **A load-bearing reference is already stale.** (Line 86.) The research's staleness map lists
    ref 26 as already stale. **Fix:** note the re-check beside the citation.
14. **Two success criteria name no instrument.** ("Outside use" and "Built on", lines 116 and 117.)
    **Fix:** name the evidence: an issue or PR author outside the project, and GitHub dependents or a
    code search.
15. **The polish step was not the configured one.** (Memlog line 27.) `doc_standards` ran as a
    self-review, not as the `bmad-review` structure and prose lenses. **Fix:** run the lenses before
    the status leaves `draft`.

## What could not be evaluated

- The claude-md-doctor and RuleReceipt repositories and the other cited URLs were not re-fetched.
  Findings 2 and 11 rely on the research text alone.
- The five-tester bar and the 2027-03-23 window are tagged `[ASSUMPTION]` and remain the
  maintainer's call. This review does not judge whether they are the right targets.
