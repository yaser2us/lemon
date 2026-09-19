# Emergent Software — Build Plan

**Delivery update:** Lemonade now implements the transfer demo. Lemon's `exercise`
command operates its actual API. A guided Anthropic input-boundary probe exposed
invalid array input being accepted as a transfer; a failing regression test,
implementation fix, and fresh HTTP replay verified the correction. This is an
actor-to-software feedback loop with a human-written fix, not automatic code
generation. [Evidence and scope](../docs/software-exercise.md).

**Date:** 2026-09-18  
**Status:** Foundation, two-actor learning, and joint rehearsals implemented; general extraction and compilation pending
**Related:** [Goal and build direction](emergent-software-goal-and-build-direction.md) · [Examples](emergent-software-examples/00-examples-index.md)

## Objective

Build one complete loop: agents solve a task, we record their behavior, the system extracts a reusable procedure, and verification determines whether it can replace future agent decisions.

Lemon now has an executable transfer World, evidence checks, replayable logs,
scenario tests, and a CLI conversation viewer. Software discussion experiments
also exist, but discussion alone does not fulfill this goal.

The next direction is actors learning through enacted scenarios, without a
dedicated reviewer in the core loop. The first slice is `python3 -m lemon act`:
an App actor submits actions, tests recovery plans in isolated hypothetical
Worlds, and retains a plan only after executable checks. Later runs revalidate
and reuse that procedure. Anthropic can propose the plans; the other actors
and scenario rules are scripted. See [implementation scope](../docs/actor-simulation.md).

The `--team` experiment now adds independently controlled App and Payment actors
with private observations, messages, role-specific capabilities, branch trials,
and separate retained procedures. Live Anthropic decisions are interleaved by a
bounded scheduler. Trial peers remain scripted, and a locally passing procedure
is saved only if the live pair also succeeds. See [two-actor scope](../docs/team-simulation.md).

This bridges reasoning and execution for one bounded problem. General pattern
extraction, learned peer models, and compilation into reusable software remain
future work. The stages below describe the broader intended system.

The next slice, `--joint`, now lets either role request a rehearsal in which
both actual controllers choose their own actions. Failure evidence returns to
both actors for revision. The World tests the recorded pair together across
additional cases; both roles must adopt a passing result before live recovery.
This replaces scripted peers inside joint rehearsals while retaining authored
World rules and scheduling. See [joint rehearsal scope](../docs/joint-simulation.md).

## 1. Build the foundation we control

Implement the World runtime, with:

- A shared message format for proposals and evidence requests.
- Authoritative transaction state.
- Executable laws and evidence validation.
- An executor for authorized actions.
- An event log that explains every decision.

**Milestone:** An attempted transfer with missing or invalid evidence is blocked, and we can reconstruct why.

## 2. Give agents capabilities and let them interact

Start with deterministic App, Risk, and Payment agents. Identity and authentication can use simulated providers.

Each agent responds to what it observes. For example, the Payment Agent supplies balance evidence; the Risk Agent assesses risk; the App Agent handles requests for user authentication.

Define their available actions and local decision rules. Allow the overall sequence to vary with the situation.

**Milestone:** The same laws produce different valid interaction paths, while invalid transfers remain blocked.

## 3. Generate experience that includes failures

Run repeatable simulations varying amounts, balances, identity status, device trust, authentication results, service delays, and event ordering.

Record:

```text
Starting conditions
→ proposals and evidence
→ decisions and state changes
→ outcome, cost, and latency
```

Include expired evidence, duplicate messages, timeouts, and conflicting proposals. Successful runs alone would give us an incomplete picture.

**Milestone:** A dataset we can replay and inspect.

## 4. Build a small behavior compiler

This is the central experiment. Initially, it should:

1. Group comparable situations.
2. Find repeated successful action sequences.
3. Compare them with failures.
4. Propose the conditions under which a sequence applies.
5. Produce a candidate rule or state machine, plus tests.

For example, it might identify a reusable procedure for collecting independent evidence concurrently, then requesting authentication when required.

**The compiler learns a procedure for satisfying laws. It does not silently rewrite the laws.**

Its first output should be readable and reviewable:

```text
Applies when: …
Required evidence: …
Actions: …
Failure handling: …
Return to agents when: …
Supporting runs: …
```

## 5. Prove the candidate is useful

Keep some scenarios out of the discovery dataset. Test the candidate on those unseen scenarios and deliberately constructed failure cases.

Check both the original agent path and compiled path against independently written policy tests. Agreement between them is useful, but both could share a mistake.

**Milestone:**

- No policy violations in the defined test scope.
- Correct handling of failures and unsupported cases.
- Fewer agent decisions for matching tasks.
- Measured performance benefits, if any.

Passing this establishes confidence within the tested scope; it does not prove universal correctness.

## 6. Make the compiled procedure a reusable capability

Register the accepted procedure so future agents can invoke it. All actions still go through the World's checks.

Each procedure records its supported conditions and policy dependencies. Unsupported situations return to agents. Policy changes suspend affected procedures until they are revalidated.

This completes the first learning loop.

## 7. Extend the proven loop to the other examples

| Next application | What we would demonstrate |
|---|---|
| App ↔ backend | A repeated conversation becomes a reusable UI/backend flow |
| ROSE / OeRacle | A repeated evidence-gathering strategy becomes a static analyzer |
| AI agents | One agent handles uncertainty using AI, while the same runtime enforces the rules |
| Higher-level capabilities | Agents compose previously verified procedures into new solutions |

## First convincing demonstration

Show a before-and-after:

1. Agents initially need several decisions to complete a scenario.
2. Lemon derives and verifies a procedure from recorded runs.
3. Fresh matching scenarios use that procedure with fewer decisions.
4. Unfamiliar cases still return to agents.

That would establish the mechanism behind the vision. Useful discovery across broader problems would be the next thing to prove.
