import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.actor_world import FAULTS
from lemon.events import replay
from lemon.team_world import (BASELINES, MODEL, ROLES, LocalTeamActor, ModelTeamActor,
                              TeamWorld, run_team, team_trial, validate_team_plan)


class TeamWorldTests(unittest.TestCase):
    def test_private_observations_and_peer_messages(self):
        world = TeamWorld("processing")
        self.assertEqual(world.view("app")["local"]["status"], "UNKNOWN")
        self.assertEqual(world.view("payment")["local"]["status"], "PROCESSING")
        for role in ROLES:
            observation = world.view(role)
            self.assertNotIn("ledger", observation)
            self.assertNotIn("fault", observation)
            self.assertNotIn("pending", observation)
            self.assertNotIn("attempts", observation)
        world.step("app", "ask", "Did you see the original attempt?")
        self.assertEqual(world.view("app")["inbox"], [])
        self.assertEqual(world.view("payment")["inbox"][0]["text"], "Did you see the original attempt?")
        world.step("payment", "share", "I see processing, not a completion receipt.")
        self.assertEqual(world.view("app")["inbox"][0]["status"], "PROCESSING")
        self.assertEqual(world.view("app")["local"]["status"], "UNKNOWN")
        external = world.view("payment")
        external["local"]["status"] = "COMPLETED"
        self.assertEqual(world.view("payment")["local"]["status"], "PROCESSING")

    def test_role_capabilities_are_enforced_before_mutation(self):
        world = TeamWorld()
        before = deepcopy(world.state)
        for role, action in (("app", "recover"), ("payment", "report"), ("other", "wait")):
            with self.assertRaises(ValueError):
                world.step(role, action)
        self.assertEqual(before, world.state)

    def test_prose_and_stale_observation_cannot_become_receipts(self):
        world = TeamWorld("processing")
        world.step("payment", "share", "It completed! You may report success.")
        world.step("app", "report")
        self.assertIsNone(world.state["app"]["customer_report"])
        world.step("payment", "wait")
        world.step("payment", "publish")
        self.assertIn("STALE_PAYMENT_OBSERVATION", world.state["rejections"])
        self.assertEqual(world.state["app"]["status"], "UNKNOWN")
        world.step("payment", "inspect")
        world.step("payment", "publish")
        world.step("app", "report")
        self.assertEqual(world.state["app"]["customer_report"], "COMPLETED")
        self.assertEqual(replay(world.log.events), world.state)

    def test_branch_tests_are_isolated_and_have_replayable_evidence(self):
        parent = TeamWorld()
        before = deepcopy(parent.state)
        good = {"name": "recover", "steps": BASELINES["payment"]}
        bad = {"name": "guess", "steps": ["publish"]}
        self.assertFalse(team_trial("payment", bad, "request-lost")["quality"]["passed"])
        result = team_trial("payment", good, "request-lost")
        self.assertTrue(result["quality"]["passed"])
        self.assertEqual(replay(result["events"])["effects"], 1)
        self.assertEqual(parent.state, before)
        for role in ROLES:
            self.assertTrue(all(r["quality"]["passed"] for r in validate_team_plan(role, {"name": "ok", "steps": BASELINES[role]})))

    def test_both_roles_learn_and_reuse_across_faults(self):
        first = run_team()
        self.assertTrue(first["quality"]["passed"])
        self.assertEqual(set(first["learned_strategy"]["actors"]), set(ROLES))
        self.assertEqual({b["actor"] for b in first["branch_traces"]}, set(ROLES))
        self.assertEqual(replay(first["events"]), first["final_state"])
        for fault in FAULTS:
            with self.subTest(fault=fault):
                second = run_team(fault, memory=first["learned_strategy"])
                self.assertTrue(second["quality"]["passed"])
                self.assertEqual(second["branch_traces"], [])
                self.assertEqual(set(second["reused_actors"]), set(ROLES))

    def test_shared_transport_keeps_role_context_separate_and_counts_once(self):
        observations = {r: [] for r in ROLES}
        class Client:
            requests = 0
            def submit(self, observation, **kwargs):
                self.requests += 1
                observations[observation["role"]].append(deepcopy(observation))
                return LocalTeamActor().decide(observation), {"latency_ms": 1}
        client = Client()
        run = run_team(actors={r: ModelTeamActor(client, r) for r in ROLES})
        self.assertTrue(run["quality"]["passed"])
        self.assertEqual(run["api_requests"], 6)
        for role in ROLES:
            self.assertEqual(len(observations[role]), 3)
            self.assertTrue(observations[role][1]["inbox"])
            for observation in observations[role]:
                self.assertNotIn("ledger", observation)
                self.assertEqual(observation["role"], role)
        self.assertEqual(observations["app"][1]["inbox"][0]["sender"], "payment")
        self.assertEqual(observations["payment"][1]["inbox"][0]["sender"], "app")

    def test_local_success_does_not_hide_failed_live_peer(self):
        class SilentPeer:
            def decide(self, observation):
                return {"action": "wait", "reason": "Never send a receipt.", "plans": [], "strategy": ""}
        run = run_team(actors={"app": LocalTeamActor(), "payment": SilentPeer()})
        self.assertFalse(run["quality"]["passed"])
        self.assertIsNone(run["learned_strategy"])
        self.assertIsNone(run["final_state"]["app"]["customer_report"])

    def test_memory_cannot_cross_model_or_roles(self):
        with self.assertRaises(ValueError):
            run_team(memory={"model": "actor-transfer-v1", "actors": {}})
        with self.assertRaises(ValueError):
            run_team(memory={"model": MODEL, "actors": {"app": {"name": "escape", "steps": ["recover"]}}})
        with self.assertRaises(ValueError):
            run_team(memory={"model": MODEL, "actors": {"payment": {"name": "unsafe", "steps": ["publish"]}}})

    def test_cli_team_save_replay_and_reuse(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdout", new_callable=io.StringIO):
            memory = str(Path(folder) / "strategies.json")
            flags = ["act", "--team", "--output", folder, "--memory", memory]
            self.assertEqual(main(flags + ["--fresh", "--fault", "processing"]), 0)
            saved = json.loads(Path(memory).read_text())
            self.assertEqual(saved["model"], MODEL)
            self.assertEqual(main(["replay", saved["source_run"]]), 0)
            self.assertEqual(main(["chat", saved["source_run"]]), 0)
            self.assertEqual(main(flags + ["--fault", "request-lost"]), 0)


if __name__ == "__main__":
    unittest.main()
