import unittest

import app


class ClaudeEnvironmentTests(unittest.TestCase):
    def setUp(self):
        app.STATE = app.load_seed()

    def test_seed_loads_expected_conversation(self):
        conversation = app.find_conversation("conv_release_plan")
        self.assertEqual(conversation["title"], "Claude launch checklist")

    def test_submit_prompt_appends_user_and_assistant_messages(self):
        before = len(app.find_conversation("conv_release_plan")["messages"])
        reply = app.submit_prompt("Review the release checklist and identify the blocker.")
        conversation = app.find_conversation("conv_release_plan")
        self.assertEqual(len(conversation["messages"]), before + 2)
        self.assertIn("Observed request excerpt", reply["content"])
        self.assertEqual(app.STATE["composer"]["draft"], "")

    def test_search_filters_visible_conversations(self):
        app.STATE["ui"]["searchQuery"] = "usage"
        visible = app.visible_conversations(app.STATE["ui"]["searchQuery"])
        self.assertEqual([item["id"] for item in visible], ["conv_usage_review"])

    def test_open_artifact_sets_ui_state(self):
        artifact = app.open_artifact("artifact_checklist")
        self.assertEqual(artifact["title"], "Launch checklist")
        self.assertEqual(app.STATE["ui"]["openArtifactId"], "artifact_checklist")

    def test_feedback_log_records_rating(self):
        entry = app.log_feedback("msg_2", "thumbs_up")
        self.assertEqual(entry["message_id"], "msg_2")
        self.assertEqual(app.STATE["feedback_log"][0]["rating"], "thumbs_up")


if __name__ == "__main__":
    unittest.main()
