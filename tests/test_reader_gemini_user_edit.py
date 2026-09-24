# SPDX-License-Identifier: MIT
"""A Gemini write or edit the user changed before accepting it is read as the model's.

Gemini records the user's version in the call's args with `modified_by_user: true` and the
model's proposal in `ai_proposed_content`. The records here are synthetic, built from those
documented shapes.
"""
import unittest

from ruleprobe import run

from test_reader_gemini import TreeTest, call, gemini_record, meta, user

PATH = "/workspace/demo-project/deploy/aws.ini"
SECRET = "aws_secret_access_key = wJalrEXAMPLEKEY0000EXAMPLEKEY0000\n"


class UserEditTests(TreeTest):

    def calls(self, *calls):
        return self.tree.session([meta(), user("u1", "go"),
                                  gemini_record("g1", "", list(calls))])

    def hits(self, session):
        return run(session.events, strict=True).get("secrets/secret-in-write", [])

    def test_an_edited_write_reads_the_models_proposal(self):
        session = self.calls(call("c1", "write_file", {
            "file_path": PATH, "content": "[default]\n", "modified_by_user": True,
            "ai_proposed_content": "[default]\nregion = us-east-1\n"}))
        use = self.uses(session)[0]
        self.assertEqual(use["name"], "Write")
        self.assertEqual(use["input"]["content"], "[default]\nregion = us-east-1\n")
        result = [e for e in session.events if e["kind"] == "tool_result"][0]
        self.assertEqual(result["tool_name"], "Write")

    def test_an_edited_write_with_no_proposal_stays_native(self):
        session = self.calls(call("c1", "write_file", {
            "file_path": PATH, "content": SECRET, "modified_by_user": True}))
        use = self.uses(session)[0]
        self.assertEqual(use["name"], "write_file")
        self.assertEqual(self.hits(session), [])

    def test_an_edited_replace_reads_the_proposed_new_string_and_drops_the_file(self):
        session = self.calls(call("c1", "replace", {
            "file_path": PATH, "instruction": "add a region",
            "old_string": "[default]\n", "new_string": "[default]\n" + SECRET,
            "modified_by_user": True, "ai_proposed_content": "region = us-east-1\n"}))
        use = self.uses(session)[0]
        self.assertEqual(use["name"], "Edit")
        self.assertEqual(use["input"]["new_string"], "region = us-east-1\n")
        self.assertNotIn("old_string", use["input"])
        self.assertEqual(self.hits(session), [])

    def test_an_edited_replace_with_no_proposal_stays_native(self):
        session = self.calls(call("c1", "replace", {
            "file_path": PATH, "old_string": "[default]\n", "new_string": SECRET,
            "modified_by_user": True}))
        self.assertEqual(self.uses(session)[0]["name"], "replace")
        self.assertEqual(self.hits(session), [])

    def test_an_unedited_write_is_unchanged(self):
        args = {"file_path": PATH, "content": SECRET}
        session = self.calls(call("c1", "write_file", dict(args)))
        use = self.uses(session)[0]
        self.assertEqual((use["name"], use["input"]), ("Write", args))
        self.assertEqual(len(self.hits(session)), 1)

    def test_a_secret_only_the_user_typed_is_not_the_agents_write(self):
        # The model proposed a clean file; the user typed the secret in before accepting it.
        session = self.calls(call("c1", "write_file", {
            "file_path": PATH, "content": "[default]\n" + SECRET, "modified_by_user": True,
            "ai_proposed_content": "[default]\n"}))
        self.assertEqual(self.hits(session), [])

    def test_a_secret_the_model_proposed_still_fires_after_the_user_edited_it(self):
        session = self.calls(call("c1", "write_file", {
            "file_path": PATH, "content": "[default]\n", "modified_by_user": True,
            "ai_proposed_content": "[default]\n" + SECRET}))
        self.assertEqual(len(self.hits(session)), 1)


if __name__ == "__main__":
    unittest.main()
