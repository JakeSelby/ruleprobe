"""The release scripts: version and changelog agreement, notes, and the stable branch."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import advance_stable  # noqa: E402
import release_notes  # noqa: E402
import release_preflight  # noqa: E402

CHANGELOG = """# Changelog

## Unreleased
{unreleased}
## {heading}

### Fixed

- A thing.
"""


def make_root(temp, version="1.2.3", heading="1.2.3 (2026-01-02)", unreleased=""):
    root = Path(temp)
    (root / "ruleprobe").mkdir()
    (root / "ruleprobe" / "__init__.py").write_text('"""Doc."""\n__version__ = "{}"\n'.format(version))
    (root / "CHANGELOG.md").write_text(CHANGELOG.format(heading=heading, unreleased=unreleased))
    return root


class PreflightTests(unittest.TestCase):
    def test_matching_version_changelog_and_tag_is_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(release_preflight.errors(make_root(temp), tag="v1.2.3"), [])

    def test_repository_itself_is_consistent(self):
        self.assertEqual(release_preflight.errors(), [])

    def test_tag_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp), tag="v1.2.4")
        self.assertTrue(any("does not match" in line for line in found))

    def test_missing_section_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp, version="1.3.0"))
        self.assertTrue(any("no section for 1.3.0" in line for line in found))

    def test_undated_heading_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp, heading="1.2.3"))
        self.assertTrue(any("carries no release date" in line for line in found))

    def test_unreleased_entries_are_refused_on_a_release(self):
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp, unreleased="\n- Pending.\n"), tag="v1.2.3")
        self.assertTrue(any("Unreleased entries" in line for line in found))

    def test_unreleased_entries_pass_between_releases(self):
        # #64: CI runs the preflight without a tag on every change, and a user-visible change adds
        # an Unreleased entry, so only a release may refuse one.
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp, unreleased="\n- Pending.\n"))
        self.assertEqual(found, [])

    def test_prerelease_version_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            found = release_preflight.errors(make_root(temp, version="1.2.3rc1", heading="1.2.3rc1 (2026-01-02)"))
        self.assertTrue(any("not a stable semantic version" in line for line in found))

    def test_prefix_version_does_not_match_a_longer_one(self):
        sections = release_preflight.changelog_sections("## 1.2.30 (2026-01-02)\n\n- x\n")
        self.assertEqual(release_preflight.version_section(sections, "1.2.3"), (None, None))


class NotesTests(unittest.TestCase):
    def test_notes_are_the_version_section_and_an_install_line(self):
        with tempfile.TemporaryDirectory() as temp:
            text = release_notes.notes(make_root(temp))
        self.assertTrue(text.startswith("### Fixed"))
        self.assertIn("pip install ruleprobe==1.2.3", text)
        self.assertNotIn("Unreleased", text)

    def test_empty_section_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            (root / "CHANGELOG.md").write_text("## 1.2.3 (2026-01-02)\n")
            with self.assertRaises(ValueError):
                release_notes.notes(root)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


class StableTests(unittest.TestCase):
    """`stable` is created, left alone, fast-forwarded, and never moved sideways."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.remote, self.work = base / "remote.git", base / "work"
        subprocess.check_call(["git", "init", "-q", "--bare", str(self.remote)])
        subprocess.check_call(["git", "init", "-q", str(self.work)])
        git(self.work, "config", "user.email", "test@example.invalid")
        git(self.work, "config", "user.name", "Test")
        git(self.work, "remote", "add", "origin", str(self.remote))
        self.first = self.commit("one")

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, message):
        git(self.work, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def test_create_current_advance_and_refuse(self):
        git(self.work, "tag", "v1", self.first)
        self.assertEqual(advance_stable.plan(self.work, "v1"), ("create", self.first))
        git(self.work, "push", "-q", "origin", self.first + ":refs/heads/stable")
        self.assertEqual(advance_stable.plan(self.work, "v1"), ("current", self.first))
        second = self.commit("two")
        git(self.work, "tag", "v2", second)
        self.assertEqual(advance_stable.plan(self.work, "v2"), ("advance", second))
        git(self.work, "checkout", "-q", "--orphan", "side")
        sideways = self.commit("unrelated")
        git(self.work, "tag", "v3", sideways)
        self.assertEqual(advance_stable.plan(self.work, "v3"), ("refuse", sideways))


if __name__ == "__main__":
    unittest.main()
