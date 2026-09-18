# From operating a feature to negotiating its design

These walkthroughs summarize recorded deterministic runs with seed `7`. The reports contain the actual messages and evidence. The short dialogue below is condensed for reading; it is not an additional agent execution.

## 1. Existing transfer conversation

Regenerate it with:

```sh
python3 -m lemon run high-risk --seed 7
```

[Full transfer conversation](../runs/review/high-risk-seed-7.md)

| Participant | What happened |
|---|---|
| App Agent | Proposed the transfer and requested missing identity, balance, and risk evidence. |
| Risk Agent | Reported high risk, which triggered the authentication requirement. |
| Identity provider and Payment Agent | Supplied identity and balance evidence while independent requests were in flight. |
| App Agent | Requested authentication and avoided repeating requests for evidence already available. |
| Payment Agent | Proposed execution after the World reported readiness. |
| World and executor | Checked authorization, rechecked current evidence and balance at execution, applied one simulated debit, and reported completion. |

The recorded result is 17 messages, zero retries, one completed transfer, and passing scenario checks. No success was announced merely because the transfer had been authorized.

The important communication behavior is that messages can arrive after the world has changed. At t=11, a delayed decision still named missing balance and authentication evidence. The App Agent observed current state and pending requests before acting, so it did not start redundant requests.

That motivates a similar rule for design conversations: a review must identify which version it applies to.

## 2. New software-design conversation

Regenerate all design variants with:

```sh
python3 -m lemon design --variant all --seed 7
```

[Full design conversation](../runs/design/design-negotiated-seed-7.md) · [Specification](../runs/design/design-negotiated-seed-7.spec.json)

The feature is a bounded transfer interface: amount and recipient input, observable progress/authentication states, safe retry semantics, and success only after execution.

**Product Agent:** Define those requirements and make cancellation explicitly outside the default exercise.

**Backend Agent:** Propose revision 1 with `REQUESTED`, `AUTHORIZED`, and `FAILED`. The draft incorrectly uses `AUTHORIZED` as success and does not specify safe retries.

**Test Agent:** Challenge that draft. Authorization can still be followed by failure; repeated submission needs an idempotency key; acceptance cases need observable authentication and execution states.

**UI Agent:** Challenge the missing `WAITING_FOR_AUTH`, `EXECUTING`, and `REJECTED` states.

**Backend Agent:** Propose revision 2, adding the missing states, `COMPLETED` as the success condition, and a same-key/same-transaction retry contract.

**World:** Discard approvals of revision 1. Require each role to review revision 2.

**Product, Backend, UI, and Test:** Approve revision 2 within their roles. UI contributes the screen mapping; Test contributes six planned acceptance cases.

For seed `7`, the result is 25 messages, two draft revisions, four approvals of the current revision, and no unresolved questions within the exercise. Two stale review notifications are rejected rather than acting on an outdated draft. Other seeds can take different paths.

## 3. What the conversation produces

The `.spec.json` artifact contains:

- Four requirements with stable IDs.
- A request/response contract with an idempotency key.
- Seven backend states and their UI meanings.
- Six planned acceptance cases, each linked to a requirement.
- Current-version approval records linked to actual messages.
- Explicit unresolved questions and challenges, if any.

This is a design artifact. The agents have not implemented the feature or run those planned application tests. The simulator's automated tests verify communication, state changes, protocol enforcement, and specification quality.

## 4. Check the incomplete outcomes too

[All design variants](../runs/design/index.md)

| Variant | Result | What it demonstrates |
|---|---|---|
| Negotiated | Agreed | Challenges cause revisions and all roles approve the current version. |
| Missing decision | Needs input | A cancellation question remains explicit; the runtime does not invent a product decision. |
| Silent reviewer | Needs review | Silence is not approval. The missing Test Agent review is recorded. |
| Duplicate delivery | Agreed | Redelivering a proposal or approval does not create another revision or another role's vote. |

Independent checks evaluate the specification in addition to counting approvals. A regression test deliberately replaces the Test Agent with an indiscriminate approver: the roles can reach consensus, but the independent evaluator still rejects the resulting quality. Agreement and correctness are different observations.

## 5. What to review as the product owner

Read the actual conversation and check whether the roles ask useful questions, whether their reasons support the proposed changes, whether disagreements remain visible, and whether the final specification is concrete enough for an implementation phase.

The current agents follow programmed local rules. Their communication is executable and reproducible; it is not yet open-ended AI reasoning. LLM integration and agents that write code remain separate next steps.
