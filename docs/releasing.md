# Releasing ruleprobe

A release is an immutable `v<version>` tag on `main`. The tag workflow repeats the gates on the
tagged commit, builds the wheel and sdist once, publishes them to PyPI through trusted publishing,
creates the GitHub release with the same files and the changelog section as its notes, and
fast-forwards `stable` to the tag. Nothing is uploaded by hand and no upload token exists.

## When a release is proposed, and what it is numbered

Every issue meant for the next release carries the `v<next>` milestone. Work merges freely, and a
release is proposed when that milestone empties or when a user-visible unreleased change is seven
days old, whichever comes first. A regression fix releases at once as a patch.

The number follows what changed. Fixes only is a patch; added or changed user-visible behaviour is
a minor. Before 1.0, a breaking change to the CLI, the detector format or the public API the
README lists is a minor, and its changelog section opens with a **Breaking** heading naming the
migration. From 1.0 a breaking change is a major.

Within a minor series nothing declared breaks, as the README's Versioning section states. The
preflight holds a patch release to it: checking `v<X>.<Y>.<Z>` with `Z` above 0, it reads
`DECLARED` from `tests/test_contract.py` at the tag `v<X>.<Y>.0` and refuses the release if the
tree no longer declares any of those names at the same import path. It reads the tag from the
local repository, so fetch it first (`git fetch origin tag v<X>.<Y>.0`); a tag it cannot read is
an error, not a pass. CI's release-PR step and the release workflow fetch the version tags
shallowly before they run the preflight, since their checkouts carry none. A `.0` release is not checked, since a new minor may break with notice, and
neither is a 0.1 patch, since the contract was first declared in 0.2.0.

## Cutting it

1. Merge every PR on the milestone, or move what is not ready to the next one.
2. In one PR that closes the release's own issue: rename `## Unreleased` in `CHANGELOG.md` to
   `## <version> (<YYYY-MM-DD>)`, add a fresh empty `## Unreleased` above it, and set
   `__version__` in `ruleprobe/__init__.py`. Both must agree:

   ```sh
   python3 scripts/release_preflight.py --tag v<version>
   python3 scripts/release_notes.py         # the GitHub release body, exactly
   ```

   CI refuses an unfolded release PR too: on a pull request that changes `__version__`, the `test`
   check runs the preflight as a release of the new version, so an entry left under
   `## Unreleased` fails it.

3. After that PR merges, tag the merge commit on `main` and push the tag:

   ```sh
   git fetch origin main && git checkout origin/main
   python3 scripts/release_preflight.py --tag v<version>
   git tag -a v<version> -m "ruleprobe <version>" && git push origin v<version>
   ```

4. Watch the `release` workflow. The `pypi` job runs in the `pypi` environment; approve it if the
   environment asks.
5. Confirm the three surfaces, each by looking rather than inferring:
   - PyPI shows the version: `curl -s https://pypi.org/pypi/ruleprobe/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"`.
   - A clean run works: `uvx ruleprobe@<version> --version`.
   - `stable` is at the tag: `python3 scripts/advance_stable.py --check`. If the workflow could
     not move it, run `python3 scripts/advance_stable.py` from a checkout with the tag.
6. Close the milestone and open the next one:

   ```sh
   gh api repos/JakeSelby/ruleprobe/milestones --jq '.[] | "\(.number) \(.title) open:\(.open_issues)"'
   gh api -X PATCH repos/JakeSelby/ruleprobe/milestones/<number> -f state=closed
   gh api repos/JakeSelby/ruleprobe/milestones -f title=v<next> -f state=open
   ```

## A failed release

Never move or delete a tag; the `tags-integrity` ruleset refuses it anyway. PyPI refuses a second
upload of the same version too. If the workflow failed before `pypi`, fix the source and release
the next patch. If PyPI has a broken version, yank it on PyPI with a reason, then release the fix
as the next patch. `stable` stays where it is until a good release advances it.

## One-time setup

The workflow publishes only once both halves exist, and fails at the `pypi` job until then:

- **GitHub:** an environment named `pypi` whose deployment branch policy allows only `v*` tags.
- **PyPI:** a trusted publisher on the `ruleprobe` project for owner `JakeSelby`, repository
  `ruleprobe`, workflow `release.yml` and environment `pypi`, added under the project's
  **Publishing** settings by an owner of the project.
