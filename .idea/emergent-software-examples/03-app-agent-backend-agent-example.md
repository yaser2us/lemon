# Example 03 — App Agent ↔ Backend Agent

This example comes from the idea that the app should have **one place to talk**, and backend capabilities should also be represented through an agent-like interface.

The concept:

```text
App Agent
   ↕
Backend Agent
```

This can later expand into:

```text
User
 ↓
App Agent
 ↓
Backend Agent
 ├── Payment Capability
 ├── Identity Capability
 ├── Profile Capability
 ├── Notification Capability
 └── Risk Capability
```

---

# Traditional Model

A frontend often needs to know:

```text
POST /api/payment/transfer
GET  /api/accounts
POST /api/risk/check
POST /api/auth/step-up
GET  /api/profile
```

The app becomes tightly coupled to:

```text
endpoint names
request shapes
sequence
backend topology
service ownership
```

The app effectively becomes an orchestrator.

---

# Agent Interaction Model

Instead the App Agent expresses intent:

```json
{
  "type": "PROPOSE",
  "goal": "TRANSFER_MONEY",
  "context": {
    "amount": 5000,
    "recipient": "Ali"
  }
}
```

The Backend Agent interprets available capabilities.

It may answer:

```json
{
  "type": "REQUEST_EVIDENCE",
  "need": "IDENTITY_VERIFIED"
}
```

The App Agent can respond using user/device context.

Then the backend may ask:

```json
{
  "type": "REQUEST_EVIDENCE",
  "need": "STRONG_AUTH"
}
```

The frontend renders the required user experience.

---

# Important Separation

The app should not need to know:

```text
Risk Service
Payment Service
Fraud Service
Identity Service
```

It only needs to understand a shared protocol.

For example:

```text
PROPOSE
REQUEST_EVIDENCE
PROVIDE_EVIDENCE
CHALLENGE
ACCEPT
REJECT
ESCALATE
COMPLETE
```

---

# Example Interaction

```text
User:
Transfer RM5,000 to Ali

App Agent:
PROPOSE TRANSFER_MONEY

Backend Agent:
REQUEST_EVIDENCE IDENTITY

App Agent:
PROVIDE_EVIDENCE IDENTITY_VERIFIED

Backend Agent:
REQUEST_EVIDENCE STRONG_AUTH

App Agent:
SHOW_AUTH_CHALLENGE

User:
Completes authentication

App Agent:
PROVIDE_EVIDENCE STRONG_AUTH_COMPLETED

Backend Agent:
ACCEPT

Payment Capability:
EXECUTE

Backend Agent:
COMPLETE
```

---

# Why This Is Different From "One Big API"

The idea is not simply to wrap all APIs behind one endpoint.

Bad interpretation:

```text
POST /doEverything
```

That only hides complexity.

The better model is:

```text
shared protocol
+
capability discovery
+
laws
+
state
+
evidence
```

The backend should not become one giant monolith.

---

# Agent Protocol Message Shape

A simple envelope could look like:

```json
{
  "messageId": "MSG-123",
  "conversationId": "CONV-99",
  "type": "REQUEST_EVIDENCE",
  "from": "backend-agent",
  "to": "app-agent",
  "subject": "TX-1001",
  "payload": {
    "need": "STRONG_AUTH"
  },
  "timestamp": "..."
}
```

---

# Capability Discovery

The Backend Agent may expose capabilities:

```json
{
  "capabilities": [
    "TRANSFER_MONEY",
    "PAY_BILL",
    "VERIFY_IDENTITY",
    "GET_ACCOUNT_SUMMARY"
  ]
}
```

The App Agent does not need to know the implementation behind them.

---

# This Can Work Without AI

The App Agent may initially be:

```ts
switch (message.type) {
  case "REQUEST_EVIDENCE":
    return handleEvidenceRequest(message);
}
```

The Backend Agent may initially be:

```ts
function handleProposal(proposal, state, laws) {
  return evaluate(proposal, state, laws);
}
```

No LLM is required.

Later, AI can help with:

```text
natural-language intent
unexpected situations
tool selection
negotiation
explanation
```

But protocol correctness should remain deterministic.

---

# Emergent Behavior in App ↔ Backend

Suppose the agents discover that certain user journeys repeatedly follow:

```text
unknown device
+
high amount
→
device verification
→
strong auth
→
payment
```

That behavior may later become a compiled UI/backend primitive:

```text
HIGH_RISK_TRANSFER_FLOW
```

Then the app no longer needs to negotiate every step.

It receives:

```json
{
  "primitive": "HIGH_RISK_TRANSFER_FLOW",
  "requiredInputs": [
    "device_verification",
    "strong_auth"
  ]
}
```

This is another example of:

```text
interaction
→
stable behavior
→
primitive
```

---

# Possible Long-Term Model

```text
                    Shared Protocol

App Agent  ◄────────────────────────► Backend Agent
   │                                      │
   │                                      ├── Identity Agent
   │                                      ├── Risk Agent
   │                                      ├── Payment Agent
   │                                      └── Compliance Agent
   │
   └── UI Capabilities
       ├── Show Form
       ├── Ask User
       ├── Device Check
       ├── Strong Auth
       └── Display Result
```

The user interface itself becomes a participant in the software world.

---

# What an AI Builder Should Build

Start with one conversation:

```text
TRANSFER_MONEY
```

Build:

1. App Agent
2. Backend Agent
3. shared message envelope
4. conversation state
5. law evaluation
6. evidence request/response
7. UI action messages
8. audit trail
9. one compiled primitive

Avoid building:

```text
general AI chat
huge MCP mesh
dozens of services
dynamic LLM planning
```

until the protocol works deterministically.
