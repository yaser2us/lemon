# Two actors coordinating through experience

```sh
# Offline, authored candidate plans
python3 -m lemon act --team --fresh --fault processing

# Both actors use Anthropic, with one shared HTTP budget
python3 -m lemon act --team --agent anthropic --fresh --fault processing --max-api-requests 16

# Revalidate and reuse saved procedures under another fault
python3 -m lemon act --team --agent anthropic --fault request-lost
```

The starting fixture submits one preconfirmed fictional RM100 transfer. With
`processing`, App observes UNKNOWN while Payment observes PROCESSING. After
this scripted setup, each role has an independent controller. Anthropic calls
use separate role prompts and observation objects, sharing only transport and
its request budget. Neither sees the inspector log or the other's private state.

App can ask Payment to resolve the attempt, wait, and report a delivered receipt.
Payment can discuss its observation, recover the original attempt, advance
processing, inspect the bank's status, and publish a checked receipt. Delivered
messages enter only the recipient's inbox. Each subsequent model decision sees
that inbox and that role's experiment results. Public explanations cannot
authorize a transfer or establish success. A stale observation cannot become a
receipt; Payment must inspect again after processing completes.

Each actor can request two to four candidate sequences of its own actions.
These execute in isolated Worlds starting at the original scenario fixture,
under completed-but-response-lost, missing-request, and processing hypotheses.
They are robustness tests, not a reconstruction of the current live state.

Trial peers are explicitly scripted: Payment recovers, waits, inspects, and
publishes; App asks, waits four turns, and reports. A local success therefore
depends on this peer and timing assumption. Fourteen additional cases vary
processing delay, turn order, normal completion, and insufficient funds.
These finite tests do not prove coordination with arbitrary peers.

A passing procedure can be retained by its owner. Its actions execute one per
turn, alternating App and Payment. The other live role may still be reasoning
or testing. The scheduler does not replace that peer with the scripted trial
peer. Different live timing can therefore fail even when a local trial passed.
Only actual joint success permits newly learned procedures to be written to
memory. Both stored procedures are independently revalidated before reuse.

Team memory defaults to `runs/actor-team/strategy.json`, separate from the
single-actor model. Role and model checks prevent cross-role or cross-model
reuse. If both procedures exist, a successful reuse can make zero model calls;
it is deterministic procedure execution rather than new reasoning.

Traces include private-observation snapshots for inspection, actor messages,
branch results, nested replayable branch events, validation failures, and final
ledger checks. `python3 -m lemon chat <trace.json>` displays a saved run offline;
`python3 -m lemon replay <trace.json>` verifies the main event chain and state.
The inspector can see more than either actor. Do not mistake its output for an
actor's prompt.

Limits are 40 alternating scheduler turns, three experiment batches per actor,
and eight steps per plan. The default HTTP budget remains eight; the live
example grants sixteen shared attempts to allow unsuccessful candidates and
revisions. Provider failures save a partial trace. A failed fresh run leaves
existing memory intact.

This is a bounded experiment in communication, executable consequences, and
role-local reuse. Roles, capabilities, turn scheduling, trial peers, and World
laws are authored. It does not yet learn peer behavior, compile general
software, or support arbitrary executable domains. All bank behavior is
fictional; there are no real payment connections.

## Observed live result

On 2026-09-18, both Anthropic roles exchanged observations, each ran a candidate
experiment and retained a procedure, and the processing scenario completed with
one transfer effect and all final checks passing. The run used six HTTP requests.
App's later decisions received Payment's message, and Payment's decisions
received App's request. Each role's plan passed fourteen additional cases.

A second run reused both procedures with a lost initial request, passed all
checks, and made zero HTTP requests. Evidence is saved locally in:

- `runs/team-verified/actor-processing-3f40a58a.json`
- `runs/team-verified/strategy.json`
- `runs/team-verified-reuse/` (the reuse trace)

Earlier live runs exhausted their HTTP budget or failed after invalid provider
output. Some candidate plans missed the scripted peer's reporting deadline.
These failures are preserved under `runs/team-live/` and `runs/team-learning/`.
The successful pair demonstrates this mechanism, not reliable discovery for
arbitrary peers. Automated coverage also checks private observations, role
boundaries, stale receipts, misleading prose, branch replay, failed live peers,
memory scope, and reuse across all five faults.
