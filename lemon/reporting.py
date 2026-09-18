"""Readable conversations and quality reports, linked to raw evidence."""

import json
from pathlib import Path


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def message_summary(msg):
    p, kind = msg["payload"], msg["type"]
    if kind == "PROVIDE_EVIDENCE" and isinstance(p.get("evidence"), dict):
        e = p["evidence"]
        return "{}: **{} = {}**; subject {}; expires t={}; state v{}; source {}".format(e["id"], e["type"], e["value"], e["subject"], e["expires_at"], e["state_version"], e["source"])
    if kind == "REQUEST_EVIDENCE":
        return "Request **{}**; deadline t={}".format(p["need"], msg.get("deadline"))
    if kind == "DECISION":
        return "{}: **{}** — {}; missing: {}".format(p["decision_id"], p["result"], p["reason"], ", ".join(p["missing"]) or "none")
    if kind == "PROPOSE":
        return "Propose **{}**. {}".format(p.get("action"), msg.get("explanation", ""))
    return "{} {}".format(kind, json.dumps(p, sort_keys=True))


def render_report(run):
    quality = run["quality"]
    metrics = quality["metrics"]
    outcomes = ", ".join("{}: {} ({})".format(k, t["conversation"], t["reason"]) for k, t in run["final_state"]["transactions"].items())
    lines = ["# {} — conversation review".format(run["scenario"]), "",
             "Seed: **{}** · Scenario checks: **{}**".format(run["seed"], "PASS" if quality["passed"] else "FAIL"), "",
             run.get("description", ""), "", "**Outcome:** {}".format(outcomes), "",
             "Deterministic simulation; no LLMs, real accounts, or real transfers. Amounts are integer simulated currency units.", "",
             quality["note"], "", "[Raw run, evidence and event log]({}.json)".format(run["scenario"] + "-seed-" + str(run["seed"])), "",
             "## Quality measurements", "", "| Measurement | Value |", "|---|---|"]
    for key, value in metrics.items():
        lines.append("| {} | {} |".format(key.replace("_", " "), cell(json.dumps(value, sort_keys=True) if isinstance(value, dict) else value)))
    lines += ["", "Logical time is a simulated clock, not milliseconds. Actual runtime is measured separately and varies by machine.", "",
              "## Agent conversation", "", "Delivery order is shown below. ACCEPTED means routing accepted; evidence and authorization are checked separately. Duplicate and rejected deliveries remain visible.", "",
              "| Time | Message / task | From → to | Communication | Disposition |", "|---|---|---|---|---|"]
    # Associate each delivery with its own subsequent disposition (including redelivery).
    deliveries = []
    active = {}
    for event in run["events"]:
        data = event["data"]
        if event["kind"] == "MESSAGE_RECEIVED":
            row = {"time": event["time"], "message": data["message"], "disposition": []}
            deliveries.append(row)
            active[data["message"]["id"]] = row
        elif event["kind"] in {"MESSAGE_ACCEPTED", "MESSAGE_REJECTED", "DUPLICATE_IGNORED", "EVIDENCE_ACCEPTED"}:
            row = active.get(data.get("message_id"))
            if row is not None:
                row["disposition"].append(data.get("reason", event["kind"]))
    for row in deliveries:
        m = row["message"]
        lines.append("| {} | {} / {} | {} → {} | {} | {} |".format(row["time"], cell(m["id"]), cell(m["conversation_id"]), cell(m["sender"]), cell(m["recipient"]), cell(message_summary(m)), cell(", ".join(row["disposition"]))))
    lines += ["", "## Decisions and state changes", "", "| Time | Task | Event | Detail |", "|---|---|---|---|"]
    for event in run["events"]:
        data, kind = event["data"], event["kind"]
        detail = None
        if kind == "POLICY_DECISION":
            detail = "{}: {} / {}; policy {}; state v{}; evidence {}; trigger {}".format(data["id"], data["result"], data["reason"], data["policy_version"], data["transaction"]["version"], ", ".join(data["evidence_ids"]) or "none", data["trigger_message_id"])
        elif kind == "TRANSACTION_CHANGED":
            before, after = data["before"], data["after"]
            detail = "{} → {}; conversation {}; v{} → v{}; {}".format(before["status"], after["status"], after["conversation"], before["version"], after["version"], after["reason"])
        elif kind == "TRANSFER_EXECUTED":
            detail = "Debit {}; balance {} → {}; authorization {}".format(data["amount"], data["before"]["balance"], data["after"]["balance"], data["decision_id"])
        elif kind in {"REQUEST_TIMEOUT", "REQUEST_RETRIED", "AUTHORIZATION_RECHECK_FAILED", "PROVIDER_UNAVAILABLE"}:
            detail = json.dumps(data, sort_keys=True)
        if detail:
            lines.append("| {} | {} | {} | {} |".format(event["time"], cell(data["transaction_id"]), kind, cell(detail)))
    lines += ["", "## Independent checks", ""]
    for check in quality["checks"]:
        lines.append("- [{}] {}{}".format("x" if check["passed"] else " ", check["name"], ": " + check["detail"] if check["detail"] else ""))
    lines += ["", "## Interpretation", "",
              "Correctness and fault handling are evaluated within this scenario's scope. Read the conversation to judge whether explanations and role behavior match the intended product. A passing suite does not establish general learning, production readiness, or application generation.", ""]
    return "\n".join(lines)


def save_run(run, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = "{}-seed-{}".format(run["scenario"], run["seed"])
    raw = directory / (stem + ".json")
    report = directory / (stem + ".md")
    raw.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.write_text(render_report(run), encoding="utf-8")
    return raw, report


def save_suite(runs, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    passed = sum(run["quality"]["passed"] for run in runs)
    representatives = {"high-risk", "expired-evidence", "conflicting-evidence", "duplicate-delivery", "unavailable-provider"}
    links = ["[{}]({}-seed-{}.md)".format(run["scenario"].replace("-", " "), run["scenario"], run["seed"])
             for run in runs if run["scenario"] in representatives and run["seed"] == runs[0]["seed"]]
    lines = ["# Agent communication — simulation suite", "", "**{} / {} scenario runs passed.**".format(passed, len(runs)), "",
             "Suggested conversations: " + ", ".join(links) + "." if links else "Inspect the per-scenario conversations below.", "",
             "A passing fault scenario means its expected rejection, escalation, or timeout occurred. It does not mean that the transfer succeeded.", "",
             "| Scenario | Seed | Checks | Outcomes | Messages | Logical time | Report |", "|---|---|---|---|---|---|---|"]
    summary = []
    for run in runs:
        q = run["quality"]
        outcomes = ", ".join(t["conversation"] for t in run["final_state"]["transactions"].values())
        link = "{}-seed-{}.md".format(run["scenario"], run["seed"])
        lines.append("| {} | {} | {} | {} | {} | {} | [Conversation]({}) |".format(run["scenario"], run["seed"], "PASS" if q["passed"] else "FAIL", outcomes, q["metrics"]["messages_sent"], q["metrics"]["logical_time"], link))
        summary.append({"scenario": run["scenario"], "seed": run["seed"], "outcomes": outcomes, **q})
    (directory / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "quality.json").write_text(json.dumps({"passed": passed, "total": len(runs), "runs": summary}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return directory / "index.md"
