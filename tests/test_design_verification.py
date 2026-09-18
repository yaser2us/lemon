import unittest
from copy import deepcopy

from lemon.__main__ import run_design
from lemon.anthropic_reviewer import AnthropicReviewer
from lemon.design import DesignWorld
from lemon.design_agents import BackendAgent
from lemon.design_evaluation import evaluate_design
from lemon.design_verification import verify_design
from lemon.events import replay
from test_anthropic_reviewer import FakeClient


class VerificationTests(unittest.TestCase):
    def test_failed_case_is_routed_repaired_and_reverified(self):
        run = run_design("repair-demo", 7)
        checks = [e for e in run["events"] if e["kind"] == "DESIGN_VERIFIED"]
        self.assertEqual([e["data"]["status"] for e in checks], ["failed", "passed"])
        feedback = [e["data"]["message"] for e in run["events"] if e["kind"] == "MESSAGE_SENT" and e["data"]["message"]["type"] == "VERIFICATION_FEEDBACK"]
        self.assertEqual([m["recipient"] for m in feedback], ["test-agent"])
        self.assertEqual(run["final_state"], replay(run["events"]))
        self.assertTrue(run["quality"]["passed"])
        self.assertFalse(any(e["kind"] == "DESIGN_CHANGED" and e["data"]["after"]["status"] == "agreed" for e in run["events"][:checks[-1]["sequence"]]))

    def test_invalid_assertions_and_transitions_cannot_pass(self):
        original = run_design("negotiated", 7)["final_state"]
        for patch in ({"initial_state": []}, {"expected_state": "COMPLETED", "success": True}, {"same_transaction": 1}):
            state = deepcopy(original)
            state["reviews"]["test-agent"]["artifact"]["test_cases"][2]["assertion"].update(patch)
            self.assertTrue(verify_design(state))
        state = deepcopy(original)
        state["contract"]["transitions"]["AUTHORIZED"] = ["COMPLETED"]
        self.assertIn("TRANSITIONS", {f["code"] for f in verify_design(state)})

    def test_ui_requirement_can_cover_display_and_execution_cases(self):
        state = run_design("negotiated", 7)["final_state"]
        cases = state["reviews"]["test-agent"]["artifact"]["test_cases"]
        cases[3]["requirement"] = "R2"
        cases[4]["requirement"] = "R2"
        self.assertEqual(verify_design(state), [])

    def test_feedback_distinguishes_rendering_from_creation(self):
        state = run_design("negotiated", 7)["final_state"]
        case = deepcopy(state["reviews"]["test-agent"]["artifact"]["test_cases"][0])
        case.update(id="positive-input")
        case["assertion"].update(event="render", expected_state="REQUESTED")
        state["reviews"]["test-agent"]["artifact"]["test_cases"].append(case)
        failures = verify_design(state)
        self.assertIn("use submit_valid from NONE", failures[0]["detail"])
        case["assertion"]["event"] = "submit_valid"
        self.assertEqual(verify_design(state), [])

    def test_contract_failure_goes_to_backend_and_invalidates_all_old_votes(self):
        class MissingGraph(BackendAgent):
            def decide(self, message, view):
                actions = super().decide(message, view)
                if not view.get("verification", {}).get("attempt"):
                    for action in actions:
                        if action.kind == "PROPOSE_CONTRACT":
                            action.payload["contract"].pop("transitions", None)
                return actions
        world = DesignWorld()
        world.agents["backend-agent"] = MissingGraph()
        run = world.run()
        self.assertTrue(evaluate_design(run)["passed"])
        feedback = [e["data"]["message"] for e in run["events"] if e["kind"] == "MESSAGE_SENT" and e["data"]["message"]["type"] == "VERIFICATION_FEEDBACK"]
        self.assertEqual(feedback[0]["recipient"], "backend-agent")
        self.assertGreaterEqual(run["final_state"]["revision"], 3)
        self.assertTrue(all(v["revision"] == run["final_state"]["revision"] for v in run["final_state"]["reviews"].values()))

    def test_anthropic_receives_rejected_artifact_and_does_not_reuse_cached_bad_vote(self):
        class RepairClient(FakeClient):
            def submit(self, view):
                review, usage = super().submit(view)
                if review["decision"] == "ACCEPT" and "verification_feedback" not in view:
                    review["test_cases"][2]["assertion"].update(expected_state="COMPLETED", success=True)
                return review, usage
        client = RepairClient()
        run = run_design("negotiated", 7, AnthropicReviewer(client))
        self.assertTrue(run["quality"]["passed"])
        feedback = [v["verification_feedback"] for v in client.observations if "verification_feedback" in v]
        self.assertEqual(len(feedback), 1)
        self.assertTrue(feedback[0]["rejected_artifact"]["test_cases"][2]["assertion"]["success"])
        self.assertEqual(run["quality"]["metrics"]["repair_rounds"], 1)


if __name__ == "__main__":
    unittest.main()
