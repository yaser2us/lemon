import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from lemon.agents import Action
from lemon.design import DesignWorld, VARIANTS, validate_design_message
from lemon.design_agents import BackendAgent, ProductAgent, TestAgent, accept
from lemon.design_evaluation import evaluate_design
from lemon.design_reporting import save_design, specification
from lemon.events import replay
from lemon.__main__ import run_design


class DesignConversationTests(unittest.TestCase):
    def test_variants_across_thirty_delivery_orders(self):
        for variant in VARIANTS:
            for seed in range(30):
                with self.subTest(variant=variant, seed=seed):
                    run = run_design(variant, seed)
                    self.assertTrue(run["quality"]["passed"], [c for c in run["quality"]["checks"] if not c["passed"]])

    def test_agreed_specification_is_derived_from_current_reviews(self):
        run = run_design("negotiated", 7)
        spec = specification(run)
        self.assertTrue(spec["agreement"])
        self.assertGreater(spec["contract_revision"], 1)
        self.assertEqual(spec["contract"]["success_state"], "COMPLETED")
        self.assertEqual(spec["ui_states"]["AUTHORIZED"], "Show authorized; still pending execution")
        self.assertEqual({c["requirement"] for c in spec["planned_test_cases"]}, {"R1", "R2", "R3", "R4"})
        self.assertEqual(spec["feature_test_execution"], "not_run")
        self.assertEqual(spec["implementation_status"], "not_generated")

    def test_open_question_never_becomes_implicit_approval(self):
        spec = specification(run_design("missing-decision", 7))
        self.assertFalse(spec["agreement"])
        self.assertEqual(spec["cancellation"], "UNDECIDED")
        self.assertTrue(spec["unresolved_questions"])

    def test_silent_reviewer_is_reported_and_not_approved(self):
        spec = specification(run_design("silent-reviewer", 7))
        self.assertFalse(spec["agreement"])
        self.assertNotIn("test-agent", spec["approvals"])
        self.assertTrue(any("test-agent" in q for q in spec["unresolved_questions"]))

    def test_seed_and_replay_are_reproducible(self):
        for variant in VARIANTS:
            a, b = run_design(variant, 9), run_design(variant, 9)
            self.assertEqual(a["events"], b["events"])
            self.assertEqual(replay(a["events"]), a["final_state"])

    def test_budget_exhaustion_is_visible(self):
        run = DesignWorld(message_budget=3).run()
        self.assertEqual(run["final_state"]["status"], "budget_exhausted")
        self.assertTrue(run["final_state"]["questions"])
        self.assertFalse(evaluate_design(run)["passed"])

    def initial_world(self):
        world = DesignWorld()
        req = world.send("product-agent", ProductAgent().start("OUT_OF_SCOPE"))
        world.deliver(req, "product-agent")
        first = BackendAgent().decide({}, world.view("backend-agent"))[0]
        msg = world.send("backend-agent", first)
        world.deliver(msg, "backend-agent")
        return world

    def test_revision_clears_approvals_and_rejects_old_votes(self):
        world = self.initial_world()
        vote = world.send("product-agent", accept(1, "Accept first draft"))
        world.deliver(vote, "product-agent")
        self.assertIn("product-agent", world.state["reviews"])
        revised = deepcopy(world.state["contract"])
        revised["states"].append("COMPLETED")
        revised["success_state"] = "COMPLETED"
        change = world.send("backend-agent", Action("world", "PROPOSE_CONTRACT", {"base_revision": 1, "contract": revised}, "Revise draft"))
        world.deliver(change, "backend-agent")
        self.assertFalse(world.state["reviews"])
        old_vote = world.send("product-agent", accept(1, "Delayed first-draft vote"))
        before = deepcopy(world.state)
        world.deliver(old_vote, "product-agent")
        self.assertEqual(before, world.state)
        self.assertTrue(any(e["kind"] == "MESSAGE_REJECTED" and e["data"]["reason"] == "STALE_REVISION" for e in world.log.events))

    def test_ui_cannot_replace_backend_contract(self):
        world = self.initial_world()
        msg = world.send("ui-agent", Action("world", "PROPOSE_CONTRACT", {"base_revision": 1, "contract": deepcopy(world.state["contract"])}, "Unauthorized replacement"))
        before = deepcopy(world.state)
        world.deliver(msg, "ui-agent")
        self.assertEqual(before, world.state)
        self.assertEqual(world.log.events[-1]["data"]["reason"], "UNAUTHORIZED_MESSAGE")

    def test_invalid_artifact_and_cross_conversation_are_rejected(self):
        world = self.initial_world()
        msg = world.send("test-agent", accept(1, "Claim review", {"test_cases": "not structured cases"}))
        self.assertEqual(validate_design_message(msg), "INVALID_DESIGN_PAYLOAD")
        proper = world.send("product-agent", accept(1, "Review"))
        proper["conversation_id"] = "FEATURE-OTHER"
        self.assertEqual(validate_design_message(proper), "WRONG_CONVERSATION")

    def test_consensus_does_not_override_independent_quality_checks(self):
        class RubberStamp(TestAgent):
            def decide(self, message, view):
                if view["contract"] is None:
                    return []
                return [accept(view["revision"], "Accept without checking", {"test_cases": [
                    {"id": "fake", "requirement": "R1", "given": "anything", "when": "submit", "then": "success"}
                ]})]
        world = DesignWorld()
        world.agents["test-agent"] = RubberStamp()
        run = world.run()
        self.assertEqual(run["final_state"]["status"], "needs_review")
        self.assertEqual(run["final_state"]["reason"], "VERIFICATION_REPAIR_LIMIT")
        self.assertEqual(run["final_state"]["verification"]["attempt"], 3)
        quality = evaluate_design(run)
        self.assertFalse(quality["passed"])
        failed = {f["code"] for f in run["final_state"]["verification"]["failures"]}
        self.assertIn("ASSERTION_REQUIRED", failed)
        self.assertTrue(run["final_state"]["questions"])

    def test_design_cli_artifacts_and_shared_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-m", "lemon", "design", "--variant", "all", "--output", tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp) / "index.md").exists())
            spec = json.loads((Path(tmp) / "design-negotiated-seed-7.spec.json").read_text())
            self.assertTrue(spec["agreement"])
            raw = Path(tmp) / "design-negotiated-seed-7.json"
            result = subprocess.run([sys.executable, "-m", "lemon", "replay", str(raw)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["final_state"]["status"], "agreed")


if __name__ == "__main__":
    unittest.main()
