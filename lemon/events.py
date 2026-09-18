"""Hash-linked event log and side-effect-free state replay."""

import hashlib
import json
from copy import deepcopy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def reduce_event(state, event):
    data, kind = event["data"], event["kind"]
    if kind == "RUN_STARTED":
        if state is not None:
            raise ValueError("Multiple initial states")
        return deepcopy(data["initial_state"])
    if state is None:
        raise ValueError("Missing initial state")
    if kind == "PROPOSAL_APPROVED":
        from .proposal import shared_proposal, proposal_hash
        current = shared_proposal(state)
        if (state.get("domain") != "scenario-discussion" or data.get("actor") != "user"
                or set(data) != {"actor", "revision", "proposal_hash", "proposal", "approved_at"}
                or not isinstance(data.get("approved_at"), str)
                or type(data.get("revision")) is not int or data["revision"] != current["revision"]
                or data.get("proposal_hash") != proposal_hash(current) or data.get("proposal") != current
                or current["status"] == "approved_by_user"):
            raise ValueError("Invalid or stale proposal approval")
        state = deepcopy(state)
        state["approvals"] = state.get("approvals", []) + [deepcopy(data)]
        state["proposal"] = shared_proposal(state)
    elif kind in {"DESIGN_CHANGED", "DISCUSSION_CHANGED", "ACTOR_CHANGED"}:
        if state != data["before"]:
            raise ValueError("Design before-state mismatch")
        if kind == "DISCUSSION_CHANGED" and state.get("approvals", []) != data["after"].get("approvals", []):
            raise ValueError("Discussion updates cannot change user approvals")
        state = deepcopy(data["after"])
    elif kind == "TRANSACTION_CHANGED":
        tx_id = data["transaction_id"]
        if state["transactions"][tx_id] != data["before"]:
            raise ValueError("Transaction before-state mismatch")
        state["transactions"][tx_id] = deepcopy(data["after"])
    elif kind == "EVIDENCE_ACCEPTED":
        ev = data["evidence"]
        if ev["id"] in state["evidence"]:
            raise ValueError("Repeated evidence ID")
        state["evidence"][ev["id"]] = deepcopy(ev)
    elif kind == "TRANSFER_EXECUTED":
        if state["ledger"] != data["before"] or data["transaction_id"] in state["executions"]:
            raise ValueError("Invalid or duplicate ledger transition")
        state["ledger"] = deepcopy(data["after"])
        state["executions"][data["transaction_id"]] = deepcopy(data)
    return state


def replay(events):
    """Validate the chain and rebuild state. Does not call agents or executors."""
    state, previous, last_time = None, "0" * 64, -1
    for index, event in enumerate(events):
        body = {k: v for k, v in event.items() if k != "hash"}
        if event["sequence"] != index or event["previous_hash"] != previous or event["hash"] != digest(body):
            raise ValueError("Event chain mismatch at {}".format(index))
        if event["time"] < last_time:
            raise ValueError("Logical time moved backwards")
        state = reduce_event(state, event)
        previous, last_time = event["hash"], event["time"]
    if state is None:
        raise ValueError("Empty event log")
    return state


class EventLog:
    def __init__(self, on_event=None):
        self.events = []
        self.state = None
        self.on_event = on_event

    def append(self, time, kind, data):
        event = {"sequence": len(self.events), "time": time, "kind": kind,
                 "data": deepcopy(data), "previous_hash": self.events[-1]["hash"] if self.events else "0" * 64}
        event["hash"] = digest(event)
        self.state = reduce_event(self.state, event)
        self.events.append(event)
        if self.on_event is not None:
            self.on_event(deepcopy(event))
        return event
