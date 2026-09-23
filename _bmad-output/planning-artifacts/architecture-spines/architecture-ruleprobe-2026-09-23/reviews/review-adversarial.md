# Review: adversarial pairs

Ran in-context, sequentially, against the unedited draft; not a subagent.

**Verdict:** four pairs of units can obey every AD and still diverge; each needs a tightened rule.

## Pairs

1. **High. Label writer and corpus reader.** AD-6 says corpus sessions are native-runtime transcripts read through the readers; AD-13 has `label` write "one session file". A label writer that serialises event-schema dicts and a validity loader that reads only native formats both comply, and the negative never loads. Fix: fix the format a label writes. [chosen: an event-schema session file, `*.events.jsonl`, loaded by validity without a runtime reader]
2. **High. `measure()` and a Python detector author on opportunities.** Same as rubric finding 1: one builder extends `run()`'s return, another sets `Detector.opportunities`; both read AD-11 as allowing it. Fix: `run()` unchanged, `measure()` owns the call.
3. **Medium. Per-file and per-section rule ids.** AD-12 gives a section id as `path#slug`; FR-13's file-level binding has no id form. One builder keys a one-rule file as `path`, another as `path#slug`, and a stored coverage count drifts across 0.1 and 0.2. Fix: a file bound in front matter keeps the bare relative path as its id.
4. **Medium. Catalog, repository and user detectors with one id.** `Registry.add` replaces in place, so the load order decides which wins, and the catalog's order is unset. Fix: fixed precedence, shipped then catalog then the three discovery places, and a replaced catalog id is reported as the user's own.
5. Low. A row with `schema_version` above the known maximum is excluded (AD-9) while a detector entry above it is a finding; consistent, no finding.
