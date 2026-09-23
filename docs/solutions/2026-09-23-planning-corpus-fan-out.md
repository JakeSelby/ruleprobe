# Planning corpus fan-out: what went wrong and the fix

- 2026-09-23: When several agents fill story files in parallel, give each its own scratch folder (for example `/tmp/rp-fill-<epic>`); a shared folder let one batch splice another batch's drafts over ten files. Re-run `python3 scripts/bmad_issue_sync.py audit --delivery N` for every item after a parallel fill, not only your own batch.
- 2026-09-23: `bmad-deep-recon` keeps project files out of the evidence by design, so a recommendation can miss what the package already does; correct it with a dated "project note" below the recommendations and a memlog `event`, never by rewriting a finding.
