"""Versioned software-interface negotiation using the shared message envelope and audit log."""

import heapq
import random
import time
from copy import deepcopy

from .agents import Action
from .anthropic_reviewer import ReviewError
from .contracts import validate_envelope
from .design_agents import (ROLES, BackendAgent, ProductAgent, SilentTestAgent,
                            TestAgent, UIAgent, RepairTestAgent)
from .design_verification import verify_design
from .events import EventLog, digest

VARIANTS = ("negotiated", "missing-decision", "silent-reviewer", "duplicate-delivery", "repair-demo")
STATES = {"REQUESTED", "WAITING_FOR_AUTH", "AUTHORIZED", "EXECUTING", "COMPLETED", "REJECTED", "FAILED"}
ISSUES = {"INPUT_CONTRACT", "UI_STATES", "SUCCESS_AFTER_EXECUTION", "IDEMPOTENCY"}


def valid_contract(c):
    if not isinstance(c, dict) or set(c) - {"transitions"} != {"operation", "request", "response", "states", "success_state", "idempotency"}:
        return False
    return (c["operation"] == "TRANSFER_MONEY" and isinstance(c["request"], dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in c["request"].items())
            and c["response"] == {"transaction_id": "nonempty_string", "status": "TransferStatus"}
            and isinstance(c["states"], list) and bool(c["states"])
            and all(isinstance(s, str) and s in STATES for s in c["states"])
            and len(set(c["states"])) == len(c["states"])
            and isinstance(c["success_state"], str) and c["success_state"] in c["states"]
            and c["idempotency"] in {"none", "same_key_same_transaction"})


def validate_design_message(msg):
    try:
        error = validate_envelope(msg, set(ROLES) | {"world"})
        if error:
            return error
        if msg["conversation_id"] != "FEATURE-1" or msg["subject"] != "transfer-feature":
            return "WRONG_CONVERSATION"
        sender, recipient, kind, p = (msg[k] for k in ("sender", "recipient", "type", "payload"))
        if kind == "VERIFICATION_FEEDBACK":
            allowed = sender == "world" and recipient in ROLES
            shape = (set(p) == {"revision", "attempt", "failures", "rejected_artifact"} and type(p["revision"]) is int
                     and type(p["attempt"]) is int and isinstance(p["failures"], list))
        elif kind == "REVIEW":
            allowed = sender == "world" and recipient in ROLES
            shape = set(p) == {"revision"} and type(p["revision"]) is int and p["revision"] >= 0
        elif kind == "PROPOSE_REQUIREMENTS":
            allowed = sender == "product-agent" and recipient == "world"
            shape = (set(p) == {"requirements", "cancellation"} and isinstance(p["requirements"], dict)
                     and bool(p["requirements"]) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in p["requirements"].items())
                     and p["cancellation"] in {"OUT_OF_SCOPE", "UNDECIDED"})
        elif kind == "PROPOSE_CONTRACT":
            allowed = sender == "backend-agent" and recipient == "world"
            shape = set(p) == {"base_revision", "contract"} and type(p["base_revision"]) is int and p["base_revision"] >= 0 and valid_contract(p["contract"])
        elif kind == "CHALLENGE":
            allowed = sender in ROLES and recipient == "world"
            shape = (set(p) == {"revision", "issues"} and type(p["revision"]) is int and p["revision"] > 0
                     and isinstance(p["issues"], list) and bool(p["issues"]) and all(isinstance(i, str) and i in ISSUES for i in p["issues"]))
        elif kind == "ACCEPT":
            allowed = sender in ROLES and recipient == "world"
            shape = (set(p) == {"revision", "artifact"} and type(p["revision"]) is int and p["revision"] > 0
                     and (p["artifact"] is None or isinstance(p["artifact"], dict)))
            if shape and sender == "ui-agent":
                a = p["artifact"]
                shape = isinstance(a, dict) and set(a) == {"ui_states"} and isinstance(a["ui_states"], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in a["ui_states"].items())
            if shape and sender == "test-agent":
                a = p["artifact"]
                shape = (isinstance(a, dict) and set(a) == {"test_cases"} and isinstance(a["test_cases"], list)
                         and bool(a["test_cases"]) and all(isinstance(case, dict) and set(case) - {"assertion"} == {"id", "requirement", "given", "when", "then"}
                                                          and all(isinstance(case[k], str) and case[k] for k in ("id", "requirement", "given", "when", "then")) for case in a["test_cases"]))
        elif kind == "ESCALATE":
            allowed = sender in ROLES and recipient == "world"
            shape = set(p) == {"questions"} and isinstance(p["questions"], list) and bool(p["questions"]) and all(isinstance(q, str) and q for q in p["questions"])
        else:
            return "UNKNOWN_DESIGN_MESSAGE"
        if not allowed:
            return "UNAUTHORIZED_MESSAGE"
        return None if shape else "INVALID_DESIGN_PAYLOAD"
    except (TypeError, ValueError):
        return "INVALID_DESIGN_PAYLOAD"


class DesignWorld:
    def __init__(self, seed=7, variant="negotiated", message_budget=120, reviewer=None, on_event=None):
        if variant not in VARIANTS or type(message_budget) is not int or message_budget < 1:
            raise ValueError("Unknown design variant or invalid message budget")
        self.seed, self.variant, self.budget = seed, variant, message_budget
        self.random, self.now, self.serial, self.counter, self.processed = random.Random(seed), 0, 0, 0, 0
        self.queue, self.seen, self.emitted = [], set(), set()
        self.agents = {a.identity: a for a in [ProductAgent(), BackendAgent(), UIAgent(), SilentTestAgent() if variant == "silent-reviewer" else TestAgent()]}
        if variant == "repair-demo":
            self.agents["test-agent"] = RepairTestAgent()
        self.reviewer_metadata = {"provider": "deterministic"}
        self.requested_reviewer = reviewer is not None
        if reviewer is not None:
            if variant == "silent-reviewer":
                self.reviewer_metadata = {"provider": "disabled_by_scenario", "reason": "silent-reviewer must remain silent"}
            else:
                self.agents["test-agent"] = reviewer
                self.reviewer_metadata = deepcopy(reviewer.metadata)
        self.log = EventLog(on_event=on_event)
        initial = {"domain": "software-design", "status": "active", "revision": 0,
                   "requirements": {}, "cancellation": None, "contract": None, "reviews": {},
                   "challenges": {}, "questions": [], "reason": "AWAITING_REQUIREMENTS",
                   "verification": {"status": "pending", "attempt": 0, "failures": []}}
        self.record("RUN_STARTED", {"initial_state": initial, "seed": seed, "variant": variant,
                                   "protocol": "software-design-v2", "participants": list(ROLES),
                                   "limits": {"messages": message_budget, "repair_rounds": 3}, "reviewer": self.reviewer_metadata,
                                   "feature": "Transfer feature interface negotiation"})

    @property
    def state(self):
        return self.log.state

    def record(self, kind, data):
        return self.log.append(self.now, kind, data)

    def change(self, trigger, **patch):
        before = deepcopy(self.state)
        after = {**before, **deepcopy(patch)}
        if before != after:
            self.record("DESIGN_CHANGED", {"before": before, "after": after, "cause_message_id": trigger})

    def enqueue(self, msg, origin, delay):
        self.serial += 1
        heapq.heappush(self.queue, (self.now + delay, self.random.random(), self.serial, deepcopy(msg), origin))

    def send(self, sender, action, reply_to=None):
        self.counter += 1
        msg = {"schema_version": 1, "id": "design-msg-{:04d}".format(self.counter), "conversation_id": "FEATURE-1",
               "sender": sender, "recipient": action.recipient, "subject": "transfer-feature", "type": action.kind,
               "payload": deepcopy(action.payload), "timestamp": self.now, "explanation": action.explanation}
        if reply_to:
            msg["reply_to"] = reply_to
        self.record("MESSAGE_SENT", {"message": msg})
        self.enqueue(msg, sender, self.random.randint(1, 3))
        if self.variant == "duplicate-delivery" and action.kind in {"ACCEPT", "PROPOSE_CONTRACT"}:
            self.enqueue(msg, sender, 4)
        return msg

    def notify(self, participants=ROLES, reply_to=None):
        for role in participants:
            self.send("world", Action(role, "REVIEW", {"revision": self.state["revision"]},
                                      "Review the current shared draft and respond within your role."), reply_to)

    def reject(self, msg, reason):
        self.record("MESSAGE_REJECTED", {"message_id": msg.get("id") if isinstance(msg, dict) else None,
                                        "reason": reason, "current_revision": self.state["revision"]})

    def view(self, role):
        # Design participants share the draft, requirements, and open challenges.
        # They never receive scenario expectations or another role's private state.
        return deepcopy({key: self.state[key] for key in ("revision", "requirements", "cancellation", "contract", "challenges", "verification")})

    def invoke(self, msg):
        actor = msg["recipient"]
        view = self.view(actor)
        try:
            actions = self.agents[actor].decide(deepcopy(msg), deepcopy(view))
            if not isinstance(actions, list) or any(not isinstance(a, Action) for a in actions):
                raise TypeError("Agents must return Actions")
        except Exception as exc:
            self.capture_model_calls(actor, msg["id"])
            code = exc.code if isinstance(exc, ReviewError) else "AGENT_ERROR"
            self.record("AGENT_FAILED", {"agent": actor, "message_id": msg["id"], "error_type": type(exc).__name__, "error_code": code})
            self.change(msg["id"], status="needs_review", reason=code, questions=[actor + " could not finish the review: " + code])
            return
        self.capture_model_calls(actor, msg["id"])
        self.record("AGENT_OBSERVED", {"agent": actor, "message_id": msg["id"], "revision": view["revision"], "actions": len(actions)})
        for action in actions:
            # Repeated notifications about the same draft need not repeat a vote.
            key = (actor, view["revision"], view["verification"]["attempt"], action.kind, digest(action.payload))
            if key in self.emitted:
                self.record("REDUNDANT_RESPONSE_SUPPRESSED", {"agent": actor, "revision": view["revision"], "type": action.kind})
                continue
            self.emitted.add(key)
            self.send(actor, action, msg["id"])

    def capture_model_calls(self, actor, message_id):
        agent = self.agents[actor]
        if hasattr(agent, "drain_telemetry"):
            for data in agent.drain_telemetry():
                self.record("MODEL_REVIEW", {**data, "trigger_message_id": message_id})

    def deliver(self, msg, origin):
        self.record("MESSAGE_RECEIVED", {"message": msg, "origin": origin})
        error = validate_design_message(msg)
        if not error and msg["sender"] != origin:
            error = "SENDER_SPOOFING"
        if error:
            self.reject(msg, error)
            return
        if msg["id"] in self.seen:
            self.record("DUPLICATE_IGNORED", {"message_id": msg["id"]})
            return
        self.seen.add(msg["id"])
        if self.state["status"] != "active":
            self.reject(msg, "CONVERSATION_TERMINATED")
            return
        if self.processed >= self.budget:
            self.reject(msg, "MESSAGE_BUDGET_EXHAUSTED")
            self.change(msg["id"], status="budget_exhausted", reason="MESSAGE_BUDGET_EXHAUSTED", questions=["The agents did not converge within the communication budget."])
            return
        self.processed += 1
        p, kind, sender = msg["payload"], msg["type"], msg["sender"]
        revision = p.get("revision", p.get("base_revision"))
        if revision is not None and revision != self.state["revision"]:
            self.reject(msg, "STALE_REVISION")
            if sender in ROLES:
                self.notify((sender,), msg["id"])
            return
        self.record("MESSAGE_ACCEPTED", {"message_id": msg["id"], "revision": self.state["revision"]})
        if kind in {"REVIEW", "VERIFICATION_FEEDBACK"}:
            self.invoke(msg)
        elif kind == "PROPOSE_REQUIREMENTS":
            if self.state["requirements"]:
                self.reject(msg, "REQUIREMENTS_ALREADY_DEFINED")
                return
            self.change(msg["id"], requirements=p["requirements"], cancellation=p["cancellation"], reason="REQUIREMENTS_PROPOSED")
            self.notify(reply_to=msg["id"])
        elif kind == "PROPOSE_CONTRACT":
            if not self.state["requirements"]:
                self.reject(msg, "REQUIREMENTS_MISSING")
                return
            if p["contract"] == self.state["contract"]:
                self.reject(msg, "UNCHANGED_DRAFT")
                return
            self.change(msg["id"], revision=self.state["revision"] + 1, contract=p["contract"], reviews={}, challenges={},
                        verification={"status": "pending", "attempt": self.state["verification"]["attempt"], "failures": []}, reason="DRAFT_REVISED")
            self.notify(reply_to=msg["id"])
        elif kind == "CHALLENGE":
            challenges = {**self.state["challenges"], sender: p["issues"]}
            reviews = {k: v for k, v in self.state["reviews"].items() if k != sender}
            self.change(msg["id"], challenges=challenges, reviews=reviews, reason="CHALLENGE_OPEN")
            self.notify(("backend-agent",), msg["id"])
        elif kind == "ACCEPT":
            if self.state["contract"] is None:
                self.reject(msg, "DRAFT_MISSING")
                return
            if sender in self.state["challenges"]:
                self.reject(msg, "CHALLENGE_REQUIRES_REVISION")
                return
            reviews = {**self.state["reviews"], sender: {"revision": revision, "message_id": msg["id"], "artifact": p["artifact"]}}
            self.change(msg["id"], reviews=reviews, reason="REVIEW_ACCEPTED")
            if set(reviews) == set(ROLES) and not self.state["challenges"] and self.state["cancellation"] != "UNDECIDED":
                self.verify(msg["id"])
        elif kind == "ESCALATE":
            self.change(msg["id"], status="needs_input", reason="UNRESOLVED_QUESTION", questions=p["questions"])

    def verify(self, trigger):
        failures = verify_design(self.state)
        attempt = self.state["verification"]["attempt"]
        result = {"status": "failed" if failures else "passed", "attempt": attempt, "failures": failures}
        self.record("DESIGN_VERIFIED", {"revision": self.state["revision"], **result})
        if not failures:
            self.change(trigger, verification=result, status="agreed", reason="ALL_ROLES_ACCEPT_AND_VERIFICATION_PASSED")
            return
        if attempt >= 3:
            self.change(trigger, verification=result, status="needs_review", reason="VERIFICATION_REPAIR_LIMIT",
                        questions=["{}: {}".format(f["owner"], f["detail"]) for f in failures])
            return
        result["attempt"] += 1
        owners = {f["owner"] for f in failures}
        previous = self.state["reviews"]
        self.change(trigger, verification=result, reviews={k: v for k, v in previous.items() if k not in owners}, reason="VERIFICATION_REPAIR_REQUIRED")
        for owner in sorted(owners):
            specific = [f for f in failures if f["owner"] == owner]
            self.send("world", Action(owner, "VERIFICATION_FEEDBACK", {
                "revision": self.state["revision"], "attempt": result["attempt"], "failures": specific,
                "rejected_artifact": previous.get(owner, {}).get("artifact")},
                "Verification failed. Repair your proposal: " + " ".join(f["detail"] for f in specific)), trigger)

    def run(self):
        started = time.perf_counter()
        self.send("product-agent", self.agents["product-agent"].start("UNDECIDED" if self.variant == "missing-decision" else "OUT_OF_SCOPE"))
        while self.queue:
            self.now, _, _, msg, origin = heapq.heappop(self.queue)
            self.deliver(msg, origin)
        if self.state["status"] == "active":
            missing = sorted(set(ROLES) - set(self.state["reviews"]))
            questions = ["Review still required from {} for revision {}.".format(role, self.state["revision"]) for role in missing]
            questions += ["Unresolved challenge from {}: {}.".format(role, ", ".join(issues)) for role, issues in self.state["challenges"].items()]
            self.change(None, status="needs_review", reason="NO_PROGRESS_POSSIBLE", questions=questions or ["No agreement was reached."])
        return {"format_version": 1, "domain": "software-design", "scenario": "design-" + ("anthropic-" if self.requested_reviewer else "") + self.variant,
                "variant": self.variant, "seed": self.seed, "events": deepcopy(self.log.events),
                "reviewer": deepcopy(self.reviewer_metadata), "final_state": deepcopy(self.state),
                "runtime_ms": round((time.perf_counter() - started) * 1000, 3)}
