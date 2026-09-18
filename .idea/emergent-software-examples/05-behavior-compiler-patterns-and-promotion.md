# Example 05 — Behavior Compiler: Pattern Detection and Promotion

The Behavior Compiler is the bridge between agentic exploration and scalable deterministic software.

It should not be imagined as:

```text
LLM sees logs
↓
writes code
↓
deploys code
```

That would be unsafe.

The proper lifecycle is controlled.

---

# Input

The compiler consumes structured behavior history.

Example run:

```json
{
  "runId": "RUN-1001",
  "scenario": "TRANSFER_MONEY",
  "initialFacts": {
    "risk": "HIGH",
    "strongAuth": false,
    "balance": "SUFFICIENT"
  },
  "events": [
    "TRANSFER_PROPOSED",
    "RISK_ASSESSED_HIGH",
    "STRONG_AUTH_REQUESTED",
    "STRONG_AUTH_COMPLETED",
    "TRANSACTION_REEVALUATED",
    "TRANSFER_EXECUTED"
  ],
  "outcome": "SUCCESS",
  "policyViolations": [],
  "latencyMs": 820
}
```

Thousands of runs create a behavior dataset.

---

# Pattern Detection

Suppose the compiler discovers:

```text
82% of HIGH risk transfers:
  request strong auth

100% of successful HIGH risk transfers:
  complete strong auth before execution

0 successful HIGH risk transfers:
  execute without strong auth
```

This is stronger than simply finding a common sequence.

We are looking for an invariant.

---

# Candidate Invariant

```text
For HIGH risk transfers:
TRANSFER_EXECUTED implies STRONG_AUTH_COMPLETED
```

Formal form:

```text
IF
  action = TRANSFER
  AND risk = HIGH
  AND state = EXECUTED

THEN
  evidence STRONG_AUTH_COMPLETED must exist
```

This is a possible law.

---

# Promotion Levels

Not every pattern should immediately become code.

Use promotion stages.

```text
LEVEL 0 — Observation
Pattern seen, no trust.

LEVEL 1 — Candidate
Pattern repeated enough to analyze.

LEVEL 2 — Verified Rule
Passes policy and security validation.

LEVEL 3 — Shadow Execution
Runs deterministically beside agent path.

LEVEL 4 — Canary
Handles small real traffic.

LEVEL 5 — Production Primitive
Default path for known cases.
```

---

# Example Promotion

## Level 0

```text
Observed 12 times.
```

Too early.

## Level 1

```text
Observed 5,000 times.
Stable outcome.
```

Create candidate.

## Level 2

Check:

```text
Does rule violate constitution?
Does rule create hidden privilege?
Does it preserve audit?
Does it handle failure?
```

## Level 3

Run both:

```text
Agent Decision
Compiled Decision
```

Compare outputs.

## Level 4

Use compiled rule for 1% of eligible traffic.

Monitor:

```text
decision mismatch
error rate
latency
policy violations
rollback rate
```

## Level 5

Promote to primitive.

---

# Candidate Rule Example

```yaml
candidate:
  id: CANDIDATE-HIGH-RISK-AUTH

  scope:
    scenario: TRANSFER_MONEY

  preconditions:
    - risk == HIGH

  required_evidence:
    - STRONG_AUTH_COMPLETED

  next:
    - REEVALUATE_TRANSACTION

  observed_runs: 18421
  successful_runs: 18377
  policy_violations: 0
```

---

# Generate Tests From Behavior

The compiler should generate counterexamples.

Example tests:

```text
High risk + no strong auth
→ must not execute

High risk + failed strong auth
→ must remain blocked

High risk + successful strong auth
→ reevaluation required

Low risk
→ rule should not incorrectly trigger

Strong auth expired
→ evidence invalid
```

---

# Generate State Machine

Sometimes a behavior is better represented as a state machine than code.

Example:

```text
REQUESTED
   ↓
RISK_HIGH
   ↓
WAITING_FOR_STRONG_AUTH
   ├── auth fail → BLOCKED
   └── auth pass → REEVALUATE
                      ↓
                  AUTHORIZED
                      ↓
                   EXECUTED
```

---

# Generate Primitive

After promotion:

```text
HIGH_RISK_TRANSFER_AUTH
```

The primitive may expose:

```ts
interface HighRiskTransferAuth {
  evaluate(ctx: TransferContext): Decision;
}
```

Agents can use this as a trusted capability.

---

# Primitive Invalidated by Change

Compiled knowledge must be reversible.

Example:

A new regulation says:

```text
High risk transfers above RM20,000 require manual approval.
```

The old primitive is no longer sufficient.

The runtime should detect law version mismatch.

```text
Primitive version:
  built against Constitution v12

Current Constitution:
  v13
```

Then:

```text
primitive suspended
↓
return to exploration
```

This is essential.

---

# Drift Detection

Compiled behavior can also degrade because the environment changes.

Signals:

```text
increased mismatch
new exception types
new policy failures
higher rollback
new unknown states
unexpected evidence requests
```

If drift exceeds threshold:

```text
KNOWN
↓
becomes uncertain again
↓
return to agent reasoning
```

So:

```text
Compile
≠
Forever
```

---

# Behavior Compiler Output Types

The compiler may produce:

```text
Rule
State Machine
Validation Function
Policy
Static Analyzer
API Primitive
UI Flow Primitive
Test Suite
Schema Constraint
Event Contract
```

The first MVP should only produce:

```text
Rule
+
Tests
```

That is enough to prove the idea.

---

# What an AI Builder Should Build

Minimum Behavior Compiler:

1. Read behavior runs.
2. Group by scenario.
3. Compare successful vs failed runs.
4. Find repeated preconditions.
5. Find repeated event subsequences.
6. Find evidence always present before success.
7. Produce human-readable candidate rule.
8. Generate tests.
9. Run candidate against historical runs.
10. Produce verification report.

Do NOT auto-deploy.

The milestone is:

```text
behavior history
→
candidate deterministic knowledge
```
