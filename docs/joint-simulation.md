# Joint rehearsals

```sh
# Deterministic demonstration: premature report fails, revised rehearsal passes
python3 -m lemon act --joint --fresh --fault processing

# Both live and branch decisions use Anthropic (paid calls)
python3 -m lemon act --joint --agent anthropic --fresh --fault processing --max-api-requests 32

# Revalidate and execute a saved pair on another fault
python3 -m lemon act --joint --fault request-lost
```

`--joint` implies `--team`. Its traces and memory default to `runs/actor-joint/`.
The earlier team mode remains available for comparison with scripted trial peers.

App and Payment first exchange observations in the live World. Either can then
request a joint rehearsal, naming a supported hypothesis and explaining the
uncertainty it wants to test. Both actual controllers take alternating turns in
an isolated World. In Anthropic mode each branch turn is a separate model call
with that role's observations, inbox, own actions, and previous experiment
results. Neither sees the other's private state. There is no scripted peer and
no nested rehearsal.

A branch starts from the original confirmed transfer fixture under the requested
`processing`, `request-lost`, or `response-lost` hypothesis. Live messages are
copied into it as context. It is a counterfactual experiment, not a clone of the
current live ledger or evidence of which live fault occurred. Branch steps and
messages never change the live World.

The branch stops on completion, a law rejection, an error, or its turn limit.
Results return to both live actors: observed failure, check results, each role's
recorded actions, and the branch event-chain hash. Actors can request a revised
rehearsal. The local demonstration deliberately tries an early report first;
its authored policy then waits for Payment's receipt. Anthropic decides its own
actions, so a failure-and-revision sequence is not guaranteed.

When a branch succeeds, the World executes its two recorded sequences together
in twenty additional deterministic cases: all five faults, two processing
delays, and both actor orders. It substitutes neither role with a baseline
peer. These checks test the recorded sequences, not further model reasoning.

Both actors must adopt the latest passing result ID before those sequences run
in the live World. Live controller actions before adoption are limited to
communication, waiting, rehearsal requests, and adoption. A chat claim cannot
publish a receipt or bypass verification. Successful live execution saves the
pair together; loading memory revalidates the pair before deterministic reuse.
Memory from single-actor or earlier team mode is rejected.

The viewer labels rehearsal steps and outcomes separately from live execution.
Saved runs can be inspected offline with `python3 -m lemon chat <trace.json>`
and verified with `python3 -m lemon replay <trace.json>`. Both commands verify
the root event chain, nested branch chains, and their links to recorded results.

Bounds: 24 live decision turns, at most three rehearsals, 16 alternating turns
per rehearsal, and at most eight actions per role in a saved sequence. Live
and branch calls share one HTTP budget. An invalid provider response gets one
retry within that budget; provider errors save the partial trace and stop.
`--fresh` ignores old memory and replaces it only after successful new learning.

This is a bounded actor-play experiment. Roles, capabilities, hypotheses,
scheduling, and bank rules remain authored. Replayable action sequences are an
early reusable procedure, not a learned conditional program or general software
compiler. A passing finite test set is not proof for arbitrary faults or peers.
All banking behavior is fictional; no real payments occur.

## Validation observed on 2026-09-18

The full suite passed 123 tests. The local demonstration rejected a premature
report, completed a revised joint rehearsal, passed all twenty paired cases,
obtained adoption from both actors, and executed successfully. Tests cover
uncooperative actual peers, role boundaries, malformed-action correction,
branch isolation, nested evidence tampering, adoption gating, and pair reuse
across all five faults.

Live Anthropic actors did enact a branch together and complete that hypothetical
transfer. Its recorded procedure failed the additional cases, however. The
actors attempted adoption and were correctly refused; subsequent rehearsals
exhausted the shared 32-request budget. No new procedure was saved and no live
transfer effect occurred. Evidence:
`runs/joint-corrected/actor-processing-94c818f1.json`.

That run motivated more concise feedback separating branch success from paired
validation. The feedback change passed the joint tests; it has not yet been
verified in another live Anthropic run. Reliable model-driven discovery and
revision remain unproven. The implementation exposes those failures rather
than treating actor agreement as success.
