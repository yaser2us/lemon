"""Actor experiment: constrained observations, counterfactual action trials and reuse.

All banking capabilities here are fictional model rules, not bank integrations.
"""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from .anthropic_reviewer import ReviewError
from .events import EventLog, digest, replay

MODEL = "actor-transfer-v1"
FAULTS = ("response-lost", "request-lost", "processing", "normal", "insufficient-funds")
BRANCHES = ("response-lost", "request-lost", "processing")
STEPS = ("send_original", "send_new", "check_status", "wait", "report")
SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": list(STEPS) + ["simulate", "remember"]},
    "reason": {"type": "string"}, "strategy": {"type": "string", "description": "Only for action remember: the tested plan name. For simulate and all other actions this MUST be an empty string."},
    "plans": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string", "enum": list(STEPS)}}},
        "required": ["name", "steps"], "additionalProperties": False}},
}, "required": ["action", "reason", "strategy", "plans"], "additionalProperties": False}
PROMPT = """You are the Banking App actor in a fictional executable transfer World, not a reviewer.
Your goal: fulfill the customer's confirmed RM100 transfer once and accurately report the outcome.
Choose ACTIONS, not a document. You see only app observations, not bank balances or the hidden fault.
Use send_original for the initial submission. A timeout means UNKNOWN, not failure.
This experiment also requires learning a reusable recovery strategy. On UNKNOWN, before further live
actions, request simulate with 2-4 candidate plans (name and 1-6 steps each). After comparing trials,
use remember for a passing plan rather than manually executing it; failed validation means revise it.
The World will enact those plans in isolated branches compatible with your observation: request absent,
transfer completed but acknowledgement lost, or transfer still processing. Trials are hypothetical,
not evidence of which branch actually occurred. Inspect outcomes and failures to choose or improve a plan.
Allowed steps: send_original submits OR retries using your existing attempt identity. It creates the
transfer if the request never arrived, or returns its recorded status if it already exists; it cannot
create a second effect. It remains available AFTER a timeout. send_new tries a different identity;
check_status queries the original attempt; wait advances simulated time; report tells the Customer only
an authoritative outcome the App has received. In this MODEL banks retain receipts and correlate attempts;
these are declared simulator capabilities, never claims about real banks. The World forbids a second
effect for the same confirmed intent and rejects unsafe attempts independently of your explanation.
A plan stops executing once the customer has a terminal report. Remember only a named plan that passed
every branch, with no law rejection. The World also independently tests it under different delivery delays
and insufficient funds. It will then execute that strategy in the real simulation and make it reusable.
There is no reviewer. Explain actions briefly in public. Never claim to know a hidden outcome or to have
executed a real payment. For non-simulate actions plans must be []; strategy is only for remember, otherwise ''.
If a trial fails, improve the plan instead of repeating the same failed action. Return one submit_review
tool call matching the action schema (the tool name is just the existing transport).
"""


class ActorWorld:
    def __init__(self, fault="response-lost", delay=2, balance=100000, on_event=None, sandbox=False, model=MODEL, limits=None):
        if fault not in FAULTS or type(delay) is not int or not 1 <= delay <= 5 or type(balance) is not int or balance < 0:
            raise ValueError("Invalid actor scenario")
        self.fault, self.delay, self.sandbox = fault, delay, sandbox
        self.tick, self.new_keys = 0, 0
        self.log = EventLog(on_event)
        initial = {"domain": "actor-simulation", "model": model, "intent": "intent-1", "amount_sen": 10000,
                   "ledger": {"maybank": balance, "cimb": 0}, "initial_balance": balance,
                   "attempts": {}, "effects": 0, "pending": None, "rejections": [],
                   "app": {"attempt": "attempt-1", "status": "READY", "customer_report": None}, "status": "active"}
        self.log.append(0, "RUN_STARTED", {"initial_state": initial, "fault": fault, "delay": delay,
                         "model": model, "sandbox": sandbox, "limits": limits or {"decisions": 20, "simulations": 3, "plan_steps": 6}})
        self.say("customer", "app-actor", "CONFIRM_TRANSFER", "Simulate RM100 to another person's CIMB account. Recipient and authorization are preconfirmed fictional fixtures.")

    @property
    def state(self):
        return self.log.state

    def change(self, **updates):
        before = deepcopy(self.state)
        self.log.append(self.tick, "ACTOR_CHANGED", {"before": before, "after": {**before, **deepcopy(updates)}})

    def say(self, sender, recipient, kind, explanation, payload=None):
        self.log.append(self.tick, "MESSAGE_RECEIVED", {"origin": sender, "message": {
            "id": "actor-{}".format(len(self.log.events)), "sender": sender, "recipient": recipient,
            "type": kind, "explanation": explanation, "payload": payload or {}}})

    def reject(self, reason):
        self.change(rejections=self.state["rejections"] + [reason])
        self.log.append(self.tick, "ACTOR_REJECTED", {"reason": reason})

    def app_status(self, status):
        self.change(app={**self.state["app"], "status": status})

    def view(self):
        # Deliberately excludes fault, ledger, bank attempts, pending queue and inspector log.
        return {"model": MODEL, "goal": "Transfer RM100 once; report the observed outcome accurately",
                "app": deepcopy(self.state["app"]), "last_rejection": self.state["rejections"][-1:]}

    def bank(self, key, lose_reply=False):
        attempts = deepcopy(self.state["attempts"])
        if key in attempts:
            status = attempts[key]
            self.say("maybank-actor", "app-actor", "EXISTING_ATTEMPT", "This attempt already exists; return its current outcome without another debit.", {"status": status})
            if not lose_reply:
                self.app_status(status)
            return
        if attempts:
            self.reject("NEW_ATTEMPT_FOR_EXISTING_INTENT")
            self.say("maybank-actor", "app-actor", "REJECT", "A different attempt for this confirmed intent is not allowed.")
            return
        if self.state["ledger"]["maybank"] < self.state["amount_sen"]:
            attempts[key] = "REJECTED"
            self.change(attempts=attempts)
            self.say("maybank-actor", "app-actor", "REJECTED", "Insufficient simulated balance. No debit or credit.")
            if not lose_reply:
                self.app_status("REJECTED")
            return
        attempts[key] = "PROCESSING"
        self.change(attempts=attempts, pending={"key": key, "ready_at": self.tick + self.delay})
        self.say("maybank-actor", "duitnow-actor", "ROUTE", "Accept the authorized fictional intent and request delivery to CIMB.")
        self.say("duitnow-actor", "cimb-actor", "DELIVER", "Route this attempt once. The completion receipt returns through this route.")
        if self.fault != "processing":
            self.complete()
        if not lose_reply:
            self.app_status(self.state["attempts"][key])

    def complete(self):
        pending = self.state["pending"]
        if pending is None:
            return
        if self.state["effects"] != 0:
            self.reject("DUPLICATE_EFFECT")
            return
        amount = self.state["amount_sen"]
        if self.state["ledger"]["maybank"] < amount:
            self.reject("INSUFFICIENT_BALANCE_AT_EXECUTION")
            return
        self.change(ledger={"maybank": self.state["ledger"]["maybank"] - amount, "cimb": self.state["ledger"]["cimb"] + amount},
                    effects=1, pending=None, attempts={**self.state["attempts"], pending["key"]: "COMPLETED"})
        self.say("cimb-actor", "duitnow-actor", "CREDIT_CONFIRMED", "The simulated recipient received RM100; the World recorded one atomic transfer effect.")
        self.say("duitnow-actor", "maybank-actor", "DELIVERY_CONFIRMED", "Return the recorded completion result for this attempt.")

    def act(self, action, reason="Execute retained strategy step."):
        if action not in STEPS:
            raise ValueError("Unknown executable actor action")
        if self.state["status"] != "active":
            return
        self.tick += 1
        if self.state["pending"] and self.tick >= self.state["pending"]["ready_at"]:
            self.complete()
        self.say("app-actor", "world", action.upper(), reason)
        if action.startswith("send_"):
            original = action == "send_original"
            key = self.state["app"]["attempt"] if original else "new-{}".format(self.new_keys)
            self.new_keys += not original
            first = self.state["app"]["status"] == "READY"
            if first and not original:
                self.reject("INITIAL_ATTEMPT_ID_REQUIRED")
                return
            if first and self.fault == "request-lost":
                self.say("network", "app-actor", "TIMEOUT", "No response observed. The App cannot tell whether the request arrived.")
                self.app_status("UNKNOWN")
                return
            lost = first and self.fault in BRANCHES
            self.bank(key, lose_reply=lost)
            if lost:
                self.say("network", "app-actor", "TIMEOUT", "No response observed. The App cannot tell whether the request arrived.")
                self.app_status("UNKNOWN")
        elif action == "check_status":
            status = self.state["attempts"].get(self.state["app"]["attempt"], "NOT_FOUND")
            self.say("maybank-actor", "app-actor", "STATUS_RESULT", "Return the original attempt's recorded state in this model.", {"status": status})
            self.app_status(status)
        elif action == "wait":
            # One bounded wait advances by the declared model maximum, not hidden delay.
            self.tick += 5
            self.complete()
            self.say("clock", "app-actor", "TIME_ELAPSED", "Five logical ticks elapsed. Time alone does not tell the App the outcome.")
        elif action == "report":
            status = self.state["app"]["status"]
            if status not in {"COMPLETED", "REJECTED"}:
                self.reject("NO_AUTHORITATIVE_OUTCOME_TO_REPORT")
                return
            self.change(app={**self.state["app"], "customer_report": status}, status="completed" if status == "COMPLETED" else "rejected")
            self.say("app-actor", "customer", "RESULT", "Observed outcome: {}. This is a simulation result.".format(status))


def evaluate_actor(world):
    state = world.state
    expected = 0 if state["initial_balance"] < state["amount_sen"] else 1
    report = "REJECTED" if expected == 0 else "COMPLETED"
    checks = {"one_intent_at_most_one_effect": state["effects"] in (0, 1),
              "money_conserved": sum(state["ledger"].values()) == state["initial_balance"],
              "no_overdraft": state["ledger"]["maybank"] >= 0,
              "correct_effect": state["effects"] == expected and state["ledger"]["cimb"] == expected * state["amount_sen"],
              "truthful_terminal_report": state["app"]["customer_report"] == report,
              "no_rejected_actions": not state["rejections"],
              "replay": replay(world.log.events) == state}
    return {"passed": all(checks.values()), "checks": checks}


def trial(plan, fault, delay=2, balance=100000):
    world = ActorWorld(fault, delay, balance, sandbox=True)
    world.act("send_original", "Establish the starting observation for this hypothetical branch.")
    for step in plan["steps"]:
        world.act(step)
    return {"hypothesis": fault, "delay": delay, "quality": evaluate_actor(world),
            "effects": world.state["effects"], "rejections": world.state["rejections"],
            "app_outcome": world.state["app"]["customer_report"], "events": world.log.events}


def valid_plan(plan):
    return (isinstance(plan, dict) and set(plan) == {"name", "steps"} and isinstance(plan["name"], str)
            and 1 <= len(plan["name"]) <= 80 and isinstance(plan["steps"], list) and 1 <= len(plan["steps"]) <= 6
            and all(isinstance(step, str) and step in STEPS for step in plan["steps"]))


def trial_summary(result):
    return {k: deepcopy(v) for k, v in result.items() if k != "events"}


def validate_strategy(plan):
    if not valid_plan(plan):
        raise ValueError("Invalid strategy")
    # Independent evaluation scenarios, withheld from actor discovery output.
    cases = [(fault, delay, 100000) for fault in BRANCHES for delay in (1, 4, 5)]
    cases += [("insufficient-funds", 2, 0), ("normal", 3, 10000)]
    results = [trial(plan, *case) for case in cases]
    return results


class LocalActor:
    """Offline demonstration of search over declared candidates, not LLM discovery."""
    def decide(self, observation):
        app = observation["app"]
        action = {"action": "send_original", "reason": "Act on the customer's confirmed intent.", "strategy": "", "plans": []}
        if app["status"] in {"COMPLETED", "REJECTED"}:
            action["action"] = "report"
        elif observation.get("experiments"):
            passing = [e for e in observation["experiments"] if e["passed"]]
            if passing:
                action.update(action="remember", strategy=min(passing, key=lambda e: len(e["plan"]["steps"]))["plan"]["name"], reason="Retain the shortest candidate that succeeded in every hypothetical branch.")
            else:
                action.update(action="wait", reason="No tested candidate succeeded.")
        elif app["status"] != "READY":
            action.update(action="simulate", reason="I cannot observe whether the transfer happened. Enact competing recovery strategies.", plans=[
                {"name": "new-attempt", "steps": ["send_new", "wait", "check_status", "report"]},
                {"name": "query-only", "steps": ["check_status", "report"]},
                {"name": "same-attempt", "steps": ["send_original", "wait", "check_status", "report"]}])
        return action


class ModelActor:
    def __init__(self, client):
        self.client = client

    def decide(self, observation):
        value, usage = self.client.submit(observation, system_prompt=PROMPT, schema=SCHEMA,
                                         tool_description="Choose an App action for the fictional World to validate and execute, or request isolated branch experiments. No real payments.")
        return value, usage


def run_actor(fault="response-lost", actor=None, memory=None, on_event=None, delay=2, balance=100000):
    if fault == "insufficient-funds":
        balance = 0
    world = ActorWorld(fault, delay, balance, on_event)
    actor = actor or LocalActor()
    experiments, trials, learned, used_memory = [], [], None, False
    stored = None
    action_error = None
    if memory is not None:
        if not isinstance(memory, dict) or memory.get("model") != MODEL or not valid_plan(memory.get("plan")):
            raise ValueError("Strategy memory does not match this World model")
        if not all(r["quality"]["passed"] for r in validate_strategy(memory["plan"])):
            raise ValueError("Stored strategy failed independent revalidation")
        stored = memory["plan"]
    for turn in range(20):
        if world.state["status"] != "active":
            break
        if stored and world.state["app"]["status"] == "UNKNOWN":
            world.log.append(world.tick, "STRATEGY_REUSED", {"plan": stored, "model": MODEL})
            for step in stored["steps"]:
                world.act(step)
            used_memory = True
            stored = None
            continue
        observation = {**world.view(), "experiments": deepcopy(experiments), "remaining_actions": 20 - turn}
        if world.state["app"]["status"] == "UNKNOWN":
            passing_names = [e["plan"]["name"] for e in experiments if e["passed"]]
            observation["learning_next_step"] = (
                {"action": "remember", "eligible_names": passing_names} if passing_names else
                {"action": "simulate", "instruction": "No eligible strategy yet. Propose revised candidate plans using available steps; do not remember a failed plan."})
        if action_error:
            observation["action_error"] = action_error
        world.log.append(world.tick, "ACTOR_DECIDING", {"observation": observation})
        try:
            response = actor.decide(observation)
            if isinstance(response, tuple):
                action, usage = response
                world.log.append(world.tick, "MODEL_REVIEW", {"result": "validated_transport", "decision": action.get("action") if isinstance(action, dict) else None, **usage})
            else:
                action = response
            if (not isinstance(action, dict) or set(action) != {"action", "reason", "strategy", "plans"}
                    or not isinstance(action["action"], str) or action["action"] not in STEPS + ("simulate", "remember")
                    or not isinstance(action["reason"], str) or not 1 <= len(action["reason"].strip()) <= 2000
                    or not isinstance(action["strategy"], str) or not isinstance(action["plans"], list)):
                raise ValueError("Invalid actor action")
            kind = action["action"]
            if (kind != "remember" and action["strategy"]) or (kind != "simulate" and action["plans"]):
                raise ValueError("Mixed actor actions")
            if kind == "simulate":
                if world.state["app"]["status"] != "UNKNOWN" or len(trials) >= 3 or not 2 <= len(action["plans"]) <= 4 or not all(valid_plan(p) for p in action["plans"]):
                    raise ValueError("Simulation requires uncertainty and 2-4 bounded plans; maximum three experiments")
                if len({p["name"] for p in action["plans"]}) != len(action["plans"]):
                    raise ValueError("Plan names must be distinct")
                before = digest(world.state)
                world.say("app-actor", "world", "SIMULATE", action["reason"], {"plans": action["plans"]})
                experiments = []
                batch = []
                for plan in action["plans"]:
                    results = [trial(plan, hypothesis) for hypothesis in BRANCHES]
                    batch.append({"plan": deepcopy(plan), "branches": results})
                    experiments.append({"plan": deepcopy(plan), "passed": all(r["quality"]["passed"] for r in results), "branches": [trial_summary(r) for r in results]})
                trials.append(batch)
                if digest(world.state) != before:
                    raise ValueError("Branch simulation changed the live World")
                world.log.append(world.tick, "BRANCH_RESULTS", {"results": experiments, "note": "Hypotheses only, not knowledge of the live outcome."})
            elif kind == "remember":
                chosen = next((e for e in experiments if e["plan"]["name"] == action["strategy"] and e["passed"]), None)
                if chosen is None:
                    raise ValueError("Only a successful tested strategy may be retained")
                held_out = validate_strategy(chosen["plan"])
                world.log.append(world.tick, "STRATEGY_VALIDATED", {"plan": chosen["plan"], "results": [trial_summary(r) for r in held_out]})
                if not all(r["quality"]["passed"] for r in held_out):
                    chosen["passed"] = False
                    chosen["validation_failures"] = [trial_summary(r) for r in held_out if not r["quality"]["passed"]]
                    continue
                learned = {"model": MODEL, "plan": deepcopy(chosen["plan"]), "validation_cases": len(held_out)}
                world.say("app-actor", "world", "RETAIN_STRATEGY", action["reason"], {"plan": chosen["plan"]})
                for step in chosen["plan"]["steps"]:
                    world.act(step)
            else:
                world.act(kind, action["reason"])
            action_error = None
        except ValueError as exc:
            action_error = str(exc)
            world.log.append(world.tick, "ACTOR_ACTION_INVALID", {"reason": action_error})
            continue
        except ReviewError as exc:
            world.log.append(world.tick, "ACTOR_STOPPED", {"reason": exc.code})
            world.change(status="needs_input")
            break
        except KeyboardInterrupt:
            world.change(status="paused")
            break
    if world.state["status"] == "active":
        world.change(status="budget_exhausted")
    quality = evaluate_actor(world)
    return {"format_version": 1, "domain": "actor-simulation", "scenario": fault, "events": world.log.events,
            "final_state": deepcopy(world.state), "quality": quality, "branch_traces": trials,
            "learned_strategy": learned if quality["passed"] else None, "used_memory": used_memory,
            "model_calls": sum(e["kind"] == "MODEL_REVIEW" for e in world.log.events),
            "api_requests": actor.client.requests if isinstance(actor, ModelActor) else 0}


def save_actor(run, directory, memory_path=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("actor-{}-{}.json".format(run["scenario"], uuid4().hex[:8]))
    path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    if memory_path is not None and run["learned_strategy"]:
        target = Path(memory_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = target.with_name(target.name + "." + uuid4().hex + ".tmp")
        pending.write_text(json.dumps({**run["learned_strategy"], "source_run": str(path)}, indent=2) + "\n", encoding="utf-8")
        pending.replace(target)
    return path
