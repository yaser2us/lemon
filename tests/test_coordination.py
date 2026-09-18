import io
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from lemon.__main__ import main
from lemon.coordination import group_questions, issue_ledger, valid_issue_updates
from lemon.discussion import run_discussion, save_discussion, validate_discussion
from lemon.proposal import proposal_lines
from test_discussion import DiscussionClient


QUESTION = "What recipient identifier type should we model?"


class DuitNowClient(DiscussionClient):
    def submit(self, observation, **kwargs):
        value, usage = super().submit(observation, **kwargs)
        value["questions"] = [QUESTION]
        value["proposal"].update(summary="Model RM100 from Maybank to someone else's CIMB account via DuitNow.", changes=[])
        if len(observation["transcript"]) == 1:
            value["proposal"]["disagreements"] = [{"message_id": "chat-0001", "detail": "A timeout may leave us without a bank reference."}]
        if observation["round"] == 2 and len(observation["transcript"]) == 6:
            value["issue_updates"] = [{"issue_id": "chat-0002-issue-1", "status": "resolved", "evidence_message_id": "chat-0005",
                                       "reason": "Reviewer clarified that the model retains unknown outcome without assuming a bank reference."}]
        return value, usage


class CoordinationTests(unittest.TestCase):
    def test_duitnow_questions_consolidate_and_reviewer_is_not_user(self):
        client = DuitNowClient()
        first = run_discussion("from maybank i want to transfer 100rm to cimb via duitnow.", client, rounds=1)
        proposal = first["final_state"]["proposal"]
        self.assertEqual(len(proposal["coordinated_questions"]), 1)
        self.assertEqual(len(proposal["coordinated_questions"][0]["owners"]), 4)
        second = run_discussion(None, client, rounds=1, previous=first,
                                reviewer_feedback="Retain an unknown outcome without assuming a bank reference.")
        p = second["final_state"]["proposal"]
        self.assertEqual(p["user_inputs"], proposal["user_inputs"])
        self.assertEqual(p["reviewer_inputs"][0]["source"], "chat-0005")
        self.assertEqual(len(p["positions"]), 4)
        self.assertEqual(p["issues"][0]["status"], "resolved")
        self.assertEqual(p["disagreements"], [])
        self.assertIn("Reviewer feedback — not user decisions", "\n".join(proposal_lines(p)))
        self.assertEqual(first["events"], second["events"][:len(first["events"])])
        validate_discussion(second)

    def test_omission_is_not_resolution_and_only_owner_can_close(self):
        first = run_discussion("DuitNow simulation", DuitNowClient(), rounds=1)
        second = run_discussion(None, DiscussionClient(), rounds=1, previous=first, user_message="someone else. name and type.")
        self.assertEqual(second["final_state"]["proposal"]["issues"][0]["status"], "open")
        transcript = second["final_state"]["messages"]
        update = {"issue_id": "chat-0002-issue-1", "status": "resolved", "reason": "Explicit later evidence", "evidence_message_id": "chat-0005"}
        self.assertTrue(valid_issue_updates([update], transcript, "backend-agent"))
        for actor, patch_value in (("test-agent", {}), ("backend-agent", {"evidence_message_id": "chat-0001"}),
                                   ("backend-agent", {"issue_id": "invented"}), ("backend-agent", {"reason": ""})):
            self.assertFalse(valid_issue_updates([{**update, **patch_value}], transcript, actor))

    def test_resolved_issue_can_be_reopened_with_later_evidence(self):
        client = DuitNowClient()
        first = run_discussion("DuitNow simulation", client, rounds=1)
        resolved = run_discussion(None, client, rounds=1, previous=first, reviewer_feedback="Do not assume reference availability.")
        messages = deepcopy(resolved["final_state"]["messages"])
        update = {"issue_id": "chat-0002-issue-1", "status": "open", "reason": "A later message reintroduces the assumption.", "evidence_message_id": "chat-0009"}
        self.assertTrue(valid_issue_updates([update], messages, "backend-agent"))
        messages.append({"id": "chat-0010", "sender": "backend-agent", "payload": {"issue_updates": [update]}})
        self.assertEqual(issue_ledger(messages)[0]["status"], "open")
        self.assertEqual(len(issue_ledger(messages)[0]["history"]), 2)
        reasserted = deepcopy(resolved["final_state"]["messages"])
        reasserted.append({"id": "chat-0010", "sender": "backend-agent", "payload": {"proposal": {
            "disagreements": [{"message_id": "chat-0001", "detail": "A timeout may leave us without a bank reference."}]}}})
        self.assertEqual(issue_ledger(reasserted)[0]["status"], "open")

    def test_grouping_ignores_case_spacing_and_end_punctuation_not_distinct_meanings(self):
        rows = [{"text": text, "owner": "agent-" + str(i), "source": str(i)} for i, text in enumerate(
            ["Which ID type?", " which  ID type? ", "WHICH ID TYPE", "Who is the recipient?"])]
        grouped = group_questions(rows)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(grouped[0]["owners"]), 3)

    def test_cli_preserves_both_feedback_sources(self):
        first = run_discussion("DuitNow simulation", DiscussionClient(), rounds=1)
        with tempfile.TemporaryDirectory() as folder:
            raw, _ = save_discussion(first, folder)
            client = DiscussionClient()
            with patch("lemon.__main__.load_configuration", return_value=("test", "model")), patch("lemon.__main__.AnthropicClient", return_value=client), patch("builtins.input", side_effect=AssertionError("No prompt")), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["chat", "--resume", str(raw), "--message", "someone else. name and type.",
                                       "--reviewer-feedback", "Do not invent bank policies.", "--rounds", "1", "--output", folder]), 0)
            transcript = client.observations[0]["transcript"]
            self.assertEqual(transcript[-2]["sender"], "user")
            self.assertEqual(transcript[-2]["explanation"], "someone else. name and type.")
            self.assertEqual(transcript[-1]["sender"], "reviewer")
            self.assertNotEqual(transcript[-2]["id"], transcript[-1]["id"])
            self.assertIn("coordination", client.observations[0])


if __name__ == "__main__":
    unittest.main()
