"""Readable design conversations and machine-readable specification artifacts."""

import json
from pathlib import Path

from .reporting import cell


def specification(run):
    s = run["final_state"]
    ui_review = s["reviews"].get("ui-agent", {})
    test_review = s["reviews"].get("test-agent", {})
    return {"schema_version": 2 if "verification" in s else 1, "feature": "Transfer feature", "status": s["status"],
            "reviewer": run.get("reviewer", {"provider": "deterministic"}),
            "agreement": s["status"] == "agreed", "quality_checks_passed": run["quality"]["passed"],
            "contract_revision": s["revision"], "requirements": s["requirements"], "cancellation": s["cancellation"],
            "contract": s["contract"], "ui_states": (ui_review.get("artifact") or {}).get("ui_states", {}),
            "design_model_verification": s.get("verification", {"status": "not_run"}),
            "planned_test_cases": (test_review.get("artifact") or {}).get("test_cases", []),
            "approvals": s["reviews"], "unresolved_questions": s["questions"], "unresolved_challenges": s["challenges"],
            "implementation_status": "not_generated", "feature_test_execution": "not_run"}


def render_design(run):
    state, quality = run["final_state"], run["quality"]
    reviewer = run.get("reviewer", {"provider": "deterministic"})
    description = ("Product, Backend, and UI use deterministic rules; the Test Agent uses Anthropic model `{}`. Model output is validated before it becomes a message.".format(reviewer["model"])
                   if reviewer["provider"] == "anthropic" else "Four deterministic agents negotiate a transfer feature. No LLM calls are involved.")
    stem = "{}-seed-{}".format(run["scenario"], run["seed"])
    lines = ["# Software-design conversation — {}".format(run["variant"]), "",
             "**Outcome: {}.** Contract revision: {}. Scenario checks: **{}**.".format(state["status"], state["revision"], "PASS" if quality["passed"] else "FAIL"), "",
             description + " Their outputs are requirements, an interface contract, UI behavior, and planned test cases. No application code is generated.", "",
             "[Specification]({}.spec.json) · [Full messages and replay log]({}.json)".format(stem, stem), "",
             "## Conversation", "", "Messages below are recorded agent statements in delivery order. Rejected or stale proposals remain visible. The World routes messages and requires current-version approvals.", ""]
    # Deliveries are paired with their local dispositions so redelivery is visible.
    rows, current = [], {}
    for e in run["events"]:
        d = e["data"]
        if e["kind"] == "MESSAGE_RECEIVED":
            row = {"time": e["time"], "message": d["message"], "outcome": ""}
            rows.append(row)
            current[d["message"]["id"]] = row
        elif e["kind"] in {"MESSAGE_REJECTED", "DUPLICATE_IGNORED"} and d.get("message_id") in current:
            current[d["message_id"]]["outcome"] = d.get("reason", e["kind"])
    for row in rows:
        m = row["message"]
        if m["sender"] == "world" and m["type"] != "VERIFICATION_FEEDBACK":
            continue
        p = m["payload"]
        version = p.get("revision", p.get("base_revision"))
        lines += ["**t={} · {} → {} · {}{}** (`{}`)".format(row["time"], m["sender"], m["recipient"], m["type"], " · revision {}".format(version) if version is not None else "", m["id"]), "",
                  "> " + m["explanation"], ""]
        if row["outcome"]:
            lines += ["Disposition: **{}**.".format(row["outcome"]), ""]
    lines += ["## Design model verification", "", "These checks execute against the bounded design model, not application code. Structured case assertions are authoritative; prose is explanatory and is not semantically verified.", ""]
    for event in run["events"]:
        if event["kind"] == "DESIGN_VERIFIED":
            d = event["data"]
            lines.append("- Revision {}, repair round {}: **{}**".format(d["revision"], d["attempt"], d["status"]))
            lines.extend("  - {} / {}: {}".format(f["owner"], f["code"], f["detail"]) for f in d["failures"])
    lines += ["", "## How the contract changed", "", "| Revision | Trigger | Statuses | Success means | Retry behavior |", "|---|---|---|---|---|"]
    for e in run["events"]:
        if e["kind"] != "DESIGN_CHANGED" or e["data"]["before"]["revision"] == e["data"]["after"]["revision"]:
            continue
        d = e["data"]
        c = d["after"]["contract"]
        lines.append("| {} | {} | {} | {} | {} |".format(d["after"]["revision"], d["cause_message_id"], cell(", ".join(c["states"])), c["success_state"], c["idempotency"]))
    spec = specification(run)
    lines += ["", "## Current specification", "", "Agreement: **{}**. This is a design artifact, not an implemented feature.".format(spec["agreement"]), "", "### Requirements", ""]
    lines.extend("- **{}:** {}".format(k, v) for k, v in spec["requirements"].items())
    lines += ["", "Cancellation: `{}`.".format(spec["cancellation"]), "", "### Interface", "", "```json", json.dumps(spec["contract"], indent=2, sort_keys=True), "```", "",
              "### UI behavior", "", "| Backend state | UI behavior |", "|---|---|"]
    lines.extend("| {} | {} |".format(cell(k), cell(v)) for k, v in spec["ui_states"].items())
    lines += ["", "### Planned acceptance tests — not executed", "", "| Case | Requirement | Given | When | Then |", "|---|---|---|---|---|"]
    for case in spec["planned_test_cases"]:
        lines.append("| {} |".format(" | ".join(cell(case[k]) for k in ("id", "requirement", "given", "when", "then"))))
    lines += ["", "### Unresolved questions", ""]
    lines.extend("- " + q for q in spec["unresolved_questions"])
    if not spec["unresolved_questions"]:
        lines.append("None within this deliberately limited design exercise. Runtime safety and the other requirements of a production transfer system remain outside this interface exercise.")
    lines += ["", "## Communication quality", "", quality["note"], "", "| Metric | Value |", "|---|---|"]
    for key, value in quality["metrics"].items():
        lines.append("| {} | {} |".format(key.replace("_", " "), cell(json.dumps(value, sort_keys=True) if isinstance(value, dict) else value)))
    lines += ["", "Logical time is a simulated clock; runtime is measured separately.", ""]
    if reviewer["provider"] == "anthropic":
        lines += ["API token totals use provider-reported usage. Failed requests without usage are counted separately; totals may exclude those requests. Model output can vary between fresh runs even with the same scheduler seed. Saved-event replay makes no API calls.", "",
                  "### Model review calls", "", "| Revision | Result | Decision or error | Attempts | Input tokens | Output tokens | Latency ms |", "|---|---|---|---|---|---|---|"]
        for event in run["events"]:
            if event["kind"] == "MODEL_REVIEW":
                m = event["data"]
                lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(m["revision"], m["result"], m.get("decision", m.get("error_code", "")), m["attempts"], m.get("input_tokens", "unknown"), m.get("output_tokens", "unknown"), m["latency_ms"]))
        lines.append("")
    lines.extend("- [{}] {}".format("x" if c["passed"] else " ", c["name"]) for c in quality["checks"])
    lines += ["", "Agreement requires Product, Backend, UI, and Test to approve the same revision. Missing input, a silent reviewer, or a message budget limit never counts as approval.", ""]
    return "\n".join(lines)


def save_design(run, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = "{}-seed-{}".format(run["scenario"], run["seed"])
    (directory / (stem + ".json")).write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / (stem + ".spec.json")).write_text(json.dumps(specification(run), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = directory / (stem + ".md")
    report.write_text(render_design(run), encoding="utf-8")
    return report


def save_design_index(runs, directory):
    lines = ["# Software-design conversations", "", "Each conversation identifies whether its Test Agent is deterministic or model-backed. No application code is generated or feature tests executed.", "",
             "| Variant | Outcome | Revision | Quality checks | Conversation |", "|---|---|---|---|---|"]
    for run in runs:
        lines.append("| {} | {} | {} | {} | [Read]({}-seed-{}.md) |".format(run["variant"], run["final_state"]["status"], run["final_state"]["revision"], "PASS" if run["quality"]["passed"] else "FAIL", run["scenario"], run["seed"]))
    path = Path(directory) / "index.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def save_comparison(baseline, candidate, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    baseline_report, candidate_report = save_design(baseline, directory), save_design(candidate, directory)
    summary = {"variant": candidate["variant"], "seed": candidate["seed"],
               "same_final_contract": baseline["final_state"]["contract"] == candidate["final_state"]["contract"],
               "baseline": {"status": baseline["final_state"]["status"], "quality": baseline["quality"]},
               "anthropic": {"status": candidate["final_state"]["status"], "reviewer": candidate["reviewer"], "quality": candidate["quality"]}}
    stem = "comparison-{}-seed-{}".format(candidate["variant"], candidate["seed"])
    (directory / (stem + ".json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Deterministic vs Anthropic reviewer", "", "Same scenario inputs and scheduler seed; only the Test Agent implementation changes.", "",
             "[Baseline conversation]({}) · [Anthropic conversation]({})".format(baseline_report.name, candidate_report.name), "",
             "| Measurement | Deterministic | Anthropic |", "|---|---|---|",
             "| Outcome | {} | {} |".format(baseline["final_state"]["status"], candidate["final_state"]["status"]),
             "| Scenario checks | {} | {} |".format("PASS" if baseline["quality"]["passed"] else "FAIL", "PASS" if candidate["quality"]["passed"] else "FAIL")]
    for key in ("messages_sent", "contract_revisions", "challenges_delivered", "current_approvals", "unresolved_questions", "api_requests", "reported_input_tokens", "reported_output_tokens", "model_reviews_without_usage", "model_latency_ms", "runtime_ms"):
        lines.append("| {} | {} | {} |".format(key.replace("_", " "), baseline["quality"]["metrics"][key], candidate["quality"]["metrics"][key]))
    lines += ["", "Same final interface contract: **{}**.".format(summary["same_final_contract"]), "",
              "This single paired run measures behavior for one scenario. It does not establish that the model is generally better or cheaper. Review the generated test cases for usefulness; schema and requirement coverage checks do not prove their semantic completeness.", "",
              "Reported token totals can exclude failed requests with no usage response. No dollar-cost estimate is inferred. API failures and invalid model reviews stop the conversation explicitly; there is no silent fallback to deterministic approval.", ""]
    report = directory / (stem + ".md")
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
