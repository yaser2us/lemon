"""Deterministic software-design participants. These produce specifications, not code."""

from copy import deepcopy

from .agents import Action
from .design_verification import TRANSITIONS

REQUIREMENTS = {
    "R1": "Accept a positive integer amount and an identified recipient.",
    "R2": "Expose pending, authentication, execution, success, and failure states to the UI.",
    "R3": "Retrying the same request must not create a second transfer.",
    "R4": "Show success only after transfer execution completes.",
}
ROLES = ("product-agent", "backend-agent", "ui-agent", "test-agent")


def action(kind, payload, explanation):
    return Action("world", kind, payload, explanation)


def challenge(revision, codes, explanation):
    return action("CHALLENGE", {"revision": revision, "issues": codes}, explanation)


def accept(revision, explanation, artifact=None):
    return action("ACCEPT", {"revision": revision, "artifact": artifact}, explanation)


class ProductAgent:
    identity = "product-agent"

    def start(self, cancellation):
        return action("PROPOSE_REQUIREMENTS", {"requirements": deepcopy(REQUIREMENTS), "cancellation": cancellation},
                      "Design a transfer feature with progress and authentication screens, safe retries, and success only after execution.")

    def decide(self, message, view):
        if view["cancellation"] == "UNDECIDED":
            return [action("ESCALATE", {"questions": ["Must users be able to cancel after submission? This needs a product decision before the interface can be agreed."]},
                           "Cancellation was requested but its behavior is unspecified. I will keep that question open.")]
        c = view["contract"]
        if c is None:
            return []
        if c["request"].get("amount") != "positive_integer" or c["request"].get("recipient_id") != "nonempty_string":
            return [challenge(view["revision"], ["INPUT_CONTRACT"], "The request must identify the recipient and constrain the amount.")]
        return [accept(view["revision"], "The operation and inputs match the requested feature. Cancellation is explicitly outside this exercise.")]


class BackendAgent:
    identity = "backend-agent"

    def decide(self, message, view):
        revision, c = view["revision"], view["contract"]
        if c is None:
            return [action("PROPOSE_CONTRACT", {"base_revision": 0, "contract": {
                "operation": "TRANSFER_MONEY", "request": {"amount": "positive_integer", "recipient_id": "nonempty_string"},
                "response": {"transaction_id": "nonempty_string", "status": "TransferStatus"},
                "states": ["REQUESTED", "AUTHORIZED", "FAILED"], "success_state": "AUTHORIZED", "idempotency": "none",
            }}, "Initial draft: submit amount and recipient, return a transaction status. I currently treat authorization as success; please review that assumption.")]
        issues = {issue for values in view["challenges"].values() for issue in values}
        issues.update(f["code"] for f in view.get("verification", {}).get("failures", []) if f["owner"] == self.identity)
        if not issues:
            return [accept(revision, "I can implement this version of the backend contract.")]
        revised = deepcopy(c)
        if "INPUT_CONTRACT" in issues:
            revised["request"].update(amount="positive_integer", recipient_id="nonempty_string")
        if "UI_STATES" in issues:
            revised["states"] = sorted(set(revised["states"]) | {"WAITING_FOR_AUTH", "EXECUTING", "REJECTED"})
        if "SUCCESS_AFTER_EXECUTION" in issues:
            revised["states"] = sorted(set(revised["states"]) | {"COMPLETED"})
            revised["success_state"] = "COMPLETED"
        if "IDEMPOTENCY" in issues:
            revised["request"]["idempotency_key"] = "nonempty_string"
            revised["idempotency"] = "same_key_same_transaction"
        if "TRANSITIONS" in issues or "SUCCESS_AFTER_EXECUTION" in issues:
            revised["transitions"] = deepcopy(TRANSITIONS)
        if revised == c:
            return [action("ESCALATE", {"questions": ["Backend cannot resolve these challenges: " + ", ".join(sorted(issues))]}, "The draft needs a decision beyond my current capabilities.")]
        return [action("PROPOSE_CONTRACT", {"base_revision": revision, "contract": revised},
                       "Revise the current draft to address: {}. All roles must review the new version.".format(", ".join(sorted(issues))))]


class UIAgent:
    identity = "ui-agent"

    def decide(self, message, view):
        c = view["contract"]
        if c is None:
            return []
        if not {"WAITING_FOR_AUTH", "EXECUTING", "REJECTED"} <= set(c["states"]):
            missing = sorted({"WAITING_FOR_AUTH", "EXECUTING", "REJECTED"} - set(c["states"]))
            return [challenge(view["revision"], ["UI_STATES"], "I cannot map the required screens yet. The current contract is missing: {}.".format(", ".join(missing)))]
        labels = {"REQUESTED": "Show pending", "WAITING_FOR_AUTH": "Show authentication challenge",
                  "AUTHORIZED": "Show authorized; still pending execution", "EXECUTING": "Show progress",
                  "COMPLETED": "Show success receipt", "REJECTED": "Show rejection reason", "FAILED": "Show execution failure"}
        mapping = {state: labels[state] for state in c["states"]}
        return [accept(view["revision"], "I can map every declared status to a UI state. Authorization will not display a success receipt.", {"ui_states": mapping})]


class TestAgent:
    identity = "test-agent"

    def decide(self, message, view):
        c = view["contract"]
        if c is None:
            return []
        issues = []
        if c["success_state"] != "COMPLETED" or "COMPLETED" not in c["states"]:
            issues.append("SUCCESS_AFTER_EXECUTION")
        if c["idempotency"] != "same_key_same_transaction" or c["request"].get("idempotency_key") != "nonempty_string":
            issues.append("IDEMPOTENCY")
        if not {"WAITING_FOR_AUTH", "EXECUTING", "REJECTED"} <= set(c["states"]):
            issues.append("UI_STATES")
        if issues:
            reasons = {"SUCCESS_AFTER_EXECUTION": "Authorization can still be followed by execution failure; success needs explicit completion.",
                       "IDEMPOTENCY": "A retried request must not create another transfer; define an idempotency key.",
                       "UI_STATES": "Authentication and failure test cases need explicit observable states."}
            return [challenge(view["revision"], issues, " ".join(reasons[i] for i in issues))]
        cases = [
            {"id": "T1", "requirement": "R1", "given": "amount <= 0 or recipient missing", "when": "submit", "then": "reject invalid input without creating a transfer"},
            {"id": "T2", "requirement": "R2", "given": "status WAITING_FOR_AUTH", "when": "render", "then": "show authentication challenge"},
            {"id": "T3", "requirement": "R3", "given": "two submissions with the same idempotency key", "when": "retry", "then": "return the same transaction; at most one transfer effect"},
            {"id": "T4", "requirement": "R4", "given": "status AUTHORIZED or EXECUTING", "when": "render", "then": "show pending; never a success receipt"},
            {"id": "T5", "requirement": "R4", "given": "execution fails after authorization", "when": "status becomes FAILED", "then": "show failure; never success"},
            {"id": "T6", "requirement": "R4", "given": "execution completed", "when": "status becomes COMPLETED", "then": "show success receipt"},
        ]
        scenarios = [("NONE", "reject_input", "REJECTED"), ("WAITING_FOR_AUTH", "render", "WAITING_FOR_AUTH"),
                     ("REQUESTED", "retry", "REQUESTED"), ("AUTHORIZED", "render", "AUTHORIZED"),
                     ("EXECUTING", "execute_failure", "FAILED"), ("EXECUTING", "execute_success", "COMPLETED")]
        cases.append({"id": "T7", "requirement": "R4", "given": "status EXECUTING", "when": "render", "then": "show pending; never success"})
        scenarios.append(("EXECUTING", "render", "EXECUTING"))
        for case, (initial, event, expected) in zip(cases, scenarios):
            case["assertion"] = {"initial_state": initial, "event": event, "expected_state": expected,
                                 "success": expected == "COMPLETED", "same_transaction": event == "retry"}
        return [accept(view["revision"], "These planned cases include structured assertions for model verification. Application tests have not been executed.", {"test_cases": cases})]


class RepairTestAgent(TestAgent):
    """Deliberately wrong first assertion makes the repair loop visible."""

    def decide(self, message, view):
        actions = super().decide(message, view)
        if actions and actions[0].kind == "ACCEPT" and not view.get("verification", {}).get("attempt", 0):
            actions[0].payload["artifact"]["test_cases"][2]["assertion"].update(expected_state="COMPLETED", success=True)
        return actions


class SilentTestAgent(TestAgent):
    def decide(self, message, view):
        return []
