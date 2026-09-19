# Actors exercising actual Lemonade software

Start a separate local demo backend (no credentials needed there):

```sh
cd ../Lemonade
API_PORT=3301 npm run start -w @lemonade/api
```

From Lemon, run either an authored smoke sequence or an Anthropic actor:

```sh
python3 -m lemon exercise
python3 -m lemon exercise --agent anthropic --max-api-requests 12
python3 -m lemon exercise --agent anthropic --max-api-requests 4 \
  --task 'Check whether populated JSON arrays are rejected for the scenario field.'
```

Anthropic uses Lemon's existing `.env.local` and makes paid calls. The actor
chooses submit/read/recover/evidence actions for two fresh UUID identities. It
receives actual HTTP responses and prior checks, not a simulated replacement
for the software. Requests are bounded to a loopback origin identifying itself
as Lemonade, the four transfer endpoints, and a maximum of sixteen actor turns.
The actor cannot choose arbitrary URLs, existing identities, or edit code.

An independently authored contract checker checks response codes, scenario
outcomes, identity, amount, receipt stability, and ledger facts. It calculates
ledger expectations rather than trusting the backend's reported check flags.
Invalid first submissions also get a read probe to verify that no transfer was
created. A failed contract check stops the exercise and saves the request,
response, check results, and action sequence in a hash-linked event log.

Passing checks apply only to requests actually exercised. An exhausted model
budget is a stopped run, not proof of coverage or a software defect. Malformed
actor actions get feedback; they are not sent to the target. The checker is
specific to this demo's declared contract, not a general software verifier.

## Replay without a model

```sh
# Verify the recorded event chain offline
python3 -m lemon replay runs/software-targeted/exercise-9ff477f0.json

# Send the same actions to the actual API using fresh identities
python3 -m lemon exercise \
  --replay-actions runs/software-targeted/exercise-9ff477f0.json \
  --output runs/software-after
```

The second command makes real local HTTP requests but no Anthropic calls. Replay
uses actions from the verified recorded state, not an unverified top-level list.
It creates fresh demo state, so it does not depend on the original server's Map.

## First observed defect and delivery

The broad model exercises tested recovery, identity conflicts, primitives, and
empty containers but did not reach the relevant populated-container case. A
human-specified targeted task then asked the actor to test a single-element
array containing a valid scenario. This was **guided probing**, not unguided
defect discovery.

The Anthropic actor chose `{"scenario":["normal"]}`. Lemonade accepted it with
HTTP 201, returned `completed`, and created a receipt. The declared contract
requires a JSON string, so the checker expected HTTP 400 and no new transfer.
Fastify's default AJV coercion converted the array into a string.

We preserved the actor's exact body as
`../Lemonade/apps/api/test/fixtures/actor-array-probe.json`, added a regression
test, and observed it fail before changing implementation. Disabling
`coerceTypes` fixed the defect. A fresh HTTP replay returned 400; the follow-up
read returned 404, establishing that no transfer was created.

Local evidence (ignored by git):

- Before: `runs/software-targeted/exercise-9ff477f0.json`
- After: `runs/software-after/exercise-7de46e74.json`
- Baseline recovery exercise: `runs/software-smoke/exercise-fc148864.json`

The fixture preserves source provenance and the failing event hash in Lemonade.
The repair was written by the coding assistant. The actor supplied an enacted
request; a deterministic checker identified the contract violation; tests and
replay verified the implementation change. This closes one practical feedback
loop without claiming automatic code generation or general autonomous discovery.
