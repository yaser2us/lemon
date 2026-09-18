"""Single-process World, seeded transport, simulated providers and executor."""

import heapq
import random
import time
from copy import deepcopy

from .agents import Action, AppAgent, LoopingAppAgent, PaymentAgent, RiskAgent
from .contracts import (POLICY_VERSION, PRODUCERS, TERMINAL, VERSION,
                        definitions, permission_error, validate_message)
from .events import EventLog


class World:
    def __init__(self, config, seed=7):
        self.config = deepcopy(config)
        self.seed, self.random, self.now = seed, random.Random(seed), 0
        self.queue, self.serial, self.message_number, self.evidence_number = [], 0, 0, 0
        self.pending, self.requests, self.attempts, self.issued = {}, {}, {}, {}
        self.seen, self.counts, self.invocations = set(), {}, {}
        self.decisions = {}
        self.log = EventLog()
        self.agents = {a.identity: a for a in [LoopingAppAgent() if config.get("fault") == "loop" else AppAgent(), RiskAgent(), PaymentAgent()]}
        self.budget = config.get("message_budget", 50)
        self.timeout = config.get("request_timeout", 20)
        self.retries = config.get("max_retries", 2)
        if self.budget < 1 or self.timeout < 1 or self.retries < 0:
            raise ValueError("Invalid runtime limits")
        transactions = {}
        for spec in config["transactions"]:
            if type(spec["amount"]) is not int or spec["amount"] <= 0 or spec["id"] in transactions:
                raise ValueError("Transactions require unique IDs and positive integer amounts")
            transactions[spec["id"]] = {
                "id": spec["id"], "user": spec.get("user", "user-1"), "account": "account-1",
                "amount": spec["amount"], "trusted_device": spec.get("trusted_device", True),
                "status": "requested", "conversation": "active", "version": 0,
                "evidence": {}, "conflicts": [], "reason": "INTENT_CREATED",
            }
        balance = config["balance"]
        if type(balance) is not int or balance < 0:
            raise ValueError("Balance must be a nonnegative integer")
        initial = {"ledger": {"balance": balance, "version": 0}, "transactions": transactions, "evidence": {}, "executions": {}}
        self.record("RUN_STARTED", {"initial_state": initial, "config": self.config, "seed": seed,
                                   "definitions": definitions(), "limits": {"messages": self.budget, "retries": self.retries, "request_timeout": self.timeout}})

    @property
    def state(self):
        return self.log.state

    def record(self, kind, data):
        return self.log.append(self.now, kind, data)

    def change(self, tx_id, **patch):
        before = deepcopy(self.state["transactions"][tx_id])
        after = deepcopy(before)
        after.update(patch)
        if before == after:
            return
        after["version"] += 1
        self.record("TRANSACTION_CHANGED", {"transaction_id": tx_id, "before": before, "after": after})

    def enqueue(self, due, kind, payload):
        self.serial += 1
        heapq.heappush(self.queue, (due, self.random.random(), self.serial, kind, deepcopy(payload)))

    def send(self, sender, tx_id, action, reply_to=None, delay=None):
        self.message_number += 1
        msg = {"schema_version": VERSION, "id": "msg-{:04d}".format(self.message_number),
               "conversation_id": tx_id, "sender": sender, "recipient": action.recipient,
               "subject": tx_id, "type": action.kind, "payload": deepcopy(action.payload),
               "timestamp": self.now, "explanation": action.explanation}
        if reply_to:
            msg["reply_to"] = reply_to
        if action.kind == "REQUEST_EVIDENCE":
            msg["deadline"] = self.now + self.timeout
        # Malformed or unauthorized agent output is delivered to the rejection
        # path without reserving requests or changing retry state.
        output_error = validate_message(msg)
        if not output_error:
            output_error = permission_error(msg)
        if action.kind == "REQUEST_EVIDENCE" and not output_error:
            key = (tx_id, action.payload["need"])
            if key in self.pending:
                self.record("REQUEST_SUPPRESSED", {"transaction_id": tx_id, "need": key[1], "reason": "ALREADY_PENDING"})
                return None
            attempt = self.attempts.get(key, 0) + 1
            if attempt > self.retries + 1:
                self.finish(tx_id, "escalated", "blocked", "EVIDENCE_RETRIES_EXHAUSTED")
                return None
            self.attempts[key] = attempt
            self.pending[key] = msg["id"]
            self.requests[msg["id"]] = deepcopy(msg)
            self.enqueue(msg["deadline"], "timeout", {"request": msg, "attempt": attempt})
            if attempt > 1:
                self.record("REQUEST_RETRIED", {"transaction_id": tx_id, "need": key[1], "attempt": attempt})
        self.record("MESSAGE_SENT", {"message": msg})
        self.enqueue(self.now + (self.random.randint(1, 3) if delay is None else delay), "message", {"message": msg, "origin": sender})
        if self.config.get("fault") == "duplicates" and (action.kind == "PROPOSE" or action.recipient == "executor"):
            self.enqueue(self.now + 4, "message", {"message": msg, "origin": sender})
            self.record("FAULT_INJECTED", {"transaction_id": tx_id, "fault": "DUPLICATE_DELIVERY", "message_id": msg["id"]})
        return msg

    def reject(self, msg, reason):
        if not isinstance(msg, dict):
            msg = {}
        tx_id = msg.get("conversation_id")
        tx = self.state["transactions"].get(tx_id) if isinstance(tx_id, str) else None
        self.record("MESSAGE_REJECTED", {"message_id": msg.get("id"), "transaction_id": tx_id,
                                        "reason": reason, "policy_version": POLICY_VERSION,
                                        "state_version": tx["version"] if tx else None,
                                        "evidence_ids": list(tx["evidence"].values()) if tx else []})

    def requirements(self, tx_id):
        tx, missing, negative = self.state["transactions"][tx_id], [], []
        facts = {}
        for need in ("identity", "balance", "risk", "auth"):
            ev = self.state["evidence"].get(tx["evidence"].get(need))
            valid = ev is not None and ev["issued_at"] <= self.now < ev["expires_at"]
            if valid and need == "balance":
                valid = ev["state_version"] == self.state["ledger"]["version"]
            if valid:
                facts[need] = ev["value"]
        for need in ("identity", "balance", "risk"):
            if need not in facts:
                missing.append(need)
        if facts.get("risk") == "HIGH" and "auth" not in facts:
            missing.append("auth")
        if facts.get("identity") is False:
            negative.append("IDENTITY_FAILED")
        if "balance" in facts and facts["balance"] < tx["amount"]:
            negative.append("INSUFFICIENT_BALANCE")
        if facts.get("risk") == "HIGH" and facts.get("auth") is False:
            negative.append("AUTHENTICATION_FAILED")
        if tx["conflicts"]:
            negative.append("UNRESOLVED_CONFLICT")
        return missing, negative, facts

    def decision(self, tx_id, result, reason, trigger, missing=None):
        tx = deepcopy(self.state["transactions"][tx_id])
        decision_id = "decision-{:04d}".format(len(self.decisions) + 1)
        data = {"id": decision_id, "transaction_id": tx_id, "result": result, "reason": reason,
                "trigger_message_id": trigger["id"], "policy_version": POLICY_VERSION,
                "laws_evaluated": list(definitions()["laws"]), "transaction": tx,
                "ledger": deepcopy(self.state["ledger"]), "evidence_ids": list(tx["evidence"].values()),
                "missing": missing or []}
        self.decisions[decision_id] = deepcopy(data)
        self.record("POLICY_DECISION", data)
        return decision_id

    def evaluate(self, tx_id, trigger):
        tx = self.state["transactions"][tx_id]
        if tx["conversation"] in TERMINAL:
            return
        missing, negative, _ = self.requirements(tx_id)
        if tx["conflicts"]:
            # A queued reevaluation cannot turn an unresolved challenge into a
            # permanent rejection. Let the App Agent explicitly escalate it.
            return
        if negative:
            self.decision(tx_id, "REJECTED", negative[0], trigger, missing)
            self.finish(tx_id, "rejected", "blocked", negative[0])
            return
        result, reason = ("PENDING", "MISSING_EVIDENCE") if missing else ("READY", "REQUIREMENTS_SATISFIED")
        self.change(tx_id, status="pending_evidence", conversation="waiting" if missing else "active", reason=reason)
        decision_id = self.decision(tx_id, result, reason, trigger, missing)
        recipient = "app-agent" if missing else "payment-agent"
        self.send("world", tx_id, Action(recipient, "DECISION", {"result": result, "reason": reason, "missing": missing, "decision_id": decision_id},
                                       "Missing: {}.".format(", ".join(missing)) if missing else "Evidence is sufficient to request execution."), trigger["id"])

    def view(self, actor, tx_id):
        tx = self.state["transactions"][tx_id]
        missing, negative, _ = self.requirements(tx_id)
        base = {"transaction_id": tx_id, "status": tx["status"]}
        if actor == "app-agent":
            base.update(missing=missing, pending=[need for conv, need in self.pending if conv == tx_id])
        elif actor == "risk-agent":
            base.update(amount=tx["amount"], trusted_device=tx["trusted_device"])
        elif actor == "payment-agent":
            base.update(balance=self.state["ledger"]["balance"], ready=not missing and not negative)
        return deepcopy(base)

    def issue(self, producer, tx_id, need, value):
        self.evidence_number += 1
        tx = self.state["transactions"][tx_id]
        return {"schema_version": VERSION, "id": "ev-{:04d}".format(self.evidence_number),
                "type": need, "producer": producer, "subject": tx["user"], "transaction_id": tx_id,
                "value": value, "source": "simulated:" + producer, "issued_at": self.now,
                "expires_at": self.now + 200, "state_version": self.state["ledger"]["version"] if need == "balance" else 0}

    def provide(self, producer, request, need, value, explanation):
        tx_id, fault = request["conversation_id"], self.config.get("fault")
        attempt = self.attempts[(tx_id, need)]
        if need == "identity" and fault == "unavailable":
            self.record("PROVIDER_UNAVAILABLE", {"transaction_id": tx_id, "provider": producer, "request_id": request["id"]})
            return
        ev = self.issue(producer, tx_id, need, value)
        if need == "identity" and attempt == 1:
            if fault == "expired":
                ev["expires_at"] = self.now
            elif fault == "wrong_subject":
                ev["subject"] = "another-user"
        self.issued[ev["id"]] = deepcopy(ev)
        delay = 8 if fault == "reordered" and need == "identity" else 1
        if fault == "stale_balance" and need == "balance" and tx_id == "TX-2" and attempt == 1:
            delay = 15
        destination = tx_id
        if fault == "cross_conversation" and need == "identity" and tx_id == "TX-1" and attempt == 1:
            destination = "TX-2"
        msg = self.send(producer, destination, Action("world", "PROVIDE_EVIDENCE", {"evidence": ev}, explanation), request["id"], delay=delay)
        if fault == "conflict" and need == "identity":
            contrary = self.issue(producer, tx_id, need, not value)
            self.issued[contrary["id"]] = deepcopy(contrary)
            self.send(producer, tx_id, Action("world", "PROVIDE_EVIDENCE", {"evidence": contrary}, "Fault injection: conflicting authoritative observation."), request["id"], delay=delay + 1)
        if fault == "duplicates" and need == "identity":
            self.enqueue(self.now + 3, "message", {"message": msg, "origin": producer})

    def invoke(self, msg):
        actor, tx_id = msg["recipient"], msg["conversation_id"]
        if actor in {"identity-provider", "auth-provider"}:
            need = msg["payload"]["need"]
            value = self.config.get("identity_valid", True) if need == "identity" else self.config.get("auth_success", True)
            self.provide(actor, msg, need, value, "Simulated provider attests {} = {}.".format(need, value))
            return
        agent = self.agents[actor]
        view = self.view(actor, tx_id)
        self.invocations[actor] = self.invocations.get(actor, 0) + 1
        try:
            actions = agent.decide(deepcopy(msg), deepcopy(view))
            if not isinstance(actions, list) or any(not isinstance(action, Action) for action in actions):
                raise TypeError("Agents must return a list of Actions")
        except Exception as exc:
            self.record("AGENT_FAILED", {"transaction_id": tx_id, "agent": actor, "message_id": msg["id"], "error_type": type(exc).__name__})
            self.finish(tx_id, "escalated", "blocked", "AGENT_ERROR")
            return
        self.record("AGENT_OBSERVED", {"transaction_id": tx_id, "agent": actor, "message_id": msg["id"], "view": view, "actions": len(actions)})
        for action in actions:
            if self.state["transactions"][tx_id]["conversation"] in TERMINAL:
                break
            if action.kind == "PROVIDE_EVIDENCE":
                self.provide(actor, msg, action.payload["type"], action.payload["value"], action.explanation)
            else:
                self.send(actor, tx_id, action, msg["id"])

    def evidence_error(self, msg):
        ev, tx_id = msg["payload"]["evidence"], msg["conversation_id"]
        tx = self.state["transactions"][tx_id]
        req = self.requests.get(msg.get("reply_to"))
        if not req or req["conversation_id"] != tx_id:
            return "CROSS_CONVERSATION_OR_UNKNOWN_REPLY"
        if req["recipient"] != msg["sender"] or req["payload"]["need"] != ev["type"]:
            return "EVIDENCE_REQUEST_MISMATCH"
        if ev["subject"] != tx["user"] or ev["transaction_id"] != tx_id:
            return "EVIDENCE_SUBJECT_MISMATCH"
        if self.issued.get(ev["id"]) != ev:
            return "UNATTESTED_EVIDENCE"
        if ev["issued_at"] > self.now or ev["expires_at"] <= self.now:
            return "EVIDENCE_EXPIRED_OR_FUTURE"
        if ev["type"] == "balance" and ev["state_version"] != self.state["ledger"]["version"]:
            return "STALE_BALANCE_EVIDENCE"
        current = self.state["evidence"].get(tx["evidence"].get(ev["type"]))
        if current and current["expires_at"] > self.now and current["state_version"] == ev["state_version"] and current["value"] != ev["value"]:
            return "CONFLICTING_EVIDENCE"
        if self.pending.get((tx_id, ev["type"])) != req["id"]:
            return "STALE_RESPONSE"
        return None

    def accept_evidence(self, msg):
        tx_id, ev = msg["conversation_id"], msg["payload"]["evidence"]
        error = self.evidence_error(msg)
        key = (tx_id, ev["type"])
        if error:
            self.reject(msg, error)
            if error == "CONFLICTING_EVIDENCE":
                tx = self.state["transactions"][tx_id]
                self.change(tx_id, conflicts=sorted(set(tx["conflicts"] + [ev["type"]])), reason=error)
                self.send("world", tx_id, Action("app-agent", "CHALLENGE", {"reason": error}, "Two current authoritative claims disagree; no trusted resolution is available."), msg["id"])
            elif error in {"EVIDENCE_EXPIRED_OR_FUTURE", "EVIDENCE_SUBJECT_MISMATCH", "STALE_BALANCE_EVIDENCE"} and self.pending.get(key) == msg["reply_to"]:
                self.pending.pop(key)
                self.evaluate(tx_id, msg)
            return
        self.pending.pop(key)
        self.record("EVIDENCE_ACCEPTED", {"transaction_id": tx_id, "message_id": msg["id"], "evidence": ev})
        mapping = dict(self.state["transactions"][tx_id]["evidence"])
        mapping[ev["type"]] = ev["id"]
        self.change(tx_id, evidence=mapping)
        self.evaluate(tx_id, msg)

    def authorize(self, msg):
        tx_id = msg["conversation_id"]
        missing, negative, _ = self.requirements(tx_id)
        if missing or negative:
            self.evaluate(tx_id, msg)
            return
        decision_id = self.decision(tx_id, "ALLOWED", "EXECUTION_AUTHORIZED", msg)
        self.change(tx_id, status="authorized", conversation="active", reason="EXECUTION_AUTHORIZED")
        self.send("world", tx_id, Action("executor", "DECISION", {"result": "ALLOWED", "reason": "EXECUTION_AUTHORIZED", "missing": [], "decision_id": decision_id}, "Execute only if authorization still matches current evidence and state."), msg["id"])

    def execute(self, msg):
        tx_id = msg["conversation_id"]
        tx = self.state["transactions"][tx_id]
        auth = self.decisions.get(msg["payload"]["decision_id"])
        if not auth or auth["transaction_id"] != tx_id or auth["result"] != "ALLOWED" or tx["status"] != "authorized":
            self.reject(msg, "INVALID_EXECUTION_AUTHORIZATION")
            return
        missing, negative, _ = self.requirements(tx_id)
        if missing or negative:
            self.record("AUTHORIZATION_RECHECK_FAILED", {"transaction_id": tx_id, "decision_id": auth["id"], "missing": missing, "negative": negative})
            self.evaluate(tx_id, msg)
            return
        before = deepcopy(self.state["ledger"])
        if before["balance"] < tx["amount"] or tx_id in self.state["executions"]:
            self.reject(msg, "ATOMIC_EXECUTION_GUARD")
            self.finish(tx_id, "rejected", "blocked", "ATOMIC_EXECUTION_GUARD")
            return
        checked = self.decision(tx_id, "ALLOWED", "EXECUTION_RECHECK_PASSED", msg)
        self.change(tx_id, status="executing", reason="EXECUTION_RECHECK_PASSED")
        if self.config.get("fault") == "execution_failure":
            self.finish(tx_id, "rejected", "failed", "SIMULATED_EXECUTION_FAILURE")
            return
        self.record("TRANSFER_EXECUTED", {"transaction_id": tx_id, "amount": tx["amount"], "before": before,
                                          "after": {"balance": before["balance"] - tx["amount"], "version": before["version"] + 1},
                                          "decision_id": checked, "authorization_id": auth["id"], "trigger_message_id": msg["id"]})
        self.finish(tx_id, "completed", "completed", "TRANSFER_COMPLETED")

    def finish(self, tx_id, conversation, status, reason):
        if self.state["transactions"][tx_id]["conversation"] in TERMINAL:
            return
        self.change(tx_id, conversation=conversation, status=status, reason=reason)
        for key in list(self.pending):
            if key[0] == tx_id:
                del self.pending[key]
        self.send("world", tx_id, Action("app-agent", "COMPLETE", {"status": conversation, "reason": reason}, "Conversation ended: {} ({}).".format(conversation, reason)), delay=0)

    def deliver(self, msg, origin):
        self.record("MESSAGE_RECEIVED", {"message": msg, "origin": origin})
        error = validate_message(msg)
        if not error and origin != msg["sender"]:
            error = "SENDER_SPOOFING"
        if not error:
            error = permission_error(msg)
        tx_id = msg.get("conversation_id") if isinstance(msg, dict) else None
        if not error and (tx_id not in self.state["transactions"] or msg["subject"] != tx_id):
            error = "CONVERSATION_SUBJECT_MISMATCH"
        if error:
            self.reject(msg, error)
            return
        key = (origin, msg["id"])
        if key in self.seen:
            self.record("DUPLICATE_IGNORED", {"message_id": msg["id"], "transaction_id": tx_id})
            return
        self.seen.add(key)
        tx = self.state["transactions"][tx_id]
        if tx["conversation"] in TERMINAL:
            if msg["type"] == "COMPLETE":
                self.record("MESSAGE_ACCEPTED", {"message_id": msg["id"], "transaction_id": tx_id})
                self.invoke(msg)
            else:
                self.reject(msg, "CONVERSATION_TERMINATED")
            return
        self.counts[tx_id] = self.counts.get(tx_id, 0) + 1
        if self.counts[tx_id] > self.budget:
            self.reject(msg, "MESSAGE_BUDGET_EXHAUSTED")
            self.finish(tx_id, "budget_exhausted", "blocked", "MESSAGE_BUDGET_EXHAUSTED")
            return
        if msg["type"] == "REQUEST_EVIDENCE":
            if self.pending.get((tx_id, msg["payload"]["need"])) != msg["id"] or self.now >= msg["deadline"]:
                self.reject(msg, "REQUEST_NO_LONGER_PENDING")
                return
        self.record("MESSAGE_ACCEPTED", {"message_id": msg["id"], "transaction_id": tx_id})
        if msg["recipient"] == "executor":
            self.execute(msg)
        elif msg["recipient"] != "world":
            self.invoke(msg)
        elif msg["type"] == "PROVIDE_EVIDENCE":
            self.accept_evidence(msg)
        elif msg["type"] == "ESCALATE":
            self.finish(tx_id, "escalated", "blocked", msg["payload"]["reason"])
        elif msg["type"] == "PROPOSE":
            if msg["payload"]["action"] == "TRANSFER":
                self.evaluate(tx_id, msg)
            else:
                self.authorize(msg)

    def inject(self):
        fault = self.config.get("fault")
        tx_id = next(iter(self.state["transactions"]))
        if fault in {"unauthorized", "late", "spoof", "malformed"}:
            sender = "risk-agent" if fault == "unauthorized" else "app-agent"
            msg = self.send(sender, tx_id, Action("world", "PROPOSE", {"action": "EXECUTE" if fault == "unauthorized" else "TRANSFER"}, "Deliberate fault injection."), delay=100 if fault == "late" else 0)
            if fault in {"spoof", "malformed"}:
                # Replace the queued delivery, preserving a recorded injection.
                self.queue = [entry for entry in self.queue if not (entry[3] == "message" and entry[4]["message"]["id"] == msg["id"])]
                heapq.heapify(self.queue)
                if fault == "malformed":
                    msg["payload"] = {"action": "TRANSFER", "unexpected": True}
                self.enqueue(0, "message", {"message": msg, "origin": "risk-agent" if fault == "spoof" else sender})
        elif fault == "unauthorized_evidence":
            ev = self.issue("app-agent", tx_id, "identity", True)
            self.send("app-agent", tx_id, Action("world", "PROVIDE_EVIDENCE", {"evidence": ev}, "Deliberate unauthorized identity claim."), reply_to="fabricated-request", delay=0)

    def run(self):
        started = time.perf_counter()
        for tx_id in self.state["transactions"]:
            self.send("app-agent", tx_id, self.agents["app-agent"].start())
        self.inject()
        while self.queue:
            due, _, _, kind, payload = heapq.heappop(self.queue)
            if kind == "timeout":
                req = payload["request"]
                key = (req["conversation_id"], req["payload"]["need"])
                if self.pending.get(key) != req["id"]:
                    continue
                self.now = due
                self.pending.pop(key)
                self.record("REQUEST_TIMEOUT", {"transaction_id": key[0], "need": key[1], "request_id": req["id"], "attempt": payload["attempt"]})
                if payload["attempt"] > self.retries:
                    self.finish(key[0], "timed_out", "blocked", "PROVIDER_TIMEOUT")
                else:
                    self.send("app-agent", key[0], Action(req["recipient"], "REQUEST_EVIDENCE", deepcopy(req["payload"]), "Retry the unanswered evidence request."), req["id"])
            else:
                self.now = due
                self.deliver(payload["message"], payload["origin"])
        for tx_id, tx in list(self.state["transactions"].items()):
            if tx["conversation"] not in TERMINAL:
                self.finish(tx_id, "escalated", "blocked", "NO_PROGRESS_POSSIBLE")
        # Deliver only terminal notices created by the no-progress safeguard.
        while self.queue:
            due, _, _, kind, payload = heapq.heappop(self.queue)
            if kind == "message":
                self.now = due
                self.deliver(payload["message"], payload["origin"])
        return {"format_version": VERSION, "scenario": self.config["name"], "seed": self.seed,
                "events": deepcopy(self.log.events), "final_state": deepcopy(self.state),
                "runtime_ms": round((time.perf_counter() - started) * 1000, 3)}
