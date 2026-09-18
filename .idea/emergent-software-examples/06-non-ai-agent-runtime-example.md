# Example 06 — Build the Architecture Without AI First

One of the important conclusions from our discussion is:

```text
Agentic architecture does not require AI.
```

AI can be added later.

This is useful because it lets us prove:

```text
world
laws
state
evidence
protocol
behavior
```

without mixing in LLM uncertainty too early.

---

# Deterministic Agent Example

A Risk Agent can initially be:

```ts
type Risk = "LOW" | "MEDIUM" | "HIGH";

function assessRisk(input: {
  amount: number;
  trustedDevice: boolean;
}): Risk {
  if (input.amount > 10000 && !input.trustedDevice) {
    return "HIGH";
  }

  if (input.amount > 3000) {
    return "MEDIUM";
  }

  return "LOW";
}
```

It is still an agent in the architectural sense because it has:

```text
identity
capability
inputs it may observe
outputs it may propose
constraints
```

---

# Deterministic Payment Agent

```ts
function paymentAgent(ctx: {
  balance: number;
  amount: number;
}) {
  return {
    type: "PROVIDE_EVIDENCE",
    evidenceType: "BALANCE_SUFFICIENT",
    value: ctx.balance >= ctx.amount
  };
}
```

---

# Deterministic Identity Agent

```ts
function identityAgent(ctx: {
  tokenValid: boolean;
}) {
  return {
    type: "PROVIDE_EVIDENCE",
    evidenceType: "IDENTITY_VERIFIED",
    value: ctx.tokenValid
  };
}
```

---

# World Runtime

The World remains responsible for authorization.

Pseudo-implementation:

```ts
function evaluateProposal(
  proposal: Proposal,
  state: State,
  evidence: Evidence[],
  laws: Law[]
): Decision {
  const applicable = laws.filter(law =>
    law.appliesTo(proposal, state)
  );

  const missing = [];

  for (const law of applicable) {
    for (const requirement of law.requirements) {
      if (!isSatisfied(requirement, state, evidence)) {
        missing.push(requirement);
      }
    }
  }

  if (missing.length > 0) {
    return {
      allowed: false,
      missingEvidence: missing
    };
  }

  return {
    allowed: true
  };
}
```

---

# Why Start This Way

If the deterministic version cannot work, adding LLMs will not fix the architecture.

The first questions should be:

```text
Can agents communicate through a common protocol?

Can state be reconstructed?

Can laws be enforced outside agents?

Can evidence be verified?

Can behavior logs be replayed?

Can multiple interaction paths exist?
```

Only after these are solid should AI be introduced.

---

# Where AI Becomes Useful

Later, AI can be inserted into specific places.

### Intent Interpretation

```text
"Send five thousand to Ali"
↓
TRANSFER_MONEY intent
```

### Unknown Situation

```text
No existing primitive matches context
↓
LLM agent explores options
```

### Evidence Search

```text
Find evidence across repository/documentation
```

### Negotiation

```text
Risk Agent challenges Payment Agent
```

### Explanation

```text
Explain why transaction was blocked
```

### Behavior Interpretation

```text
Propose human-readable invariant from run history
```

But the safety boundary stays deterministic.

---

# Trusted vs Untrusted

A useful model:

```text
UNTRUSTED / ADVISORY

LLM Agent
External Agent
Remote Agent
Human Suggestion

        ↓ Proposal

========================

TRUST BOUNDARY

Policy Gate
Evidence Validation
Permissions
State Rules

========================

TRUSTED EXECUTION

Action Executor
Database
Payment Rail
Kafka
External API
```

Even a very capable model should not bypass the trusted boundary.

---

# Agent Replacement

Because protocol and laws are externalized, one agent implementation can be replaced.

Example:

```text
Risk Agent v1
  deterministic rule

↓ replace

Risk Agent v2
  ML model

↓ replace

Risk Agent v3
  LLM + tools
```

The rest of the world remains stable.

This is a major architectural advantage.

---

# Example: Same Protocol, Different Implementation

All versions produce:

```json
{
  "type": "PROVIDE_EVIDENCE",
  "evidenceType": "RISK_ASSESSED",
  "value": "HIGH",
  "confidence": 0.93
}
```

The World does not care how the conclusion was reached.

It only cares whether:

```text
producer is authorized
evidence shape is valid
evidence is fresh
policy accepts it
```

---

# MVP Recommendation

Build version 1 with:

```text
0 LLM agents
3 deterministic agents
1 World Runtime
5 laws
1 state store
1 event log
1 behavior recorder
```

Then prove:

```text
same world
+
same laws
+
different conditions
=
different valid behaviors
```

After that, replace only one agent with AI.

For example:

```text
Risk Agent
```

Compare:

```text
deterministic result
vs
AI result
```

This creates a clean experiment rather than a confused platform.

---

# Final Principle

The architecture should remain valuable even if all AI models are removed.

That proves the foundation is software architecture, not AI dependency.

AI should increase capability.

It should not be required for correctness.
