#!/usr/bin/env python3
"""Refuse a release whose version, changelog and tag disagree.

Without `--tag`, it checks that `__version__` and the changelog agree; CI runs it so on every change,
while `## Unreleased` collects entries. With `--tag`, it also refuses Unreleased entries, which a
release must fold into its version section: run it so before tagging, and the release workflow runs
it again on the tag. `--base-init` takes the path of the base branch's `ruleprobe/__init__.py`;
when `__version__` differs from the version declared there, the run checks as a release of the new
version, as if `--tag v<version>` were given. CI runs it so on every pull request, so a version bump
that leaves Unreleased entries fails before the tag. It checks only what a file in this repository can prove; the test suite and the corpus floor
are separate gates.

A release of a patch version, `X.Y.Z` with `Z` above 0, is also held to the contract its series
opened with: every name `DECLARED` held in `tests/test_contract.py` at the tag `vX.Y.0` must still
be there, at the same import path. The tag is read from the local repository, so it must have been
fetched; an unreadable tag is an error, never a pass. A new minor may drop names, with notice, so
`X.Y.0` is not checked, and neither is a 0.1 patch: the contract was first declared in 0.2.0.
"""
import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
CONTRACT_TEST = "tests/test_contract.py"
#: The first minor series whose opening tag carries a contract test; an earlier one declared none.
FIRST_CONTRACT_SERIES = (0, 2)


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


def series_tag(version):
    """The tag that opened `version`'s minor series, or None when `version` opens one itself."""
    major, minor, patch = version.split(".")
    return None if int(patch) == 0 else "v{}.{}.0".format(major, minor)


def declared_names(source):
    """The `(module, name)` pairs of the `DECLARED = {...}` literal in a contract test's source."""
    for node in ast.parse(source).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "DECLARED"):
            value = ast.literal_eval(node.value)
            for module, names in value.items():
                if not isinstance(names, (tuple, list)):
                    raise ValueError("DECLARED[{!r}] is not a tuple or list of names".format(module))
            return {(module, name) for module, names in value.items() for name in names}
    raise ValueError("{} assigns no DECLARED literal".format(CONTRACT_TEST))


def source_at(root, tag):
    """The contract test's text at `tag` in the git repository at `root`."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", "refs/tags/{}:{}".format(tag, CONTRACT_TEST)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(message or "git show exited {}".format(result.returncode))
    return result.stdout.decode("utf-8")


def contract_errors(root, version):
    """A line for each name the series' opening tag declared that the contract test no longer does."""
    if not SEMVER.fullmatch(version):
        return ["cannot check the series contract of {}: not a stable semantic version".format(version)]
    base = series_tag(version)
    if base is None or tuple(int(part) for part in version.split(".")[:2]) < FIRST_CONTRACT_SERIES:
        return []
    try:
        before = declared_names(source_at(root, base))
    except (OSError, ValueError, SyntaxError, TypeError, AttributeError) as exc:
        return ["cannot read the names {} declared in {}: {}".format(base, CONTRACT_TEST, exc)]
    try:
        now = declared_names((root / CONTRACT_TEST).read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError, TypeError, AttributeError) as exc:
        return ["cannot read the names {} declares: {}".format(CONTRACT_TEST, exc)]
    return ["{} no longer declares {}.{}, which {} declared".format(CONTRACT_TEST, module, name, base)
            for module, name in sorted(before - now)]


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
    if tag is not None and SEMVER.fullmatch(version):  # else reported above
        found.extend(contract_errors(Path(root), version))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None)
    parser.add_argument("--base-init", metavar="PATH",
                        help="path to the base branch's ruleprobe/__init__.py; if __version__ differs from it, "
                             "check as a release of the new version")
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
