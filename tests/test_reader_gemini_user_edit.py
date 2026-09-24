# SPDX-License-Identifier: MIT
"""A Gemini write or edit the user changed before accepting it is not measured as a write.

Gemini records the user's version in the call's args with `modified_by_user: true`, and keeps
an earlier version in `ai_proposed_content`, which may itself be an edit of the user's. The
records here are synthetic, built from those documented shapes.
"""
import unittest

from ruleprobe import run

from test_reader_gemini import TreeTest, call, gemini_record, meta, user

PATH = "/workspace/demo-project/deploy/aws.ini"
SECRET = "aws_secret_access_key = wJalrEXAMPLEKEY0000EXAMPLEKEY0000\n"
TEXT_ARGS = ("content", "new_string", "old_string", "ai_proposed_content")


def write_args(**extra):
    return dict({"file_path": PATH, "content": "[default]\n" + SECRET}, **extra)


def replace_args(**extra):
    return dict({"file_path": PATH, "instruction": "add the key",
                 "old_string": "[default]\n", "new_string": "[default]\n" + SECRET}, **extra)


class UserEditTests(TreeTest):

    def calls(self, *calls):
        return self.tree.session([meta(), user("u1", "go"),
                                  gemini_record("g1", "", list(calls))])

    def only_use(self, native, args):
        session = self.calls(call("c1", native, args))
        uses = self.uses(session)
        self.assertEqual(len(uses), 1)
        return session, uses[0]

    def assert_native_without_text(self, native, args):
        session, use = self.only_use(native, args)
        self.assertEqual(use["name"], native)
        for key in TEXT_ARGS:
            self.assertNotIn(key, use["input"])
        self.assertEqual(use["input"]["file_path"], PATH)
        result = [e for e in session.events if e["kind"] == "tool_result"][0]
        self.assertEqual(result["tool_name"], native)
        self.assertEqual(run(session.events, strict=True), {})
        return use

    def test_an_edited_write_with_a_proposal_stays_native_without_its_text(self):
        use = self.assert_native_without_text("write_file", write_args(
            modified_by_user=True, ai_proposed_content="[default]\n"))
        self.assertIs(use["input"]["modified_by_user"], True)

    def test_an_edited_write_without_a_proposal_stays_native_without_its_text(self):
        self.assert_native_without_text("write_file", write_args(modified_by_user=True))

    def test_an_edited_replace_with_a_proposal_stays_native_without_its_text(self):
        use = self.assert_native_without_text("replace", replace_args(
            modified_by_user=True, ai_proposed_content="region = us-east-1\n"))
        self.assertEqual(use["input"]["instruction"], "add the key")

    def test_an_edited_replace_without_a_proposal_stays_native_without_its_text(self):
        self.assert_native_without_text("replace", replace_args(modified_by_user=True))

    def test_a_truthy_flag_that_is_not_true_counts_as_edited(self):
        for flag in (1, "true", "yes"):
            with self.subTest(flag=flag):
                self.assert_native_without_text("write_file",
                                                write_args(modified_by_user=flag))

    def test_a_proposal_without_the_flag_counts_as_edited(self):
        for native, args in (("write_file", write_args(ai_proposed_content="x")),
                             ("replace", replace_args(ai_proposed_content="x"))):
            with self.subTest(tool=native):
                self.assert_native_without_text(native, args)

    def test_a_false_flag_with_no_proposal_is_an_ordinary_write(self):
        _session, use = self.only_use("write_file", write_args(modified_by_user=False))
        self.assertEqual(use["name"], "Write")

    def test_a_relative_file_path_on_an_edited_call_is_resolved(self):
        for native in ("write_file", "replace"):
            with self.subTest(tool=native):
                _session, use = self.only_use(native, {
                    "file_path": "src/../deploy/aws.ini", "content": SECRET,
                    "new_string": SECRET, "modified_by_user": True})
                self.assertEqual(use["input"]["file_path"], PATH)

    def test_an_unedited_write_is_unchanged(self):
        args = write_args()
        session, use = self.only_use("write_file", dict(args))
        self.assertEqual((use["name"], use["input"]), ("Write", args))
        self.assertEqual(len(run(session.events, strict=True)["secrets/secret-in-write"]), 1)

    def test_a_secret_only_the_user_typed_is_not_the_agents_write(self):
        # The retrospective's reproduction: the model proposed a clean file and the user
        # typed the secret in before accepting it.
        session = self.calls(call("c1", "write_file", write_args(
            modified_by_user=True, ai_proposed_content="[default]\n")))
        self.assertNotIn("secrets/secret-in-write", run(session.events, strict=True))


if __name__ == "__main__":
    unittest.main()
