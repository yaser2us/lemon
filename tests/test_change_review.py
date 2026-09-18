import io
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from lemon.__main__ import main
from lemon.change_review import review_changes, change_review_lines
from lemon.discussion import approve_proposal, run_discussion, save_discussion
from test_discussion import DiscussionClient


class RevisedClient(DiscussionClient):
    def submit(self, *args, **kwargs):
        value, usage = super().submit(*args, **kwargs)
        value["questions"] = []
        if self.requests == 1:
            value["proposal"]["summary"] = "Let guests book after email verification."
            value["proposal"]["assumptions"] = ["Email verification exists."]
        if self.requests == 2:
            value["proposal"]["disagreements"] = [{"message_id": "chat-0001", "detail": "Membership scope needs revision."}]
        return value, usage


class ChangeReviewTests(unittest.TestCase):
    def baseline(self):
        return approve_proposal(run_discussion("Booking", DiscussionClient(), rounds=1), 4)

    def revised(self):
        return run_discussion(None, RevisedClient(), rounds=1, previous=self.baseline(), user_message="Allow guests too.")

    def test_additions_changes_removals_and_unchanged_have_exact_sources(self):
        revised = self.revised()
        review = review_changes(revised["final_state"])
        roles = {e["item"]: e for e in review["entries"] if e["section"] == "Role proposals"}
        self.assertEqual(roles["product-agent"]["status"], "changed")
        self.assertEqual(roles["product-agent"]["before"], "Propose a member booking flow.")
        self.assertEqual(roles["product-agent"]["after"], "Let guests book after email verification.")
        self.assertEqual(roles["backend-agent"]["status"], "unchanged")
        self.assertNotEqual(roles["backend-agent"]["before_source"], roles["backend-agent"]["after_source"])
        assumptions = [e for e in review["entries"] if e["section"] == "Assumptions" and e["item"][0] == "product-agent"]
        self.assertEqual({e["status"] for e in assumptions}, {"added", "removed"})
        questions = [e for e in review["entries"] if e["section"] == "Open questions"]
        self.assertEqual({e["status"] for e in questions}, {"removed"})
        self.assertEqual(review["feedback"], [{"source": "chat-0006", "text": "Allow guests too."}])
        self.assertEqual(review["remaining_disagreements"][0]["owner"], "backend-agent")

    def test_reported_changes_do_not_decide_actual_classification(self):
        revised = self.revised()
        review = review_changes(revised["final_state"])
        # The offline fixture claims it restricted booking to members, despite
        # proposing guests. Preserve that claim, but compare actual summaries.
        self.assertIn("Restrict booking to members.", [r["text"] for r in review["reported_changes"]])
        role = next(e for e in review["entries"] if e["section"] == "Role proposals" and e["item"] == "product-agent")
        self.assertEqual(role["after"], "Let guests book after email verification.")

    def test_reapproval_preserves_comparison_and_next_draft_uses_new_baseline(self):
        revised = self.revised()
        before = review_changes(revised["final_state"])
        approved = approve_proposal(revised, 9)
        self.assertEqual(review_changes(approved["final_state"]), before)
        next_draft = run_discussion(None, DiscussionClient(), rounds=1, previous=approved, user_message="Add a waiting list.")
        self.assertEqual(review_changes(next_draft["final_state"])["baseline_revision"], 9)

    def test_no_baseline_is_explicit_and_does_not_change_state(self):
        run = run_discussion("Booking", DiscussionClient(), rounds=1)
        original = deepcopy(run)
        review = review_changes(run["final_state"])
        self.assertIsNone(review["baseline_revision"])
        self.assertIn("No approved baseline yet", "\n".join(change_review_lines(review)))
        self.assertEqual(run, original)

    def test_partial_responses_remain_visible(self):
        client = RevisedClient()
        client.max_requests = 1
        run = run_discussion(None, client, rounds=1, previous=self.baseline(), user_message="Allow guests too.")
        review = review_changes(run["final_state"])
        self.assertEqual(set(review["awaiting_response"]), {"backend-agent", "ui-agent", "test-agent"})
        self.assertIn("Awaiting response", "\n".join(change_review_lines(review)))

    def test_feedback_from_multiple_batches_is_kept_since_approval(self):
        run = run_discussion(None, DiscussionClient(), rounds=1, previous=self.revised(), user_message="Add a waiting list.")
        review = review_changes(run["final_state"])
        self.assertEqual(len(review["feedback"]), 2)
        self.assertEqual({c["feedback_source"] for c in review["reported_changes"]}, {f["source"] for f in review["feedback"]})

    def test_offline_cli_and_export_show_change_review_before_reapproval(self):
        with tempfile.TemporaryDirectory() as directory:
            source, report = save_discussion(self.revised(), directory)
            text = source.with_suffix(".changes.md").read_text()
            self.assertIn("Before [chat-0001]", text)
            self.assertIn("Remaining reported disagreements", text)
            self.assertIn("Change review", report.read_text())
            with patch("builtins.input", side_effect=["/changes", "/approve 9", "/quit"]), patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["chat", "--resume", str(source), "--output", directory]), 0)
                displayed = output.getvalue()
                self.assertLess(displayed.index("CHANGE REVIEW"), displayed.index("Approval saved"))
                self.assertIn("Let guests book", displayed)


if __name__ == "__main__":
    unittest.main()
