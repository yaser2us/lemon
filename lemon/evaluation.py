"""Independent outcome and invariant checks; never used by the agents."""

from collections import Counter

from .events import replay


def evaluate(run, expected):
    events, final = run["events"], run["final_state"]
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        check("Replay reconstructs final state", replay(events) == final)
    except (ValueError, KeyError, TypeError) as exc:
        check("Replay reconstructs final state", False, str(exc))
    initial = events[0]["data"]["initial_state"]
    limits = events[0]["data"]["limits"]
    txs = final["transactions"]
    check("Expected conversation outcomes", sorted(t["conversation"] for t in txs.values()) == sorted(expected["statuses"]))
    executions = [e for e in events if e["kind"] == "TRANSFER_EXECUTED"]
    check("Expected transfer count", len(executions) == expected["effects"])
    check("At most one debit per transaction", len({e["data"]["transaction_id"] for e in executions}) == len(executions))
    check("Ledger conserves funds", initial["ledger"]["balance"] - sum(e["data"]["amount"] for e in executions) == final["ledger"]["balance"])
    check("No overdraft", final["ledger"]["balance"] >= 0 and all(e["data"]["after"]["balance"] >= 0 for e in executions))
    check("All conversations terminate", all(t["conversation"] in {"completed", "rejected", "escalated", "timed_out", "budget_exhausted"} for t in txs.values()))
    if expected.get("reason"):
        check("Expected terminal reason", all(t["reason"] == expected["reason"] for t in txs.values()))
    rejections = [e["data"]["reason"] for e in events if e["kind"] == "MESSAGE_REJECTED"]
    if expected.get("rejection"):
        check("Expected fault detected", expected["rejection"] in rejections, expected["rejection"])
    messages = {e["data"]["message"]["id"]: e["data"]["message"] for e in events if e["kind"] == "MESSAGE_RECEIVED"}
    decisions = {e["data"]["id"]: e for e in events if e["kind"] == "POLICY_DECISION"}
    evidence = {}
    safe_authorizations, attributed, traceable = True, True, True
    producer_for = {"identity": "identity-provider", "auth": "auth-provider", "risk": "risk-agent", "balance": "payment-agent"}
    for event in events:
        data = event["data"]
        if event["kind"] == "EVIDENCE_ACCEPTED":
            ev = data["evidence"]
            evidence[ev["id"]] = ev
            tx = txs[data["transaction_id"]]
            attributed &= ev["producer"] == producer_for.get(ev["type"]) and ev["source"] == "simulated:" + ev["producer"]
            attributed &= ev["subject"] == tx["user"] and ev["transaction_id"] == tx["id"]
            attributed &= ev["issued_at"] <= event["time"] < ev["expires_at"]
        if event["kind"] == "POLICY_DECISION":
            tx = data["transaction"]
            traceable &= data["trigger_message_id"] in messages and data["policy_version"] == "transfer-v1"
            traceable &= all(ev_id in evidence for ev_id in data["evidence_ids"])
            if data["result"] == "ALLOWED":
                facts = {evidence[ev_id]["type"]: evidence[ev_id] for ev_id in data["evidence_ids"] if ev_id in evidence}
                needed = ["identity", "balance", "risk"] + (["auth"] if expected["risk"][tx["id"]] == "HIGH" else [])
                valid = all(n in facts for n in needed)
                valid &= all(facts[n]["issued_at"] <= event["time"] < facts[n]["expires_at"] for n in needed if n in facts)
                valid &= facts.get("identity", {}).get("value") is True
                valid &= facts.get("risk", {}).get("value") == expected["risk"][tx["id"]]
                valid &= facts.get("balance", {}).get("value", -1) >= tx["amount"]
                valid &= facts.get("balance", {}).get("state_version") == data["ledger"]["version"]
                if "auth" in needed:
                    valid &= facts.get("auth", {}).get("value") is True
                valid &= not tx["conflicts"]
                safe_authorizations &= valid
    check("Accepted evidence is attributed, scoped and fresh", attributed)
    check("Authorizations satisfy independent policy assertions", safe_authorizations)
    check("Decisions link to triggers, evidence and policy", traceable)
    executed_safely = True
    for event in executions:
        data = event["data"]
        dec = decisions.get(data["decision_id"])
        executed_safely &= dec is not None and dec["sequence"] < event["sequence"]
        if dec:
            executed_safely &= dec["data"]["result"] == "ALLOWED" and dec["data"]["reason"] == "EXECUTION_RECHECK_PASSED"
            executed_safely &= dec["data"]["transaction_id"] == data["transaction_id"]
            executed_safely &= dec["data"]["ledger"] == data["before"]
        executed_safely &= data["after"]["balance"] == data["before"]["balance"] - data["amount"]
        executed_safely &= data["after"]["version"] == data["before"]["version"] + 1
    check("Execution follows a current atomic authorization check", executed_safely)
    check("Completion corresponds to a transfer effect", all((t["status"] == "completed") == (tx_id in final["executions"]) for tx_id, t in txs.items()))
    sent = [e["data"]["message"] for e in events if e["kind"] == "MESSAGE_SENT"]
    requested = [m for m in sent if m["type"] == "REQUEST_EVIDENCE"]
    request_counts = Counter((m["conversation_id"], m["payload"]["need"]) for m in requested)
    check("Requests stay within retry limit", all(count <= limits["retries"] + 1 for count in request_counts.values()))
    check("Low-risk paths avoid unnecessary authentication", all(m["payload"]["need"] != "auth" or expected["risk"][m["conversation_id"]] == "HIGH" for m in requested))
    if run["scenario"] == "duplicate-delivery":
        check("Duplicate delivery was exercised", any(e["kind"] == "DUPLICATE_IGNORED" for e in events))
        executor_deliveries = [e["data"]["message"]["id"] for e in events if e["kind"] == "MESSAGE_RECEIVED" and e["data"]["message"]["recipient"] == "executor"]
        check("Executor authorization was redelivered", len(executor_deliveries) > len(set(executor_deliveries)))
    if run["scenario"] == "unavailable-provider":
        check("All bounded identity attempts exercised", request_counts[("TX-1", "identity")] == limits["retries"] + 1)
    if run["scenario"] == "missing-identity":
        check("Missing identity was requested", request_counts[("TX-1", "identity")] >= 1)
    if run["scenario"] == "execution-failure":
        check("Execution failure is visible", all(t["status"] == "failed" for t in txs.values()))
    metrics = {
        "messages_sent": len(sent), "deliveries": sum(e["kind"] == "MESSAGE_RECEIVED" for e in events),
        "messages_per_conversation": dict(Counter(m["conversation_id"] for m in sent)),
        "rejections_by_reason": dict(Counter(rejections)),
        "duplicates_ignored": sum(e["kind"] == "DUPLICATE_IGNORED" for e in events),
        "redundant_requests_suppressed": sum(e["kind"] == "REQUEST_SUPPRESSED" for e in events),
        "retries": sum(e["kind"] == "REQUEST_RETRIED" for e in events),
        "agent_invocations": dict(Counter(e["data"]["agent"] for e in events if e["kind"] == "AGENT_OBSERVED")),
        "logical_time": events[-1]["time"], "runtime_ms": run["runtime_ms"],
        "conversation_latency_ticks": {e["data"]["transaction_id"]: e["time"] for e in events
                                       if e["kind"] == "TRANSACTION_CHANGED" and e["data"]["after"]["conversation"] in {"completed", "rejected", "escalated", "timed_out", "budget_exhausted"}},
        "completed_tasks": sum(t["conversation"] == "completed" for t in txs.values()),
        "incomplete_tasks": sum(t["conversation"] in {"timed_out", "escalated", "budget_exhausted"} for t in txs.values()),
        "authorizations_checked": sum(e["data"]["result"] == "ALLOWED" for e in decisions.values()),
    }
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "metrics": metrics,
            "note": "A scenario passes when its expected behavior occurs. A timeout or blocked transfer can be an expected result; it is not task success."}
