# Example 04 — ROSE / OeRacle as Law-Driven Engineering Review

This example applies the same architecture to engineering governance.

Instead of reviewing software using a static checklist only, define **engineering laws**.

Then let review agents collect evidence from repositories.

Stable review behavior can later compile into deterministic analyzers.

---

# Traditional Governance

A typical review may ask:

```text
Does every external call have timeout?
Is retry bounded?
Is circuit breaker used?
Is rate limiting present?
Is caching safe?
Is access control enforced?
Is traceability present?
Are dashboards available?
```

Often these checks exist as:

```text
documents
review forms
human memory
checklists
```

The problem is that these are not always executable.

---

# Law-Driven Governance

Turn engineering expectations into laws.

Example:

```yaml
law:
  id: OE-RESILIENCY-001

  applies_to:
    - EXTERNAL_HTTP_CALL

  require:
    - timeout.configured == true
    - retry.bounded == true
```

Another:

```yaml
law:
  id: OE-TRACE-001

  applies_to:
    - CRITICAL_FLOW

  require:
    - trace_id.propagated == true
    - logs.correlated == true
```

Another:

```yaml
law:
  id: OE-ACCESS-001

  applies_to:
    - PROTECTED_RESOURCE

  require:
    - authorization.enforced == true
```

---

# Review Agent Model

A repository review agent does not simply say:

```text
PASS
FAIL
```

It must produce evidence.

Example:

```json
{
  "law": "OE-RESILIENCY-001",
  "subject": "PaymentClient.transfer()",
  "finding": "TIMEOUT_PRESENT",
  "evidence": {
    "file": "src/payment/PaymentClient.ts",
    "line": 82,
    "value": "timeout: 3000"
  }
}
```

For missing evidence:

```json
{
  "law": "OE-RESILIENCY-001",
  "subject": "PaymentClient.transfer()",
  "finding": "UNKNOWN",
  "reason": "No static timeout configuration found"
}
```

This is important:

```text
UNKNOWN != FAIL
```

The system must distinguish:

```text
PASS
FAIL
UNKNOWN
NOT_APPLICABLE
INSUFFICIENT_EVIDENCE
```

---

# Multiple Review Agents

Different agents can inspect different concerns:

```text
Resiliency Agent
Security Agent
Traceability Agent
Caching Agent
Access Control Agent
Frontend Quality Agent
API Contract Agent
```

Each returns evidence.

The World / Review Runtime evaluates engineering laws.

---

# Example: External API Call

Code:

```ts
await http.post(url, payload);
```

Resiliency Agent observes:

```text
External HTTP call detected.
No timeout found locally.
No wrapper evidence found.
```

It should not immediately declare:

```text
FAIL
```

It may request more evidence:

```json
{
  "type": "REQUEST_EVIDENCE",
  "need": "HTTP_CLIENT_GLOBAL_TIMEOUT"
}
```

Another agent or repository knowledge source may provide:

```text
All calls use shared client with timeout=3000ms.
```

Now the law can pass.

This prevents shallow review behavior.

---

# Repository Knowledge as Shared State

The system may maintain facts such as:

```text
service = payment-api
framework = NestJS
http-client = shared-http
global-timeout = 3000ms
retry-policy = bounded-2
trace-library = OpenTelemetry
feature-flag = GrowthBook
logging = ELK
```

Review agents should reason against repository-level knowledge, not isolated files only.

---

# From Agent Review to Deterministic Rule

At first, an agent may inspect code semantically.

Example behavior:

```text
detect external call
↓
search local config
↓
search shared wrapper
↓
search environment config
↓
search framework defaults
↓
classify PASS / FAIL / UNKNOWN
```

If this review sequence becomes stable, it can be compiled into a deterministic analyzer.

For example:

```text
CHECK_EXTERNAL_CALL_TIMEOUT
```

Implementation may become:

```text
AST scan
+
dependency resolution
+
config resolution
+
policy check
```

The AI agent no longer needs to reason through this every time.

---

# Behavior Compilation for Engineering Review

```text
Agent review behavior
       ↓
Repeated search pattern
       ↓
Stable evidence strategy
       ↓
Analyzer specification
       ↓
AST / static rule
       ↓
Deterministic OE check
```

Example:

```text
Before:
LLM searches repository to determine timeout coverage.

After:
AST analyzer detects all external clients and resolves timeout policy.

LLM is used only for unresolved cases.
```

This is a powerful use of:

```text
Unknowns are reasoned about.
Knowns are compiled.
```

---

# Example: Error Handling Review

A review agent may repeatedly discover:

```text
external call
+
no try/catch
+
no result-type
+
no error middleware coverage
=
unhandled failure path
```

After enough verification, this may become:

```text
ERROR-HANDLING-EXTERNAL-CALL-001
```

and compile into a static analysis rule.

The agent then focuses only on ambiguous cases.

---

# Example: API Integration Quality

For frontend → API integration, laws could include:

```text
API call has timeout
Loading state exists
Error state exists
Retry behavior is bounded
Authentication failure is handled
Correlation ID is propagated
Feature flag path is observable
No sensitive data stored in local storage
```

At first AI may review implementation behaviorally.

Later stable checks become deterministic lint/static rules.

---

# Why This Matters

The review system itself improves over time.

Initially:

```text
Human checklist
+
AI reasoning
```

Later:

```text
Deterministic checks
+
AI only for uncertainty
+
Human only for judgment / policy decisions
```

The cost of review should go down as the system learns what can be formalized.

---

# Suggested ROSE/OeRacle Experiment

Choose one engineering law:

```text
Every external API call must have a bounded timeout.
```

Then:

1. Let AI inspect 20 repositories.
2. Record every reasoning step used to determine timeout coverage.
3. Classify repeated search behavior.
4. Extract the stable algorithm.
5. Build deterministic scanner.
6. Compare AI result vs scanner result.
7. Route disagreements to AI.
8. Continue until deterministic coverage is high.

This creates a self-improving governance tool without allowing uncontrolled code generation.

---

# What an AI Builder Should Understand

ROSE/OeRacle can be viewed as a special case of Emergent Software:

```text
Repository
   ↓
Agents observe
   ↓
Engineering laws
   ↓
Evidence
   ↓
Review behavior
   ↓
Repeated patterns
   ↓
Compiled analyzers
```

The long-term objective is not "AI reviews everything forever."

It is:

> use AI to discover how to review what is not yet formalized, then turn stable review knowledge into deterministic engineering controls.
