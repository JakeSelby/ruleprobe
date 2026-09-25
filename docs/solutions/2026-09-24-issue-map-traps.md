# Two traps in the BMad issue map

- **2026-09-24, reserving by hand:** `python3 scripts/bmad_issue_sync.py new` can file an issue and
  then fail to reserve it, reporting "issue #N was not found". While filing the 0.2.0 follow-ups it
  failed seven times in seven. A few seconds later, run
  `python3 scripts/bmad_issue_sync.py reserve --issue N --kind KIND [--parent P]`, and run it again
  if it fails once more.
- **2026-09-24, merging the map:** a rebase or merge that touches `_bmad-output/issue-map.json` can
  apply cleanly and still be wrong: one duplicated an item and marked an active one completed.
  Rebuild the file as `origin/main`'s map plus the branch's own items, keeping the larger of each
  `next_ids` counter. Then compare it with `main`'s item by item rather than by diff, because the
  tool reorders items when it writes the file.
