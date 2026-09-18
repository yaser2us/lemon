# Learning through enacted scenarios

The `act` command is the first bridge from agent decisions to World actions and
retained behavior. There is no reviewer agent in this mode. The World enforces
laws and checks results mechanically.

```sh
python3 -m lemon act --fresh
python3 -m lemon act --agent anthropic --fresh
python3 -m lemon act --agent anthropic --fault request-lost
python3 -m lemon act --fault processing
```

The default agent is a local demonstration with three authored candidates.
`--agent anthropic` uses `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` from
`.env.local`, making paid calls. The App sees its own observations and trial
results, not hidden bank state or the live fault. The Customer, Maybank,
DuitNow, and CIMB are deterministic participants in the World, not separate
reasoning models. The inspector's terminal view is broader than the App's view.

## The experiment

1. The scripted Customer confirms a fictional RM100 transfer to someone else.
   Recipient details and authorization are preconfirmed fixtures.
2. The App submits an attempt. A timeout gives it the same UNKNOWN observation
   whether the request was lost, completed without a reply, or is processing.
3. The App can propose two to four action sequences. The World executes each in
   all three hypothetical branches, isolated from the live ledger.
4. Branch results expose concrete outcomes, law rejections, and failed checks.
   They do not reveal which fault occurred in the live World.
5. The App can retain a passing candidate. Eleven additional cases test delivery
   delays, insufficient funds, and normal completion. Failed validation returns
   feedback so the App can revise within the experiment budget.
6. The retained procedure executes in the live simulation. Successful runs save
   it; subsequent runs revalidate it against the same model and execute it when
   UNKNOWN occurs, avoiding further model decisions for recovery.

The offline example tests a new attempt, querying alone, and resending the
original attempt followed by waiting, querying, and reporting. The first two
fail in some branches; the last passes within this model. Anthropic chooses its
own candidate plans, so outputs and API costs can vary. The prompt asks it to
experiment; successful transfer execution alone does not establish learning.

## Evidence and bounds

Quality checks cover at most one transfer effect, conserved money, no overdraft,
the expected final credit, a truthful terminal report, no rejected actions, and
event replay. Branch execution uses the same simulator implementation; these
checks are not external validation of its banking assumptions.

Runs save JSON traces under `runs/actors/`, including branch event logs. The
default memory file is `runs/actors/strategy.json`. Use `--output` and `--memory`
to separate experiments. `--fresh` ignores existing memory and replaces it only
when a new strategy is learned successfully. It does not delete old memory if
the new run fails or learns nothing.

```sh
python3 -m lemon chat runs/actors/actor-response-lost-<id>.json
python3 -m lemon replay runs/actors/actor-response-lost-<id>.json
```

Replay commands are offline. The chat replay displays branch summaries; full
nested branch traces remain in JSON. Each branch has its own event chain.

The runtime bounds decisions to 20, experiment batches to three, candidates to
four per batch, and plans to six steps. Anthropic defaults to eight HTTP
attempts. Available faults are `response-lost`, `request-lost`, `processing`,
`normal`, and `insufficient-funds`.

This World assumes stable attempt identities, retained receipts, correlation
of attempts to an intent, bounded processing time, and atomic ledger updates.
These are declared fictional capabilities, not claims about the named banks.
Only the initial response/request is lost; ongoing network failures are outside
this model. Finite passing trials establish success only within the tested model.

The saved strategy is a bounded action sequence scoped to a model version. It
is an early reusable procedure, not general software generation or a behavior
compiler. Arbitrary scenarios still use discussion mode; executable actor
scenarios currently cover only this transfer problem.

## Observed validation, 2026-09-18

The full suite passed 102 tests. A live Anthropic run tested two batches of
candidates, retained `send_original → wait → check_status → report`, passed
11 additional validation cases, and completed with one transfer effect. It
used six HTTP requests. A second live run with `request-lost` reused the saved
procedure, passed all final checks, and used one HTTP request.

Local evidence files (ignored by git):

- `runs/actor-capabilities/actor-response-lost-e40d8cac.json`
- `runs/actor-capabilities/strategy.json`
- `runs/actor-capabilities-reuse/actor-request-lost-b2a575c7.json`

Earlier live attempts skipped learning or exhausted their budgets on failed
plans. These results motivated clearer capability descriptions and actionable
validation feedback. One successful pair of runs demonstrates the mechanism;
it does not establish reliable discovery across models or arbitrary scenarios.
