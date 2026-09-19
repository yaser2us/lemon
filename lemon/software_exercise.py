"""Bounded actor-driven HTTP exercises against the local Lemonade demo API."""
import json
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from .anthropic_reviewer import NoRedirect, ReviewError
from .events import EventLog, replay

SCENARIOS = ("response-lost", "request-lost", "processing", "insufficient-funds", "normal")
OPERATIONS = ("submit", "read", "recover", "evidence", "finish")
SCHEMA = {"type": "object", "properties": {
    "operation": {"type": "string", "enum": list(OPERATIONS)},
    "slot": {"type": "string", "enum": ["primary", "secondary"]},
    "body_json": {"type": "string", "description": "For submit, literal JSON request body. Otherwise empty string."},
    "reason": {"type": "string"}},
    "required": ["operation", "slot", "body_json", "reason"], "additionalProperties": False}
PROMPT = """You are Lemon's API actor exercising REAL local Lemonade software via HTTP.
Enact requests; do not just discuss concerns. Only supplied operations and two fresh identities are
available. You cannot edit code, change the server, or access other endpoints. No real payments exist.
Contract: submit PUT requires an object with exactly one property scenario, a JSON STRING from
response-lost, request-lost, processing, insufficient-funds, normal. Missing, extra, or wrong-type
fields require HTTP 400 with no transfer created. First valid submit is 201; same identity/same
scenario is 200; different valid scenario on existing identity is 409. UUIDs are supplied by runtime.
A timeout observation is unknown, not failure. Response-lost means provider completed without receipt;
request-lost means provider did not receive it. Recovery reuses the same identity; processing stays
pending on the first recovery and completes on the second. Normal completes immediately; insufficient
funds rejects without effect. read returns last observation; evidence is explicit inspector access to
ledger and event history. GET/POST unknown identities return 404, never create a transfer.
Your task: probe recovery and input-boundary behavior, including non-string JSON types for scenario.
Include both empty and populated containers with otherwise valid-looking values; primitive type checks
alone do not establish strict input validation. Prioritize untested input shapes over repeated evidence reads.
Start with populated arrays and populated objects for scenario, before the ordinary recovery cases.
Choose your own exact requests from this contract. Look at actual responses and checks before deciding
the next action. Evidence, not your claim, determines success. Avoid repeating already-covered cases.
Finish after exercising both normal/recovery behavior and invalid-input boundaries, or when budget is
nearly exhausted. The runtime stops at the first contract failure and saves a replayable test case.
Use body_json only for submit, otherwise ''. Return one submit_review tool call matching the schema.
"""


class HttpDemo:
    def __init__(self, base_url, timeout=5):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("Exercise requires a loopback HTTP origin")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def send(self, method, path, body=None):
        data = body.encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("Demo response exceeded 64 KiB")
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError):
                body = {"unparseable_json": True}
            return {"status": response.status, "body": body}


def valid_body(raw):
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    if (type(value) is dict and set(value) == {"scenario"} and type(value["scenario"]) is str
            and value["scenario"] in SCENARIOS):
        return value
    return None


def expected_http(action, bindings):
    known = bindings.get(action["slot"])
    if action["operation"] == "submit":
        body = valid_body(action["body_json"])
        if body is None:
            return 400
        if known is None:
            return 201
        return 200 if known == body["scenario"] else 409
    return 200 if known is not None else 404


class LocalApiActor:
    """Authored smoke route; model mode independently chooses its probes."""
    def decide(self, obs):
        steps = [("submit", "primary", '{"scenario":"response-lost"}'),
                 ("read", "primary", ""), ("recover", "primary", ""),
                 ("recover", "primary", ""), ("evidence", "primary", ""),
                 ("submit", "secondary", '{"scenario":null}'), ("finish", "primary", "")]
        operation, slot, body = steps[min(len(obs["history"]), len(steps) - 1)]
        return {"operation": operation, "slot": slot, "body_json": body, "reason": "Exercise the declared transfer contract."}


class ModelApiActor:
    def __init__(self, client):
        self.client = client

    def decide(self, observation):
        return self.client.submit(observation, system_prompt=PROMPT, schema=SCHEMA,
                                  tool_description="Execute a bounded HTTP action against fictional local demo software; responses are recorded and independently checked.")


def run_exercise(base_url, actor=None, actions=None, on_event=None, max_turns=16, task="Exercise actual recovery and invalid-input behavior"):
    api = HttpDemo(base_url)
    health = api.send("GET", "/api/health")
    if health != {"status": 200, "body": {"status": "ok", "service": "lemonade-api"}}:
        raise ValueError("Endpoint did not identify itself as Lemonade")
    actor = actor or LocalApiActor()
    ids = {slot: str(uuid4()) for slot in ("primary", "secondary")}
    log = EventLog(on_event)
    log.append(0, "RUN_STARTED", {"initial_state": {"domain": "software-exercise", "status": "active", "history": []},
                                 "target": base_url, "identities": ids, "task": task, "mode": "replay" if actions is not None else "actor"})
    bindings, history, failures, error = {}, [], [], None
    action_error = None
    recovery_counts, observed, receipts = {}, {}, {}
    for turn in range(min(max_turns, len(actions) if actions is not None else max_turns)):
        try:
            observation = {"goal": task, "history": deepcopy(history),
                           "identities": ids, "remaining_actions": max_turns - turn, "action_error": action_error}
            if isinstance(actor, ModelApiActor):
                observation["remaining_http_attempts"] = actor.client.max_requests - actor.client.requests
            if actions is None:
                log.append(turn, "SOFTWARE_DECIDING", {})
                response = actor.decide(observation)
                if isinstance(response, tuple):
                    action, usage = response
                    log.append(turn, "MODEL_REVIEW", {"result": "api_actor_decision", **usage})
                else:
                    action = response
            else:
                action = deepcopy(actions[turn])
            if (type(action) is not dict or set(action) != {"operation", "slot", "body_json", "reason"}
                    or not all(type(v) is str for v in action.values()) or action["operation"] not in OPERATIONS
                    or action["slot"] not in ids or len(action["body_json"]) > 2000
                    or not 1 <= len(action["reason"].strip()) <= 2000
                    or (action["operation"] != "submit" and action["body_json"])):
                action_error = "Use exactly operation, slot, body_json, reason as strings. slot must be primary or secondary, even for finish. body_json is literal JSON text for submit; empty string for every other operation."
                log.append(turn, "SOFTWARE_ACTION_REJECTED", {"action": action, "reason": action_error})
                if actions is not None:
                    raise ValueError("Invalid replay action")
                continue
            action_error = None
            if action["operation"] == "finish":
                break
            operation, slot = action["operation"], action["slot"]
            expected = expected_http(action, bindings)
            path = "/api/transfers/" + ids[slot]
            if operation in {"recover", "evidence"}:
                path += "/" + operation
            method = {"submit": "PUT", "read": "GET", "recover": "POST", "evidence": "GET"}[operation]
            response = api.send(method, path, action["body_json"] if operation == "submit" else None)
            checks = {"http_contract": response["status"] == expected}
            body = response["body"]
            if expected in (200, 201) and response["status"] == expected:
                checks["json_object"] = type(body) is dict
            if expected in (200, 201) and response["status"] == expected and type(body) is dict:
                if operation == "evidence":
                    numbers = all(type(body.get(k)) is int for k in ("senderBalance", "recipientBalance", "initialBalance", "effects"))
                    scenario = bindings[slot]
                    wanted_effects = int(scenario != "insufficient-funds" and (scenario in {"normal", "response-lost"} or recovery_counts.get(slot, 0) >= (2 if scenario == "processing" else 1)))
                    initial = 5000 if scenario == "insufficient-funds" else 100000
                    checks.update(integer_ledger=numbers,
                                  money_conserved=numbers and body["senderBalance"] + body["recipientBalance"] == body["initialBalance"],
                                  at_most_one_effect=type(body.get("effects")) is int and body["effects"] in (0, 1),
                                  expected_ledger=body.get("effects") == wanted_effects and body.get("initialBalance") == initial and body.get("senderBalance") == initial - 10000 * wanted_effects and body.get("recipientBalance") == 10000 * wanted_effects,
                                  no_overdraft=numbers and body["senderBalance"] >= 0)
                else:
                    scenario = valid_body(action["body_json"])["scenario"] if expected == 201 else bindings[slot]
                    count = recovery_counts.get(slot, 0) + (operation == "recover")
                    wanted = ("completed" if scenario == "normal" else "rejected" if scenario == "insufficient-funds" else "unknown") if expected == 201 else observed[slot]
                    if operation == "recover":
                        wanted = "rejected" if scenario == "insufficient-funds" else "processing" if scenario == "processing" and count == 1 else "completed"
                    checks["observed_outcome"] = body.get("status") == wanted
                    checks["amount_preserved"] = body.get("amountSen") == 10000
                    checks["identity_preserved"] = body.get("id") == ids[slot]
                    checks["truthful_receipt"] = (isinstance(body.get("receipt"), dict) and body["receipt"].get("transferId") == ids[slot] and body["receipt"].get("amountSen") == 10000 and body["receipt"].get("outcome") == "completed") if body.get("status") == "completed" else body.get("receipt") is None
                    if body.get("status") == "completed" and isinstance(body.get("receipt"), dict):
                        receipt = body["receipt"]
                        checks["stable_receipt"] = isinstance(receipt.get("id"), str) and bool(receipt["id"]) and (slot not in receipts or receipts[slot] == receipt)
                        receipts[slot] = deepcopy(receipt)
                    observed[slot] = wanted
                    recovery_counts[slot] = count
            # Check invalid submission has no side effects, even if HTTP 400 looked right.
            if operation == "submit" and expected == 400 and slot not in bindings:
                probe = api.send("GET", "/api/transfers/" + ids[slot])
                checks["invalid_input_did_not_create_transfer"] = probe["status"] == 404
            else:
                probe = None
            entry = {"action": action, "request": {"method": method, "path": path, "body_json": action["body_json"]},
                     "response": response, "expected_status": expected, "checks": checks, "postcondition_probe": probe}
            history.append(entry)
            log.append(turn, "SOFTWARE_RESULT", deepcopy(entry))
            if not all(checks.values()):
                failures.append(len(history) - 1)
                break
            if operation == "submit" and expected == 201:
                bindings[slot] = valid_body(action["body_json"])["scenario"]
        except (ReviewError, ValueError, OSError) as exc:
            error = exc.code if isinstance(exc, ReviewError) else str(exc) if isinstance(exc, ValueError) else "LOCAL_HTTP_UNAVAILABLE"
            break
        except KeyboardInterrupt:
            error = "INTERRUPTED"
            break
    passed = bool(history) and not failures and not error
    status = "failed" if failures else "stopped" if error else "checked"
    log.append(len(history) + max_turns, "ACTOR_CHANGED", {"before": deepcopy(log.state), "after": {"domain": "software-exercise", "status": status, "history": history}})
    assert replay(log.events) == log.state
    return {"format_version": 1, "domain": "software-exercise", "events": log.events, "final_state": deepcopy(log.state),
            "quality": {"passed": passed, "observed_checks_passed": bool(history) and not failures, "failures": failures}, "error": error,
            "replay_actions": [h["action"] for h in history], "api_requests": actor.client.requests if isinstance(actor, ModelApiActor) else 0,
            "note": "Checks apply only to exercised requests; passing is not complete feature coverage."}


def save_exercise(run, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("exercise-" + uuid4().hex[:8] + ".json")
    path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return path
