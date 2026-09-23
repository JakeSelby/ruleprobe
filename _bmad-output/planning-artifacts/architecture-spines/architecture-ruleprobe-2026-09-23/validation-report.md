# Validation report: ARCHITECTURE-SPINE.md (ruleprobe, 2026-09-23)

```json
{"status": "findings", "intent": "validate", "spine": "ARCHITECTURE-SPINE.md", "lint_spine": {"ok": true, "total_findings": 0}, "findings": {"high": 4, "medium": 5, "low": 5}, "ad4_reproduced": true}
```

**Verdict:** the spine is structurally clean and its adopted claims mostly match the code, but four seams let
two correctly built units disagree: compliance polarity, compliance under unknown input, package data under
zip import, and the reviewer gate itself. AD-4's claim is real and reaches beyond `command`.

Process notes. Run from the repository root against HEAD `91ce821` (the spine cites `ae84ac3`; the one
commit between is docs only, no code drift). `lint_spine.py` returned 0 findings. The skill's Validate
ending is an HTML plus markdown report; this run writes the markdown only, by the caller's constraint.
Lenses were run in this one fresh context, not as parallel subagents. The author's `reviews/` were not
used as input.

## AD-4 reproduction

The claim holds on 0.1.0. A Bash command the shell parse skips (over `MAX_COMMAND`, or one the tokenizer
gives up on, such as an unbalanced quote) makes `not` over a segment-reading matcher fire, and makes
`absent` of it fire. It is not limited to `command`: `git` behaves the same. A `command` matcher holding
only `regex` reads the raw text and is not affected. No shipped detector uses `not` or `absent`
(`ruleprobe/detectors/common.yaml`), so the exposure is user-authored detectors.

```python
from ruleprobe.matchers import compile_detector
from ruleprobe.shell import analyse, Parsed, MAX_COMMAND
def ev(cmd): return {"kind": "tool_use", "turn": 1, "id": "t1", "name": "Bash", "input": {"command": cmd}}
neg = compile_detector({"id": "use-uv/non-uv-bash", "when": {"all": [
    {"tool": "Bash"}, {"not": {"command": {"name": ["uv"]}}}]}})
absent = compile_detector({"id": "run-tests/no-test-run", "event": "session",
    "when": {"absent": {"of": {"command": {"name": ["pytest"]}}}}})
# cases: "uv run pytest -q", "pytest -q tests/", "uv run pytest -k " + "x"*MAX_COMMAND,
#        "pytest -q -k " + "x"*MAX_COMMAND, "uv run pytest -k 'foo", "pytest -q -k 'foo"
```

```text
parsed uv          len=16     skipped=False not-fires=False absent-fires=True
parsed pytest      len=16     skipped=False not-fires=True  absent-fires=False
overlong uv        len=16401  skipped=True  not-fires=True  absent-fires=True
overlong pytest    len=16397  skipped=True  not-fires=True  absent-fires=True
unbalanced uv      len=21     skipped=True  not-fires=True  absent-fires=True
unbalanced pytest  len=17     skipped=True  not-fires=True  absent-fires=True
```

Rows 3 to 6 are the bug: a `uv` call counted as a non-`uv` call, and a session that ran `pytest` counted
as one with no test run. (Row 1's `absent` hit is a correct miss of `pytest` in segment 0, not the bug.)
A second run: `absent` of `git: {subcommand: [push]}` fires on `git push origin 'main` and on an
over-long `git push`, and not on `git push origin main`. `not` over `command: {regex: "^uv "}` on an
over-long `uv` command does not fire.

The PRD states NFR-4 as "implemented (0.1.0)". That status is wrong, and the fix is not in PRD §8's scope.

## High

1. **AD-11, compliance polarity for `absent`.** AD-11 compiles `absent` opportunities "using the PRD
   glossary's meaning of followed": "a turn where the trigger matched and the forbidden match did not".
   `absent` has no trigger key (only `of` and `scope`, `ruleprobe/matchers.py:587`), and its `of` is the
   action the rule *asks for* (`matchers.py` docstring: "nothing matched, which is the only way to
   measure a rule that asks for something to happen"), not a forbidden one. Adversarial pair A below.
   Fix: AD-11 names the new trigger key as an AD-7 vocabulary change and defines followed as "`of`
   matched in the trigger's turn". Also raise the glossary wording against the PRD.
2. **AD-11 with AD-4, compliance under unknown input.** The opportunity triple carries a boolean
   `followed`. Under AD-4's three-valued rule, an `order` opportunity whose `then` event is a skipped
   parse (an over-long `pytest`) has no legal value. `False` over-counts non-compliance, which breaks
   NFR-4 in the new figure. Fix: an opportunity with an unknown trigger or follow-up is dropped from both
   N and M, and counted separately in the row.
3. **AD-9, package data under zip import (inherited AD-21 at risk).** AD-9 puts a shipped fold map and a
   shipped-id list "in the package" and says package data is "found relative to `ruleprobe.__file__`",
   while the wheel must import from a zip. A plain `open()` beside `__file__` fails inside a zip. The
   harness already unpacks the corpus for this reason (`wheel_corpus` in agent-harness
   `scripts/detector_corpus.py`). The fold map is read when a registry is built (AD-9: "a cycle is an
   error when the registry is built"), and the harness builds `Registry(list)` on the hook path.
   Adversarial pair B. Fix: the shipped fold map and shipped ids are Python literals in a module, as
   `SECRET_PATTERNS` is, or read through `pkgutil.get_data`. Add a test that builds `Registry()` and
   calls `report_data` with the wheel imported from a zip.
4. **Reviewer gate not met.** `reviews/review-adversarial.md` says "Ran in-context, sequentially, against
   the unedited draft; not a subagent". `references/reviewer-gate.md`: "An inline self-check does not
   count: the independent context is the point". Fix: rerun the configured lenses in independent
   contexts before `status: final`.

## Medium

1. **AD-4 scope and wording.** It names only `command` and says the matcher "returns false for a skipped
   parse". That is true of its segment keys, not of `regex` or `unparsed`. `git` and `env` also read
   segments and fail the same way. Changing `not` and `absent` changes results for existing user detector
   files, a format change the 0.2 break (AD-9, PRD §6) does not name. Fix: list every segment-reading
   matcher; state the change as part of the 0.2 break in AD-9; file the 0.1.0 bug; correct NFR-4's status
   in the PRD.
2. **AD-12, section id collision.** `path#slug(heading)` gives two sections with the same heading text in
   one file the same id. FR-15's "twelve sections yields twelve rules" then fails. Adversarial pair C.
   Fix: suffix a same-slug ordinal in document order, or slug the heading path. A collision that remains
   is a finding.
3. **AD-6 with AD-13, the label session's `turn` and `final`.** AD-2 has readers derive `turn` and `final`.
   A `.events.jsonl` session is loaded "without a runtime reader", and the spine does not say whether the
   written values are kept. If `label` writes turn 37 and the key `"37:tu-x"`, and the loader re-derives
   turn from `user_prompt` count (0), the negative never matches and FR-26's "rerunning corpus counts the
   new negative" fails. A one-event session also cannot reproduce a session hit (`"<turn>:-"`) from
   `absent` or `order`. Fix: the loader takes `turn` and `final` as written; `label` refuses session
   hits, or writes the whole turn window.
4. **AD-13, redaction against label fidelity.** Redacting the written event can change what the detector
   sees. A `secrets/secret-in-write` false positive becomes a negative that passes trivially, and a
   redacted command can tokenise differently. Fix: `label` refuses to write, and says why, when redaction
   changes the matched field.
5. **Deferred omits PRD Q7 and Q8.** AD-11 states the default of 20 as settled, but Q7 is open. Q8 (root
   `__all__` names outside FR-30) is a divergence point for AD-9's contract test: one builder adds them
   and another does not. Fix: add both to Deferred, with their revisit condition.

## Low

1. **AD-1 graph.** It omits two real edges, `cli -> registry` (`cli.py:26`) and `validity -> events`
   (`validity.py:29`). As written, "Imports point down the graph" reads as violated by 0.1.0. Fix: add
   both edges.
2. **Binds coverage.** FR-9, FR-17 to FR-20 and NFR-9 are bound only through AD-1's blanket "FR-1 to
   FR-34". The blanket hides the gap. Fix: bind FR-9 where the Errors convention lives and FR-17 to FR-20
   in AD-11 or AD-9, then drop the blanket.
3. **AD-14 citation.** `ruleprobe/rules.py:52` is off. `def registry` is at :53 and the copy at :57.
4. **AD-9 `version` key.** Detector files already carry `version: 1` (`common.yaml:14`), which 0.1.0
   ignores. Fix: say that an existing file-level `version` other than 1 becomes a finding in 0.2.
5. **AD-9 decides "integer" ahead of PRD Q9.** The PRD glossary also says integer, so this is consistent
   with the PRD. Fix: mark the type as Q9-dependent, or record that the glossary settles it.

## Adversarial pairs (built independently of `reviews/`)

- **A (High 1).** The matchers unit follows AD-11 and the glossary: followed means "`of` did not match"
  in the turn. The catalog unit follows the matchers docstring: an `absent` entry's `of` is the required
  action. Both obey every AD, and every compliance rate for an `absent` catalog rule comes out inverted.
- **B (High 3).** The fold-map unit ships `detectors/renamed.json` and reads it lazily beside
  `ruleprobe.__file__` on the first registry build. That obeys AD-9: no import-time read, and the data is
  found relative to `__file__`. The harness imports the wheel from a zip under AD-9 and inherited AD-21.
  Its hook's `Registry([...])` raises, and every harness detector goes dark.
- **C (Medium 2).** The binding unit slugs two `## Testing` sections to `CLAUDE.md#testing`, which obeys
  AD-12. The report unit keys the coverage block by rule id, which obeys AD-12 and the Row convention.
  One rule overwrites the other, and the coverage count is off by one.

## Checks that passed

- **Every Binds id is real.** FR-1 to FR-34 and NFR-1 to NFR-9 all exist in the PRD.
- **Adopted claims checked against the code, and they match:**
  - AD-2: the five event kinds (`events.py` docstring).
  - AD-3: the Codex table and the `cmd` and `command` keys (`readers/codex.py:27,91-92`), and the
    file-tool assumption (`detectors/common.py:114-117`).
  - AD-8: no network or subprocess import, and no `open()` for writing.
  - AD-14: `DEFAULT` is populated at the registry's tail (`registry.py:254-256`), and `Bundle.registry`
    copies it.
  - Stack pins match the workflows, including `build==1.6.1`.
- **No AD re-opens a PRD or maintainer decision.** AD-8 keeps the model out of `report` (decision 2).
  AD-13's CLI implements FR-25 and FR-26. No HTML, hosted or prescriptive surface appears.
- **Inherited AD-13 is not weakened.** Pinned wheel, no fork, a release means a bump, and declarative
  detectors read through this engine are all restated, and AD-9 carries the contract.
- **Inherited AD-21 holds in text.** The standard library comes first on 3.9 (AD-8). High 3 is the one
  place a unit built to the letter would break it in practice.
- **Public only.** No local path, private name or personal detail in the spine, the memlog or the
  reviews. No em dash in the spine.
