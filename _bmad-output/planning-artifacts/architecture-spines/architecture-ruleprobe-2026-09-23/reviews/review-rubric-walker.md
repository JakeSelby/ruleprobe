# Review: rubric walker (good-spine checklist)

Ran in-context, sequentially, against the unedited draft; not a subagent (none available to the worker). The maintainer's session runs an independent validation after this.

**Verdict:** sound build substrate; ratifies the code and covers every PRD FR; three gaps to close.

## Findings

1. **High. AD-11 leaves the caller of `opportunities` unowned.** `run()`'s return shape is declared (FR-30), so it cannot carry opportunities, and nothing says who calls the new callable or how its failure is isolated. Fix: `measure()` calls it, behind the same `enabled(stances)` gate and the same per-detector failure isolation as `run()`.
2. **Medium. Shared mutable state has no owner rule.** `DEFAULT` and `COMPILERS` are process-global. `Bundle.registry` copies `DEFAULT` today (`ruleprobe/rules.py:52`), but no AD says package code never mutates `DEFAULT` after import. Fix: ratify it.
3. **Medium. AD-3 overstates the canonical `Edit` keys.** `ruleprobe/detectors/common.py` reads `new_string`, not `old_string`. Fix: list only keys a shipped detector reads.
4. Low. AD-6 names `hit_key` and `event_key` as the only key builders but does not bind explain and label to them.
5. Low. Operational envelope: covered by the deployment diagram and Deferred. No finding.
