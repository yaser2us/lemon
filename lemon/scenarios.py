"""Scenario inputs and independent expectations. Only inputs enter the World."""

from copy import deepcopy


def scenario(name, description, *, fault=None, amount=500, balance=10000,
             status="completed", effects=1, reason=None, rejection=None,
             high=False, second=None, **options):
    transactions = [{"id": "TX-1", "amount": amount, "trusted_device": not high}]
    if second is not None:
        transactions.append({"id": "TX-2", "amount": second, "trusted_device": True})
    config = {"name": name, "balance": balance, "transactions": transactions,
              "message_budget": 50, "request_timeout": 20, "max_retries": 2, **options}
    if fault:
        config["fault"] = fault
    expected = {"statuses": [status] if second is None else status,
                "effects": effects, "reason": reason, "rejection": rejection,
                "risk": {t["id"]: "HIGH" if high or t["amount"] > 3000 else "LOW" for t in transactions}}
    return {"description": description, "config": config, "expected": expected}


SCENARIOS = {
    item["config"]["name"]: item for item in [
        scenario("low-risk", "Valid low-risk transfer without additional authentication."),
        scenario("high-risk", "High-risk transfer requires a successful authentication challenge.", amount=5000),
        scenario("missing-identity", "Identity starts unknown and must be requested before authorization."),
        scenario("identity-failed", "Negative identity evidence blocks execution.", identity_valid=False, status="rejected", effects=0, reason="IDENTITY_FAILED"),
        scenario("auth-failed", "Failed additional authentication blocks a high-risk transfer.", high=True, auth_success=False, status="rejected", effects=0, reason="AUTHENTICATION_FAILED"),
        scenario("insufficient-balance", "Balance is below the requested amount.", balance=300, status="rejected", effects=0, reason="INSUFFICIENT_BALANCE"),
        scenario("expired-evidence", "First identity evidence expires; agents request a fresh attestation.", fault="expired", rejection="EVIDENCE_EXPIRED_OR_FUTURE"),
        scenario("wrong-subject", "First identity response describes another user.", fault="wrong_subject", rejection="EVIDENCE_SUBJECT_MISMATCH"),
        scenario("unauthorized-evidence", "App Agent attempts to attest identity without that capability.", fault="unauthorized_evidence", rejection="UNAUTHORIZED_MESSAGE"),
        scenario("conflicting-evidence", "Provider supplies two contradictory current identity claims.", fault="conflict", status="escalated", effects=0, reason="CONFLICTING_EVIDENCE", rejection="CONFLICTING_EVIDENCE"),
        scenario("duplicate-delivery", "Transport redelivers proposals, evidence, and executor authorization with unchanged IDs.", fault="duplicates"),
        scenario("unavailable-provider", "Identity provider stays unavailable through bounded retries.", fault="unavailable", status="timed_out", effects=0, reason="PROVIDER_TIMEOUT"),
        scenario("reordered-evidence", "Identity is delayed while independent evidence arrives first.", fault="reordered"),
        scenario("competing-transfers", "Two transfers compete for a balance sufficient for only one.", amount=700, second=700, balance=1000, status=["completed", "rejected"], effects=1),
        scenario("stale-balance", "Delay the second transaction's balance evidence until the first debits.", fault="stale_balance", amount=700, second=700, balance=1000, status=["completed", "rejected"], effects=1, rejection="STALE_BALANCE_EVIDENCE"),
        scenario("unauthorized-action", "Risk Agent attempts to request execution.", fault="unauthorized", rejection="UNAUTHORIZED_MESSAGE"),
        scenario("no-progress-loop", "Faulty App Agent repeats its intent instead of obtaining evidence.", fault="loop", status="budget_exhausted", effects=0, reason="MESSAGE_BUDGET_EXHAUSTED"),
        scenario("execution-failure", "Simulated executor fails after authorization without a debit.", fault="execution_failure", status="rejected", effects=0, reason="SIMULATED_EXECUTION_FAILURE"),
        scenario("cross-conversation", "Identity response is misrouted into another conversation.", fault="cross_conversation", second=500, status=["completed", "completed"], effects=2, rejection="CROSS_CONVERSATION_OR_UNKNOWN_REPLY"),
        scenario("late-message", "A new proposal arrives after the transaction has completed.", fault="late", rejection="CONVERSATION_TERMINATED"),
        scenario("spoofed-sender", "Transport origin disagrees with the claimed sender.", fault="spoof", rejection="SENDER_SPOOFING"),
        scenario("malformed-message", "A proposal contains an unsupported payload field.", fault="malformed", rejection="INVALID_PROPOSAL"),
    ]
}


def get_scenario(name):
    if name not in SCENARIOS:
        raise ValueError("Unknown scenario: {}".format(name))
    return deepcopy(SCENARIOS[name])
