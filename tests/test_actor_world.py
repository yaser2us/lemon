import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main
from lemon.actor_world import (ActorWorld, BRANCHES, FAULTS, LocalActor, MODEL, ModelActor,
                               evaluate_actor, run_actor, save_actor, trial, validate_strategy)
from lemon.anthropic_reviewer import ReviewError
from lemon.events import replay


class ActorWorldTests(unittest.TestCase):
    def test_unknown_observations_do_not_reveal_hidden_bank_state(self):
        worlds = [ActorWorld(fault) for fault in BRANCHES]
        for world in worlds:
            world.act("send_original")
        self.assertEqual({w.state["effects"] for w in worlds}, {0, 1})
        self.assertEqual(worlds[0].view(), worlds[1].view())
        self.assertEqual(worlds[1].view(), worlds[2].view())
        self.assertEqual(worlds[0].view()["app"]["status"], "UNKNOWN")
        self.assertNotIn("fault", worlds[0].view())
        self.assertNotIn("ledger", worlds[0].view())

    def test_branch_trials_have_actual_events_and_leave_parent_unchanged(self):
        world = ActorWorld()
        world.act("send_original")
        state, events = deepcopy(world.state), deepcopy(world.log.events)
        plan = {"name": "bad-retry", "steps": ["send_new", "wait", "check_status", "report"]}
        branch = trial(plan, "response-lost")
        self.assertFalse(branch["quality"]["passed"])
        self.assertIn("NEW_ATTEMPT_FOR_EXISTING_INTENT", branch["rejections"])
        self.assertEqual(branch["effects"], 1)
        self.assertEqual(replay(branch["events"])["effects"], 1)
        self.assertEqual(world.state, state)
        self.assertEqual(world.log.events, events)

    def test_local_experiment_learns_and_executes_successful_candidate(self):
        run = run_actor()
        self.assertTrue(run["quality"]["passed"])
        self.assertIsNotNone(run["learned_strategy"])
        self.assertEqual(run["final_state"]["ledger"], {"maybank": 90000, "cimb": 10000})
        self.assertEqual(run["final_state"]["effects"], 1)
        self.assertEqual(replay(run["events"]), run["final_state"])
        results = next(e["data"]["results"] for e in run["events"] if e["kind"] == "BRANCH_RESULTS")
        self.assertEqual([r["passed"] for r in results], [False, False, True])
        for branch in run["branch_traces"][0]:
            for result in branch["branches"]:
                replay(result["events"])

    def test_strategy_is_reused_across_faults_without_new_branch_search(self):
        memory = run_actor()["learned_strategy"]
        for fault in FAULTS:
            for delay in (1, 3, 5):
                with self.subTest(fault=fault, delay=delay):
                    run = run_actor(fault, memory=memory, delay=delay)
                    self.assertTrue(run["quality"]["passed"])
                    self.assertEqual(run["branch_traces"], [])
                    self.assertEqual(run["used_memory"], fault in BRANCHES)

    def test_held_out_delay_catches_strategy_that_passes_discovery_delay(self):
        short = {"name": "too-short", "steps": ["send_original", "check_status", "check_status", "report"]}
        self.assertTrue(all(trial(short, f, delay=2)["quality"]["passed"] for f in BRANCHES))
        self.assertFalse(all(r["quality"]["passed"] for r in validate_strategy(short)))

    def test_world_rejects_false_success_without_authoritative_receipt(self):
        world = ActorWorld("response-lost")
        world.act("send_original")
        self.assertEqual(world.state["effects"], 1)
        world.act("report", "I think it probably succeeded.")
        self.assertEqual(world.state["app"]["customer_report"], None)
        self.assertIn("NO_AUTHORITATIVE_OUTCOME_TO_REPORT", world.state["rejections"])

    def test_bank_actor_state_changes_cannot_double_spend(self):
        world = ActorWorld()
        world.act("send_original")
        for _ in range(4):
            world.act("send_original")
        world.act("send_new")
        self.assertEqual(world.state["effects"], 1)
        self.assertEqual(sum(world.state["ledger"].values()), 100000)

    def test_memory_is_revalidated_and_model_version_is_bound(self):
        memory = run_actor()["learned_strategy"]
        with self.assertRaises(ValueError):
            run_actor(memory={**memory, "model": "different-laws"})
        with self.assertRaises(ValueError):
            run_actor(memory={"model": MODEL, "plan": {"name": "unsafe", "steps": ["send_new", "report"]}})

    def test_provider_failure_and_unbounded_actions_do_not_persist_learning(self):
        class BrokenActor:
            def decide(self, observation):
                raise ReviewError("HTTP_401")
        run = run_actor(actor=BrokenActor())
        self.assertEqual(run["final_state"]["status"], "needs_input")
        self.assertFalse(run["quality"]["passed"])
        self.assertIsNone(run["learned_strategy"])
        class LoopActor:
            def decide(self, observation):
                return {"action": "wait", "plans": [], "strategy": "", "reason": "Wait forever."}
        run = run_actor(actor=LoopActor())
        self.assertEqual(run["final_state"]["status"], "budget_exhausted")

    def test_invalid_action_returns_feedback_without_executing_it(self):
        class RepairActor:
            def decide(self, observation):
                if observation["remaining_actions"] == 20:
                    return {"action": "send_new", "reason": "Malformed mixed action", "strategy": "wrong", "plans": []}
                if observation["remaining_actions"] == 19:
                    self_test.assertEqual(observation["action_error"], "Mixed actor actions")
                    self_test.assertEqual(observation["app"]["status"], "READY")
                return LocalActor().decide(observation)
        self_test = self
        run = run_actor(actor=RepairActor())
        self.assertTrue(run["quality"]["passed"])
        self.assertIsNotNone(run["learned_strategy"])

    def test_model_actor_gets_only_observations_and_memory_reduces_model_calls(self):
        class Client:
            requests = 0
            def submit(self, observation, **kwargs):
                self.requests += 1
                self_test.assertNotIn("fault", observation)
                self_test.assertNotIn("ledger", observation)
                return LocalActor().decide(observation), {"attempts": 1, "latency_ms": 1}
        self_test = self
        first = run_actor(actor=ModelActor(Client()))
        second = run_actor("request-lost", actor=ModelActor(Client()), memory=first["learned_strategy"])
        self.assertEqual(first["model_calls"], 3)
        self.assertEqual(second["model_calls"], 1)
        self.assertTrue(second["quality"]["passed"])

    def test_cli_saves_trace_and_memory_and_replay_is_offline(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdout", new_callable=io.StringIO):
            memory = str(Path(folder) / "memory.json")
            self.assertEqual(main(["act", "--fresh", "--output", folder, "--memory", memory]), 0)
            retained = json.loads(Path(memory).read_text())
            self.assertEqual(retained["model"], MODEL)
            trace = Path(retained["source_run"])
            self.assertEqual(main(["replay", str(trace)]), 0)
            self.assertEqual(main(["chat", str(trace), "--delay", "0"]), 0)
            self.assertEqual(main(["act", "--fault", "request-lost", "--output", folder, "--memory", memory]), 0)


if __name__ == "__main__":
    unittest.main()
