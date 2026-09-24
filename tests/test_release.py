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


SERIES_DECLARED = {"ruleprobe": ("report", "run"), "ruleprobe.shell": ("Parsed",)}


def write_contract(root, declared):
    """A contract test holding `declared` as its `DECLARED` literal, beside other code."""
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_contract.py").write_text(
        '"""Doc."""\nimport unittest\n\nDECLARED = {!r}\n\n\nclass T(unittest.TestCase):\n'
        '    pass\n'.format(declared))


def make_root(temp, version="1.2.3", heading="1.2.3 (2026-01-02)", unreleased=""):
    """A repository whose `v1.2.0` tag declared `SERIES_DECLARED`, and whose tree still does."""
    root = Path(temp)
    (root / "ruleprobe").mkdir()
    (root / "ruleprobe" / "__init__.py").write_text('"""Doc."""\n__version__ = "{}"\n'.format(version))
    (root / "CHANGELOG.md").write_text(CHANGELOG.format(heading=heading, unreleased=unreleased))
    write_contract(root, SERIES_DECLARED)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "-c", "user.email=test@example.invalid", "-c", "user.name=Test", "-c", "commit.gpgsign=false",
        "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "series")
    git(root, "tag", "v1.2.0")
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
            base = self.write_base(temp, "1.2.2")
            self.assertEqual(release_preflight.release_tag(root, None, base), "v1.2.3")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = self.run_main_stdout(root, ["--base-init", base])
        self.assertEqual(result, (0, ""))
        self.assertIn("checking as v1.2.3", out.getvalue())

    def run_main_stdout(self, root, argv):
        """`main(argv)` over `root` without the GitHub ref variables, leaving stdout to the caller."""
        clean = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REF_TYPE", "GITHUB_REF_NAME")}
        err = io.StringIO()
        with mock.patch.object(release_preflight, "ROOT", root), \
                mock.patch.dict(os.environ, clean, clear=True), contextlib.redirect_stderr(err):
            code = release_preflight.main(argv)
        return code, err.getvalue()

    def test_an_explicit_tag_wins_over_the_base(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            base = self.write_base(temp, "1.2.2")
            self.assertEqual(release_preflight.release_tag(root, None, base), "v1.2.3")
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


class SeriesContractTests(unittest.TestCase):
    """A patch release keeps every name its series' opening tag declared."""

    run_main = PreflightTests.run_main

    def test_the_series_tag_is_the_minor_opening_one(self):
        self.assertIsNone(release_preflight.series_tag("0.2.0"))
        self.assertEqual(release_preflight.series_tag("0.2.1"), "v0.2.0")
        self.assertEqual(release_preflight.series_tag("1.10.12"), "v1.10.0")

    def test_a_patch_release_keeping_every_name_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            write_contract(root, dict(SERIES_DECLARED, **{"ruleprobe.events": ("hit",)}))
            self.assertEqual(release_preflight.errors(root, tag="v1.2.3"), [])

    def test_a_patch_release_that_drops_a_name_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            write_contract(root, {"ruleprobe": ("run",), "ruleprobe.shell": ("Parsed",)})
            found = release_preflight.errors(root, tag="v1.2.3")
        self.assertEqual(found, ["tests/test_contract.py no longer declares ruleprobe.report, "
                                 "which v1.2.0 declared"])

    def test_a_name_moved_to_another_module_is_dropped_from_its_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            write_contract(root, {"ruleprobe": ("report", "run", "Parsed")})
            found = release_preflight.errors(root, tag="v1.2.3")
        self.assertEqual(found, ["tests/test_contract.py no longer declares ruleprobe.shell.Parsed, "
                                 "which v1.2.0 declared"])

    def test_a_release_candidate_from_the_base_is_checked(self):
        # A release PR in CI passes --base-init, not --tag, and must be refused the same way.
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            write_contract(root, {"ruleprobe": ("report", "run")})
            base = Path(temp) / "base_init.py"
            base.write_text('"""Doc."""\n__version__ = "1.2.2"\n')
            code, err = self.run_main(root, ["--base-init", str(base)], {})
        self.assertEqual(code, 1)
        self.assertIn("no longer declares ruleprobe.shell.Parsed", err)

    def test_a_drop_between_releases_waits_for_the_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            write_contract(root, {"ruleprobe": ("run",)})
            self.assertEqual(release_preflight.errors(root), [])

    def test_a_new_minor_may_drop_a_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp, version="1.3.0", heading="1.3.0 (2026-02-01)")
            write_contract(root, {"ruleprobe": ("run",)})
            self.assertEqual(release_preflight.errors(root, tag="v1.3.0"), [])

    def test_a_name_written_as_a_bare_string_is_an_error(self):
        # `("run")` without its comma is a string, which would otherwise read as r, u, n.
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            (root / "tests" / "test_contract.py").write_text(
                'DECLARED = {"ruleprobe": ("report", "run"), "ruleprobe.shell": ("Parsed")}\n')
            found = release_preflight.errors(root, tag="v1.2.3")
        self.assertEqual(len(found), 1)
        self.assertIn("is not a tuple or list of names", found[0])

    def test_a_prerelease_version_is_reported_not_raised(self):
        self.assertEqual(release_preflight.contract_errors(Path("."), "1.2.3rc1"),
                         ["cannot check the series contract of 1.2.3rc1: not a stable semantic version"])
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp, version="1.2.3rc1", heading="1.2.3rc1 (2026-01-02)")
            found = release_preflight.errors(root, tag="v1.2.3rc1")
        self.assertEqual(found, ["__version__ 1.2.3rc1 is not a stable semantic version"])

    def test_a_series_before_the_contract_is_not_checked(self):
        # v0.1.0 carries no contract test, so a 0.1 patch has no declared names to keep.
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(release_preflight.contract_errors(Path(temp), "0.1.1"), [])
            self.assertTrue(release_preflight.contract_errors(Path(temp), "0.2.1")[0].startswith(
                "cannot read the names v0.2.0 declared"))

    def test_a_missing_series_tag_is_an_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            git(root, "tag", "-d", "v1.2.0")
            found = release_preflight.errors(root, tag="v1.2.3")
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("cannot read the names v1.2.0 declared"), found)

    def test_a_contract_test_without_the_literal_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            for text in ('"""Doc."""\n', "DECLARED = dict(ruleprobe=('run',))\n", "DECLARED = ['run']\n"):
                with self.subTest(text=text):
                    (root / "tests" / "test_contract.py").write_text(text)
                    found = release_preflight.errors(root, tag="v1.2.3")
                    self.assertEqual(len(found), 1)
                    self.assertTrue(found[0].startswith("cannot read the names tests/test_contract.py"),
                                    found)
            (root / "tests" / "test_contract.py").unlink()
            found = release_preflight.errors(root, tag="v1.2.3")
        self.assertTrue(found[0].startswith("cannot read the names tests/test_contract.py"), found)

    def test_the_repository_contract_test_reads_as_its_declared_list(self):
        tests = str(Path(__file__).resolve().parent)
        if tests not in sys.path:
            sys.path.insert(0, tests)
        import test_contract
        root = Path(release_preflight.ROOT)
        text = (root / release_preflight.CONTRACT_TEST).read_text(encoding="utf-8")
        self.assertEqual(release_preflight.declared_names(text),
                         {(module, name) for module, names in test_contract.DECLARED.items()
                          for name in names})


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
    """git in `root` alone: no signing, no hook's repository variables, no parent repository."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")}
    env["GIT_CEILING_DIRECTORIES"] = str(Path(root).resolve().parent)
    return subprocess.check_output(["git", "-c", "tag.gpgSign=false", "-C", str(root), *args],
                                   text=True, env=env).strip()


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
