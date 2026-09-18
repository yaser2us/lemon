"""Independent checks of negotiation results; agreement alone is insufficient."""

from collections import Counter

from .events import replay
from .design_verification import verify_design


def evaluate_design(run):
    state, events, checks = run["final_state"], run["events"], []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})

    try:
        check("Replay reconstructs the design", replay(events) == state)
    except (ValueError, KeyError, TypeError):
        check("Replay reconstructs the design", False)
    expected = {"negotiated": "agreed", "duplicate-delivery": "agreed", "missing-decision": "needs_input", "silent-reviewer": "needs_review", "repair-demo": "agreed"}
    check("Expected negotiation outcome", state["status"] == expected[run["variant"]])
    received = {e["data"]["message"]["id"]: e["data"]["message"] for e in events if e["kind"] == "MESSAGE_RECEIVED"}
    accepted = {e["data"]["message_id"] for e in events if e["kind"] == "MESSAGE_ACCEPTED"}
    rejected = {e["data"]["message_id"] for e in events if e["kind"] == "MESSAGE_REJECTED"}
    drafts = [e for e in events if e["kind"] == "DESIGN_CHANGED" and e["data"]["after"]["revision"] != e["data"]["before"]["revision"]]
    draft_provenance = True
    for e in drafts:
        data = e["data"]
        msg = received.get(data["cause_message_id"], {})
        draft_provenance &= msg.get("sender") == "backend-agent" and msg.get("type") == "PROPOSE_CONTRACT"
        draft_provenance &= msg.get("payload", {}).get("base_revision") == data["before"]["revision"]
        draft_provenance &= msg.get("payload", {}).get("contract") == data["after"]["contract"]
        draft_provenance &= data["after"]["revision"] == data["before"]["revision"] + 1
        draft_provenance &= not data["after"]["reviews"]
    check("Revisions have a valid author, base version and cleared approvals", draft_provenance)
    reviews_valid = True
    for role, review in state["reviews"].items():
        msg = received.get(review["message_id"], {})
        reviews_valid &= (msg.get("sender") == role and msg.get("type") == "ACCEPT"
                          and review["revision"] == state["revision"]
                          and msg.get("payload", {}).get("revision") == state["revision"]
                          and msg.get("payload", {}).get("artifact") == review["artifact"]
                          and review["message_id"] in accepted and review["message_id"] not in rejected)
    check("Reviews and artifacts are attributed to the current revision", reviews_valid)
    check("Communication is bounded", sum(e["kind"] == "MESSAGE_ACCEPTED" for e in events) <= events[0]["data"]["limits"]["messages"])
    if state["status"] == "agreed":
        if "verification" in state:
            check("Independent design model verification passes", not verify_design(state) and state["verification"]["status"] == "passed")
            check("Agreement follows a recorded verification pass", any(e["kind"] == "DESIGN_VERIFIED" and e["data"]["status"] == "passed" and e["data"]["revision"] == state["revision"] for e in events))
        c = state["contract"]
        check("All four roles explicitly approve", set(state["reviews"]) == {"product-agent", "backend-agent", "ui-agent", "test-agent"})
        check("No unresolved challenges or questions", not state["challenges"] and not state["questions"] and state["cancellation"] == "OUT_OF_SCOPE")
        check("Draft actually changed following challenges", state["revision"] > 1 and any(e["kind"] == "MESSAGE_RECEIVED" and e["data"]["message"]["type"] == "CHALLENGE" for e in events))
        check("Required inputs are explicit", c["request"].get("amount") == "positive_integer" and c["request"].get("recipient_id") == "nonempty_string")
        check("Authorization is not completion", c["success_state"] == "COMPLETED" and {"AUTHORIZED", "EXECUTING", "COMPLETED", "FAILED"} <= set(c["states"]))
        check("Retry semantics are explicit", c["request"].get("idempotency_key") == "nonempty_string" and c["idempotency"] == "same_key_same_transaction")
        ui = (state["reviews"].get("ui-agent", {}).get("artifact") or {}).get("ui_states", {})
        check("UI covers each contract state", set(ui) == set(c["states"]) and {"WAITING_FOR_AUTH", "REJECTED"} <= set(ui))
        check("UI distinguishes pending, success and failure", "success" not in ui.get("AUTHORIZED", "").lower() and "success" in ui.get("COMPLETED", "").lower() and "failure" in ui.get("FAILED", "").lower())
        cases = (state["reviews"].get("test-agent", {}).get("artifact") or {}).get("test_cases", [])
        check("Planned test cases cover every requirement", {t["requirement"] for t in cases} == set(state["requirements"]) == {"R1", "R2", "R3", "R4"})
        check("Planned cases have distinct IDs and concrete assertions", len({t["id"] for t in cases}) == len(cases) and all(t["given"] and t["when"] and t["then"] for t in cases))
    else:
        check("Unfinished work has explicit open questions", bool(state["questions"]))
        if run["variant"] == "silent-reviewer":
            check("Silent reviewer is not counted as approval", "test-agent" not in state["reviews"])
        if run["variant"] == "missing-decision":
            check("Product uncertainty remains explicit", state["cancellation"] == "UNDECIDED")
    if run["variant"] == "duplicate-delivery":
        check("Duplicate messages were exercised", any(e["kind"] == "DUPLICATE_IGNORED" for e in events))
    model_reviews = [e["data"] for e in events if e["kind"] == "MODEL_REVIEW"]
    if run.get("reviewer", {}).get("provider") == "anthropic":
        check("Model reviews completed without provider or validation errors", all(m["result"] == "validated" for m in model_reviews))
        if state["status"] == "agreed":
            check("Current Test Agent approval came from a validated model review", any(m.get("decision") == "ACCEPT" and m["revision"] == state["revision"] and m["result"] == "validated" for m in model_reviews))
    metrics = {
        "verification_checks": sum(e["kind"] == "DESIGN_VERIFIED" for e in events),
        "verification_failures": sum(e["kind"] == "DESIGN_VERIFIED" and e["data"]["status"] == "failed" for e in events),
        "repair_rounds": state.get("verification", {}).get("attempt", 0),
        "messages_sent": sum(e["kind"] == "MESSAGE_SENT" for e in events),
        "deliveries": sum(e["kind"] == "MESSAGE_RECEIVED" for e in events),
        "contract_revisions": state["revision"],
        "challenges_delivered": sum(m["type"] == "CHALLENGE" for m in received.values()),
        "rejections_by_reason": dict(Counter(e["data"]["reason"] for e in events if e["kind"] == "MESSAGE_REJECTED")),
        "duplicate_deliveries_ignored": sum(e["kind"] == "DUPLICATE_IGNORED" for e in events),
        "redundant_responses_suppressed": sum(e["kind"] == "REDUNDANT_RESPONSE_SUPPRESSED" for e in events),
        "current_approvals": len(state["reviews"]), "unresolved_questions": len(state["questions"]),
        "logical_time": events[-1]["time"], "runtime_ms": run["runtime_ms"],
        "model_reviews": len(model_reviews), "api_requests": sum(m["attempts"] for m in model_reviews),
        "reported_input_tokens": sum(m.get("input_tokens", 0) + m.get("cache_creation_input_tokens", 0) + m.get("cache_read_input_tokens", 0) for m in model_reviews),
        "reported_output_tokens": sum(m.get("output_tokens", 0) for m in model_reviews),
        "model_reviews_without_usage": sum("input_tokens" not in m for m in model_reviews),
        "model_latency_ms": round(sum(m["latency_ms"] for m in model_reviews), 3),
    }
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "metrics": metrics,
            "note": "These checks validate the design conversation and specification. Planned feature tests have not been executed, and no application code has been generated."}
