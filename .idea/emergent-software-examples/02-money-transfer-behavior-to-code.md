# Example 02 — Money Transfer: From Agent Interaction to Compiled Behavior

This is the primary MVP example.

---

# Goal

User requests:

```text
Transfer RM5,000 to Ali
```

We use:

```text
App Agent
Identity Agent
Risk Agent
Payment Agent
Policy Gate
World Runtime
```

---

# Step 1 — Intent

The App Agent observes:

```json
{
  "intent": "TRANSFER_MONEY",
  "amount": 5000,
  "recipient": "Ali"
}
```

It does not directly call the database.

It creates a proposal.

```json
{
  "type": "PROPOSE",
  "agent": "app-agent",
  "action": "TRANSFER",
  "amount": 5000,
  "recipient": "Ali"
}
```

---

# Step 2 — World Evaluates

The World checks relevant laws.

Example result:

```json
{
  "allowed": false,
  "missingEvidence": [
    "IDENTITY_VERIFIED",
    "BALANCE_SUFFICIENT",
    "RISK_ASSESSED"
  ]
}
```

The action is not rejected permanently.

It is unresolved.

---

# Step 3 — Evidence Gathering

Identity Agent provides:

```json
{
  "type": "PROVIDE_EVIDENCE",
  "evidenceType": "IDENTITY_VERIFIED",
  "value": true
}
```

Payment Agent provides:

```json
{
  "type": "PROVIDE_EVIDENCE",
  "evidenceType": "BALANCE_SUFFICIENT",
  "value": true
}
```

Risk Agent provides:

```json
{
  "type": "PROVIDE_EVIDENCE",
  "evidenceType": "RISK_ASSESSED",
  "value": "HIGH"
}
```

---

# Step 4 — Law Trigger

The Constitution contains:

```yaml
law:
  id: PAYMENT-HIGH-RISK-001

  when:
    transaction.risk: HIGH

  require:
    - STRONG_AUTH_COMPLETED
```

The World transitions to:

```text
WAITING_FOR_STRONG_AUTH
```

---

# Step 5 — Strong Authentication

After the user completes authentication:

```json
{
  "type": "PROVIDE_EVIDENCE",
  "evidenceType": "STRONG_AUTH_COMPLETED",
  "value": true
}
```

The World evaluates again.

Now:

```text
IDENTITY_VERIFIED = true
BALANCE_SUFFICIENT = true
RISK = HIGH
STRONG_AUTH = true
```

All required laws are satisfied.

The World authorizes:

```text
EXECUTE_TRANSFER
```

---

# Important Observation

The system did not have to contain one fixed implementation like:

```text
identity()
balance()
risk()
otp()
payment()
```

The behavior was created from:

```text
state
+
laws
+
evidence
+
agent interaction
```

---

# Behavior Log

The entire interaction should be recorded.

Example:

```text
RUN-10082

01 PROPOSE TRANSFER
02 LAW PAYMENT-001 requires identity
03 REQUEST_EVIDENCE IDENTITY_VERIFIED
04 PROVIDE_EVIDENCE IDENTITY_VERIFIED=true
05 LAW PAYMENT-002 requires balance
06 PROVIDE_EVIDENCE BALANCE_SUFFICIENT=true
07 RISK_ASSESSED=HIGH
08 LAW PAYMENT-HIGH-RISK-001 triggered
09 STATE → WAITING_FOR_STRONG_AUTH
10 STRONG_AUTH_COMPLETED=true
11 REEVALUATE
12 ACTION AUTHORIZED
13 EXECUTE_TRANSFER
14 STATE → COMPLETED
```

---

# Repeat the Simulation

Now run many variants.

Example dimensions:

```text
amount:
  50
  500
  5000
  50000

risk:
  LOW
  MEDIUM
  HIGH

deviceTrust:
  TRUSTED
  UNKNOWN
  COMPROMISED

identity:
  VERIFIED
  EXPIRED
  UNKNOWN

balance:
  SUFFICIENT
  INSUFFICIENT

strongAuth:
  AVAILABLE
  FAILED
  SUCCESS
```

---

# Discovered Pattern

Suppose thousands of safe runs reveal:

```text
IF
  risk = HIGH

THEN
  strong auth is always required

AND AFTER SUCCESS
  transaction is always reevaluated
```

The Behavior Compiler proposes:

```yaml
candidate_rule:
  id: CANDIDATE-27

  when:
    transaction.risk: HIGH

  require:
    - STRONG_AUTH_COMPLETED

  then:
    - REEVALUATE_TRANSACTION
```

---

# Generate Tests

The compiler should generate tests before production code.

Example:

```text
TEST 1
Given risk = HIGH
And strong auth = false
Then transfer must not execute

TEST 2
Given risk = HIGH
And strong auth = true
Then transaction must be reevaluated

TEST 3
Given risk = LOW
Then strong auth is not required by this rule

TEST 4
Given strong auth failed
Then state must not become EXECUTED
```

---

# Compile the Behavior

After verification:

```ts
function evaluateHighRiskTransfer(ctx) {
  if (ctx.risk !== "HIGH") {
    return NOT_APPLICABLE;
  }

  if (!ctx.strongAuthCompleted) {
    return {
      allowed: false,
      requiredEvidence: ["STRONG_AUTH_COMPLETED"]
    };
  }

  return {
    allowed: false,
    nextAction: "REEVALUATE_TRANSACTION"
  };
}
```

Now that path no longer requires open-ended reasoning.

---

# Before and After

## Before

```text
Unknown situation
↓
Agent reasoning
↓
Interaction
↓
Evidence
↓
Decision
```

## After Compilation

```text
Known condition
↓
Deterministic rule
↓
Immediate decision
```

---

# Scaling Benefit

At large scale:

```text
1 million transactions
```

should not mean:

```text
1 million expensive multi-agent reasoning sessions
```

Instead:

```text
known cases
→ deterministic path

unknown / novel cases
→ agent exploration
```

This is one of the strongest reasons for the architecture.

---

# What an AI Builder Should Implement First

1. Proposal model
2. Evidence model
3. Law evaluator
4. State machine storage
5. Behavior log
6. Deterministic agents
7. Scenario generator
8. Pattern detector
9. Candidate rule output
10. Test generator
11. Compiled rule path
12. Compare agent path vs compiled path

Measure:

```text
latency
cost
consistency
policy violations
reasoning steps avoided
```
