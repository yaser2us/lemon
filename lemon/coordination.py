"""Deterministic question grouping and source-linked issue lifecycle."""

import re
from copy import deepcopy

ISSUE_UPDATE_SCHEMA = {"type": "array", "items": {"type": "object", "properties": {
    "issue_id": {"type": "string"}, "status": {"type": "string", "enum": ["open", "resolved"]},
    "reason": {"type": "string"}, "evidence_message_id": {"type": "string"}},
    "required": ["issue_id", "status", "reason", "evidence_message_id"], "additionalProperties": False}}


def question_key(text):
    return re.sub(r"\s+", " ", text.strip().casefold()).rstrip(" ?.!;")


def group_questions(questions):
    groups = {}
    for q in questions:
        key = question_key(q["text"])
        if key not in groups:
            groups[key] = {"text": q["text"], "owners": [], "sources": [], "awaiting_feedback_response": False}
        group = groups[key]
        if q["owner"] not in group["owners"]:
            group["owners"].append(q["owner"])
        if q["source"] not in group["sources"]:
            group["sources"].append(q["source"])
        group["awaiting_feedback_response"] |= q.get("awaiting_feedback_response", False)
    return list(groups.values())


def issue_ledger(messages):
    issues, keys = {}, {}
    for message in messages:
        role = message["sender"]
        for index, d in enumerate(message["payload"].get("proposal", {}).get("disagreements", []), 1):
            key = (role, d["message_id"], question_key(d["detail"]))
            if key not in keys:
                issue_id = "{}-issue-{}".format(message["id"], index)
                keys[key] = issue_id
                issues[issue_id] = {"issue_id": issue_id, "owner": role, "source": message["id"],
                                    "message_id": d["message_id"], "detail": d["detail"], "status": "open", "history": []}
            elif issues[keys[key]]["status"] == "resolved":
                issue = issues[keys[key]]
                issue["status"] = "open"
                issue["history"].append({"issue_id": issue["issue_id"], "status": "open", "source": message["id"],
                                         "evidence_message_id": message["id"], "reason": "Owner explicitly raised the same objection again."})
        for update in message["payload"].get("issue_updates", []):
            issue = issues[update["issue_id"]]
            issue["status"] = update["status"]
            issue["history"].append({**deepcopy(update), "source": message["id"]})
    return list(issues.values())


def valid_issue_updates(updates, transcript, actor):
    if not isinstance(updates, list) or len(updates) > 6:
        return False
    issues = {i["issue_id"]: i for i in issue_ledger(transcript)}
    positions = {m["id"]: index for index, m in enumerate(transcript)}
    seen = set()
    for update in updates:
        if not isinstance(update, dict) or set(update) != {"issue_id", "status", "reason", "evidence_message_id"}:
            return False
        if any(not isinstance(v, str) for v in update.values()):
            return False
        issue = issues.get(update["issue_id"])
        if (not issue or issue["owner"] != actor or update["issue_id"] in seen or update["status"] not in {"open", "resolved"}
                or not 1 <= len(update["reason"].strip()) <= 1000
                or update["evidence_message_id"] not in positions
                or positions[update["evidence_message_id"]] <= positions[issue["source"]]):
            return False
        seen.add(update["issue_id"])
    return True
