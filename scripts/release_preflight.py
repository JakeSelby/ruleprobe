#!/usr/bin/env python3
"""Refuse a release whose version, changelog and tag disagree.

Without `--tag`, it checks that `__version__` and the changelog agree; CI runs it so on every change,
while `## Unreleased` collects entries. With `--tag`, it also refuses Unreleased entries, which a
release must fold into its version section: run it so before tagging, and the release workflow runs
it again on the tag. With `--base-init`, the base branch's `ruleprobe/__init__.py`, a changed
`__version__` makes the run a release of the new version, as if `--tag v<version>` were given: CI
runs it so on every pull request, so a version bump that leaves Unreleased entries fails before the
tag. It checks only what a file in this repository can prove; the test suite and the corpus floor
are separate gates.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def package_version(root=ROOT, init=None):
    """The one version source: `__version__` in the package, which pyproject reads too.

    `init` reads it from another copy of `__init__.py` instead, such as the base branch's.
    """
    path = init if init is not None else root / "ruleprobe" / "__init__.py"
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    if not match:
        raise ValueError("{} declares no __version__".format(path))
    return match.group(1)


def release_tag(root=ROOT, tag=None, base_init=None):
    """The tag to check as a release: `tag`, else `v<version>` when `__version__` differs from `base_init`'s."""
    if tag is not None or base_init is None:
        return tag
    version = package_version(root)
    return "v" + version if version != package_version(init=base_init) else None


def changelog_sections(text):
    """Map each `## <heading>` to the text under it, in file order."""
    sections, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def version_section(sections, version):
    for heading, body in sections.items():
        if heading == version or heading.startswith(version + " "):
            return heading, body
    return None, None


def errors(root=ROOT, tag=None):
    found = []
    version = package_version(root)
    if not SEMVER.fullmatch(version):
        found.append("__version__ {} is not a stable semantic version".format(version))
    sections = changelog_sections((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    heading, _ = version_section(sections, version)
    if heading is None:
        found.append("CHANGELOG.md has no section for {}".format(version))
    elif not re.fullmatch(r"{} \(\d{{4}}-\d{{2}}-\d{{2}}\)".format(re.escape(version)), heading):
        found.append("CHANGELOG.md heading for {} carries no release date: {}".format(version, heading))
    if tag is not None and re.search(r"^\s*- ", sections.get("Unreleased", ""), re.M):
        found.append("CHANGELOG.md still has Unreleased entries; fold them into the version section")
    if tag is not None and tag != "v" + version:
        found.append("tag {} does not match __version__ {}".format(tag, version))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None)
    parser.add_argument("--base-init", metavar="PATH",
                        help="the base branch's ruleprobe/__init__.py; a changed __version__ checks as a release")
    args = parser.parse_args(argv)
    tag = release_tag(ROOT, args.tag, args.base_init)
    if tag is not None and args.tag is None:
        print("release preflight: __version__ changed from the base; checking as {}".format(tag))
    found = errors(ROOT, tag)
    for line in found:
        print("release error: " + line, file=sys.stderr)
    if not found:
        print("release preflight: {} is ready".format(package_version(ROOT)))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
