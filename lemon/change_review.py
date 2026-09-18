"""Deterministic text comparisons against an immutable user-approved proposal."""

from copy import deepcopy

from .proposal import shared_proposal, proposal_hash


def review_changes(state):
    current = shared_proposal(state)
    approvals = state.get("approvals", [])
    # Retain the useful before/after comparison immediately after re-approval.
    earlier = [a for a in approvals if a["revision"] < current["revision"]]
    baseline = earlier[-1] if earlier else approvals[-1] if approvals else None
    review = {"schema_version": 1, "current_revision": current["revision"], "current_hash": proposal_hash(current),
              "baseline_revision": baseline["revision"] if baseline else None,
              "baseline_hash": baseline["proposal_hash"] if baseline else None,
              "entries": [], "feedback": [], "reviewer_feedback": [], "reported_changes": [],
              "remaining_disagreements": deepcopy(current["disagreements"]),
              "awaiting_response": [p["owner"] for p in current["positions"] if p["awaiting_feedback_response"]],
              "legacy_positions": [p["owner"] for p in current["positions"] if not p["structured"]],
              "legacy_baseline_positions": [p["owner"] for p in baseline["proposal"]["positions"] if not p["structured"]] if baseline else [],
              "note": "Exact text comparison, not a semantic judgment. Rewording counts as a change; removed questions or objections are not proof of resolution."}
    if not baseline:
        return review
    before = baseline["proposal"]

    def compare(section, old, new):
        for key in sorted(set(old) | set(new)):
            a, b = old.get(key), new.get(key)
            status = "added" if a is None else "removed" if b is None else "unchanged" if a["text"] == b["text"] else "changed"
            review["entries"].append({"section": section, "item": key, "status": status,
                                      "before": a["text"] if a else None, "after": b["text"] if b else None,
                                      "before_source": a["source"] if a else None, "after_source": b["source"] if b else None})

    compare("User statements", {x["source"]: x for x in before["user_inputs"]}, {x["source"]: x for x in current["user_inputs"]})
    compare("Reviewer feedback", {x["source"]: x for x in before.get("reviewer_inputs", [])}, {x["source"]: x for x in current.get("reviewer_inputs", [])})
    compare("Role proposals", {p["owner"]: {"text": p["summary"], "source": p["source"]} for p in before["positions"]},
            {p["owner"]: {"text": p["summary"], "source": p["source"]} for p in current["positions"]})

    def assumptions(proposal):
        return {(p["owner"], text): {"text": text, "source": p["source"]} for p in proposal["positions"] for text in p["assumptions"]}

    def questions(proposal):
        return {(q["owner"], q["text"]): {"text": q["text"], "source": q["source"]} for q in proposal["questions"]}

    def disagreements(proposal):
        return {(d["owner"], d["message_id"], d["detail"]): {"text": d["detail"], "source": d["source"]} for d in proposal["disagreements"]}

    for section, extract in (("Assumptions", assumptions), ("Open questions", questions), ("Reported disagreements", disagreements)):
        compare(section, extract(before), extract(current))
    old_inputs = {x["source"] for x in before["user_inputs"]}
    review["feedback"] = [deepcopy(x) for x in current["user_inputs"] if x["source"] not in old_inputs]
    old_review = {x["source"] for x in before.get("reviewer_inputs", [])}
    review["reviewer_feedback"] = [deepcopy(x) for x in current.get("reviewer_inputs", []) if x["source"] not in old_review]
    # Keep each role's latest explanation for each user-feedback batch, not just
    # the last batch. These remain explicitly model-reported rather than inferred.
    feedback_sources = {x["source"] for x in review["feedback"] + review["reviewer_feedback"]}
    feedback_id, latest, kinds = None, {}, {}
    for message in state["messages"]:
        if message["sender"] in {"user", "reviewer"}:
            feedback_id = message["id"]
            kinds[feedback_id] = message["sender"]
        elif feedback_id in feedback_sources:
            latest[(feedback_id, message["sender"])] = message
    for (feedback_id, role), message in latest.items():
        for text in message["payload"].get("proposal", {}).get("changes", []):
            review["reported_changes"].append({"feedback_source": feedback_id, "feedback_kind": kinds[feedback_id], "owner": role, "source": message["id"], "text": text})
    return review


def change_review_lines(review):
    lines = ["# Change review — revision {}".format(review["current_revision"]), "", review["note"], ""]
    if review["baseline_revision"] is None:
        return lines + ["No approved baseline yet. Review the shared proposal before its first approval."]
    lines += ["Compared with approved revision {} (hash `{}`).".format(review["baseline_revision"], review["baseline_hash"]), "",
              "## User feedback since approval", "", "These are the recorded requests; individual causal links below are agent-reported.", ""]
    lines += ["- [{}] {}".format(f["source"], f["text"]) for f in review["feedback"]] or ["No new user feedback."]
    if review["reviewer_feedback"]:
        lines += ["", "## Reviewer feedback since approval — not user decisions", ""]
        lines += ["- [{}] {}".format(f["source"], f["text"]) for f in review["reviewer_feedback"]]
    for status in ("added", "changed", "removed", "unchanged"):
        entries = [e for e in review["entries"] if e["status"] == status]
        lines += ["", "## {} ({})".format(status.title(), len(entries)), ""]
        for entry in entries:
            item = entry["item"] if isinstance(entry["item"], str) else " / ".join(entry["item"][:-1])
            lines.append("- {} / {}".format(entry["section"], item))
            if status in {"changed", "removed"}:
                lines.append("  Before [{}]: {}".format(entry["before_source"], entry["before"]))
            if status in {"changed", "added"}:
                lines.append("  After [{}]: {}".format(entry["after_source"], entry["after"]))
            if status == "unchanged":
                lines.append("  [{} → {}]: {}".format(entry["before_source"], entry["after_source"], entry["after"]))
    lines += ["", "## Agent-reported reasons for changes", ""]
    lines += ["- {} [{}], responding to {} [{}]: {}".format(x["owner"], x["source"], x["feedback_kind"], x["feedback_source"], x["text"]) for x in review["reported_changes"]] or ["No reasons recorded."]
    lines += ["", "## Remaining reported disagreements", ""]
    lines += ["- {} [{}] on [{}]{}: {}".format(d["owner"], d["source"], d["message_id"], " (awaiting feedback response)" if d["awaiting_feedback_response"] else "", d["detail"]) for d in review["remaining_disagreements"]] or ["None explicitly reported; this does not establish agreement."]
    if review["awaiting_response"]:
        lines += ["", "Awaiting response to your latest feedback: " + ", ".join(review["awaiting_response"])]
    if review["legacy_positions"]:
        lines += ["", "Structured summaries unavailable for: " + ", ".join(review["legacy_positions"])]
    if review["legacy_baseline_positions"]:
        lines += ["", "Approved baseline lacks structured summaries for: " + ", ".join(review["legacy_baseline_positions"]),
                  "Newly recorded assumptions or objections may have existed previously but were not separately recorded."]
    return lines
