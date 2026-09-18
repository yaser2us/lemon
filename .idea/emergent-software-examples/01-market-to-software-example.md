# Example 01 — From Market Behavior to Software Behavior

## Why the Market Analogy Matters

A market is useful because no single participant controls the whole system.

Each actor has only a partial view.

Example actors:

```text
Buyer
Seller
Supplier
Bank
Regulator
Logistics Provider
Investor
```

Each one has:

```text
Goal
Information
Resources
Constraints
Strategy
```

A buyer may only know:

```text
price
budget
need
availability
```

A seller may only know:

```text
inventory
cost
margin
demand
```

A bank may care about:

```text
settlement
credit
fraud
liquidity
```

A regulator may care about:

```text
legal boundaries
consumer protection
market integrity
```

None of them is "the market".

Yet together they create:

```text
price movement
shortage
competition
cooperation
trust
specialization
arbitrage
liquidity
panic
stability
```

These are **system-level behaviors** emerging from local interactions.

---

# Software Translation

Now replace market actors with software actors.

```text
Market Actor            Software Equivalent
------------------------------------------------
Buyer                   User Agent
Seller                  Service Agent
Bank                    Payment Agent
Regulator               Policy Engine
Risk Analyst            Risk Agent
Market Ledger           Shared State
Receipts                Evidence
Market Rules            Constitution
Transactions            Actions
```

The important shift is this:

Traditional software asks:

> What exact sequence should happen?

Emergent software asks:

> What must be true before an action is allowed?

---

# Traditional Workflow

```text
1. User submits transfer
2. Validate identity
3. Check balance
4. Run fraud
5. Run compliance
6. Ask for OTP
7. Execute payment
8. Write audit log
```

This sequence is centrally encoded.

---

# Law-Driven World

Instead, define laws:

```text
LAW-01
No transfer without valid identity.

LAW-02
No transfer without sufficient balance.

LAW-03
High-risk transactions require stronger authentication.

LAW-04
Every external dependency must have timeout and bounded retry.

LAW-05
Every state change must produce audit evidence.
```

Now the actual sequence may vary.

For one transaction:

```text
Identity
↓
Balance
↓
Risk
↓
Strong Auth
↓
Payment
```

For another:

```text
Identity
↓
Risk
↓
Device Evidence
↓
Balance
↓
Strong Auth
↓
Payment
```

For a low-risk transaction:

```text
Identity
↓
Balance
↓
Risk
↓
Payment
```

The laws stay stable while the interaction path can differ.

---

# Why This Is Interesting

This means:

```text
Law != Workflow
```

A workflow tells the system:

> Do A, then B, then C.

A law tells the system:

> C is not allowed unless X, Y, and Z are true.

This creates room for local reasoning while preserving safety.

---

# A Simple Simulation

Imagine 1,000 simulated transactions.

Each transaction varies:

```text
amount
risk
device trust
balance
identity
strong auth
network quality
service latency
```

Agents react.

The system records:

```text
what happened
what evidence was requested
which law blocked an action
what order agents interacted in
whether the transaction succeeded
latency
cost
failures
```

After many simulations, patterns may appear.

Example:

```text
Pattern A

WHEN
  risk = HIGH
  AND device_trust = LOW

AGENTS USUALLY DO
  request device evidence
  request strong auth
  reevaluate risk

RESULT
  safe completion in 99.9% of valid simulations
```

This becomes a candidate for formalization.

---

# From Emergence to Primitive

Once stable:

```text
Observed Behavior
      ↓
Formal Rule
      ↓
Verification
      ↓
Primitive
```

For example:

```text
REQUIRE_HIGH_RISK_AUTH
```

Later agents no longer need to rediscover this pattern.

They can call the primitive.

This is similar to how a market develops conventions, contracts, standards, and institutions after repeated interactions.

---

# What an AI Builder Should Take From This

Do not model the first system as one large orchestrator.

Build:

```text
Actors
+
Laws
+
State
+
Evidence
+
Interaction Protocol
```

Then let multiple valid paths exist.

The experiment is successful when:

```text
same laws
+
different situations
=
different valid interaction paths
```

while safety constraints remain intact.
