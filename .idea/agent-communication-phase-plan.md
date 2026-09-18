# Phase 1 — Agent Communication and Simulation

**Date:** 2026-09-18  
**Status:** Implemented locally; automated validation completed; user review of conversations pending.  
**Parent:** [Emergent Software build plan](emergent-software-build-plan.md)  
**References:** [App/backend communication](emergent-software-examples/03-app-agent-backend-agent-example.md) · [Deterministic runtime](emergent-software-examples/06-non-ai-agent-runtime-example.md)

## Implementation and review

The implementation uses Python 3.9+ with no external dependencies. See the [README](../README.md) for commands and architecture, and the [generated review index](../runs/review/index.md) for conversations and quality reports. Regenerate that index with `python3 -m lemon suite` from the repository root.

Automated validation covers all 22 registered scenarios across 30 delivery-order seeds (660 runs), plus contract, evidence, state-isolation, replay, CLI, and agent-failure regressions. Run `python3 -m unittest discover -s tests -v` to reproduce the checks.

The representative conversations are ready for human review. Whether the communication style and local decisions match the intended product remains a user judgment; passing tests does not resolve that acceptance item.

The sections below preserve the agreed scope and acceptance criteria. The proposed implementation choices are now Python, a command-line runner, and generated Markdown/JSON reports.

## 1. Goal

Given a task, agents exchange information, resolve uncertainty, and reach a valid outcome through a conversation we can inspect, replay, and evaluate.

This phase establishes the communication foundation for the larger Emergent Software vision. It does not yet establish that agents can discover new algorithms or build complete applications autonomously.

The user should be able to run a scenario, read the agents' conversation, understand why each consequential message was accepted or rejected, and see an independent quality report.

## 2. Scope and proposed decisions

- Build a small agent runtime in one process with an in-process message queue.
- Start with deterministic agents whose next actions depend on observed state and incoming messages.
- Use a simulated money transfer as the first scenario, consistent with the existing design documents.
- Use simulated identity, authentication, balances, and execution. No real transfers or external accounts.
- Use structured messages with optional readable explanations.
- Provide a command-line runner and a generated readable transcript first. A browser interface is a later presentation decision.
- Persist run records as structured files so they remain inspectable without a database service.
- Keep transport, policy enforcement, and agent decision functions separate so one agent can later be replaced by an LLM.

Deferred: LLM integration, model credentials, distributed services, behavior compilation, generated application code, production deployment, and automatic policy changes.

The implementation uses Python's standard library and does not require an external agent framework.

## 3. What makes this agentic

Each agent has an identity, a goal, permitted observations, available capabilities, and a decision function:

```text
Observe relevant messages and state
→ choose a request, proposal, response, wait, or escalation
→ submit it to the runtime
→ react to subsequent updates
```

The runtime schedules work and enforces constraints. It does not prescribe one global sequence of identity, balance, risk, and authentication steps.

Agent behavior will still be programmed in this phase. Different paths demonstrate local decision-making under shared rules; they do not by themselves prove learning or novel discovery.

## 4. Participants and responsibilities

| Participant | Responsibility | Boundary |
|---|---|---|
| App Agent | Express the user's intent, request missing capabilities, handle simulated user challenges, report outcomes | Cannot authorize or execute a transfer |
| Risk Agent | Assess simulated risk from permitted facts and provide attributed evidence | Cannot waive authentication requirements |
| Payment Agent | Obtain balance evidence and propose execution when appropriate | Cannot directly mutate the ledger |
| Identity/authentication providers | Return simulated verification evidence or a challenge outcome | Providers are capabilities, not additional autonomous agents in this phase |
| World runtime | Route messages, validate evidence and proposals, enforce laws, update authoritative state | Does not treat an agent's assertion as authorization |
| Executor | Apply an authorized simulated transfer exactly once | Requires a current authorization and transaction identity |
| Simulator/evaluator | Supply inputs and faults, record activity, check expected outcomes | Expected results remain hidden from agents |

Agents can request capabilities through the runtime. The runtime attributes evidence to the actual producer; forwarding a provider's result does not make an agent its issuer.

## 5. Communication contract

Start with these message types:

| Type | Purpose |
|---|---|
| `PROPOSE` | Request an action or state transition |
| `REQUEST_EVIDENCE` | Ask for a specific fact or verification |
| `PROVIDE_EVIDENCE` | Supply evidence or a reference to a recorded evidence object |
| `CHALLENGE` | Identify a concrete inconsistency or invalid claim |
| `DECISION` | Runtime response: allowed, pending evidence, or rejected, with reasons |
| `ESCALATE` | Report an unresolved condition requiring intervention |
| `COMPLETE` | Runtime-confirmed terminal result |

Common fields: schema version, message ID, conversation ID, sender, recipient, subject, message type, typed payload, simulated timestamp, optional reply-to ID, and request deadline where applicable.

Every consequential message must identify the task and subject it concerns. An optional explanation makes the transcript readable; it is not used as executable policy or a substitute for evidence. We record observable actions and stated reasons, not private model reasoning.

The runtime validates message shape, sender permissions, recipients, and conversation scope. Invalid messages produce explicit rejection records without changing domain state.

## 6. Evidence and state

Evidence records include an ID, type, authorized producer, subject, value, source, issue time, expiry where applicable, and relevant transaction or state version.

Validation checks include producer authority, value, freshness, subject binding, and applicability to the current transaction. A well-formed record alone does not make a claim true.

Maintain separate conversation status and transaction status:

- Conversation: active, waiting, completed, rejected, escalated, timed out, or budget exhausted.
- Transaction: requested, pending evidence, authorized, executing, completed, blocked, or failed.

Missing evidence is pending rather than a permanent rejection. Negative evidence, such as insufficient balance, can legitimately block a transfer. Unknown information remains explicit.

Authorization must be checked against current state at execution. In the simulated ledger, the balance check and debit occur atomically; old balance evidence cannot authorize spending money that has already been spent. Duplicate requests cannot create duplicate debits.

## 7. Delivery, conflicts, and stopping

- Use a seeded scheduler and logical clock for reproducible delays, timeouts, and event ordering.
- Preserve message identity when simulating redelivery. Process duplicates idempotently and record their disposition.
- Keep pending request tracking so agents avoid repeatedly asking for the same unresolved evidence.
- Use finite request deadlines, bounded retries, and a per-conversation message budget. Initial proposed defaults: 2 retries per request and 50 messages per conversation; record overrides in each run.
- Reject late state-changing messages after conversation termination and record the reason.
- Resolve stale evidence through a fresh request to the authorized source. Conflicting current evidence that cannot be resolved leads to escalation, not majority voting.
- Stop on a terminal result, timeout, escalation, or exhausted budget. A budget stop is visible as incomplete work and cannot count as successful task completion.

## 8. First demonstration

```text
App Agent → World: Propose transfer
World → App Agent: Identity, balance, and risk evidence required
App Agent → Identity provider: Request identity evidence
App Agent → Payment Agent: Request balance evidence
App Agent → Risk Agent: Request risk assessment
Providers/agents → World: Supply attributed evidence
World → App Agent: High risk requires additional authentication
App Agent → Authentication provider: Initiate simulated challenge
Authentication provider → World: Supply challenge result
Payment Agent → World: Propose execution when requirements are satisfied
World → Executor: Authorize execution against current state
Executor → World: Record simulated result
World → App Agent: Report completion or failure
```

This is an example transcript, not a fixed runtime script. Low-risk, preverified, blocked, and delayed scenarios should produce different paths.

## 9. Scenario suite

| Scenario | Expected result |
|---|---|
| Valid low-risk transfer | Complete without an unnecessary strong-authentication challenge |
| Valid high-risk transfer | Complete only after valid additional authentication |
| Missing identity evidence | Request it; execution remains pending |
| Failed authentication or insufficient balance | Block with an explicit reason and no debit |
| Expired evidence | Reject it and request fresh evidence within limits |
| Wrong subject or unauthorized evidence producer | Reject the evidence; do not authorize from it |
| Conflicting evidence | Refresh from the authoritative source or escalate |
| Duplicate proposal or execution message | At most one transfer effect |
| Unavailable provider | Bounded retry, then timeout or escalation |
| Delayed or reordered evidence | Maintain correct authorization and termination behavior |
| Two transfers competing for one balance | No overdraft from stale checks |
| Unauthorized action proposal | Reject with no domain side effect |
| Repeated requests without progress | Detect budget exhaustion and report incomplete work |
| Execution failure after authorization | Report failed execution, never successful completion |
| Message for another conversation | Reject or isolate it; no cross-conversation evidence leakage |
| Message after termination | Record rejection without reopening or mutating the transaction |

Include hand-authored cases and seeded variations. Define expected outcomes and invariants independently of the agents' decision logic.

## 10. Communication quality

| Dimension | Evidence and measurement |
|---|---|
| Clarity | Required subject, request, response, and correlation fields are present; transcript review confirms understandable intent |
| Relevance | Requests correspond to unresolved requirements; report redundant requests separately |
| Evidence quality | Every consequential decision links to accepted evidence and the applicable policy version |
| Correctness | Outcome matches the scenario expectation and independent invariants |
| Progress | Every run terminates within limits; distinguish meaningful resolution from budget exhaustion |
| Efficiency | Message count, duplicate requests, retry count, agent invocations, and elapsed logical time |
| Robustness | Fault scenarios retain the expected outcome or explicit bounded fallback |
| Traceability | State and decisions can be reconstructed from the run log |

Do not collapse these into one score initially. Agreement among agents and persuasive explanations are not substitutes for correctness.

Report logical time separately from actual runtime. With deterministic agents, report message and invocation counts; do not claim LLM token-cost savings.

## 11. Implementation milestones

1. **Contracts and fixtures:** Define message schemas, evidence types, permissions, laws, and scenario expectations. Review example transcripts against the agreed behavior.
2. **Runtime and enforcement:** Build the queue, logical clock, state store, policy gate, evidence validation, and simulated executor. Demonstrate that invalid requests cannot change protected state.
3. **Agent interaction:** Implement the three local decision loops and simulated providers. Demonstrate several paths under the same laws without a global task script.
4. **Fault simulation:** Add seeded ordering, expiry, duplicates, unavailability, conflicting evidence, and competing transfers. Demonstrate bounded termination and correct effects.
5. **Inspection and evaluation:** Generate structured run logs, readable transcripts, replay output, and per-scenario quality reports.
6. **Review demonstration:** Present successful, blocked, stale-evidence, duplicate-delivery, and timeout conversations alongside their quality results for user review.

Each milestone depends on the preceding contracts and runtime behavior. No application-building or behavior-compilation work is implied by completing this phase.

## 12. Reviewable deliverables

- A runnable local communication simulator.
- Versioned message, evidence, and agent capability definitions.
- Three deterministic agents and simulated providers.
- A scenario suite with explicit expected results.
- Structured run logs and a readable conversation report.
- Replay support that reconstructs final state without repeating external effects.
- A quality report with per-scenario outcomes, evidence links, and communication metrics.
- Instructions for running a scenario, replaying a run, and adding an agent or scenario.

## 13. Acceptance criteria

- All named scenarios have independent assertions and pass within their declared expectations.
- No unauthorized execution, duplicate debit, or overdraft occurs in the defined test suite.
- Every authorization and rejection is reconstructable from policy, evidence, state version, and triggering proposal.
- Agents demonstrate distinct interaction paths when inputs or delivery order change.
- All conversations stop within configured limits; nominal valid scenarios complete without exhausting their budgets.
- A fixed seed and configuration reproduce the same logical trace; replay reconstructs the recorded final state.
- Quality metrics are visible per scenario, with incomplete work and failures reported explicitly.
- The user can inspect the representative conversations and decide whether the communication behavior matches the intended product.

Passing these criteria establishes the communication foundation within the tested scope. It does not establish production readiness or general intelligence.

## 14. Decisions for user review

The proposed defaults are a money-transfer simulation, three deterministic agents, structured communication, one process, and a readable local report.

Review especially:

1. Whether money transfer is the right first conversation, or whether the first scenario should instead be agents negotiating a software interface.
2. Whether the proposed roles and degree of local agent autonomy match the intended behavior.
3. Whether a readable report is enough for the first review, or an interactive conversation viewer is essential.

The user authorized implementation after reviewing this plan. A later phase can replace one decision function with an LLM and evaluate it against the same protocol and scenarios. Software-building agents and the behavior compiler remain subsequent phases in the parent plan.
