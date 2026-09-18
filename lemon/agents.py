"""Local decisions over restricted snapshots. Agents cannot access World."""

from dataclasses import dataclass
from typing import Any, Dict, List

from .contracts import PRODUCERS


@dataclass(frozen=True)
class Action:
    recipient: str
    kind: str
    payload: Dict[str, Any]
    explanation: str


class AppAgent:
    identity = "app-agent"

    def start(self):
        return Action("world", "PROPOSE", {"action": "TRANSFER"}, "Please fulfill the user's transfer intent.")

    def decide(self, message, view) -> List[Action]:
        if message["type"] == "CHALLENGE":
            return [Action("world", "ESCALATE", {"reason": message["payload"]["reason"]}, "Conflicting authoritative evidence needs intervention.")]
        if message["type"] != "DECISION" or message["payload"]["result"] != "PENDING":
            return []
        return [Action(PRODUCERS[need], "REQUEST_EVIDENCE", {"need": need}, "Please provide current {} evidence for this transaction.".format(need))
                for need in message["payload"]["missing"]
                if need in view["missing"] and need not in view["pending"]]


class RiskAgent:
    identity = "risk-agent"

    def decide(self, message, view):
        if message["type"] != "REQUEST_EVIDENCE":
            return []
        high = view["amount"] > 3000 or not view["trusted_device"]
        return [Action("world", "PROVIDE_EVIDENCE", {"type": "risk", "value": "HIGH" if high else "LOW"}, "Assess risk using amount and device trust.")]


class PaymentAgent:
    identity = "payment-agent"

    def decide(self, message, view):
        if message["type"] == "REQUEST_EVIDENCE":
            return [Action("world", "PROVIDE_EVIDENCE", {"type": "balance", "value": view["balance"]}, "Report the current simulated account balance.")]
        if message["type"] == "DECISION" and message["payload"]["result"] == "READY":
            reason = "Requirements appear satisfied; request execution authorization." if view["ready"] else "State changed since the readiness notice; request a fresh authorization check."
            return [Action("world", "PROPOSE", {"action": "EXECUTE"}, reason)]
        return []


class LoopingAppAgent(AppAgent):
    """Deliberately faulty participant used only by the budget-exhaustion scenario."""

    def decide(self, message, view):
        if message["type"] == "DECISION":
            return [self.start()]
        return []
