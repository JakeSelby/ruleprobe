# SPDX-License-Identifier: MIT
"""`ruleprobe bind`: the plan, the bindings file `--apply` writes, and how `report` reads it.

Every test runs in a synthetic home under a temporary directory, with `HOME`, `USERPROFILE`
and `XDG_CONFIG_HOME` pointed into it, so no test reads or writes the real one.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ruleprobe import bindings
from ruleprobe.cli import main
from ruleprobe.declarative import parse
from ruleprobe.rules import load_bundle
from test_envelope import no_network_no_writes

GIT = "# Git\n\nNever force-push to main unless a release manager says so.\n"
STYLE = "# Style\n\nKeep functions short.\n"
RULES = GIT + "\n" + STYLE
FORCE = "git-safety/force-push-default"


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        code = main(list(argv), out=out)
    return code, out.getvalue(), err.getvalue()


def transcript_line(cwd, stamp, message, kind="assistant"):
    return json.dumps({"type": kind, "timestamp": stamp, "sessionId": "sess-bind",
                       "cwd": cwd, "message": message}) + "\n"


class BindTestCase(unittest.TestCase):
    """A home holding a rules folder (`~/rules/git.md`), a project the one transcript ran in
    (`~/work/app/CLAUDE.md`), and that transcript; the working directory is a neutral folder
    outside both."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="ruleprobe-bind-")
        self.addCleanup(shutil.rmtree, self.base, True)
        self.home = os.path.join(self.base, "home")
        self.rules = os.path.join(self.home, "rules")
        self.project = os.path.join(self.home, "work", "app")
        self.config = os.path.join(self.home, ".config")
        self.write(os.path.join(self.rules, "git.md"), RULES)
        self.write(os.path.join(self.project, "CLAUDE.md"), RULES)
        push = {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                "input": {"command": "git push --force origin main"}}
        self.write(os.path.join(self.home, ".claude", "projects", "-work-app", "sess.jsonl"),
                   transcript_line(self.project, "2026-09-20T10:00:00.000Z",
                                   {"role": "user", "content": "ship it"}, kind="user")
                   + transcript_line(self.project, "2026-09-20T10:00:05.000Z",
                                     {"id": "msg_1", "model": "claude-opus-5",
                                      "content": [push]}))
        patched = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home,
                                               "XDG_CONFIG_HOME": self.config})
        patched.start()
        self.addCleanup(patched.stop)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.neutral = os.path.join(self.base, "elsewhere")
        os.makedirs(self.neutral)
        os.chdir(self.neutral)

    def write(self, path, text):
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def snapshot(self):
        out = []
        for base, dirs, files in os.walk(self.base):
            dirs.sort()
            for name in sorted(dirs + files):
                path = os.path.join(base, name)
                out.append((path, os.stat(path).st_mtime_ns))
        return out

    @property
    def global_file(self):
        return os.path.join(self.config, "ruleprobe", "bindings.yaml")

    def plan(self, *argv):
        code, text, _err = run_cli("bind", "--plan", *argv)
        self.assertEqual(code, 0)
        return text

    def choose(self, text, rule, detector):
        """The plan `text` with `bind:` set to `detector` for `rule`, written to a file."""
        doc = parse(text)
        for item in doc["sections"]:
            if item["rule"] == rule:
                item["bind"] = detector
        path = os.path.join(self.base, "plan-%d.json" % len(os.listdir(self.base)))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return path

    def bind_git(self, *argv):
        """Plan and apply `git.md#git` -> force-push-default under `--rules ~/rules`."""
        plan = self.choose(self.plan("--rules", self.rules), "git.md#git", FORCE)
        code, out, err = run_cli("bind", "--apply", plan, "--rules", self.rules, *argv)
        self.assertEqual(code, 0, err)
        return out

    def rule_line(self, text, rule):
        return [line for line in text.split("\n") if rule in line][0]


class PlanTests(BindTestCase):

    def test_the_plan_lists_each_unmeasured_section_sorted_with_its_candidates_and_reason(self):
        doc = parse(self.plan("--rules", self.rules))
        self.assertEqual([item["rule"] for item in doc["sections"]],
                         ["git.md#git", "git.md#style"])
        git, style = doc["sections"]
        self.assertEqual(git["candidates"][0]["detector"], FORCE)
        self.assertIn("unbound by unless", git["candidates"][0]["evidence"])
        self.assertIn("exception or condition (unless)", git["reason"])
        self.assertIsNone(git["bind"])
        self.assertEqual(len(git["sha256"]), 64)
        # No pattern matched, so no candidate is guessed.
        self.assertEqual(style["candidates"], [])
        self.assertEqual(style["reason"], bindings.NO_MATCH)

    def test_the_plan_text_opens_with_how_to_use_it(self):
        text = self.plan("--rules", self.rules)
        self.assertTrue(text.startswith("# ruleprobe bind plan"))
        self.assertIn("ruleprobe bind --apply", text)

    def test_candidates_rank_by_sentences_matched_then_catalog_order(self):
        self.write(os.path.join(self.rules, "git.md"),
                   "# Git\n\nNever force-push to main if it is late. Never force-push to "
                   "main when tired. Use uv, not pip, when it is late.\n")
        doc = parse(self.plan("--rules", self.rules))
        ranked = [c["detector"] for c in doc["sections"][0]["candidates"]]
        self.assertEqual(ranked, [FORCE, "package-manager/pip-install"])
        self.assertIn("2 sentences matched", doc["sections"][0]["candidates"][0]["evidence"])

    def test_a_rule_id_the_subset_cannot_spell_points_at_json(self):
        self.write(os.path.join(self.rules, "odd\x01.md"), GIT)
        code, out, err = run_cli("bind", "--plan", "--rules", self.rules)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--json", err)
        self.assertEqual(run_cli("bind", "--plan", "--json", "--rules", self.rules)[0], 0)

    def test_json_is_the_same_plan_as_data(self):
        text = self.plan("--rules", self.rules)
        self.assertEqual(json.loads(self.plan("--rules", self.rules, "--json")), parse(text))

    def test_a_measured_section_is_not_in_the_plan(self):
        self.write(os.path.join(self.rules, "git.md"), "# Git\n\nNever force-push to main.\n")
        doc = parse(self.plan("--rules", self.rules))
        self.assertEqual(doc["sections"], [])

    def test_the_plan_finds_rule_files_through_the_transcripts_with_no_rules(self):
        doc = parse(self.plan())
        self.assertIn("~/work/app/CLAUDE.md#git", [item["rule"] for item in doc["sections"]])

    def test_the_plan_writes_nothing(self):
        before = self.snapshot()
        with no_network_no_writes() as attempts:
            code, _text, _err = run_cli("bind", "--plan")
            json_code, _data, _err = run_cli("bind", "--plan", "--json", "--rules", self.rules)
        self.assertEqual((code, json_code, attempts), (0, 0, []))
        self.assertEqual(self.snapshot(), before)


class ApplyTests(BindTestCase):

    def test_apply_writes_the_global_sidecar_sorted_with_no_timestamp(self):
        out = self.bind_git()
        digest = bindings.section_digest(
            "Git", ["Never force-push to main unless a release manager says so."])
        self.assertEqual(self.read(self.global_file),
                         "bindings:\n"
                         "  - detector: %s\n"
                         "    path: \"~/rules/git.md\"\n"
                         "    section: git\n"
                         "    sha256: \"%s\"\n"
                         "version: 1\n" % (FORCE, digest))
        self.assertIn("recorded in ~/.config/ruleprobe/bindings.yaml", out)
        # The rule file itself is never edited.
        self.assertEqual(self.read(os.path.join(self.rules, "git.md")), RULES)

    def test_project_writes_the_repository_s_file_with_a_project_relative_path(self):
        repo = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        self.write(os.path.join(repo, "rules", "git.md"), RULES)
        os.chdir(repo)
        plan = self.choose(self.plan("--rules", "rules"), "git.md#git", FORCE)
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", "rules", "--project")
        self.assertEqual(code, 0, err)
        written = parse(self.read(os.path.join(repo, ".ruleprobe", "bindings.yaml")))
        self.assertEqual(written["bindings"][0]["path"], "rules/git.md")
        self.assertFalse(os.path.exists(self.global_file))

    def test_an_unknown_detector_id_is_refused_and_nothing_is_written(self):
        plan = self.choose(self.plan("--rules", self.rules), "git.md#git", "made/up")
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 2)
        self.assertIn("unknown detector id made/up", err)
        self.assertIn("nothing written", err)
        self.assertFalse(os.path.exists(self.global_file))

    def test_one_refused_choice_writes_none_of_the_others(self):
        text = self.plan("--rules", self.rules)
        doc = parse(text)
        doc["sections"][0]["bind"] = FORCE
        doc["sections"][1]["bind"] = "made/up"
        plan = os.path.join(self.base, "plan.json")
        with open(plan, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        self.assertEqual(run_cli("bind", "--apply", plan, "--rules", self.rules)[0], 2)
        self.assertFalse(os.path.exists(self.global_file))

    def test_a_detector_from_the_user_s_own_detector_file_may_be_named(self):
        self.write(os.path.join(self.config, "ruleprobe", "detectors.yaml"),
                   "detectors:\n  - id: mine/style\n    rule: style\n    event: tool_use\n"
                   "    when:\n      command:\n        starts_with: wc\n")
        plan = self.choose(self.plan("--rules", self.rules), "git.md#style", "mine/style")
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 0, err)
        _code, text, _err = run_cli("report", "--rules", self.rules)
        self.assertIn("user-bound, mine/style", self.rule_line(text, "git.md#style"))

    def test_a_section_changed_since_the_plan_is_refused(self):
        plan = self.choose(self.plan("--rules", self.rules), "git.md#git", FORCE)
        self.write(os.path.join(self.rules, "git.md"), RULES.replace("main", "trunk"))
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 2)
        self.assertIn("changed since the plan", err)

    def test_a_catalog_measured_section_is_refused(self):
        text = self.plan("--rules", self.rules)
        self.write(os.path.join(self.rules, "git.md"), "# Git\n\nNever force-push to main.\n")
        doc = parse(text)
        doc["sections"][0]["bind"] = FORCE
        doc["sections"][0]["sha256"] = bindings.section_digest(
            "Git", ["Never force-push to main."])
        plan = os.path.join(self.base, "plan.json")
        with open(plan, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 2)
        self.assertIn("measured by the catalog", err)

    def test_binding_a_section_again_replaces_its_binding_and_keeps_the_rest(self):
        self.bind_git()
        plan = self.choose(self.plan("--rules", self.rules), "git.md#style",
                           "transcript-hygiene/whole-file-cat")
        self.assertEqual(run_cli("bind", "--apply", plan, "--rules", self.rules)[0], 0)
        doc = parse(self.read(self.global_file))
        self.assertEqual([(b["section"], b["detector"]) for b in doc["bindings"]],
                         [("git", FORCE), ("style", "transcript-hygiene/whole-file-cat")])
        # The git section is user-bound, so a fresh plan leaves it out; rebinding it from an
        # older plan replaces its detector rather than adding one.
        stale_plan = os.path.join(self.base, "older-plan.json")
        with open(stale_plan, "w", encoding="utf-8") as handle:
            json.dump({"sections": [{"rule": "git.md#git", "bind": "package-manager/pip-install",
                                     "sha256": doc["bindings"][0]["sha256"]}],
                       "version": 1}, handle)
        self.assertEqual(run_cli("bind", "--apply", stale_plan, "--rules", self.rules)[0], 0)
        doc = parse(self.read(self.global_file))
        self.assertEqual([(b["section"], b["detector"]) for b in doc["bindings"]],
                         [("git", "package-manager/pip-install"),
                          ("style", "transcript-hygiene/whole-file-cat")])

    def test_a_linked_bindings_file_is_never_written_through(self):
        target = os.path.join(self.base, "elsewhere.yaml")
        self.write(target, "bindings: []\nversion: 1\n")
        os.makedirs(os.path.dirname(self.global_file))
        os.symlink(target, self.global_file)
        plan = self.choose(self.plan("--rules", self.rules), "git.md#git", FORCE)
        code, _out, err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 2)
        self.assertIn("not a regular file", err)
        self.assertEqual(self.read(target), "bindings: []\nversion: 1\n")

    def test_a_plan_choosing_nothing_writes_nothing(self):
        plan = self.choose(self.plan("--rules", self.rules), "none", FORCE)
        code, out, _err = run_cli("bind", "--apply", plan, "--rules", self.rules)
        self.assertEqual(code, 0)
        self.assertIn("nothing to bind", out)
        self.assertFalse(os.path.exists(self.global_file))


class ReportTests(BindTestCase):

    def test_a_user_bound_rule_reads_measured_user_bound(self):
        self.bind_git()
        _code, text, _err = run_cli("report", "--rules", self.rules)
        line = self.rule_line(text, "git.md#git")
        self.assertTrue(line.startswith("  measured   git.md#git"), line)
        self.assertIn("user-bound, %s" % FORCE, line)
        self.assertNotIn("catalog-bound", line)
        _code, data, _err = run_cli("report", "--rules", self.rules, "--json")
        coverage = json.loads(data)["coverage"]
        self.assertEqual((coverage["measured"], coverage["user"], coverage["catalog"]),
                         (1, 1, 0))

    def test_the_bound_detector_joins_the_registry(self):
        self.bind_git()
        bundle = load_bundle(rules_dir=self.rules, config=False,
                             bindings=bindings.load_trusted())
        self.assertIn(FORCE, [d.id for d in bundle.registry()])
        unbound = load_bundle(rules_dir=self.rules, config=False)
        self.assertNotIn(FORCE, [d.id for d in unbound.registry()])

    def test_a_changed_section_is_stale_and_not_measured(self):
        self.bind_git()
        self.write(os.path.join(self.rules, "git.md"),
                   RULES.replace("release manager", "lead"))
        _code, text, _err = run_cli("report", "--rules", self.rules)
        line = self.rule_line(text, "git.md#git")
        self.assertTrue(line.startswith("  unmeasured"), line)
        self.assertIn("binding stale, run ruleprobe bind", line)
        doc = parse(self.plan("--rules", self.rules))
        self.assertEqual(doc["sections"][0]["stale"], [FORCE])
        self.assertIn("(unless)", doc["sections"][0]["reason"])

    def test_a_markup_only_change_keeps_the_binding(self):
        self.bind_git()
        self.write(os.path.join(self.rules, "git.md"),
                   RULES.replace("main", "`main`").replace("Never", "**Never**"))
        _code, text, _err = run_cli("report", "--rules", self.rules)
        self.assertIn("user-bound", self.rule_line(text, "git.md#git"))

    def test_a_cloned_project_s_bindings_file_is_ignored_and_counted(self):
        digest = bindings.section_digest(
            "Git", ["Never force-push to main unless a release manager says so."])
        entry = ("bindings:\n  - detector: %s\n    path: %%s\n    section: git\n"
                 "    sha256: \"%s\"\nversion: 1\n" % (FORCE, digest))
        self.write(os.path.join(self.project, ".ruleprobe", "bindings.yaml"),
                   entry % "CLAUDE.md")
        _code, text, _err = run_cli("report")
        line = self.rule_line(text, "~/work/app/CLAUDE.md#git")
        self.assertTrue(line.strip().startswith("unmeasured"), line)
        self.assertIn("bindings files ignored: 1", text)
        # The same binding in the global file is honoured, so only the source was refused.
        self.write(self.global_file, entry % "~/work/app/CLAUDE.md")
        _code, text, _err = run_cli("report")
        self.assertIn("user-bound, %s" % FORCE, self.rule_line(text, "~/work/app/CLAUDE.md#git"))

    def test_the_project_the_user_is_in_is_honoured(self):
        digest = bindings.section_digest(
            "Git", ["Never force-push to main unless a release manager says so."])
        self.write(os.path.join(self.project, ".ruleprobe", "bindings.yaml"),
                   "bindings:\n  - detector: %s\n    path: CLAUDE.md\n    section: git\n"
                   "    sha256: \"%s\"\nversion: 1\n" % (FORCE, digest))
        os.chdir(self.project)
        _code, text, _err = run_cli("report")
        self.assertIn("user-bound", self.rule_line(text, "~/work/app/CLAUDE.md#git"))
        self.assertNotIn("bindings files ignored", text)

    def test_a_binding_that_defines_a_detector_is_refused(self):
        digest = bindings.section_digest(
            "Git", ["Never force-push to main unless a release manager says so."])
        self.write(self.global_file,
                   "bindings:\n  - detector: evil/one\n    path: ~/rules/git.md\n"
                   "    section: git\n    sha256: \"%s\"\n"
                   "    when: {tool: {name: Bash}}\nversion: 1\n" % digest)
        _code, text, _err = run_cli("report", "--rules", self.rules)
        self.assertTrue(self.rule_line(text, "git.md#git").startswith("  unmeasured"))
        self.assertIn("when cannot be set here", text)
        self.assertNotIn("evil/one", run_cli("detectors", "--rules", self.rules)[1])

    def test_a_binding_naming_an_unknown_id_measures_nothing(self):
        digest = bindings.section_digest(
            "Git", ["Never force-push to main unless a release manager says so."])
        self.write(self.global_file,
                   "bindings:\n  - detector: made/up\n    path: ~/rules/git.md\n"
                   "    section: git\n    sha256: \"%s\"\nversion: 1\n" % digest)
        _code, text, _err = run_cli("report", "--rules", self.rules)
        line = self.rule_line(text, "git.md#git")
        self.assertTrue(line.startswith("  unmeasured"), line)
        self.assertIn("names made/up, which no detector holds", line)

    def test_no_config_reads_no_bindings(self):
        self.bind_git()
        _code, text, _err = run_cli("report", "--rules", self.rules, "--no-config")
        self.assertNotIn("user-bound", text)

    def test_report_still_writes_nothing(self):
        self.bind_git()
        self.write(os.path.join(self.project, ".ruleprobe", "bindings.yaml"),
                   "bindings: []\nversion: 1\n")
        before = self.snapshot()
        with no_network_no_writes() as attempts:
            code, _text, _err = run_cli("report")
            json_code, _data, _err = run_cli("report", "--json", "--rules", self.rules)
        self.assertEqual((code, json_code, attempts), (0, 0, []))
        self.assertEqual(self.snapshot(), before)


class DeterminismTests(BindTestCase):

    def test_the_plan_is_the_same_bytes_every_run(self):
        self.assertEqual(self.plan(), self.plan())
        self.assertEqual(self.plan("--json"), self.plan("--json"))

    def test_the_same_choices_in_any_order_write_the_same_bytes(self):
        text = self.plan("--rules", self.rules)
        doc = parse(text)
        doc["sections"][0]["bind"] = FORCE
        doc["sections"][1]["bind"] = ["transcript-hygiene/whole-file-cat",
                                      "package-manager/pip-install"]
        written = []
        for sections in (doc["sections"], list(reversed(doc["sections"]))):
            if os.path.exists(self.global_file):
                os.remove(self.global_file)
            plan = os.path.join(self.base, "plan.json")
            with open(plan, "w", encoding="utf-8") as handle:
                json.dump({"sections": sections, "version": 1}, handle)
            self.assertEqual(run_cli("bind", "--apply", plan, "--rules", self.rules)[0], 0)
            written.append(self.read(self.global_file))
        self.assertEqual(written[0], written[1])
        detectors = [b["detector"] for b in parse(written[0])["bindings"]]
        self.assertEqual(detectors, [FORCE, "package-manager/pip-install",
                                     "transcript-hygiene/whole-file-cat"])
        # Applying it again changes nothing.
        self.assertEqual(run_cli("bind", "--apply", plan, "--rules", self.rules)[0], 0)
        self.assertEqual(self.read(self.global_file), written[1])

    def test_the_digest_reads_the_text_the_binder_reads(self):
        plain = bindings.section_digest("Git", ["Never force-push to main."])
        self.assertEqual(bindings.section_digest("Git", ["**Never**  force-push to `main`."]),
                         plain)
        self.assertNotEqual(bindings.section_digest("Git", ["Never force-push to trunk."]),
                            plain)


class OptionTests(BindTestCase):

    def test_json_and_project_go_with_their_own_mode(self):
        self.assertEqual(run_cli("bind", "--apply", "x", "--json")[0], 2)
        self.assertEqual(run_cli("bind", "--plan", "--project")[0], 2)

    def test_a_plan_or_apply_is_required(self):
        with self.assertRaises(SystemExit):
            run_cli("bind")


if __name__ == "__main__":
    unittest.main()
