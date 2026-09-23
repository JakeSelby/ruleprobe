"""The release scripts: version and changelog agreement, notes, and the stable branch."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def run_main(self, root, argv, environ):
        """`main(argv)` over `root`, with the GitHub ref variables replaced by `environ`."""
        clean = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REF_TYPE", "GITHUB_REF_NAME")}
        err = io.StringIO()
        with mock.patch.object(release_preflight, "ROOT", root), \
                mock.patch.dict(os.environ, dict(clean, **environ), clear=True), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = release_preflight.main(argv)
        return code, err.getvalue()

    def test_main_passes_the_tag_to_the_unreleased_check(self):
        # The refusal depends on --tag reaching errors(), from the flag or from a tag ref in CI.
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp, unreleased="\n- Pending.\n")
            self.assertEqual(self.run_main(root, [], {}), (0, ""))
            code, err = self.run_main(root, ["--tag", "v1.2.3"], {})
            self.assertEqual(code, 1)
            self.assertIn("Unreleased entries", err)
            code, err = self.run_main(root, [], {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v1.2.3"})
            self.assertEqual(code, 1)
            self.assertIn("Unreleased entries", err)
            self.assertEqual(self.run_main(root, [], {"GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"}),
                             (0, ""))

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

    def write_base(self, temp, version):
        base = Path(temp) / "base_init.py"
        base.write_text('"""Doc."""\n__version__ = "{}"\n'.format(version))
        return str(base)

    def test_a_version_bump_with_unreleased_entries_is_refused(self):
        # #68: CI passes the base branch's __init__.py, so a release PR that leaves Unreleased
        # entries fails before the tag rather than in the release workflow after it.
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp, unreleased="\n- Pending.\n")
            base = self.write_base(temp, "1.2.2")
            self.assertEqual(release_preflight.release_tag(root, None, base), "v1.2.3")
            code, err = self.run_main(root, ["--base-init", base], {})
        self.assertEqual(code, 1)
        self.assertIn("Unreleased entries", err)

    def test_an_unchanged_version_keeps_unreleased_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp, unreleased="\n- Pending.\n")
            base = self.write_base(temp, "1.2.3")
            self.assertIsNone(release_preflight.release_tag(root, None, base))
            self.assertEqual(self.run_main(root, ["--base-init", base], {}), (0, ""))

    def test_a_folded_version_bump_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            self.assertEqual(self.run_main(root, ["--base-init", self.write_base(temp, "1.2.2")], {}), (0, ""))

    def test_an_explicit_tag_wins_over_the_base(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            base = self.write_base(temp, "1.2.3")
            self.assertEqual(release_preflight.release_tag(root, "v9.9.9", base), "v9.9.9")
            code, err = self.run_main(root, ["--tag", "v9.9.9", "--base-init", base], {})
        self.assertEqual(code, 1)
        self.assertIn("does not match", err)

    def test_a_base_without_a_version_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            base = Path(temp) / "base_init.py"
            base.write_text('"""Doc."""\n')
            with self.assertRaises(ValueError):
                release_preflight.release_tag(root, None, str(base))


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
