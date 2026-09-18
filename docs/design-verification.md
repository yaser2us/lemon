# Design verification and repair

The World runs a pure verifier after all four roles approve the current draft.
It records `DESIGN_VERIFIED`, including the contract revision, repair round,
result and specific failures. Agreement is impossible until this check passes.
The final independent evaluator reruns the verifier against the saved state.

Failures identify an owner, stable code and concrete diagnostic. World removes
the affected approvals and sends each owner `VERIFICATION_FEEDBACK` with its
failures and rejected artifact. Unaffected approvals remain valid unless Backend
changes the contract, which advances the revision and clears all approvals.
Every replacement artifact remains attributable to an actual agent message.

Three repair rounds are allowed across all revisions. A fourth failed check
ends in `needs_review` with outstanding diagnostics. A silent repair agent also
ends in `needs_review`. Existing message, model-review and HTTP-request limits
still apply; transport failures and invalid protocol envelopes stop or reject
the response rather than pretending that repair succeeded.

## Bounded model

The transfer graph allows REQUESTED to move to WAITING_FOR_AUTH, AUTHORIZED or
REJECTED. WAITING_FOR_AUTH can move to AUTHORIZED or REJECTED. AUTHORIZED moves
to EXECUTING; EXECUTING ends at COMPLETED or FAILED. Terminal states have no
outgoing transitions. This allows authentication to be skipped when unnecessary.

Each planned test has an `assertion` with `initial_state`, `event`,
`expected_state`, `success` and `same_transaction`. The supported events are:

| Event | Precondition | Outcome |
|---|---|---|
| submit_valid | NONE, valid input as defined by this event | REQUESTED |
| reject_input | NONE, invalid input as defined by this event | REJECTED |
| render | Any declared state | Same state |
| retry | An existing transaction in any declared state | Same transaction and state |
| execute_success | EXECUTING | COMPLETED |
| execute_failure | EXECUTING | FAILED |

Success is true only for COMPLETED; same_transaction is true for retry.
Required cases cover invalid input, authentication display, pending display for
both AUTHORIZED and EXECUTING, retry of a REQUESTED transaction, and both
execution outcomes. Input cases belong to R1, retries to R3, and display or
execution outcomes can cover R2 or R4. Requirement IDs must match these behaviors. Malformed
assertions, duplicate case IDs, missing coverage and contradictory outcomes fail.

These are model checks, not evidence of actual storage, UI rendering, atomic
payments or application test execution. `reject_input` abstracts an invalid
request; it does not execute an input parser. UI label checks are limited string
and state-coverage checks. Prose is explanatory and can still need human review;
structured assertions define the machine-checked test meaning.

## Anthropic and replay

The Test Agent receives structured assertion instructions. Repair observations
include feedback and the rejected artifact, so they have a different cache key
from the original review. The model must submit a new action; there is no
deterministic fallback. Automated tests use offline provider fixtures.

New runs use protocol `software-design-v2` and specification schema 2. Existing
saved conversations remain replayable without API calls; old runs are not
retroactively claimed to have passed these new checks. Reports and CLI chat show
verification failures, feedback messages and later passes.

Try `python3 -m lemon chat --variant repair-demo`. Completed runs save under
`runs/chat/`, including the full audit log and final verification result.

## Validation recorded during implementation

All 53 automated tests passed, including thirty scheduler seeds per design
variant, contract-owner repair, corrected provider responses through an offline
fixture, repeated-failure limits, and replay integrity.

The [local repair demo](../runs/verification/design-repair-demo-seed-7.md) fails
its first verification, corrects the retry assertion and passes the second.

The first live Anthropic check stopped after three repair rounds (five API
requests). It exposed an overly restrictive requirement mapping in the verifier
and insufficient diagnostics for a creation case mislabeled as rendering. The
verifier now allows UI-related outcomes under R2 as well as R4, supports an
explicit valid-submission event, and reports expected versus actual values.
That [earlier trace](../runs/verification-live/design-anthropic-negotiated-seed-7.md)
is preserved and reflects the earlier verifier behavior.

The [final live check](../runs/verification-live-final/design-anthropic-negotiated-seed-7.md)
using the configured Anthropic model reached agreement with a passing
verification in two API requests, reporting 4,084 input and 1,642 output tokens.
It needed no repair round; successful provider repair is covered by the offline
fixture, not claimed from this live sample. The saved live trace also replayed
successfully without API calls. These are single-run observations, not a
general reliability benchmark. Generated run files are local and ignored by Git.
