"""Scrolling terminal chat, driven by recorded events rather than invented dialogue."""

import json
import os
import shutil
import sys
import textwrap
import time
import unicodedata

from .events import replay
from .proposal import shared_proposal, proposal_lines
from .change_review import review_changes, change_review_lines


def safe_text(value):
    # Treat model/file content as text, never as terminal control sequences.
    return "".join(c if c == "\n" or not unicodedata.category(c).startswith("C") else " "
                   for c in str(value))


def load_chat(path):
    run = json.loads(path.read_text(encoding="utf-8"))
    if run.get("format_version") != 1:
        raise ValueError("Unsupported run format")
    if replay(run["events"]) != run["final_state"]:
        raise ValueError("Recorded final state differs from replay")
    return run


class ChatViewer:
    COLORS = {"product-agent": "35", "backend-agent": "36", "ui-agent": "34", "test-agent": "33", "user": "32",
              "app-actor": "36", "customer": "32", "maybank-actor": "33", "duitnow-actor": "35", "cimb-actor": "34"}

    def __init__(self, stream=None, delay=None, details=False, no_color=False):
        self.stream = stream if stream is not None else sys.stdout
        tty = self.stream.isatty()
        self.color = tty and not no_color and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
        self.delay = (0.45 if tty else 0) if delay is None else delay
        self.details = details
        self.width = max(24, min(96, shutil.get_terminal_size((80, 24)).columns - 2))
        self.provider = "deterministic"
        self.live = False
        self.discussion = False

    def write(self, value="", color=None):
        value = safe_text(value)
        if self.color and color:
            value = "\033[{}m{}\033[0m".format(color, value)
        print(value, file=self.stream, flush=True)

    def note(self, value):
        for line in textwrap.wrap(safe_text(value), self.width - 2):
            self.write("  " + line, "90")

    def start(self, live):
        self.live = live
        self.write("\nLEMON / AGENT CHAT", "1;32")
        self.note("{} | Ctrl+C to stop | scroll back to revisit messages".format("LIVE" if live else "VERIFIED REPLAY / no API calls"))
        self.note("Messages appear on delivery. World validates them afterwards.")
        self.write()

    def card(self, message, tick):
        sender = message["sender"]
        name = sender.replace("-", " ").title().replace("Ui Agent", "UI Agent")
        payload = message.get("payload", {})
        revision = payload.get("revision", payload.get("base_revision"))
        title = "{} -> {} | {}".format(name, message["recipient"], message["type"])
        meta = "t={} / {}{}".format(tick, message["id"], " / revision {}".format(revision) if revision is not None else "")
        if payload.get("round"):
            meta += " / round {}".format(payload["round"])
        if message.get("reply_to"):
            meta += " / reply to " + message["reply_to"]
        lines = [title, meta, "", message.get("explanation") or "(No explanation supplied)"]
        if self.details:
            lines += ["", json.dumps(payload, indent=2, ensure_ascii=False)]
        else:
            if "issues" in payload:
                lines += ["Issues: " + ", ".join(payload["issues"])]
            if "contract" in payload:
                contract = payload["contract"]
                lines += ["States: " + ", ".join(contract.get("states", [])),
                          "Success: {} | Retries: {}".format(contract.get("success_state"), contract.get("idempotency"))]
            if "questions" in payload and not self.discussion:
                lines += payload["questions"]
            artifact = payload.get("artifact") or {}
            if "test_cases" in artifact:
                lines += ["{} proposed test cases (not executed)".format(len(artifact["test_cases"]))]
            proposal = payload.get("proposal")
            if proposal:
                lines += ["", "Current proposal: " + proposal["summary"]]
                lines += ["Changed after feedback: " + text for text in proposal["changes"]]
                lines += ["Disagrees with [{}]: {}".format(d["message_id"], d["detail"]) for d in proposal["disagreements"]]
            lines += ["Issue {}: {} (evidence {}) — {}".format(u["issue_id"], u["status"], u["evidence_message_id"], u["reason"]) for u in payload.get("issue_updates", [])]
        color = self.COLORS.get(sender, "37")
        self.write("+" + "-" * (self.width - 2) + "+", color)
        for section in lines:
            for line in safe_text(section).split("\n"):
                for wrapped in textwrap.wrap(line, self.width - 4) or [""]:
                    self.write("| " + wrapped.ljust(self.width - 4) + " |", color)
        self.write("+" + "-" * (self.width - 2) + "+\n", color)
        if self.delay:
            time.sleep(self.delay)

    def event(self, event):
        kind, data = event["kind"], event["data"]
        if kind == "RUN_STARTED":
            if data.get("initial_state", {}).get("domain") == "actor-simulation":
                self.note("Actor World: {} | executable laws and outcome checks".format(data["model"]))
                return
            self.provider = data.get("reviewer", {}).get("provider", "deterministic")
            self.discussion = data.get("reviewer", {}).get("all_roles", False)
            self.note("Reviewer: {} | seed {}".format(self.provider, data.get("seed", "?")))
            if data.get("reviewer", {}).get("all_roles"):
                self.note("All four roles use Anthropic in a shared discussion room. No domain checks are run.")
            elif self.provider == "anthropic":
                self.note("Test Agent uses Anthropic; Product, Backend and UI use local rules.")
        elif kind == "DISCUSSION_RESUMED":
            self.provider, self.discussion = "anthropic", True
            self.note("Continuing the saved discussion with your feedback. Model: {}".format(data["model"]))
        elif kind == "MESSAGE_RECEIVED":
            message = data["message"]
            if message["sender"] != "world" or message["type"] == "VERIFICATION_FEEDBACK":
                self.card(message, event["time"])
            elif message["type"] == "REVIEW" and self.details:
                self.note("World -> {}: review revision {}".format(message["recipient"], message["payload"].get("revision")))
            if self.live and not self.discussion and self.provider == "anthropic" and message["recipient"] == "test-agent":
                self.note("Test Agent review requested; waiting for processing (may call Anthropic)...")
        elif kind == "BRANCH_RESULTS":
            self.write("\nBRANCH EXPERIMENTS / hypothetical outcomes", "1;35")
            for result in data["results"]:
                self.note("{}: {} / {}".format(result["plan"]["name"], "PASS" if result["passed"] else "FAIL", " -> ".join(result["plan"]["steps"])))
                for branch in result["branches"]:
                    failed = [k for k, v in branch["quality"]["checks"].items() if not v]
                    self.note("  {}: effects={}, report={}, rejected={}, failed={}".format(branch["hypothesis"], branch["effects"], branch["app_outcome"], branch["rejections"], failed))
        elif kind == "STRATEGY_VALIDATED":
            self.note("World: strategy tested on {} additional model cases; {}".format(len(data["results"]), "PASS" if all(r["quality"]["passed"] for r in data["results"]) else "FAIL"))
        elif kind == "STRATEGY_REUSED":
            self.note("Reuse retained strategy: {}".format(" -> ".join(data["plan"]["steps"])))
        elif kind in {"ACTOR_REJECTED", "ACTOR_STOPPED", "ACTOR_ACTION_INVALID"}:
            self.note("World: " + data["reason"])
        elif kind == "ACTOR_DECIDING":
            self.note("App observes {} and chooses an action...".format(data["observation"]["app"]["status"]))
        elif kind == "AGENT_THINKING":
            self.note("{} / round {} / waiting for Anthropic...".format(data["agent"], data["round"]))
        elif kind == "DESIGN_VERIFIED":
            self.note("Verification / {} / revision {} / repair round {}".format(data["status"].upper(), data["revision"], data["attempt"]))
            for failure in data["failures"]:
                self.note("{} -> {}: {}".format(failure["code"], failure["owner"], failure["detail"]))
        elif kind == "DESIGN_CHANGED":
            state = data["after"]
            self.note("World / revision {} / {} / approvals {}/4 / {}".format(
                state["revision"], state["status"], len(state["reviews"]), state["reason"]))
            for question in state.get("questions", []):
                self.note("Open question: " + question)
        elif kind in ("MESSAGE_REJECTED", "DUPLICATE_IGNORED", "AGENT_FAILED"):
            self.note("{} / {} / {}".format(kind, data.get("message_id", ""), data.get("reason", data.get("error_code", ""))))
        elif kind == "MODEL_REVIEW":
            self.note("Anthropic / {} / {} ms / {}".format(data.get("result"), data.get("latency_ms", "?"), data.get("decision", data.get("error_code", ""))))
        elif kind in ("TRANSACTION_CHANGED", "TRANSFER_EXECUTED"):
            self.note("{} / {} / {}".format(kind, data.get("transaction_id"), data.get("after", {}).get("status", "executed")))

    def finish(self, run):
        self.write("\nDISCUSSION CHECKPOINT" if run.get("domain") == "scenario-discussion" else "\nCONVERSATION COMPLETE", "1;32")
        state = run["final_state"]
        if run.get("domain") == "actor-simulation":
            self.note("Outcome: {} / checks: {} / simulated transfer effects: {} / API requests: {}".format(
                state["status"], "PASS" if run["quality"]["passed"] else "FAIL", state["effects"], run.get("api_requests", 0)))
            self.note("Retained strategy reused: {}. Model assumptions apply only to this fictional World.".format(run.get("used_memory", False)))
            return
        if run.get("domain") == "scenario-discussion":
            self.note("Outcome: {} / {}".format(state["status"], state["reason"]))
            self.note("Discussion only. No verified agreement, domain checks, or code execution.")
            self.note("API requests: {}".format(run.get("api_requests", "unknown")))
            self.proposal(run)
            if state.get("approvals"):
                self.changes(run)
            return
        passed = run.get("quality", {}).get("passed")
        self.note("Outcome: {} | checks: {}".format(state.get("status", "see transactions"),
                  "unavailable" if passed is None else "PASS" if passed else "FAIL"))
        if run.get("domain") == "software-design":
            self.note("This conversation produces a specification. Application code and feature tests have not been executed.")

    def proposal(self, run):
        self.write("\nSHARED PROPOSAL", "1;36")
        for line in proposal_lines(shared_proposal(run["final_state"])):
            if line.startswith("#"):
                self.write(line.lstrip("# "), "1")
            elif line:
                self.note(line)
            else:
                self.write()
        self.versions(run)

    def versions(self, run):
        proposal = shared_proposal(run["final_state"])
        self.note("Current revision {}: {}".format(proposal["revision"], proposal["status"]))
        approvals = run["final_state"].get("approvals", [])
        for approval in approvals:
            self.note("User approved revision {} at {} (hash {}).".format(approval["revision"], approval["approved_at"], approval["proposal_hash"][:12]))
        if not approvals:
            self.note("No proposal versions approved yet.")
        if proposal["status"] != "approved_by_user":
            self.note("To approve this exact draft: /approve {}".format(proposal["revision"]))

    def changes(self, run):
        self.write("\nCHANGE REVIEW", "1;36")
        for line in change_review_lines(review_changes(run["final_state"])):
            if line.startswith("#"):
                self.write(line.lstrip("# "), "1")
            elif line:
                self.note(line)
            else:
                self.write()
