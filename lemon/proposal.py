"""Source-linked shared proposal, projected from the actual discussion messages."""

from copy import deepcopy
from .events import digest
from .coordination import group_questions, issue_ledger


def proposal_hash(proposal):
    return digest({**proposal, "status": "draft_for_user_review"})

PROPOSAL_SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "string"},
    "assumptions": {"type": "array", "items": {"type": "string"}},
    "disagreements": {"type": "array", "items": {"type": "object", "properties": {
        "message_id": {"type": "string"}, "detail": {"type": "string"}},
        "required": ["message_id", "detail"], "additionalProperties": False}},
    "changes": {"type": "array", "items": {"type": "string"}},
}, "required": ["summary", "assumptions", "disagreements", "changes"], "additionalProperties": False}


def valid_proposal(value, transcript):
    if not isinstance(value, dict) or set(value) != set(PROPOSAL_SCHEMA["required"]):
        return False
    if not isinstance(value["summary"], str) or not 1 <= len(value["summary"].strip()) <= 1600:
        return False
    for name in ("assumptions", "changes"):
        if (not isinstance(value[name], list) or len(value[name]) > 6
                or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 1000 for v in value[name])):
            return False
    disagreements = value["disagreements"]
    if not isinstance(disagreements, list) or len(disagreements) > 6:
        return False
    ids = {m["id"] for m in transcript}
    return all(isinstance(d, dict) and set(d) == {"message_id", "detail"}
               and isinstance(d["message_id"], str) and d["message_id"] in ids
               and isinstance(d["detail"], str) and 1 <= len(d["detail"].strip()) <= 1000 for d in disagreements)


def shared_proposal(state):
    inputs = [{"source": "scenario", "text": state["scenario"]}]
    latest, feedback_index, feedback_id, feedback_kind = {}, -1, None, None
    reviewer_inputs = []
    for index, message in enumerate(state["messages"]):
        if message["sender"] == "user":
            inputs.append({"source": message["id"], "text": message["explanation"]})
            feedback_index, feedback_id, feedback_kind = index, message["id"], "user"
        elif message["sender"] == "reviewer":
            reviewer_inputs.append({"source": message["id"], "text": message["explanation"]})
            feedback_index, feedback_id, feedback_kind = index, message["id"], "reviewer"
        else:
            latest[message["sender"]] = (index, message)
    positions, questions, disagreements, changes = [], [], [], []
    for role, (index, message) in latest.items():
        structured = message["payload"].get("proposal")
        position = {"owner": role, "source": message["id"], "summary": structured["summary"] if structured else message["explanation"],
                    "assumptions": deepcopy(structured["assumptions"]) if structured else [],
                    "structured": structured is not None, "awaiting_feedback_response": index < feedback_index}
        positions.append(position)
        for question in message["payload"].get("questions", []):
            questions.append({"owner": role, "source": message["id"], "text": question,
                              "awaiting_feedback_response": index < feedback_index})
        if structured:
            disagreements.extend({"owner": role, "source": message["id"], **deepcopy(d),
                                  "awaiting_feedback_response": index < feedback_index} for d in structured["disagreements"])
            if feedback_id and index > feedback_index:
                changes.extend({"owner": role, "source": message["id"], "feedback_source": feedback_id, "text": text}
                               for text in structured["changes"])
    proposal = {"schema_version": 1, "revision": len(state["messages"]), "status": "draft_for_user_review",
            "user_inputs": inputs, "positions": positions, "questions": questions,
            "disagreements": disagreements, "changes_since_feedback": changes,
            "latest_feedback_source": feedback_id,
            "note": "User statements are verbatim. Agent summaries, assumptions, disagreements and reported changes are proposals, not user approval or verified agreement."}
    if state.get("coordination_version"):
        issues = issue_ledger(state["messages"])
        proposal.update(schema_version=2, reviewer_inputs=reviewer_inputs, coordinated_questions=group_questions(questions),
                        issues=issues, latest_feedback_kind=feedback_kind)
        awaiting = {p["owner"]: p["awaiting_feedback_response"] for p in positions}
        proposal["disagreements"] = [{**deepcopy(i), "awaiting_feedback_response": awaiting.get(i["owner"], False)} for i in issues if i["status"] == "open"]
    if any(a["proposal_hash"] == proposal_hash(proposal) for a in state.get("approvals", [])):
        proposal["status"] = "approved_by_user"
    return proposal


def proposal_lines(proposal):
    lines = ["# Shared proposal — revision {}".format(proposal["revision"]), "", "Status: **{}**".format(proposal["status"]),
             "User approval records acceptance of this exact proposal; it does not verify correctness or authorize code execution.", "", proposal["note"], "",
             "## Your stated requirements and feedback", "", "In order received; later corrections take precedence. Questions in your messages are not automatically decisions.", ""]
    for item in proposal["user_inputs"]:
        lines += ["[{}] {}".format(item["source"], item["text"]), ""]
    if proposal.get("reviewer_inputs"):
        lines += ["## Reviewer feedback — not user decisions", ""]
        for item in proposal["reviewer_inputs"]:
            lines += ["[{}] {}".format(item["source"], item["text"]), ""]
    lines += ["## Current proposal by role", ""]
    for position in proposal["positions"]:
        lines += ["### {} [{}]{}".format(position["owner"], position["source"], " — awaiting response to your latest feedback" if position["awaiting_feedback_response"] else ""),
                  "", position["summary"], ""]
        if not position["structured"]:
            lines += ["Legacy message: shown verbatim; assumptions and disagreements were not separately recorded.", ""]
        lines += ["Assumption: " + text for text in position["assumptions"]]
        lines.append("")
    lines += ["## Changes after latest feedback{}".format(" (reviewer)" if proposal.get("latest_feedback_kind") == "reviewer" else " (user)"), ""]
    for item in proposal["changes_since_feedback"]:
        lines.append("- {} [{}], responding to [{}]: {}".format(item["owner"], item["source"], item["feedback_source"], item["text"]))
    if not proposal["changes_since_feedback"]:
        lines.append("No changes reported after user feedback yet.")
    lines += ["", "## Open questions", ""]
    if "coordinated_questions" in proposal:
        for item in proposal["coordinated_questions"]:
            lines.append("- {} [{}; {}]{}".format(item["text"], ", ".join(item["owners"]), ", ".join(item["sources"]), " (awaiting feedback response)" if item["awaiting_feedback_response"] else ""))
    else:
        for item in proposal["questions"]:
            lines.append("- {} [{}]{}: {}".format(item["owner"], item["source"], " (awaiting feedback response)" if item["awaiting_feedback_response"] else "", item["text"]))
    if not proposal["questions"]:
        lines.append("No questions reported; this does not establish agreement.")
    lines += ["", "## Reported disagreements", ""]
    for item in proposal["disagreements"]:
        lines.append("- {} [{}] on [{}]{}: {}".format(item["owner"], item["source"], item["message_id"], " (awaiting feedback response)" if item["awaiting_feedback_response"] else "", item["detail"]))
    if not proposal["disagreements"]:
        lines.append("No disagreements explicitly recorded; unreported conflicts may remain.")
    if "issues" in proposal:
        lines += ["", "## Issue status history", "", "Resolution is an agent's explicit assessment, not verified correctness. Omission does not resolve an issue.", ""]
        for issue in proposal["issues"]:
            lines.append("- {} / {} / {}: {}".format(issue["issue_id"], issue["owner"], issue["status"], issue["detail"]))
            for update in issue["history"]:
                lines.append("  {} [{}], evidence [{}]: {}".format(update["status"], update["source"], update["evidence_message_id"], update["reason"]))
    return lines
