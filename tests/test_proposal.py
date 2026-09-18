import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.anthropic_reviewer import ReviewError
from lemon.chat import load_chat
from lemon.discussion import run_discussion, save_discussion, validate_contribution, validate_discussion
from lemon.events import EventLog, replay
from lemon.proposal import shared_proposal
from test_discussion import DiscussionClient


class ProposalTests(unittest.TestCase):
    def test_user_statements_and_agent_assumptions_stay_separate(self):
        run = run_discussion("Should visitors be allowed to book?", DiscussionClient(), rounds=1)
        proposal = run["final_state"]["proposal"]
        self.assertEqual(proposal["user_inputs"], [{"source": "scenario", "text": "Should visitors be allowed to book?"}])
        self.assertEqual(proposal["status"], "draft_for_user_review")
        self.assertEqual(proposal["changes_since_feedback"], [])
        for position in proposal["positions"]:
            self.assertEqual(position["assumptions"], ["Membership already exists."])
            self.assertTrue(position["source"].startswith("chat-"))
        self.assertEqual(replay(run["events"]), run["final_state"])

    def test_feedback_marks_old_positions_pending_and_records_new_changes(self):
        client = DiscussionClient()
        original = run_discussion("Public booking", client, rounds=1)
        run = run_discussion(None, client, rounds=1, previous=original, user_message="Correction: members only.")
        feedback = next(e for e in run["events"] if e["kind"] == "DISCUSSION_CHANGED" and e["data"]["after"]["reason"] == "USER_FEEDBACK")
        self.assertTrue(all(p["awaiting_feedback_response"] for p in feedback["data"]["after"]["proposal"]["positions"]))
        proposal = run["final_state"]["proposal"]
        self.assertEqual([i["text"] for i in proposal["user_inputs"]], ["Public booking", "Correction: members only."])
        self.assertFalse(any(p["awaiting_feedback_response"] for p in proposal["positions"]))
        self.assertEqual(len(proposal["changes_since_feedback"]), 4)
        self.assertTrue(all(c["feedback_source"] == "chat-0005" for c in proposal["changes_since_feedback"]))

    def test_disagreement_has_real_source_and_is_replaced_by_owners_update(self):
        class DisagreeClient(DiscussionClient):
            def submit(self, observation, **kwargs):
                value, usage = super().submit(observation, **kwargs)
                if len(observation["transcript"]) == 1:
                    value["proposal"]["disagreements"] = [{"message_id": "chat-0001", "detail": "Visitors conflict with membership scope."}]
                if len(observation["transcript"]) == 6:
                    value["issue_updates"] = [{"issue_id": "chat-0002-issue-1", "status": "resolved", "evidence_message_id": "chat-0005", "reason": "User confirmed members only."}]
                return value, usage

        client = DisagreeClient()
        original = run_discussion("Booking", client, rounds=1)
        self.assertEqual(original["final_state"]["proposal"]["disagreements"][0]["owner"], "backend-agent")
        updated = run_discussion(None, client, rounds=1, previous=original, user_message="Members only.")
        self.assertEqual(updated["final_state"]["proposal"]["disagreements"], [])
        self.assertEqual(len(original["final_state"]["proposal"]["disagreements"]), 1)

    def test_invalid_sources_and_invented_feedback_changes_are_rejected(self):
        client = DiscussionClient()
        value, _ = client.submit({"round": 1, "scenario": "Booking", "transcript": []}, system_prompt="", schema={})
        for update in ({"disagreements": [{"message_id": "invented", "detail": "No"}]}, {"changes": ["User approved payments"]}, {"summary": ""}):
            candidate = deepcopy(value)
            candidate["proposal"].update(update)
            with self.assertRaises(ReviewError):
                validate_contribution(candidate, [])

    def test_legacy_history_remains_readable_and_new_projection_is_checked(self):
        run = run_discussion("Booking", DiscussionClient(), rounds=1)
        state = deepcopy(run["final_state"])
        state.pop("proposal")
        for message in state["messages"]:
            message["payload"].pop("proposal")
        self.assertTrue(all(not p["structured"] for p in shared_proposal(state)["positions"]))
        state["proposal"] = shared_proposal(state)
        state["proposal"]["user_inputs"][0]["text"] = "Invented approval"
        log = EventLog()
        log.append(0, "RUN_STARTED", {"initial_state": state})
        with self.assertRaisesRegex(ValueError, "Shared proposal differs"):
            validate_discussion({**run, "events": log.events, "final_state": state})

    def test_proposal_artifact_and_command_work_without_api_calls(self):
        run = run_discussion("Booking", DiscussionClient(), rounds=1)
        with tempfile.TemporaryDirectory() as directory:
            raw, report = save_discussion(run, directory)
            self.assertEqual(load_chat(raw), run)
            self.assertIn("Current proposal by role", raw.with_suffix(".proposal.md").read_text())
            self.assertIn("Shared proposal", report.read_text())
            with patch("builtins.input", side_effect=["/proposal", "/quit"]), patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["chat", "--resume", str(raw), "--delay", "0"]), 0)
                self.assertIn("SHARED PROPOSAL", output.getvalue())
                self.assertIn("Membership already exists.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
