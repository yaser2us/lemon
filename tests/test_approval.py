import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.chat import load_chat
from lemon.discussion import approve_proposal, run_discussion, save_discussion
from lemon.events import EventLog, replay
from test_discussion import DiscussionClient


class ApprovalTests(unittest.TestCase):
    def draft(self):
        return run_discussion("Booking example", DiscussionClient(), rounds=1)

    def test_exact_snapshot_approval_replays_without_calls_or_changing_draft(self):
        draft = self.draft()
        approved = approve_proposal(draft, 4)
        self.assertEqual(approved["events"][:-1], draft["events"])
        self.assertEqual(approved["api_requests"], draft["api_requests"])
        self.assertEqual(approved["final_state"]["proposal"]["status"], "approved_by_user")
        self.assertEqual(approved["final_state"]["approvals"][0]["proposal"], draft["final_state"]["proposal"])
        self.assertEqual(draft["final_state"]["proposal"]["status"], "draft_for_user_review")
        self.assertEqual(replay(approved["events"]), approved["final_state"])
        self.assertEqual(approve_proposal(approved, 4), approved)
        self.assertEqual(approved["final_state"]["questions"], draft["final_state"]["questions"])

    def test_new_feedback_is_a_draft_and_agents_see_approved_baseline(self):
        approved = approve_proposal(self.draft(), 4)
        client = DiscussionClient()
        revised = run_discussion(None, client, rounds=1, previous=approved, user_message="Allow guest bookings too.")
        self.assertEqual(revised["final_state"]["proposal"]["status"], "draft_for_user_review")
        self.assertEqual(revised["final_state"]["approvals"], approved["final_state"]["approvals"])
        self.assertTrue(all(o["approved_baseline"]["revision"] == 4 for o in client.observations))
        self.assertEqual(approve_proposal(revised, 9)["final_state"]["proposal"]["status"], "approved_by_user")
        with self.assertRaisesRegex(ValueError, "Stale"):
            approve_proposal(revised, 4)

    def test_approval_cannot_be_inserted_as_a_regular_state_change(self):
        draft = self.draft()
        log = EventLog()
        log.events, log.state = deepcopy(draft["events"]), deepcopy(draft["final_state"])
        forged = {**deepcopy(log.state), "approvals": [{"actor": "backend-agent"}]}
        with self.assertRaisesRegex(ValueError, "cannot change user approvals"):
            log.append(5, "DISCUSSION_CHANGED", {"before": log.state, "after": forged})

    def test_forged_or_stale_approval_event_is_rejected(self):
        draft = self.draft()
        event = approve_proposal(draft, 4)["events"][-1]
        for patch_value in ({"actor": "test-agent"}, {"revision": 3}, {"proposal_hash": "fake"}, {"proposal": {}}):
            log = EventLog()
            log.events, log.state = deepcopy(draft["events"]), deepcopy(draft["final_state"])
            with self.assertRaises(ValueError):
                log.append(5, "PROPOSAL_APPROVED", {**event["data"], **patch_value})

    def test_offline_cli_approval_and_approved_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source, _ = save_discussion(self.draft(), folder)
            old_bytes = source.read_bytes()
            with patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["chat", "--resume", str(source), "--approve-revision", "4", "--output", folder]), 0)
            self.assertEqual(source.read_bytes(), old_bytes)
            approved_file = next(p for p in Path(folder).glob("*.json") if p != source)
            self.assertEqual(load_chat(approved_file)["final_state"]["proposal"]["status"], "approved_by_user")
            self.assertIn("approved_by_user", next(Path(folder).glob("*.approved-r4.md")).read_text())

    def test_interactive_approval_commands_bind_to_displayed_revision(self):
        for command in ("/approve 4", "Approve this proposal."):
            with tempfile.TemporaryDirectory() as folder:
                source, _ = save_discussion(self.draft(), folder)
                with patch("builtins.input", side_effect=["/approve 3", command, "/versions", "/quit"]), patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(main(["chat", "--resume", str(source), "--output", folder]), 0)
                    self.assertIn("Stale proposal revision", output.getvalue())
                    self.assertIn("User approved revision 4", output.getvalue())
                self.assertEqual(len(list(Path(folder).glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
