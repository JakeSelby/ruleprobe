#!/usr/bin/env python3
"""Print the release notes for the package version: its changelog section, verbatim."""
import sys

from release_preflight import ROOT, changelog_sections, package_version, version_section


def notes(root=ROOT):
    version = package_version(root)
    _, body = version_section(changelog_sections((root / "CHANGELOG.md").read_text(encoding="utf-8")), version)
    if not body:
        raise ValueError("CHANGELOG.md has no entries for {}".format(version))
    return body + "\n\nInstall: `pip install ruleprobe=={0}`, or run it with `uvx ruleprobe@{0} report`.\n".format(version)


if __name__ == "__main__":
    sys.stdout.write(notes())
