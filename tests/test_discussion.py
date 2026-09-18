import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.anthropic_reviewer import AnthropicClient, ReviewError
from lemon.chat import ChatViewer, load_chat
from lemon.discussion import ROLES, SCHEMA, run_discussion, save_discussion, validate_contribution
from lemon.events import replay


class DiscussionClient:
    model, max_requests = "offline-fixture", 8

    def __init__(self):
        self.requests, self.observations, self.prompts = 0, [], []

    def submit(self, observation, system_prompt, schema):
        if self.requests >= self.max_requests:
            raise ReviewError("REVIEW_BUDGET_EXHAUSTED")
        self.requests += 1
        self.observations.append(deepcopy(observation))
        self.prompts.append(system_prompt)
        return {"kind": "PROPOSE" if observation["round"] == 1 else "REVISE", "recipient": "team",
                "reply_to": observation["transcript"][-1]["id"] if observation["transcript"] else None,
                "content": "Discussing: " + observation["scenario"], "questions": ["Which users are in scope?"], "issue_updates": [],
                "proposal": {"summary": "Propose a member booking flow.", "assumptions": ["Membership already exists."], "disagreements": [],
                             "changes": ["Restrict booking to members."] if any(m["sender"] == "user" for m in observation["transcript"]) else []}}, {
                    "attempts": 1, "latency_ms": 1, "input_tokens": 20, "output_tokens": 20}


class DiscussionTests(unittest.TestCase):
    def test_custom_scenario_is_shared_and_each_role_reads_actual_previous_messages(self):
        client = DiscussionClient()
        run = run_discussion("Plan a community garden booking system", client)
        self.assertEqual(client.requests, 8)
        self.assertEqual([len(o["transcript"]) for o in client.observations], list(range(8)))
        self.assertEqual([m["sender"] for m in run["final_state"]["messages"]], list(ROLES) * 2)
        self.assertTrue(all("community garden" in o["scenario"] for o in client.observations))
        self.assertEqual(run["final_state"]["status"], "needs_input")
        self.assertEqual(run["final_state"]["questions"], ["Which users are in scope?"])
        self.assertEqual(run["final_state"], replay(run["events"]))
        self.assertNotIn("quality", run)

    def test_invalid_reply_or_spoofed_role_is_rejected(self):
        good = {"kind": "PROPOSE", "recipient": "team", "reply_to": None, "content": "Hello", "questions": []}
        for update in ({"reply_to": "nonexistent"}, {"sender": "world"}, {"content": " "}, {"recipient": "executor"}, {"kind": []}):
            with self.subTest(update=update), self.assertRaises(ReviewError):
                validate_contribution({**good, **update}, [])

    def test_budget_failure_preserves_partial_conversation(self):
        client = DiscussionClient()
        client.max_requests = 2
        run = run_discussion("A delivery service", client)
        self.assertEqual(len(run["final_state"]["messages"]), 2)
        self.assertEqual(run["final_state"]["reason"], "REVIEW_BUDGET_EXHAUSTED")
        self.assertEqual(run["final_state"]["status"], "needs_review")
        with tempfile.TemporaryDirectory() as folder:
            raw, report = save_discussion(run, folder)
            self.assertEqual(load_chat(raw), run)
            self.assertIn("REVIEW_BUDGET_EXHAUSTED", report.read_text())
            self.assertNotEqual(save_discussion(run, folder)[0], raw)

    def test_cli_and_saved_replay_do_not_use_transfer_world(self):
        with tempfile.TemporaryDirectory() as folder, patch("lemon.__main__.load_configuration", return_value=("test", "model")), patch("lemon.__main__.AnthropicClient", return_value=DiscussionClient()), patch("lemon.__main__.run_design", side_effect=AssertionError("No transfer scenario")), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["chat", "--scenario", "A classroom quiz", "--rounds", "1", "--delay", "0", "--output", folder]), 0)
            self.assertIn("All four roles use Anthropic", output.getvalue())
            self.assertNotIn("checks: PASS", output.getvalue())
            raw = next(Path(folder).glob("*.json"))
            with patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")):
                self.assertEqual(main(["chat", str(raw), "--delay", "0"]), 0)

    def test_custom_transport_sends_custom_prompt_and_schema(self):
        def opener(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(body["system"], "Custom discussion role")
            self.assertEqual(body["tools"][0]["input_schema"], SCHEMA)
            return io.BytesIO(json.dumps({"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "submit_review", "input": {}}]}).encode())
        AnthropicClient("secret-key", "model", opener=opener).submit({}, system_prompt="Custom discussion role", schema=SCHEMA)

    def test_invalid_scenario_does_not_call_provider(self):
        client = DiscussionClient()
        for scenario, rounds in [("", 2), ("x" * 12001, 2), ("hello", 0), ("hello", 6)]:
            with self.assertRaises(ValueError):
                run_discussion(scenario, client, rounds)
        self.assertEqual(client.requests, 0)

    def test_resume_preserves_history_and_delivers_user_decision_to_every_role(self):
        client = DiscussionClient()
        original = run_discussion("Delivery cancellation", client, rounds=1)
        resumed = run_discussion(None, client, rounds=1, previous=original,
                                 user_message="Allow cancellation only before restaurant acceptance.")
        self.assertEqual(resumed["events"][:len(original["events"])], original["events"])
        self.assertEqual(len(original["final_state"]["messages"]), 4)
        self.assertEqual(resumed["api_requests"], 8)
        messages = resumed["final_state"]["messages"]
        self.assertEqual(messages[4]["sender"], "user")
        self.assertEqual(len({m["id"] for m in messages}), 9)
        for observation in client.observations[4:]:
            self.assertEqual(observation["transcript"][4], messages[4])
            self.assertEqual(observation["round"], 2)
        self.assertEqual(replay(resumed["events"]), resumed["final_state"])
        self.assertEqual(client.requests, client.max_requests)

    def test_new_invocation_counts_only_new_requests_and_updates_questions(self):
        original = run_discussion("Booking", DiscussionClient(), rounds=1)

        class AnsweredClient(DiscussionClient):
            def submit(self, *args, **kwargs):
                value, usage = super().submit(*args, **kwargs)
                value["questions"] = []
                return value, usage

        resumed = run_discussion(None, AnsweredClient(), rounds=1, previous=original, user_message="Members only.")
        self.assertEqual(resumed["api_requests"], 8)
        self.assertEqual(resumed["final_state"]["questions"], [])
        self.assertEqual(resumed["final_state"]["status"], "discussion_complete")

    def test_tampered_resume_is_rejected_before_provider_call(self):
        original = run_discussion("Booking", DiscussionClient(), rounds=1)
        original["events"][0]["data"]["initial_state"]["scenario"] = "tampered"
        client = DiscussionClient()
        with self.assertRaises(ValueError):
            run_discussion(None, client, previous=original, user_message="Members only.")
        self.assertEqual(client.requests, 0)

    def test_interrupt_saves_a_replayable_partial_run(self):
        class InterruptedClient(DiscussionClient):
            def submit(self, *args, **kwargs):
                if self.requests == 1:
                    raise KeyboardInterrupt
                return super().submit(*args, **kwargs)

        run = run_discussion("Booking", InterruptedClient())
        self.assertEqual(run["final_state"]["status"], "paused")
        self.assertEqual(len(run["final_state"]["messages"]), 1)
        self.assertEqual(replay(run["events"]), run["final_state"])

    def test_interactive_cli_saves_then_accepts_feedback_without_resetting_budget(self):
        client = DiscussionClient()
        with tempfile.TemporaryDirectory() as folder, patch("lemon.__main__.load_configuration", return_value=("test", "model")), patch("lemon.__main__.AnthropicClient", return_value=client), patch("sys.stdout", new_callable=io.StringIO), patch("builtins.input", return_value="Members only.") as prompt:
            self.assertEqual(main(["chat", "--scenario", "Booking", "--interactive", "--delay", "0", "--output", folder]), 0)
            prompt.assert_called_once()
            runs = [load_chat(p) for p in Path(folder).glob("*.json")]
            self.assertEqual(sorted(len(r["final_state"]["messages"]) for r in runs), [4, 9])
            self.assertEqual(client.requests, 8)

    def test_quit_on_resume_needs_no_credentials_and_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, _ = save_discussion(run_discussion("Booking", DiscussionClient(), rounds=1), folder)
            for answer in ("/quit", EOFError(), KeyboardInterrupt()):
                with patch("builtins.input", side_effect=[answer]), patch("lemon.__main__.load_configuration", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(["chat", "--resume", str(raw), "--delay", "0"]), 0)

    def test_resume_message_cli_writes_new_snapshot_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, _ = save_discussion(run_discussion("Booking", DiscussionClient(), rounds=1), folder)
            original = raw.read_bytes()
            with patch("lemon.__main__.load_configuration", return_value=("test", "model")), patch("lemon.__main__.AnthropicClient", return_value=DiscussionClient()), patch("builtins.input", side_effect=AssertionError("No prompt")), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["chat", "--resume", str(raw), "--message", "Members only.", "--delay", "0", "--output", folder]), 0)
            self.assertEqual(raw.read_bytes(), original)
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
