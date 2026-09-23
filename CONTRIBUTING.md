# Contributing

Ideas, false positives and new detectors are as welcome as patches. This page says where things
go and how a change lands.

## The cheapest useful contributions

- **A false positive or a missed hit.** Open a [Detector miss](../../issues/new?template=02-detector-miss.yml)
  issue with the smallest command or event that shows it. Do not paste a real transcript: cut
  it down to the one event, and replace paths and names.
- **A labelled corpus session.** Add a synthetic session under `ruleprobe/corpus/sessions/`,
  label it in `ruleprobe/corpus/labels.yaml`, and put a near-miss beside every positive. The
  validity table moves, and every detector gets harder to get wrong.
- **A detector for a rule of your own.** Most belong in your own `.ruleprobe/detectors.yaml`,
  not in this package. The package ships only detectors that mean the same thing in every
  repository; open an [Idea](../../issues/new?template=03-idea.yml) first if you think yours does.

Anything bigger than a typo is better discussed first. A PR that follows a short thread almost
always merges faster than one that arrives cold.

## The fork, branch and pull request flow

Every change, including documentation, needs a dedicated delivery issue before implementation.
Each PR closes exactly one issue in this repository with `Closes #N`, and each delivery issue
belongs to one PR. Contextual references are welcome; do not use closing keywords for them. A
replacement PR may reuse an issue only after the previous PR closed without merging.

The required `issue-ownership` check validates GitHub's closing links, rejects an issue already
claimed by an open or merged PR, and requires the issue to carry a planning ID. For a community
issue the maintainer reserves that ID during triage, so you do not need to.

1. Fork and clone:
   ```sh
   gh repo fork JakeSelby/ruleprobe --clone --remote
   cd ruleprobe
   ```
2. Keep your `main` current with upstream and branch from it:
   ```sh
   git fetch upstream && git checkout main && git rebase upstream/main
   git checkout -b <short-topic>
   ```
3. Make the change and run the checks below.
4. Commit with a [Conventional Commit](https://www.conventionalcommits.org/) message:
   `fix(shell): recognise an escaped heredoc delimiter`, `feat(matchers): add a count matcher`,
   `docs(readme): show the stance grouping`.
5. Push and open the PR against `main`:
   ```sh
   git push -u origin <short-topic>
   gh pr create --repo JakeSelby/ruleprobe --base main --fill
   ```
6. CI runs the suite on the newest Python and on 3.9, the corpus floor, and an install of the
   built wheel. Squash merge is the only merge method and the PR title becomes the commit
   message, so make the title a good Conventional Commit line.

## Checks to run before opening a PR

```sh
python3 -m unittest discover -s tests
uv run --python 3.9 python -m unittest discover -s tests
python3 -m ruleprobe corpus --no-config --floor 0.9
```

## What will not be merged

- A runtime dependency. The package is standard library only, and the README promises it.
- Anything that sends data off the machine, asks a model, or writes to disk from `report`.
- Real transcript content anywhere in the tree: corpus, fixtures, tests or docs.
- A detector without corpus labels or `examples:`, or a code change without a test.
- A detector that is about one team's rules rather than a shape every repository shares.
- Copyleft, share-alike or unlicensed material, including snippets whose origin you cannot name.
- Credentials of any kind. GitHub push protection blocks them, and a PR that trips it is closed.

## Landing a pull request (maintainers)

- Bring the branch up to date with `git merge --no-edit origin/main`, never a rebase or a
  force-push; the squash keeps history linear regardless.
- Read the suite's exit code directly. `… | tail -1` hides a red suite behind `tail`'s status.
- `gh pr checks <n> --watch` returns at once when no check has registered yet. Wait until every
  required check is listed, then watch, then `gh pr merge --squash`. Never `--admin`.
- `scripts/bmad_issue_sync.py new` files the issue and then races the list endpoint. When it
  prints "not reserved", wait a few seconds and run `reserve --issue N --kind K`.
- Never bypass a pre-commit hook, not even for a first attempt you intend to redo.

## Review

One maintainer reviews every PR, usually within a week. Small, single-concern PRs go fastest.
The maintainer may push small edits to your branch before merging.

## Licensing of contributions

By opening a pull request you agree that your contribution is licensed under the MIT licence of
this repository, with no additional terms, and that you have the right to contribute it.
GitHub's Terms of Service say the same for any repository with a licence notice
([section D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license)).
No CLA, no sign-off line.
