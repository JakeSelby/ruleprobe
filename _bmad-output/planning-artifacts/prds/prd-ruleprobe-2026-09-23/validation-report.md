# Validation Report - PRD: ruleprobe

- **PRD:** `_bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md` (with `addendum.md`, `.memlog.md`)
- **Rubric:** `.claude/skills/bmad-prd/assets/prd-validation-checklist.md`
- **Run at:** 2026-09-23 (headless, validate intent; HTML report skipped by instruction)
- **Checked against:** ruleprobe code at `ae84ac3` (no change under `ruleprobe/`, `tests/`, `README.md` or `pyproject.toml` since the `984c830` the memlog cites); agent-harness `main` at `1307113` (two commits after the `991b13e` the PRD cites; the four files read are unchanged between them); the brief, its addendum, and the research artifact.
- **Grade:** Fair

## Overall verdict

The PRD reads as a real capability spec. The thesis is clear, and the nine maintainer decisions are carried through without being re-decided. The bounded claim matches the research, and nearly every 0.1.0 status label matches the code. The risk sits in the 0.2 requirements that downstream epics will build on. FR-29 is labelled planned when the fold on read already exists. FR-30's declared call shapes leave out the detector-function protocol that most harness detectors depend on, so a contract test built from it would pass while the harness broke. FR-25 cannot hold for reports over stored rows. FR-16's consequences only test what the catalog must not do.

## Dimension verdicts

- Decision-readiness - strong
- Substance over theater - adequate
- Strategic coherence - strong
- Done-ness clarity - thin
- Scope honesty - adequate
- Downstream usability - adequate
- Shape fit - strong

## Findings by severity

### Critical (0)

### High (4)

**[Status labels]** - FR-29 is labelled planned, but the fold map already exists (§4.8 FR-29, §8)
`Registry(detectors=None, renamed=None)`, `Registry.rename(old_id, new_id)` (`ruleprobe/registry.py:70,101`) and `report.folded_rules` (`ruleprobe/report.py:55`) fold renamed ids on every read in 0.1.0. The harness passes its own `RENAMED` map today (`policy/hooks/rule-detectors.py`). The FR's first consequence already passes.
Fix: label FR-29 "partial (0.1.0 fold on read)". Scope the 0.2 work to the rename-without-entry check and to the fold map's place in the versioned contract. State that each consumer supplies its own fold map through `Registry`.

**[Done-ness / FR-30]** - The declared call shapes leave out surface the harness depends on (§4.8 FR-30, third and fourth consequences)
The harness uses the following, and FR-30 declares none of it:
- `fn(events, ctx)` for every detector function, reading `ctx.bash` (a list of `Parsed`, with `.event`) and `ctx.finals` (`ruleprobe/shell.py:444,485`). About ten harness detectors depend on this.
- `hit(event, tool_use_id=False)`.
- `git_calls(parsed, subcommands)` yielding 3-tuples.
- `Registry(<list of detectors>)`.
- Reads of `.id`, `.rule`, `.event`, `.fn` and `.gate` on `common.DETECTORS` items, and `bin/harness` reads `.rule`.
- `ruleprobe.__file__` used to locate `corpus/`.

The addendum lists the attribute reads and the list constructor, but the FR does not. As written, the contract test "fails on any removal or signature change" only for the shapes that are declared.
Fix: add each item to the call-shape consequence, including `Context` and `Parsed` as declared types. Re-derive the list from harness `main` immediately before the 0.2.0 tag.

**[Done-ness / FR-25]** - The explain path cannot cover "every hit in a report" (§4.7 FR-25, SM-7)
A row stores only `{detector_id: hit_count}` (`ruleprobe/report.py`, `measure`). The README says a report can be taken over rows stored months ago. Those rows keep no session, turn or tool-use id, so the first consequence and SM-7's 100% cannot hold for them.
Fix: scope FR-25 and SM-7 to reports run over transcripts. Alternatively, add an open question on whether FR-28's row schema carries hit keys. That is a maintainer call.

**[Done-ness / FR-16]** - The catalog has no positive, testable consequence (§4.5 FR-16)
All four consequences are guards: examples and the floor, the label, "cannot bind with confidence", and no model. Nothing tests that a known rule shape actually binds. "With confidence" has no bound. SM-1 rests on this FR.
Fix: add "a fixture rule section of shape X binds catalog detector X and is reported as measured". Define what counts as a confident binding, for example an anchored text pattern per catalog entry. Otherwise tie it to open question Q3.

### Medium (8)

**[Done-ness / FR-21]** - The consequences test that the fields exist, not that the numbers are right, and "followed" is undefined in the PRD (§4.6 FR-21, §3)
Fix: add "a fixture with N opportunities and M followed yields `opportunities: N, followed: M`". Put the definition of "followed" in the Glossary, not only in the addendum.

**[Scope honesty]** - The `promote?` note is an implemented quasi-prescription held "unchanged" (§4.6 FR-17, §1.1, §7)
The README says `promote?` means "either the rule is worth stating more loudly or the rule is wrong". The PRD says ruleprobe "prescribes nothing".
Fix: do not re-decide it here. Add an open question for the maintainer: keep it as a count flag with neutral wording, reword it, or drop it in the 0.2 break.

**[Done-ness / FR-15]** - "A section that is not a rule is not counted as unmeasured" cannot be tested without a definition (§4.5 FR-15)
Fix: define "not a rule" in terms of the split unit from Q2, and give a fixture.

**[Done-ness / FR-25, FR-26]** - Secrets reach the terminal and the corpus (§4.7)
The explain path "quotes the event's matched field". For `secret-in-write`, that field is the secret. FR-26 writes the event into a corpus that UJ-1 then opens a pull request with. The `[ASSUMPTION]` that the user reviews it is not a control.
Fix: add a consequence that both commands redact with `SECRET_PATTERNS` before printing or writing.

**[Publishing question]** - A figure measured on the maintainer's machine appears in a public document (§9 baseline)
"1,913 sessions measured in 14 days on one machine" is sourced to an unpublished maintainer measurement of the maintainer's own transcripts.
Fix: the maintainer decides whether to publish it, round it, or drop it. It is not needed for any SM target.

**[Done-ness / NFR-9]** - "On a developer laptop" is an adjective, not a bound, and there is no timing (§5 NFR-9)
Fix: name the reference volume, for example sessions or MB over 30 days, and state that the default window applies. Once a timing exists, treat the machine it came from as a publishing question.

**[Downstream usability]** - "Event kind" means two things (§3, FR-3, FR-6)
The Glossary gives five transcript kinds (`assistant_text`, `tool_use`, `tool_result`, `user_prompt`, `compact`). FR-6's "unknown event kind" means the registry's `EVENT_KINDS` (`bash`, `write`, `agent-brief`, `assistant-final`, `session`, `tool_use`, `assistant_text`; `ruleprobe/registry.py:18`).
Fix: add a Glossary term for the detector's input shape.

**[Done-ness / FR-29]** - "A rename that ships without a fold map entry fails the test suite" has no mechanism (§4.8)
Fix: add "a committed list of shipped detector ids; an id removed without a fold entry fails".

### Low (6)

**[Status labels]** - FR-14's `[ASSUMPTION]` is a checkable fact (§4.5 FR-14)
`ruleprobe/rules.py:74` prints "rules: %d measured, %d dark, %d unmeasured" and gives no share.
Fix: state it as fact and remove it from §12.

**[FR-30]** - The `SECRET_PATTERNS` dependency is stated more loosely than the harness reads it (§4.8)
`decisions.py` matches only a plain module-level `ast.Assign`. An annotated assignment would break it silently.
Fix: say "a plain module-level assignment of a literal list".

**[FR-30]** - The re-derivation is pinned to `991b13e`, and `main` has moved (§4.8)
The four files are unchanged at `1307113`.
Fix: add a consequence that the list is re-derived at release time.

**[Substance]** - The figures in UJ-1 and UJ-2 (31 and 12; 1.00 and 0.75) read as measured (§2.3)
Fix: mark them as illustrative.

**[Decision-readiness]** - FR-31's `[ASSUMPTION]` "a minor may break" sits beside decision 4's "taken once" (§4.8 FR-31)
Fix: move it to §11 as a question for the maintainer, and do not settle it in the FR.

**[Outside the PRD]** - The README says "six names" but lists seven lines plus two (`README.md:339`)
FR-30's count of eight is right.
Fix: a README edit, out of scope here.

## Mechanical notes

- The IDs are contiguous and unique: FR-1 to FR-34, NFR-1 to NFR-9, SM-1 to SM-8, UJ-1 to UJ-4, Q1 to Q10.
- The assumptions index round-trips: 12 inline, 12 indexed.
- No local absolute path, private name or personal detail was found in `prd.md` or `addendum.md`. `~/.claude/projects/` and `~/.codex/sessions/` are generic runtime paths.
- The research citations check out: refs 1, 2, 9 (rated low), 15 to 19, 26 (stale, cited for parity only), 27, 31, and recommendation 4. The claude-md-doctor and RuleReceipt credit satisfies decision 9.
- No FR smuggles in doctor features. There is no cause triage, no blocking hook, and no model in `report`. FR-34 is labelled proposed and has its own non-goals. The only tension is `promote?`, listed above.

## Reviewer files

- None. This was a single-pass rubric walk, and only this file was written.
