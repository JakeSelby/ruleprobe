---
bmad_id: "RP-SP004"
type: "spike"
title: "spike(rules): score the section binder and a per-sentence binder on a rules zoo"
lifecycle: "active"
provenance: "authored"
github_issue: 137
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/137"
parent_bmad_id: "RP-E010"
parent_github_issue: 128
updated: "2026-09-25"
---

# RP-SP004 — spike(rules): score the section binder and a per-sentence binder on a rules zoo

<!-- bmad-sync:begin -->
- **GitHub issue:** [#137](https://github.com/JakeSelby/ruleprobe/issues/137)
- **Primary parent:** [RP-E010](https://github.com/JakeSelby/ruleprobe/issues/128)
- **State:** active

The issue carries the summary, discussion and acceptance evidence; this file carries the design.

This work item was authored as part of the repository's committed BMad planning system.
<!-- bmad-sync:end -->

## Question

Does a per-sentence binder reach binding recall of at least 0.70 with zero false binds on a labelled
rules zoo, where today's section binder does not? Stories 8.2 and 8.3 wait on the answer: 8.3 ships
per-sentence binding only on that number (FR-37, AD-18).

## Experiment

- **The zoo** (`tests/fixtures/rules-zoo/zoo.json`, synthetic): 65 invented rule sections, 84
  labelled lines, each labelled with the catalog detector id it should bind, or `null`. 41 labels
  name today's seven catalog entries and 4 name default detectors with no catalog pattern yet
  (story 8.4). The rest are near-misses: exceptions and permissions in the matched sentence,
  conditions, contrasts, topic neighbours, exceptions stated in the *next* sentence, negated
  markers ("no exceptions", "without exception", "admit no exception"), and six multi-rule
  sections. The zoo was frozen before the first scoring run (sha256 `0a22f9b2…a0325a`) and no
  label was changed after it.
- **Labelling rule.** A line binds a detector only when the detector's observable is the rule as
  written. A rule with an exception, a permission or a narrowing condition is `null`, because the
  detector would count the permitted case as a violation (AD-4). A contrast that leaves the
  observable intact keeps its label ("Run the tests before finishing, but skip the slow
  integration suite").
- **Section binder (baseline):** `ruleprobe/rules.py` at 2397cd6 as shipped in 0.2.0, called
  through `_bind` on each section as `_units` parses it.
- **Per-sentence prototype (throwaway, under Dev notes, never under `ruleprobe/`):** over the same
  `_sentences` split (heading first), each sentence binds the one catalog entry whose pattern
  matches it, unless `_EXCEPTION` or `_CONDITION` finds a word in that sentence once a closed list
  of negated markers is removed. A section binds the union of its sentences' binds. Patterns and
  both word lists are today's; nothing else changed.
- **Scoring.** Per section, expected = the set of catalog ids its lines and heading carry; bound =
  what the binder bound. A true bind is in both, a false bind is bound and not expected, a miss is
  expected and not bound. Recall = true / expected, precision = true / bound. For the prototype a
  stricter sentence-level count is also kept: a sentence bound to an id other than its own label.
  An id outside today's catalog counts as expected-none for the headline and is reported apart.
- **Variant B** (run after the prototype missed, as the next cheapest experiment): the prototype,
  plus an exception or permission word in the *next* sentence of the same section unbinds a bound
  sentence.

## Exit criterion

Per-sentence recall ≥ 0.70 on the zoo's 41 catalog labels **and** zero false binds, section-level
and sentence-level. Fixed in the story (8.1) and the roadmap before the run.

## Result

Run 2026-09-25 on an Apple M5 Pro, macOS 26.5, Python 3.14.5, and again under Python 3.9 through
`uv`: byte-identical output across two runs and both interpreters. Binding is deterministic, so one
run is the measurement. The zoo is synthetic; these figures are validated on the zoo, not field
accuracy on real rule files.

**Status: failed.** The prototype meets the recall bar and misses the zero-false-bind bar.

| Binder | Recall | Precision | False binds |
| --- | --- | --- | --- |
| Section binder (0.2.0) | 0.44 (18/41) | 0.95 (18/19) | 1 |
| Per-sentence prototype | 0.73 (30/41) | 0.86 (30/35) | 5 (5 sentence-level) |
| Variant B | 0.68 (28/41) | 0.97 (28/29) | 1 (1 sentence-level) |

Per catalog entry, recall (true/expected), false binds:

| Entry | Section binder | Prototype | Variant B |
| --- | --- | --- | --- |
| `testing/test-after-change` | 0.33 (3/9), 1 | 0.67 (6/9), 2 | 0.67 (6/9), 1 |
| `verification/no-verify` | 0.50 (3/6), 0 | 0.83 (5/6), 0 | 0.83 (5/6), 0 |
| `git-safety/force-push-default` | 0.38 (3/8), 0 | 0.75 (6/8), 1 | 0.62 (5/8), 0 |
| `package-manager/pip-install` | 0.40 (2/5), 0 | 0.60 (3/5), 1 | 0.60 (3/5), 0 |
| `transcript-hygiene/whole-file-cat` | 0.75 (3/4), 0 | 0.75 (3/4), 0 | 0.75 (3/4), 0 |
| `commits/non-conventional-subject` | 0.40 (2/5), 0 | 0.80 (4/5), 1 | 0.80 (4/5), 0 |
| `secrets/secret-file-add` | 0.50 (2/4), 0 | 0.75 (3/4), 0 | 0.50 (2/4), 0 |

No binder bound any of the 4 labels for the uncatalogued defaults, as expected before story 8.4.

**What the prototype gained.** Twelve binds over the section binder: four through negated markers
(`t05`, `t06`, `h05`, `f04`) and eight in multi-rule sections, where the section binder saw several
matches or one permission word elsewhere and bound nothing (`x01` ×3, `x02` ×2, `x04` ×2, `x05`).

**What blocks it.** All five false binds are an exception stated in the sentence *after* the rule:
"Never force-push to main. Release managers are the exception." (`t11`, `t12`, `f10`, `p08`,
`m06`). The section binder catches four of them because it scans the whole section for exception
words; scoping the words to their own sentence is exactly what lets them through. The fifth, `t12`
("Docs-only changes are exempt."), is also the section binder's one false bind: "exempt" is not in
`_EXCEPTION`, a vocabulary gap in both.

**What the misses are.** Of the prototype's 11 misses, 9 are phrasings no catalog pattern reads
("Before you hand back, run the tests", "Prefer uv over pip", "Keep credentials out of source
control"), and 2 are a condition or contrast word in the matched sentence (`t07` "but", `f06`
"if"). Neither is a binding-unit question; the first is catalog coverage.

**Variant B** removes the four cross-sentence false binds and keeps `t12`, but its next-sentence
scope also unbinds two true binds whose next sentence permits something else ("Force-pushing your
own feature branch is okay", "Squash merges are fine"), so recall falls to 0.68, under the bar.

## Decision

What the numbers support:

1. **Per-sentence scoping as specified in AD-18 fails its own gate** on this zoo: five false binds,
   all from exceptions in a following sentence. Shipping it as written would bind rules the
   section binder correctly leaves unmeasured.
2. **The next cheapest experiment** is a scope between the two: variant B with the exception word
   required to refer back ("the exception", "exempt", "excepted") rather than any permission word,
   plus "exempt" in the word list. That is a design change to AD-18's exception rule, and tuning
   it on this zoo alone would fit the test set, so it wants fresh held-out near-misses first.
3. **Recall headroom is in the catalog, not the binder:** 9 of 11 prototype misses are pattern
   phrasings, which story 8.4 or a pattern-widening story would address, each with its own
   near-misses.
4. Whichever scope is chosen, the zoo stands as story 8.2's gate input; its labels need no change.

**Decision, 2026-09-25**, taken under the maintainer's delegation and flagged to the maintainer to
confirm or override:

1. Story 8.3 builds variant B's scope, and adds "exempt" to the exception words. An exception or
   permission word in the matched sentence, or in the sentence after it, unbinds the rule. Variant B
   measured one false bind, `t12`, and that one is the "exempt" gap, so 8.3 expects none. Its own
   run on the zoo must show it. Under-counting (AD-4) outranks the 0.02 recall shortfall. 8.3 amends
   AD-18 to match, through `bmad-architecture`.
2. The recall bar moves from the binder alone to Epic 8 as a whole. 9 of the 11 misses are catalog
   phrasings, which story 8.4 and a pattern-widening story address, each with its own near-misses.
   The coverage goal stands.
3. The refer-back refinement in point 2 above is a follow-up experiment on a fresh, held-out
   near-miss set. It changes AD-18 again only if it clears zero false binds there.

## Dev notes

- Binds FR-36 (per-sentence binding), FR-37 (the binder scored like a detector), AD-18 (rules bind
  per sentence, under the under-count rule) and AD-4 (under-count rather than over-count).
- Files: this story file; `tests/fixtures/rules-zoo/zoo.json`. No test and no change under
  `ruleprobe/`; 8.2 moves the zoo to `ruleprobe/corpus/` and makes it a gate.
- The zoo is JSON, not markdown, so that the fixtures root, which suites read as a mixed-runtime
  transcript root, gains no rule file; no reader picks up a `.json` outside a Gemini `chats/`
  directory.
- **To reproduce:** save the script below as `score_zoo.py` anywhere, then from a checkout at the
  commit that adds the zoo run
  `PYTHONPATH=. python3 score_zoo.py tests/fixtures/rules-zoo/zoo.json --variant-b`. It reads
  `rules._units`, `rules._sentences`, `rules._bind`, `rules._CATALOG`, `rules._EXCEPTION` and
  `rules._CONDITION`, all private: 8.2 should expect to adapt it if any of those move.
- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.1]
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#FR-36]
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#FR-37]
- [Source: _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md#AD-18]
- [Source: _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md#AD-4]
- [Source: ruleprobe/rules.py#_match]

```python
"""RP-SP004: score the section binder and a per-sentence prototype on the rules zoo.

From a checkout: PYTHONPATH=. python3 score_zoo.py tests/fixtures/rules-zoo/zoo.json [--variant-b]
Throwaway; reads ruleprobe's private helpers and changes nothing under ruleprobe/.
"""
import json
import re
import sys
from collections import Counter

from ruleprobe import rules
from ruleprobe.registry import fold_map

CATALOG = [(p, d.id) for p, d in rules._CATALOG if d.id not in fold_map()]
IDS = [i for _p, i in CATALOG]
#: The prototype's closed list of negated markers: removed before the exception scan.
NEGATED = re.compile(r"\b(?:(?:admit|allow|make|with)\s+no|without(?:\s+any)?|no)\s+"
                     r"exceptions?\b", re.IGNORECASE)


def section(item):
    body = "## %s\n\n%s\n" % (item["heading"], "\n".join(t for t, _l in item["lines"]))
    units = rules._units(body)
    assert len(units) == 1 and units[0][2], item["id"]
    return units[0][0], units[0][3]


def labels(item):
    """One label per sentence as `rules._sentences` splits the section: heading first."""
    out = [item.get("heading_label")]
    for text, label in item["lines"]:
        out.extend(label for _s in rules._sentences("", [text]))
    return out


def section_binder(item, heading, paragraphs):
    entry = rules._bind(item["id"], "zoo.md", heading, paragraphs)
    return set(entry.detectors) if entry.state == "measured" else set(), None


def per_sentence(item, heading, paragraphs, adjacent=False):
    """Each sentence binds the one entry whose pattern matches it, unless an exception or
    permission word, or a condition word, is in that sentence once negated markers are
    removed. `adjacent` (variant B) also lets an exception or permission word in the next
    sentence of the same section unbind a bound sentence."""
    sentences = rules._sentences(heading, paragraphs)
    plain = [NEGATED.sub(" ", s) for s in sentences]
    binds = []
    for n, sentence in enumerate(sentences):
        hits = [i for p, i in CATALOG if p.match(sentence)]
        blocked = rules._EXCEPTION.search(plain[n]) or rules._CONDITION.search(plain[n])
        if adjacent and n + 1 < len(plain):
            blocked = blocked or rules._EXCEPTION.search(plain[n + 1])
        binds.append(hits[0] if len(hits) == 1 and not blocked else None)
    return {b for b in binds if b}, binds


def score(zoo, binder, **kw):
    tp, fb, fn = Counter(), Counter(), Counter()
    sentence_fb, detail = 0, []
    pending = [0, 0]
    for item in zoo["items"]:
        heading, paragraphs = section(item)
        want_all = [l for l in labels(item) if l]
        want = {l for l in want_all if l in IDS}
        pending[0] += len({l for l in want_all if l not in IDS})
        bound, per = binder(item, heading, paragraphs, **kw)
        pending[1] += len({b for b in bound if b not in IDS and b in want_all})
        for d in bound & want:
            tp[d] += 1
        for d in bound - want:
            fb[d] += 1
            detail.append("FB %s %s" % (item["id"], d))
        for d in want - bound:
            fn[d] += 1
        if per is not None:
            lab = labels(item)
            assert len(lab) == len(per), (item["id"], lab, per)
            for got, exp in zip(per, lab):
                if got and got != exp:
                    sentence_fb += 1
                    detail.append("sentence FB %s %s" % (item["id"], got))
    return tp, fb, fn, sentence_fb, pending, detail


def ratio(a, b):
    return "%.2f" % (a / b) if b else "-"


def report(name, result):
    tp, fb, fn, sfb, pending, detail = result
    print("== %s" % name)
    for d in IDS:
        print("  %-36s recall %s (%d/%d)  precision %s  false binds %d"
              % (d, ratio(tp[d], tp[d] + fn[d]), tp[d], tp[d] + fn[d],
                 ratio(tp[d], tp[d] + fb[d]), fb[d]))
    T, F, N = sum(tp.values()), sum(fb.values()), sum(fn.values())
    print("  TOTAL recall %s (%d/%d)  precision %s (%d/%d)  false binds %d"
          % (ratio(T, T + N), T, T + N, ratio(T, T + F), T, T + F, F))
    if sfb or name != "section binder":
        print("  sentence-level false binds %d" % sfb)
    print("  uncatalogued defaults bound %d/%d" % (pending[1], pending[0]))
    for line in detail:
        print("  " + line)


if __name__ == "__main__":
    zoo = json.load(open(sys.argv[1], encoding="utf-8"))
    report("section binder", score(zoo, section_binder))
    report("per-sentence prototype", score(zoo, per_sentence))
    if "--variant-b" in sys.argv:
        report("variant B: prototype + next-sentence exception scope",
               score(zoo, per_sentence, adjacent=True))
```

## Change log

- 2026-09-25: written from the planning corpus; question, experiment and exit criterion fixed and the zoo frozen before the run.
- 2026-09-25: run; failed on false binds (5), recall 0.73; variant B run as the next cheapest experiment; decision left to the maintainer.
- 2026-09-25: decision taken under the maintainer's delegation: variant B plus "exempt" for 8.3, the recall bar moves to Epic 8, and the refer-back refinement waits for held-out near-misses. Flagged to the maintainer for confirm or override.
- 2026-09-25, amendment: story 8.2 moved the zoo byte for byte to `ruleprobe/corpus/rules-zoo.json` in #140, so `tests/fixtures/rules-zoo/zoo.json` is gone. To reproduce, run the script from a checkout with that path: `PYTHONPATH=. python3 score_zoo.py ruleprobe/corpus/rules-zoo.json --variant-b`. The reproduction command above is left as it was run.
