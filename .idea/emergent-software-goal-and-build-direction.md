# Emergent Software
## From Agent Behavior to Verified, Scalable Code

**Status:** Concept / Build Direction  
**Purpose:** Give an AI engineer or software team enough context to understand the idea, connect the concepts, and start designing a working prototype.

---

# 1. The Goal

We want to explore a different way of building software.

Instead of defining every workflow, branch, and interaction in advance, we create:

- a **world**
- a set of **laws**
- a set of **agents**
- a shared **state**
- a common **interaction protocol**
- an **evidence model**
- a controlled way for agents to act

The agents interact inside that world.

From those interactions, useful behaviors may emerge.

When a behavior becomes:

- repeated,
- successful,
- safe,
- explainable,
- policy-compliant,
- and stable,

we do not want to keep paying the cost of reasoning about it forever.

We want to turn that stable behavior into deterministic software.

The core loop is:

```text
Experience
   ↓
Behavior
   ↓
Pattern
   ↓
Law / Invariant
   ↓
Verification
   ↓
Code
   ↓
Primitive
   ↓
Higher-Level Behavior
```

The simplest expression of the idea is:

> **Unknowns are reasoned about. Knowns are compiled.**

Agents explore what is not yet known.

Stable knowledge becomes software.

---

# 2. What We Want to Achieve

The long-term objective is to create a system that can move through the following lifecycle:

```text
Unknown Problem
      ↓
Agent Exploration
      ↓
Observed Interaction
      ↓
Emergent Behavior
      ↓
Behavior Mining
      ↓
Candidate Rule
      ↓
Verification
      ↓
Generated Deterministic Code
      ↓
Reusable Primitive
      ↓
Agents Operate at a Higher Level
```

The software should gradually become:

- more deterministic where the problem is already understood,
- more autonomous where uncertainty remains,
- cheaper to operate,
- easier to scale,
- easier to audit,
- easier to test,
- and easier to reason about.

The goal is **not** to make AI generate random production code.

The goal is to create a controlled system where:

> **experience can become behavior, behavior can become law, and law can become verified code.**

---

# 3. Why This Matters

Modern software often accumulates complexity like this:

```text
Requirement
   ↓
Workflow
   ↓
More Conditions
   ↓
More Exceptions
   ↓
More If/Else
   ↓
More Services
   ↓
More Coordination
   ↓
More Complexity
```

Agentic systems introduce another problem.

If every transaction or request requires multiple LLM agents to reason every time, the system may become:

- expensive,
- slow,
- non-deterministic,
- difficult to test,
- difficult to audit,
- difficult to scale.

We want a different model.

Use agents where reasoning is valuable.

Use deterministic software where reasoning is no longer necessary.

```text
Novel / uncertain situation
        ↓
      Agent

Known / stable situation
        ↓
  Compiled behavior
```

This allows intelligence to be used for discovery rather than wasting reasoning on things the system already knows.

---

# 4. The Market Analogy

A useful analogy is a market.

Imagine many participants:

- buyers,
- sellers,
- investors,
- suppliers,
- regulators,
- banks,
- logistics providers.

No single participant "is the market."

Each participant only has:

- local information,
- a goal,
- limited resources,
- constraints,
- a strategy.

For example:

```text
Buyer
Goal: obtain a product at an acceptable price

Seller
Goal: sell profitably

Supplier
Goal: maintain demand and inventory

Regulator
Goal: enforce boundaries

Bank
Goal: manage settlement and risk
```

Each actor behaves locally.

But from repeated interaction, global behavior appears:

- prices,
- competition,
- shortages,
- liquidity,
- trust,
- cooperation,
- bubbles,
- arbitrage,
- specialization.

These behaviors are not necessarily programmed directly into one central controller.

They **emerge from interaction**.

That is the key idea we want to bring into software.

---

# 5. From Market to Software

Replace market participants with software agents.

```text
Market                     Software

Buyer                      User Agent
Seller                     Service Agent
Bank                       Payment Agent
Regulator                  Policy Engine
Risk Analyst               Risk Agent
Evidence / receipts        Evidence Store
Market state               Shared State
Transactions               Actions
Market rules               Constitution
```

Instead of writing one giant workflow:

```text
Step 1
Step 2
Step 3
Step 4
...
```

we define what must be true.

For example:

```text
A payment may happen only if:

- identity is valid
- balance is sufficient
- risk policy is satisfied
- authorization is valid
- the action is traceable
```

The agents may discover the interaction sequence required to satisfy those conditions.

---

# 6. The World

The system needs a controlled runtime called the **World**.

The World is not a giant orchestrator.

Its purpose is to enforce the environment.

Conceptually:

```text
                         ┌──────────────────┐
                         │  CONSTITUTION    │
                         │ Laws / Policies  │
                         └────────┬─────────┘
                                  │
                                  ▼
Intent ─────► World ─────► Proposals ─────► Policy Gate
                │                              │
                │                              ▼
                │                         Evidence Check
                │                              │
                ▼                              ▼
              State ◄────── State Change ◄── Action
                │
                ▼
            Event Stream
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
      App      Risk    Payment
     Agent     Agent    Agent
```

The World controls:

- accepted message types,
- permissions,
- policy evaluation,
- state transitions,
- evidence requirements,
- action authorization,
- audit events,
- budgets,
- timeouts,
- retries,
- resource limits.

---

# 7. The Constitution

The system needs executable laws.

These laws must exist outside the agents.

An agent may suggest an action.

An agent must not be able to bypass the laws.

Example:

```yaml
law:
  id: PAYMENT-001

  when:
    action: TRANSFER

  require:
    - identity.verified == true
    - account.balance >= action.amount

  otherwise:
    state: BLOCKED

  evidence:
    - identity_verification
    - balance_confirmation
```

Another example:

```yaml
law:
  id: RESILIENCY-004

  when:
    action: EXTERNAL_API_CALL

  require:
    - timeout != null
    - timeout <= 5000
    - retry.max <= 3
```

The important idea is:

> The law is not documentation.  
> The law is executable.

---

# 8. Agents

Each agent can be described using a small model:

```text
Identity
Goal
Knowledge
Capabilities
Constraints
```

Example:

```ts
const RiskAgent = {
  id: "risk-agent",

  goal: "Reduce transaction risk",

  capabilities: [
    "ASSESS_RISK",
    "REQUEST_EVIDENCE"
  ],

  canObserve: [
    "transaction",
    "device",
    "risk_signals"
  ]
}
```

An agent may be implemented as:

- deterministic code,
- rules,
- an LLM,
- machine learning,
- a human,
- a remote service,
- another software system.

The World should not care how an agent thinks.

It should only care about:

- what the agent may observe,
- what the agent may propose,
- what evidence it provides,
- and whether the resulting action is legal.

---

# 9. Proposal, Not Direct Execution

Agents should not directly perform sensitive actions.

Bad model:

```text
Risk Agent
   ↓
Database
   ↓
Change data
```

Preferred model:

```text
Agent
  ↓
Proposal
  ↓
Policy Gate
  ↓
Evidence Check
  ↓
Authorized Action
  ↓
Executor
```

Example:

```json
{
  "agent": "payment-agent",
  "proposal": "TRANSFER",
  "amount": 5000,
  "from": "ACCOUNT-A",
  "to": "ACCOUNT-B"
}
```

The World may respond:

```json
{
  "allowed": false,
  "reason": "STRONG_AUTH_REQUIRED",
  "requiredEvidence": [
    "IDENTITY_VERIFIED",
    "STEP_UP_AUTH"
  ]
}
```

This separates:

> **reasoning** from **authority**.

---

# 10. Evidence as a First-Class Object

Agents should not simply make claims.

They should provide evidence.

Example:

```json
{
  "evidenceId": "EV-8392",
  "type": "IDENTITY_VERIFICATION",
  "producer": "identity-agent",
  "subject": "USER-123",
  "value": true,
  "source": "PingID",
  "timestamp": "2026-09-18T10:00:00Z",
  "expiresAt": "2026-09-18T10:10:00Z"
}
```

This makes the system:

- auditable,
- explainable,
- challengeable,
- testable,
- reversible where possible.

A decision should be reconstructable later.

---

# 11. Shared State

Agents should not each own a private version of reality.

The system needs an authoritative state.

Example:

```json
{
  "transactionId": "TX-1001",
  "state": "WAITING_FOR_AUTH",

  "facts": {
    "identityVerified": true,
    "balanceAvailable": true,
    "risk": "HIGH",
    "strongAuth": false
  }
}
```

Agents observe state.

Agents propose changes.

The World validates transitions.

---

# 12. Events

The system should be event-driven.

Example event types:

```text
TRANSACTION_REQUESTED
IDENTITY_VERIFIED
BALANCE_CONFIRMED
RISK_ASSESSED
STRONG_AUTH_REQUIRED
STRONG_AUTH_COMPLETED
PAYMENT_AUTHORIZED
PAYMENT_EXECUTED
```

But the key difference is:

> The full sequence should not necessarily be hard-coded as one workflow.

The sequence may emerge from:

```text
State
+
Events
+
Laws
+
Agent decisions
```

---

# 13. A Common Agent Protocol

Agents need a small shared language.

Possible message types:

```text
OBSERVE
PROPOSE
REQUEST_EVIDENCE
PROVIDE_EVIDENCE
CHALLENGE
ACCEPT
REJECT
ESCALATE
ACT
```

Example:

```json
{
  "type": "REQUEST_EVIDENCE",
  "from": "risk-agent",
  "to": "identity-agent",
  "subject": "TX-1001",
  "need": "DEVICE_TRUST"
}
```

This protocol should work whether the agent is:

- local,
- remote,
- AI-based,
- deterministic,
- human-operated.

---

# 14. Example: Money Transfer

Suppose a user asks:

```text
Transfer RM5,000 to Ali
```

The App Agent proposes:

```text
TRANSFER RM5,000
```

The World checks the Constitution.

It may require:

```text
identity verification
balance evidence
risk assessment
```

Identity Agent provides:

```text
IDENTITY_VERIFIED
```

Payment Agent provides:

```text
BALANCE_SUFFICIENT
```

Risk Agent provides:

```text
RISK = HIGH
```

A law is triggered:

```text
High Risk
   ↓
Strong Authentication Required
```

The transaction enters:

```text
WAITING_FOR_STRONG_AUTH
```

After authentication:

```text
STRONG_AUTH_COMPLETED
```

The World evaluates again.

All laws are satisfied.

The transfer is authorized.

What is important is that we did not necessarily write:

```text
Step 1 identity
Step 2 balance
Step 3 risk
Step 4 auth
Step 5 payment
```

We defined the laws.

The interaction produced the behavior.

---

# 15. From Behavior to Code

This is the most important extension.

Suppose agents run thousands of simulations.

A repeated successful pattern appears:

```text
risk = HIGH
     ↓
request device evidence
     ↓
request strong authentication
     ↓
reevaluate
     ↓
execute
```

We do not want agents to rediscover this forever.

We introduce a **Behavior Compiler**.

Its job is to move from:

```text
Observed Behavior
      ↓
Stable Pattern
      ↓
Candidate Rule
      ↓
Verification
      ↓
Deterministic Implementation
```

Example candidate rule:

```yaml
when:
  transaction.risk == HIGH

require:
  - device_trust
  - strong_auth

then:
  reevaluate_transaction
```

That rule may later compile into:

```ts
if (risk === "HIGH") {
  requireEvidence("DEVICE_TRUST");
  requireEvidence("STRONG_AUTH");
  return REEVALUATE;
}
```

The result:

> A behavior that originally required reasoning has become deterministic software.

---

# 16. The Behavior Compiler

The Behavior Compiler should analyze recorded interactions.

It should look for:

- repeated sequences,
- repeated preconditions,
- successful outcomes,
- failed outcomes,
- invariants,
- common evidence requirements,
- conflict patterns,
- latency,
- cost,
- rule violations,
- exception frequency.

Conceptually:

```text
Behavior Log
     ↓
Pattern Mining
     ↓
Invariant Discovery
     ↓
Candidate Specification
     ↓
Policy Validation
     ↓
Generated Tests
     ↓
Simulation
     ↓
Approval
     ↓
Generated Rule / State Machine / Code
```

The compiler should never promote a behavior merely because it is common.

A repeated behavior may still be wrong.

---

# 17. Safety Gate Before Compilation

Before behavior becomes production code, it should pass:

```text
Behavior
   ↓
Invariant Extraction
   ↓
Policy Validation
   ↓
Security Validation
   ↓
Generated Tests
   ↓
Regression Tests
   ↓
Simulation
   ↓
Canary
   ↓
Production
```

We should evaluate:

- Does this behavior violate the Constitution?
- Does it bypass authorization?
- Does it create unsafe shortcuts?
- Is the evidence sufficient?
- Are failure modes known?
- Is the behavior deterministic enough?
- What happens on partial failure?
- Can it be rolled back or compensated?
- Does it preserve observability?
- Is there any unresolved unknown?

---

# 18. Discovery World and Production World

The system can eventually have two major environments.

```text
          DISCOVERY WORLD

        Agent Simulation
             ↓
         Exploration
             ↓
        Negotiation
             ↓
      Behavior Discovery
             ↓
      Behavior Compiler
             ↓
        Verification


══════════════════════════════


          PRODUCTION WORLD

       Compiled Behavior
             ↓
       Rules / State Machines
             ↓
      Deterministic Runtime
             ↓
       High-Scale Execution
```

This is important because production does not need to run expensive reasoning when a behavior is already known.

---

# 19. Software Should Become Simpler Over Time

Traditional systems often become more complicated over time.

This model should attempt the opposite.

```text
Unknown
  ↓
Agent reasoning

Known
  ↓
Rule

Repeated
  ↓
Primitive

Stable
  ↓
Compiled code
```

When something becomes a primitive, agents no longer need to reason about its internal details.

For example:

Initially:

```text
Agent must reason about:
- identity provider
- token verification
- device trust
- auth expiry
```

Later these become:

```text
VERIFY_IDENTITY
```

Then agents operate at a higher level.

Eventually:

```text
TRANSFER_MONEY
OPEN_ACCOUNT
PAY_BILL
APPLY_LOAN
```

may become higher-order primitives.

The software develops a vocabulary from experience.

---

# 20. A Useful Mental Model

A biological analogy can help, without implying biological consciousness.

```text
DNA
=
Constitution / Laws

Nervous System
=
Events + Shared State + Agents

Memory
=
Evidence + Behavior History

Reflex
=
Compiled Stable Behavior

Learning
=
Agent Exploration + Behavior Mining
```

The important transformation is:

```text
Experience
   ↓
Adaptation
   ↓
Consolidation
```

A behavior that once required reasoning becomes a reflex.

---

# 21. Core Principles

The first version should follow these principles.

### 1. No agent owns absolute truth

Each agent has a limited view.

Important decisions must be based on evidence.

### 2. Possible does not mean permitted

An action must pass policy.

### 3. Every important decision must be explainable

We should be able to reconstruct:

- what was observed,
- what law was triggered,
- what evidence existed,
- who proposed the action,
- why it was accepted or rejected.

### 4. Agents cannot bypass the Constitution

Enforcement lives outside the agents.

### 5. State is authoritative

Agents observe state.

They do not independently redefine it.

### 6. Conflict is normal

The architecture must support:

- challenge,
- negotiation,
- escalation,
- arbitration.

### 7. Unknown is a valid state

The system should support:

```text
UNKNOWN
INSUFFICIENT_EVIDENCE
NEEDS_REVIEW
```

Not every situation should be forced into yes/no.

### 8. Resources are bounded

Every agent must have limits:

- timeout,
- retry,
- concurrency,
- token budget,
- action budget,
- rate limit.

### 9. Effects should be recoverable

Use:

- rollback,
- compensation,
- idempotency,
- replay safety.

### 10. Law is more important than agent implementation

Models, vendors, and agent implementations may change.

The Constitution should remain stable, versioned, testable, and auditable.

---

# 22. What AI Is and Is Not

This architecture does not require AI everywhere.

The first implementation can work without LLMs.

An agent may simply be:

```ts
function decide(context) {
  // deterministic decision logic
}
```

Later it may become:

```text
Rules Agent
ML Agent
LLM Agent
Human Agent
Remote Agent
```

This separation is important.

The idea is not:

> "Put AI everywhere."

The idea is:

> "Allow intelligent exploration where uncertainty exists, but compile stable knowledge into deterministic software."

---

# 23. Suggested MVP

Do not start with a large platform.

Build one complete learning loop.

Use one scenario:

> **Money Transfer**

Use three agents:

```text
User / App Agent
Risk Agent
Payment Agent
```

Use five laws:

```text
LAW-01
Identity is required.

LAW-02
Balance must be sufficient.

LAW-03
High risk requires strong authentication.

LAW-04
Every external call must have a timeout.

LAW-05
Every state transition must create audit evidence.
```

The first MVP should demonstrate:

```text
Intent
  ↓
Proposal
  ↓
Policy Evaluation
  ↓
Evidence Request
  ↓
Agent Interaction
  ↓
State Change
  ↓
Behavior Log
```

Then the second stage should demonstrate:

```text
Behavior Log
  ↓
Pattern Detection
  ↓
Candidate Rule
  ↓
Generated Tests
  ↓
Verification
  ↓
Compiled Rule
```

If this loop works once, the idea is alive.

---

# 24. Suggested Technical Shape

A practical first implementation could use:

```text
Language
- TypeScript

Runtime
- Node.js / NestJS

Database
- PostgreSQL

Core tables
- states
- events
- evidence
- proposals
- decisions
- laws
- behavior_runs
- behavior_patterns

Eventing
- In-process event bus first
- NATS / Kafka later

Policy
- Simple custom rules first
- OPA/Rego or Cedar can be evaluated later

Frontend
- React / Next.js

Agent SDK
- TypeScript
```

Do not over-engineer the first version.

The first purpose is to prove the behavioral loop.

---

# 25. Minimum Data Model

A simple model could include:

## Law

```text
law_id
version
trigger
conditions
required_evidence
allowed_actions
failure_state
```

## Proposal

```text
proposal_id
agent_id
action
payload
timestamp
```

## Evidence

```text
evidence_id
type
producer
subject
value
source
timestamp
expiry
```

## Decision

```text
decision_id
proposal_id
laws_evaluated
evidence_used
result
reason
timestamp
```

## State

```text
entity_id
state
facts
version
timestamp
```

## Event

```text
event_id
type
producer
subject
payload
timestamp
```

## Behavior Run

```text
run_id
scenario
initial_state
events
decisions
outcome
cost
latency
violations
```

---

# 26. What the Behavior Compiler Must Eventually Produce

The compiler may generate one of several artifacts.

### Rule

```yaml
when:
  risk: HIGH
require:
  - STRONG_AUTH
```

### State Machine

```text
REQUESTED
   ↓
RISK_ASSESSED
   ↓
WAITING_FOR_AUTH
   ↓
AUTHORIZED
   ↓
EXECUTED
```

### Function

```ts
authorizeHighRiskTransfer(...)
```

### Primitive

```text
VERIFY_IDENTITY
ASSESS_RISK
AUTHORIZE_PAYMENT
```

### Test

```text
Given:
  risk = HIGH

When:
  strong_auth is missing

Then:
  TRANSFER must not execute
```

The first compiler does not need to generate arbitrary application code.

Generating **rules + tests** is enough for the first proof.

---

# 27. Success Criteria for the First Prototype

The prototype is successful if we can demonstrate:

1. Agents interact without one hard-coded end-to-end workflow.
2. Laws constrain their actions.
3. Evidence is required for important claims.
4. State transitions are traceable.
5. Multiple simulations produce behavior history.
6. A repeated pattern can be detected.
7. The pattern can be represented as a candidate rule.
8. Tests can be generated from the candidate rule.
9. The rule can be verified against the Constitution.
10. The accepted rule can replace future agent reasoning for that same situation.

The key proof is:

```text
Reasoning
   ↓
Stable behavior
   ↓
Compiled behavior
```

---

# 28. Non-Goals

The first version should NOT attempt to:

- create artificial consciousness,
- build fully autonomous production systems,
- let LLMs directly mutate production databases,
- automatically deploy generated code without verification,
- discover every business rule,
- replace architecture governance,
- replace human accountability,
- build a general AGI framework.

Keep the experiment narrow.

---

# 29. Open Research Questions

These questions should remain explicit.

### Behavior stability

How many repetitions are enough before a behavior is considered stable?

### Context

How do we know two behaviors are really the same pattern if their context differs?

### Invariants

Can invariants be inferred automatically, or must they be human-approved?

### Negative evidence

How should failed and unsafe behavior influence compilation?

### Conflict

How do we handle different successful behaviors for the same goal?

### Versioning

What happens when a law changes after behavior has already been compiled?

### Decompilation

Can a compiled primitive return to agent exploration when the environment changes?

### Confidence

How do we measure confidence in a candidate behavior?

### Boundaries

Which behaviors should never be learned automatically?

These are not reasons to stop.

They are part of the architecture.

---

# 30. Important Design Insight: Compiled Behavior Can Return to Exploration

The lifecycle should not be one-way.

A stable behavior may become invalid later.

For example:

```text
Compiled Primitive
       ↓
Environment Changes
       ↓
Law Changes
       ↓
Failure / Drift Detected
       ↓
Primitive Suspended
       ↓
Return to Agent Exploration
```

So the full lifecycle may be:

```text
Explore
  ↓
Learn
  ↓
Compile
  ↓
Operate
  ↓
Observe
  ↓
Drift?
  ├── No  → Continue
  └── Yes → Explore Again
```

This makes the system adaptive without allowing uncontrolled self-modification.

---

# 31. A Possible Name

Working names:

```text
Emergent Software
Behavior-to-Code Architecture
Law-Driven Software
Emergent Software Compiler
Behavior Compiler
```

A useful distinction:

**Law-Driven Software**
describes how the world is constrained.

**Emergent Software**
describes how behavior appears.

**Behavior Compiler**
describes how stable behavior becomes deterministic software.

Together:

```text
Law-Driven World
      +
Agent Interaction
      +
Emergent Behavior
      +
Behavior Compiler
      =
Emergent Software
```

---

# 32. How an AI Engineer Should Read This Document

If you are an AI coding agent reading this document, do not immediately generate a large platform.

First understand these boundaries:

1. **The World is not a workflow orchestrator.**
2. **Agents propose; they do not directly authorize.**
3. **The Constitution lives outside the agents.**
4. **Evidence is first-class.**
5. **Shared state is authoritative.**
6. **Every important decision is reconstructable.**
7. **Unknown is an acceptable state.**
8. **Behavior history must be recorded.**
9. **Repeated behavior must not become code without verification.**
10. **The first compiler should generate simple rules and tests, not arbitrary software.**

Then build the smallest possible experiment.

---

# 33. Recommended Build Order for an AI Coding Agent

Build in this order:

```text
1. Core domain model
   - Law
   - Agent
   - Proposal
   - Evidence
   - State
   - Decision
   - Event

2. World Runtime
   - receive proposal
   - evaluate law
   - request evidence
   - authorize/reject
   - transition state
   - emit event

3. Three deterministic agents
   - App Agent
   - Risk Agent
   - Payment Agent

4. Five laws

5. Money-transfer simulation

6. Full behavior logging

7. Repeat simulation with varied inputs

8. Pattern detector

9. Candidate rule generator

10. Test generator

11. Rule verification

12. Replace one repeated reasoning path with compiled rule

13. Run comparison:
    agent reasoning vs compiled behavior
```

Measure:

```text
latency
cost
decision consistency
violations
success rate
number of reasoning steps avoided
```

---

# 34. The First Experiment

A very small simulation is enough.

Generate 1,000 transactions with combinations of:

```text
amount
risk level
device trust
identity state
balance
strong-auth state
```

Let the agents interact under the Constitution.

Record every run.

Then ask:

```text
Which interaction patterns repeatedly lead to valid success?
Which patterns repeatedly fail?
Which preconditions are invariant?
Can any sequence be replaced by a deterministic rule?
```

Example:

```text
Observed:
18,421 simulations

Pattern:
risk = HIGH
→ strong auth requested
→ transaction reevaluated
→ transfer allowed if auth succeeds

Policy violations:
0

Candidate:
Compile to deterministic rule
```

That is the first meaningful milestone.

---

# 35. Final Vision

The long-term vision is not software that endlessly reasons.

It is software that knows when it still needs to reason.

```text
Unknown
   ↓
Explore

Repeated
   ↓
Understand

Stable
   ↓
Formalize

Verified
   ↓
Compile

Reusable
   ↓
Primitive

New complexity
   ↓
Explore at a higher level
```

Over time, the system should move intelligence upward.

Lower-level solved problems become deterministic foundations.

Agents operate on increasingly higher abstractions.

The system does not simply grow.

It **learns what no longer needs to be thought about**.

---

# 36. One-Sentence Definition

> **Emergent Software is a law-driven architecture in which agents explore uncertain problems, stable behaviors are discovered from interaction, and verified behaviors are compiled into deterministic, scalable software.**

---

# 37. Core Formula

```text
Experience
   ↓
Behavior
   ↓
Pattern
   ↓
Law
   ↓
Verified Code
   ↓
Primitive
   ↓
Higher-Level Experience
```

That is the idea to build.
