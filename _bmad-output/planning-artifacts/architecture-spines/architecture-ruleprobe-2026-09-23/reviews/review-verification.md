# Review: verification lens (reality-checked, not asserted)

Ran in-context, sequentially, against the unedited draft; not a subagent.

**Verdict:** every stack row and code claim traces to a repository file; two residual gaps.

## Findings

1. **Medium. Action versions come from the pin comments.** Each action is SHA-pinned and tagged in a comment (`# v7.0.1`). The SHA-to-tag mapping was not checked; the brief scoped verification to repository files. Record, do not fix.
2. **Medium. The zip import is declared (AD-9) but nothing in CI exercises it.** The `package` job installs the wheel with pip; the harness puts it on `sys.path` as a zip. Open question for the contract test.
3. Low. `3.x` in CI floats; the Stack row says so.
4. Checked and holding: the three sanctioned upward imports (`registry.py:209,254`, `report.py:32`); sorted paths in all three walkers; the clock only in `readers/__init__.py:26`; no `subprocess`, `socket`, `urllib` or `http` import; `DEFAULT_FLOOR = 0.9`; `STATES`; harness AD-13 and AD-21 text at agent-harness `main` 6869009.
