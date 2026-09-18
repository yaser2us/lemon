"""Versioned contracts and transport permissions. No external dependencies."""

from copy import deepcopy

VERSION = 1
POLICY_VERSION = "transfer-v1"
LAWS = {
    "IDENTITY": "Valid identity evidence is required.",
    "BALANCE": "Current balance must cover the transfer; debit is atomic.",
    "RISK": "A valid risk assessment is required.",
    "STRONG_AUTH": "High risk requires valid additional authentication.",
    "ONCE": "A transaction may have at most one execution effect.",
    "AUDIT": "Every decision and state change must be recorded.",
}
CAPABILITIES = {
    "app-agent": {"role": "Express intent, request evidence, escalate", "needs": ["identity", "balance", "risk", "auth"]},
    "risk-agent": {"role": "Assess risk from amount and device trust", "produces": ["risk"]},
    "payment-agent": {"role": "Report balance and propose execution", "produces": ["balance"]},
    "identity-provider": {"role": "Simulated identity verification", "produces": ["identity"]},
    "auth-provider": {"role": "Simulated authentication challenge", "produces": ["auth"]},
    "world": {"role": "Enforce policy and route messages"},
    "executor": {"role": "Apply an authorized simulated transfer"},
}
PRODUCERS = {"identity": "identity-provider", "balance": "payment-agent", "risk": "risk-agent", "auth": "auth-provider"}
TERMINAL = {"completed", "rejected", "escalated", "timed_out", "budget_exhausted"}


def integer(value):
    return type(value) is int


def validate_message(message):
    """Return a stable rejection reason, or None. Explanations never authorize."""
    try:
        return _validate_message(message)
    except (TypeError, ValueError):
        return "INVALID_PAYLOAD"


def validate_envelope(message, participants=CAPABILITIES):
    """Shared wire envelope; each domain validates its own payload and permissions."""
    if not isinstance(message, dict):
        return "INVALID_MESSAGE"
    required = {"schema_version", "id", "conversation_id", "sender", "recipient", "subject", "type", "payload", "timestamp"}
    if not required <= message.keys() or set(message) - required - {"reply_to", "deadline", "explanation"}:
        return "INVALID_ENVELOPE"
    if type(message["schema_version"]) is not int or message["schema_version"] != VERSION:
        return "UNSUPPORTED_SCHEMA"
    if any(not isinstance(message[k], str) or not message[k] for k in required - {"schema_version", "payload", "timestamp"}):
        return "INVALID_ENVELOPE"
    if not integer(message["timestamp"]) or message["timestamp"] < 0:
        return "INVALID_TIMESTAMP"
    if "explanation" in message and not isinstance(message["explanation"], str):
        return "INVALID_EXPLANATION"
    if "reply_to" in message and (not isinstance(message["reply_to"], str) or not message["reply_to"]):
        return "INVALID_CORRELATION"
    if message["sender"] not in participants or message["recipient"] not in participants:
        return "UNKNOWN_PARTICIPANT"
    if not isinstance(message["payload"], dict):
        return "INVALID_PAYLOAD"
    return None


def _validate_message(message):
    error = validate_envelope(message)
    if error:
        return error
    payload, kind = message["payload"], message["type"]
    if kind == "PROPOSE":
        if set(payload) != {"action"} or payload["action"] not in {"TRANSFER", "EXECUTE"}:
            return "INVALID_PROPOSAL"
    elif kind == "REQUEST_EVIDENCE":
        if set(payload) != {"need"} or payload["need"] not in PRODUCERS:
            return "INVALID_REQUEST"
        if not integer(message.get("deadline")) or message["deadline"] <= message["timestamp"]:
            return "INVALID_DEADLINE"
    elif kind == "PROVIDE_EVIDENCE":
        if set(payload) != {"evidence"} or not isinstance(payload["evidence"], dict):
            return "INVALID_EVIDENCE"
        if not message.get("reply_to"):
            return "MISSING_CORRELATION"
        error = validate_evidence(payload["evidence"])
        if error:
            return error
    elif kind == "DECISION":
        if set(payload) != {"result", "reason", "missing", "decision_id"}:
            return "INVALID_DECISION"
        if payload["result"] not in {"PENDING", "READY", "ALLOWED", "REJECTED"}:
            return "INVALID_DECISION"
        if not isinstance(payload["missing"], list) or any(n not in PRODUCERS for n in payload["missing"]):
            return "INVALID_DECISION"
        if any(not isinstance(payload[k], str) or not payload[k] for k in ("reason", "decision_id")):
            return "INVALID_DECISION"
    elif kind in {"CHALLENGE", "ESCALATE"}:
        if set(payload) != {"reason"} or not isinstance(payload["reason"], str) or not payload["reason"]:
            return "INVALID_REASON"
    elif kind == "COMPLETE":
        if set(payload) != {"status", "reason"} or payload["status"] not in TERMINAL or not isinstance(payload["reason"], str):
            return "INVALID_COMPLETION"
    else:
        return "UNKNOWN_MESSAGE_TYPE"
    return None


def validate_evidence(ev):
    try:
        return _validate_evidence(ev)
    except (TypeError, ValueError):
        return "INVALID_EVIDENCE_SHAPE"


def _validate_evidence(ev):
    fields = {"schema_version", "id", "type", "producer", "subject", "transaction_id", "value", "source", "issued_at", "expires_at", "state_version"}
    if set(ev) != fields:
        return "INVALID_EVIDENCE_SHAPE"
    if type(ev["schema_version"]) is not int or ev["schema_version"] != VERSION:
        return "UNSUPPORTED_EVIDENCE_SCHEMA"
    if ev["type"] not in PRODUCERS:
        return "UNKNOWN_EVIDENCE_TYPE"
    for key in ("id", "producer", "subject", "transaction_id", "source"):
        if not isinstance(ev[key], str) or not ev[key]:
            return "INVALID_EVIDENCE_SHAPE"
    if any(not integer(ev[k]) or ev[k] < 0 for k in ("issued_at", "expires_at", "state_version")):
        return "INVALID_EVIDENCE_TIME_OR_VERSION"
    if ev["type"] in {"identity", "auth"} and type(ev["value"]) is not bool:
        return "INVALID_EVIDENCE_VALUE"
    if ev["type"] == "balance" and (not integer(ev["value"]) or ev["value"] < 0):
        return "INVALID_EVIDENCE_VALUE"
    if ev["type"] == "risk" and ev["value"] not in {"LOW", "HIGH"}:
        return "INVALID_EVIDENCE_VALUE"
    return None


def permission_error(message):
    sender, recipient, kind, p = (message[k] for k in ("sender", "recipient", "type", "payload"))
    if kind == "PROPOSE":
        allowed = (sender, recipient, p["action"]) in {
            ("app-agent", "world", "TRANSFER"),
            ("payment-agent", "world", "EXECUTE"),
        }
    elif kind == "REQUEST_EVIDENCE":
        allowed = sender == "app-agent" and recipient == PRODUCERS[p["need"]]
    elif kind == "PROVIDE_EVIDENCE":
        ev = p["evidence"]
        allowed = recipient == "world" and sender == ev["producer"] == PRODUCERS[ev["type"]]
    elif kind == "DECISION":
        allowed = sender == "world" and recipient in {"app-agent", "payment-agent", "executor"}
    elif kind == "CHALLENGE":
        allowed = recipient == "app-agent" and sender == "world"
    elif kind == "ESCALATE":
        allowed = sender in {"app-agent", "risk-agent", "payment-agent"} and recipient == "world"
    else:
        allowed = kind == "COMPLETE" and sender == "world" and recipient == "app-agent"
    return None if allowed else "UNAUTHORIZED_MESSAGE"


def definitions():
    return deepcopy({"schema_version": VERSION, "policy_version": POLICY_VERSION, "laws": LAWS, "participants": CAPABILITIES, "evidence_producers": PRODUCERS})
