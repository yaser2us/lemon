import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.actor_world import FAULTS
from lemon.anthropic_reviewer import ReviewError
from lemon.events import replay
from lemon.joint_world import (MODEL, LocalJointActor, ModelJointActor, decision,
                               choose, rehearse, run_joint, validate_pair, verify_joint_evidence)
from lemon.team_world import ROLES, TeamWorld


class JointWorldTests(unittest.TestCase):
    def test_failure_then_revision_requires_two_adoptions_before_live_execution(self):
        run = run_joint()
        self.assertTrue(run["quality"]["passed"])
        self.assertEqual([r["passed"] for r in run["joint_results"]], [False, True])
        self.assertIn("NO_DELIVERED_PAYMENT_RECEIPT", run["joint_results"][0]["rejections"])
        self.assertEqual(len(run["joint_results"][1]["validation"]), 20)
        self.assertEqual(run["learned_strategy"]["model"], MODEL)
        adopted = set()
        for event in run["events"]:
            if event["kind"] == "MESSAGE_RECEIVED" and event["data"]["message"]["type"] == "ADOPT_JOINT_RESULT":
                adopted.add(event["data"]["message"]["sender"])
            if event["kind"] == "JOINT_APPLIED":
                self.assertEqual(adopted, {"app-actor", "payment-actor"})
        self.assertEqual(replay(run["events"]), run["final_state"])
        for result, trace in zip(run["joint_results"], run["branch_traces"]):
            replay(trace["events"])
            self.assertEqual(result["event_hash"], trace["events"][-1]["hash"])

    def test_both_real_controllers_act_with_private_branch_context(self):
        observations = {r: [] for r in ROLES}
        class Recorder:
            def __init__(self, role):
                self.role = role
            def decide(self, obs):
                observations[self.role].append(deepcopy(obs))
                return LocalJointActor().decide(obs)
        parent = TeamWorld("request-lost")
        parent.step("app", "ask", "Did this arrive?")
        before = deepcopy(parent.state)
        result, events = rehearse({r: Recorder(r) for r in ROLES}, "processing", parent.state["inboxes"], [{"passed": False}], "branch-1")
        self.assertTrue(result["passed"])
        self.assertEqual(before, parent.state)
        self.assertTrue(observations["app"])
        self.assertTrue(observations["payment"])
        for role in ROLES:
            for obs in observations[role]:
                self.assertEqual(obs["role"], role)
                self.assertEqual(obs["phase"], "rehearsal")
                self.assertNotIn("ledger", obs)
                self.assertNotIn("fault", obs)
                self.assertNotIn("trial_peer", obs)
        self.assertEqual(observations["payment"][0]["inbox"][0]["text"], "Did this arrive?")
        replay(events)

    def test_uncooperative_actual_peer_is_not_replaced_by_scripted_peer(self):
        class Silent:
            def decide(self, obs):
                return decision("wait", "I will not send a receipt.")
        result, _ = rehearse({"app": LocalJointActor(), "payment": Silent()}, "processing", {r: [] for r in ROLES}, [{"passed": False}], "silent")
        self.assertFalse(result["passed"])
        self.assertEqual(result["plans"]["payment"]["steps"], ["wait"] * 8)

    def test_nested_rehearsal_and_cross_role_action_are_rejected(self):
        class Invalid:
            def __init__(self, action):
                self.action = action
            def decide(self, obs):
                return decision(self.action, "Invalid role action.")
        for action in ("joint", "recover"):
            summary, _ = rehearse({"app": Invalid(action), "payment": LocalJointActor()}, "processing", {r: [] for r in ROLES}, [], "invalid")
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["plans"]["app"]["steps"], [])

    def test_pair_validation_and_memory_reuse_across_faults(self):
        memory = run_joint()["learned_strategy"]
        for fault in FAULTS:
            reused = run_joint(fault, memory=memory)
            self.assertTrue(reused["quality"]["passed"])
            self.assertTrue(reused["used_memory"])
            self.assertEqual(reused["model_calls"], 0)
        bad = deepcopy(memory)
        bad["actors"]["payment"]["steps"] = ["share"]
        with self.assertRaises(ValueError):
            run_joint(memory=bad)
        with self.assertRaises(ValueError):
            run_joint(memory={**memory, "model": "actor-team-transfer-v1"})
        self.assertFalse(all(r["quality"]["passed"] for r in validate_pair(bad["actors"])))

    def test_malformed_branch_action_returns_feedback_instead_of_provider_failure(self):
        class Repair:
            def __init__(self):
                self.first = True
                self.feedback = None
            def decide(self, obs):
                if self.first:
                    self.first = False
                    return decision("recover", "Mixed fields by mistake.", hypothesis="processing")
                self.feedback = self.feedback or obs.get("action_error")
                return LocalJointActor().decide(obs)
        payment = Repair()
        result, _ = rehearse({"app": LocalJointActor(), "payment": payment}, "processing", {r: [] for r in ROLES}, [{"passed": False}], "repair")
        self.assertIsNone(result["failure"])
        self.assertEqual(payment.feedback, "Mixed joint action fields")
        self.assertTrue(result["passed"])

    def test_live_execution_cannot_bypass_joint_adoption(self):
        class Bypass:
            def decide(self, obs):
                return decision("recover", "Skip rehearsal and execute now.")
        world = TeamWorld()
        before = deepcopy(world.state)
        with self.assertRaises(ValueError):
            choose(Bypass(), world, "payment", {**world.view("payment"), "phase": "live"})
        self.assertEqual(before, world.state)

    def test_nested_trace_and_summary_tampering_are_detected(self):
        run = run_joint()
        verify_joint_evidence(run)
        changed = deepcopy(run)
        changed["branch_traces"][0]["events"][-1]["data"]["injected"] = True
        with self.assertRaises(ValueError):
            verify_joint_evidence(changed)
        changed = deepcopy(run)
        changed["joint_results"][0]["passed"] = True
        with self.assertRaises(ValueError):
            verify_joint_evidence(changed)

    def test_provider_failure_in_branch_saves_partial_trace_and_no_memory(self):
        class Broken:
            def decide(self, obs):
                if obs["phase"] == "rehearsal":
                    raise ReviewError("HTTP_401")
                return LocalJointActor().decide(obs)
        run = run_joint(actors={r: Broken() for r in ROLES})
        self.assertEqual(run["final_state"]["status"], "needs_input")
        self.assertIsNone(run["learned_strategy"])
        self.assertEqual(run["joint_results"][0]["failure"], "HTTP_401")
        replay(run["branch_traces"][0]["events"])

    def test_shared_client_budget_counts_live_and_branch_calls(self):
        class Client:
            requests = 0
            def submit(self, obs, **kwargs):
                self.requests += 1
                return LocalJointActor().decide(obs), {"latency_ms": 1}
        client = Client()
        run = run_joint(actors={r: ModelJointActor(client, r) for r in ROLES})
        self.assertTrue(run["quality"]["passed"])
        self.assertEqual(run["api_requests"], run["model_calls"])
        self.assertGreater(run["model_calls"], 10)

    def test_invalid_provider_response_gets_one_bounded_retry(self):
        class RetryActor:
            calls = 0
            def decide(self, obs):
                self.calls += 1
                if self.calls == 1:
                    raise ReviewError("INVALID_RESPONSE")
                return decision("ask", "Ask the peer about the original attempt.")
        actor = RetryActor()
        world = TeamWorld()
        result = choose(actor, world, "app", {**world.view("app"), "phase": "live"})
        self.assertEqual(result["action"], "ask")
        self.assertEqual(actor.calls, 2)

    def test_cli_replays_joint_steps_and_reuses_memory(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdout", new_callable=io.StringIO) as output:
            memory = Path(folder) / "memory.json"
            args = ["act", "--joint", "--output", folder, "--memory", str(memory)]
            self.assertEqual(main(args + ["--fresh", "--fault", "processing"]), 0)
            data = json.loads(memory.read_text())
            self.assertEqual(main(["chat", data["source_run"]]), 0)
            self.assertIn("[joint-2] payment", output.getvalue())
            self.assertEqual(main(["replay", data["source_run"]]), 0)
            self.assertEqual(main(args + ["--fault", "request-lost"]), 0)


if __name__ == "__main__":
    unittest.main()
