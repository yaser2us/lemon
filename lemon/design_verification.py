"""Executable checks of a bounded design model, not application implementation tests."""

import json

TRANSITIONS = {
    "REQUESTED": ["WAITING_FOR_AUTH", "AUTHORIZED", "REJECTED"],
    "WAITING_FOR_AUTH": ["AUTHORIZED", "REJECTED"],
    "AUTHORIZED": ["EXECUTING"],
    "EXECUTING": ["COMPLETED", "FAILED"],
    "COMPLETED": [], "FAILED": [], "REJECTED": [],
}
ASSERTION_FIELDS = {"initial_state", "event", "expected_state", "success", "same_transaction"}


def verify_design(state):
    failures = []

    def require(ok, owner, code, detail):
        if not ok:
            failures.append({"owner": owner, "code": code, "detail": detail})

    c = state["contract"]
    require(c["request"].get("amount") == "positive_integer" and c["request"].get("recipient_id") == "nonempty_string",
            "backend-agent", "INPUT_CONTRACT", "Constrain amount and recipient inputs.")
    require(set(c["states"]) == set(TRANSITIONS), "backend-agent", "UI_STATES", "Declare all seven transfer states.")
    require(c["success_state"] == "COMPLETED", "backend-agent", "SUCCESS_AFTER_EXECUTION", "Only COMPLETED means success.")
    require(c["idempotency"] == "same_key_same_transaction" and c["request"].get("idempotency_key") == "nonempty_string",
            "backend-agent", "IDEMPOTENCY", "Retries must retain the same transaction using an idempotency key.")
    require(c.get("transitions") == TRANSITIONS, "backend-agent", "TRANSITIONS", "Declare the bounded transition model: " + str(TRANSITIONS))
    ui = (state["reviews"].get("ui-agent", {}).get("artifact") or {}).get("ui_states", {})
    require(set(ui) == set(c["states"]), "ui-agent", "UI_COVERAGE", "Map every declared state to a screen.")
    require("success" not in ui.get("AUTHORIZED", "").lower() and "success" in ui.get("COMPLETED", "").lower()
            and "failure" in ui.get("FAILED", "").lower(), "ui-agent", "UI_OUTCOMES", "Show pending for AUTHORIZED, success for COMPLETED, failure for FAILED.")
    cases = (state["reviews"].get("test-agent", {}).get("artifact") or {}).get("test_cases", [])
    require({t["requirement"] for t in cases} == set(state["requirements"]), "test-agent", "REQUIREMENT_COVERAGE", "Cover every requirement ID.")
    require(len({t["id"] for t in cases}) == len(cases), "test-agent", "CASE_IDS", "Use distinct case IDs.")
    covered = set()
    for case in cases:
        a = case.get("assertion")
        if (not isinstance(a, dict) or set(a) != ASSERTION_FIELDS or type(a.get("success")) is not bool
                or type(a.get("same_transaction")) is not bool
                or any(not isinstance(a.get(k), str) for k in ("initial_state", "event", "expected_state"))):
            require(False, "test-agent", "ASSERTION_REQUIRED", case["id"] + ": supply initial_state, event, expected_state, success and same_transaction.")
            continue
        initial, event = a["initial_state"], a["event"]
        expected, same, requirements = None, False, set()
        if event == "reject_input" and initial == "NONE":
            expected, requirements = "REJECTED", {"R1"}
        elif event == "submit_valid" and initial == "NONE":
            expected, requirements = "REQUESTED", {"R1"}
        elif event == "render" and initial in TRANSITIONS:
            expected, requirements = initial, {"R2", "R4"}
        elif event == "retry" and initial in TRANSITIONS:
            expected, same, requirements = initial, True, {"R3"}
        elif event in ("execute_success", "execute_failure") and initial == "EXECUTING":
            expected = "COMPLETED" if event == "execute_success" else "FAILED"
            requirements = {"R2", "R4"}
        ok = expected is not None and a["expected_state"] == expected and a["success"] == (expected == "COMPLETED") and a["same_transaction"] == same and case["requirement"] in requirements
        diagnostic = ("Expected " + json.dumps({"expected_state": expected, "success": expected == "COMPLETED", "same_transaction": same,
                                               "allowed_requirements": sorted(requirements)}, sort_keys=True)
                      if expected is not None else "Unsupported event/precondition. render requires an existing declared state; use submit_valid from NONE to create REQUESTED, reject_input from NONE for invalid input, or execute_success/execute_failure from EXECUTING.")
        require(ok, "test-agent", "CASE_OUTCOME", case["id"] + ": " + diagnostic + " Actual: " + json.dumps({**a, "requirement": case["requirement"]}, sort_keys=True))
        if ok:
            covered.add((event, initial))
    required = {("reject_input", "NONE"), ("render", "WAITING_FOR_AUTH"), ("render", "AUTHORIZED"),
                ("render", "EXECUTING"), ("retry", "REQUESTED"), ("execute_failure", "EXECUTING"), ("execute_success", "EXECUTING")}
    require(required <= covered, "test-agent", "BEHAVIOR_COVERAGE", "Include valid assertions for: " + str(sorted(required - covered)))
    return failures
