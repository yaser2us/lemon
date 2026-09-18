import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from lemon.agents import Action, AppAgent
from lemon.contracts import validate_evidence, validate_message
from lemon.evaluation import evaluate
from lemon.events import digest, replay
from lemon.reporting import save_run, save_suite
from lemon.runtime import World
from lemon.scenarios import SCENARIOS, get_scenario
from lemon.__main__ import run_scenario


class ScenarioTests(unittest.TestCase):
    def test_all_scenarios_across_thirty_delivery_orders(self):
        for seed in range(30):
            for name, scenario in SCENARIOS.items():
                with self.subTest(scenario=name, seed=seed):
                    run = World(scenario["config"], seed).run()
                    quality = evaluate(run, scenario["expected"])
                    self.assertTrue(quality["passed"], [c for c in quality["checks"] if not c["passed"]])

    def test_seed_reproduces_trace_and_replay_reproduces_state(self):
        for name in ("high-risk", "conflicting-evidence", "competing-transfers", "no-progress-loop"):
            with self.subTest(scenario=name):
                a, b = run_scenario(name, 22), run_scenario(name, 22)
                self.assertEqual(a["events"], b["events"])
                self.assertEqual(a["final_state"], replay(a["events"]))

    def test_paths_vary_with_conditions_and_delivery_order(self):
        def requests(run):
            return [e["data"]["message"]["payload"]["need"] for e in run["events"] if e["kind"] == "MESSAGE_SENT" and e["data"]["message"]["type"] == "REQUEST_EVIDENCE"]
        self.assertNotIn("auth", requests(run_scenario("low-risk", 7)))
        self.assertIn("auth", requests(run_scenario("high-risk", 7)))
        orders = set()
        for seed in range(10):
            run = run_scenario("low-risk", seed)
            orders.add(tuple(e["data"]["evidence"]["type"] for e in run["events"] if e["kind"] == "EVIDENCE_ACCEPTED"))
        self.assertGreater(len(orders), 1)

    def test_boundary_amounts_and_device_risk(self):
        for amount, trusted, risk in [(1, True, "LOW"), (3000, True, "LOW"), (3001, True, "HIGH"), (1, False, "HIGH")]:
            for balance in (amount - 1, amount, amount + 1):
                with self.subTest(amount=amount, trusted=trusted, balance=balance):
                    s = get_scenario("low-risk")
                    s["config"]["transactions"][0].update(amount=amount, trusted_device=trusted)
                    s["config"]["balance"] = balance
                    s["expected"].update(statuses=["completed" if balance >= amount else "rejected"], effects=int(balance >= amount), risk={"TX-1": risk})
                    quality = evaluate(World(s["config"]).run(), s["expected"])
                    self.assertTrue(quality["passed"], quality["checks"])

    def test_message_budget_is_visible_and_not_task_success(self):
        run = run_scenario("no-progress-loop", 7)
        q = run["quality"]
        self.assertTrue(q["passed"])
        self.assertEqual(q["metrics"]["completed_tasks"], 0)
        self.assertEqual(q["metrics"]["incomplete_tasks"], 1)
        self.assertEqual(run["final_state"]["ledger"]["balance"], 10000)
        accepted = [e for e in run["events"] if e["kind"] == "MESSAGE_ACCEPTED"]
        # The terminal COMPLETE notification is outside the 50-message work budget.
        self.assertLessEqual(len(accepted), 51)


class TrustBoundaryTests(unittest.TestCase):
    def make_evidence_reply(self, world, **changes):
        request = world.send("app-agent", "TX-1", Action("identity-provider", "REQUEST_EVIDENCE", {"need": "identity"}, "Test request"))
        evidence = world.issue("identity-provider", "TX-1", "identity", True)
        world.issued[evidence["id"]] = deepcopy(evidence)
        evidence.update(changes)
        message = world.send("identity-provider", "TX-1", Action("world", "PROVIDE_EVIDENCE", {"evidence": evidence}, "Test reply"), request["id"])
        return message

    def test_fabricated_or_modified_provider_evidence_is_rejected(self):
        for changes in ({"value": False}, {"source": "untrusted"}, {"id": "invented"}):
            with self.subTest(changes=changes):
                world = World(get_scenario("low-risk")["config"])
                msg = self.make_evidence_reply(world, **changes)
                before = deepcopy(world.state)
                world.deliver(msg, "identity-provider")
                self.assertEqual(before, world.state)
                self.assertEqual(world.log.events[-1]["data"]["reason"], "UNATTESTED_EVIDENCE")

    def test_auth_claim_cannot_be_sent_by_app_agent(self):
        run = run_scenario("unauthorized-evidence", 7)
        self.assertIn("UNAUTHORIZED_MESSAGE", run["quality"]["metrics"]["rejections_by_reason"])
        accepted = [e["data"]["evidence"] for e in run["events"] if e["kind"] == "EVIDENCE_ACCEPTED"]
        self.assertTrue(all(e["producer"] != "app-agent" for e in accepted))

    def test_mutating_observation_cannot_change_world_state(self):
        class MutatingApp(AppAgent):
            def decide(self, message, view):
                view["status"] = "completed"
                view["missing"].clear()
                message["payload"].get("missing", []).clear()
                return []
        world = World(get_scenario("low-risk")["config"])
        world.agents["app-agent"] = MutatingApp()
        run = world.run()
        self.assertFalse(run["final_state"]["executions"])
        self.assertNotEqual(run["final_state"]["transactions"]["TX-1"]["status"], "completed")

    def test_agent_exception_becomes_explicit_escalation(self):
        class BrokenApp(AppAgent):
            def decide(self, message, view):
                raise RuntimeError("Simulated agent failure")
        world = World(get_scenario("low-risk")["config"])
        world.agents["app-agent"] = BrokenApp()
        run = world.run()
        self.assertEqual(run["final_state"]["transactions"]["TX-1"]["reason"], "AGENT_ERROR")
        self.assertFalse(run["final_state"]["executions"])
        self.assertTrue(any(e["kind"] == "AGENT_FAILED" for e in run["events"]))

    def test_observation_does_not_expose_other_roles_inputs(self):
        world = World(get_scenario("low-risk")["config"])
        self.assertNotIn("balance", world.view("risk-agent", "TX-1"))
        self.assertNotIn("trusted_device", world.view("payment-agent", "TX-1"))
        self.assertNotIn("expected", world.view("app-agent", "TX-1"))

    def test_contract_rejects_wrong_types_and_unknown_versions(self):
        world = World(get_scenario("low-risk")["config"])
        good = world.send("app-agent", "TX-1", AppAgent().start())
        self.assertIsNone(validate_message(good))
        for patch in ({"schema_version": True}, {"schema_version": 2}, {"payload": {"action": []}}, {"timestamp": True}, {"sender": []}, {"type": "FREEFORM_CHAT"}):
            with self.subTest(patch=patch):
                self.assertIsNotNone(validate_message({**good, **patch}))
        ev = world.issue("identity-provider", "TX-1", "identity", True)
        self.assertIsNone(validate_evidence(ev))
        self.assertIsNotNone(validate_evidence({**ev, "value": "true"}))
        self.assertIsNotNone(validate_evidence({**ev, "type": []}))
        self.assertIsNotNone(validate_message(None))

    def test_malformed_deliveries_do_not_crash_or_change_domain_state(self):
        world = World(get_scenario("low-risk")["config"])
        good = world.send("app-agent", "TX-1", AppAgent().start())
        before = deepcopy(world.state)
        for message in (None, {}, {**good, "conversation_id": []}, {**good, "payload": []}, {**good, "sender": []}):
            with self.subTest(message=message):
                world.deliver(message, "app-agent")
                self.assertEqual(world.state, before)
                self.assertEqual(world.log.events[-1]["kind"], "MESSAGE_REJECTED")

    def test_expired_authorization_is_rechecked_before_execution(self):
        # Shorten all provider evidence lifetimes enough to expire before execution.
        # The runtime must refresh/escalate, never debit using expired evidence.
        class ShortLivedWorld(World):
            def issue(self, producer, tx_id, need, value):
                ev = super().issue(producer, tx_id, need, value)
                ev["expires_at"] = self.now + 4
                return ev
        for seed in range(5):
            s = get_scenario("high-risk")
            world = ShortLivedWorld(s["config"], seed)
            run = world.run()
            self.assertFalse(run["final_state"]["executions"])
            self.assertIn(run["final_state"]["transactions"]["TX-1"]["conversation"], {"escalated", "budget_exhausted", "timed_out"})


class AuditAndOutputTests(unittest.TestCase):
    def test_tampered_event_is_detected(self):
        run = run_scenario("high-risk", 7)
        run["events"][1]["data"]["message"]["payload"]["action"] = "EXECUTE"
        with self.assertRaisesRegex(ValueError, "chain mismatch"):
            replay(run["events"])

    def test_independent_evaluator_detects_bad_authorization_even_with_rehashed_log(self):
        run = run_scenario("high-risk", 7)
        for event in run["events"]:
            if event["kind"] == "POLICY_DECISION" and event["data"]["result"] == "ALLOWED":
                event["data"]["evidence_ids"] = []
        previous = "0" * 64
        for event in run["events"]:
            event["previous_hash"] = previous
            event["hash"] = digest({k: v for k, v in event.items() if k != "hash"})
            previous = event["hash"]
        self.assertEqual(replay(run["events"]), run["final_state"])
        q = evaluate(run, run["expectations"])
        policy = next(c for c in q["checks"] if c["name"] == "Authorizations satisfy independent policy assertions")
        self.assertFalse(policy["passed"])

    def test_reports_and_replay_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_scenario("high-risk", 7)
            raw, report = save_run(run, tmp)
            index = save_suite([run], tmp)
            self.assertIn("Agent conversation", report.read_text())
            self.assertIn("1 / 1 scenario runs passed", index.read_text())
            result = subprocess.run([sys.executable, "-m", "lemon", "replay", str(raw)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["final_state"], run["final_state"])
            altered = json.loads(raw.read_text())
            altered["final_state"]["ledger"]["balance"] = 0
            raw.write_text(json.dumps(altered))
            result = subprocess.run([sys.executable, "-m", "lemon", "replay", str(raw)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_cli_run_and_invalid_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-m", "lemon", "run", "conflicting-evidence", "--output", tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp) / "conflicting-evidence-seed-7.md").exists())
            result = subprocess.run([sys.executable, "-m", "lemon", "suite", "--seeds", "0"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
