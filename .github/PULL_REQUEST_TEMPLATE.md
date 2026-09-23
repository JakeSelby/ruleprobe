## What and why

<!-- Two sentences. Exactly one dedicated delivery issue is required. -->

Closes #N

## Where it lands

<!-- One: reader · shell parse · matcher · declarative format · detector · corpus · report/CLI · docs · CI/release -->

## Checklist

- [ ] `python3 -m unittest discover -s tests` passes, and a code change carries a test
- [ ] `python3 -m ruleprobe corpus --no-config --floor 0.9` passes, and a detector change carries labels or `examples:`
- [ ] No runtime dependency added; nothing sent off the machine or written to disk by `report`
- [ ] No real transcript content, home-directory path or personal name in the corpus, fixtures or docs
- [ ] A user-visible change has a line under `## Unreleased` in `CHANGELOG.md`
- [ ] Conventional Commit title (it becomes the squash commit message)
