# Anthropic reviewer — implementation and first comparison

The user selected Anthropic and supplied `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` in `.env.local`. The integration uses that configuration; it neither changes the file nor creates an OpenAI credential. The env file is now ignored by Git.

## What changed

The Test Agent can call Anthropic for a structured review of the current design revision. Product, Backend, UI, message routing, permissions, revision checks, replay, and independent evaluation remain local and deterministic.

The model receives the requirements, contract, revision, and cancellation scope. It can propose `CHALLENGE`, `ACCEPT`, or `ESCALATE`. Its structured response is validated before it becomes a message; malformed replies, stale revisions, exhausted budgets, and provider failures become explicit incomplete outcomes. There is no silent fallback to deterministic approval.

The implementation follows the [Messages API reference](https://platform.claude.com/docs/en/api/messages/create), [authentication/version header documentation](https://platform.claude.com/docs/en/api/overview), and [tool definition and tool-choice documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools). It uses a named `submit_review` tool as an output contract, not a tool that executes application code.

## Captured live run

Command:

```sh
python3 -m lemon compare --max-api-requests 6
```

[Paired comparison](../runs/comparison/comparison-negotiated-seed-7.md) · [Anthropic transcript](../runs/comparison/design-anthropic-negotiated-seed-7.md) · [Anthropic specification](../runs/comparison/design-anthropic-negotiated-seed-7.spec.json)

Configuration: model `claude-haiku-4-5`, scenario `negotiated`, scheduler seed `7`.

| Observation | Deterministic Test Agent | Anthropic Test Agent |
|---|---|---|
| Outcome | Agreed | Agreed |
| Automated scenario checks | Passed | Passed |
| Messages | 25 | 25 |
| Contract revisions | 2 | 2 |
| Final interface contract | Same | Same |
| Planned test cases | 6 | 10 |
| HTTP requests | 0 | 2 |
| Reported input tokens | 0 | 3,167 |
| Reported output tokens | 0 | 1,455 |
| Model request time | None | Approximately 11.4 seconds |

Anthropic challenged the incomplete initial contract, then accepted the revised contract with test cases. Both versions kept approvals attached to the current revision. No extra paid runs were needed to obtain this comparison.

## Semantic review findings

The automatic checks establish structured output validity, requirement-ID coverage, current-version approvals, and agreement on the required contract fields. They do not prove that every sentence in a model-generated test case follows from the contract.

Reading this specific model response revealed assumptions that should be corrected before generating application tests:

1. **Case `TC-R3-1` assumes completion.** Its precondition says an earlier request created transaction `TX-001`, but the expected result requires status `COMPLETED`. Creation alone does not establish completion. Either explicitly state that the original transaction completed, or expect the same transaction and its actual current status without inventing completion.
2. **Case `TC-R2-1` assumes a full authentication path.** It expects every listed authentication/execution state in sequence without a condition requiring additional authentication. The existing transfer simulation has different low-risk and high-risk paths. State vocabulary alone does not specify a mandatory sequence.
3. **The explanation conflates authorization and authentication.** They are distinct concepts in the World: evidence can establish authentication, while authorization decides whether an action is permitted.
4. **The acceptance explanation assumes a transition rule.** It says `COMPLETED` is reached only after `EXECUTING`, but this interface contract lists states and a success state, not a transition graph. That can be a candidate requirement to specify or a test precondition to state, rather than an already-proven property.

These are review observations, not claims that the simulator detected those prose errors automatically. The raw transcript and generated specification preserve the original model output for inspection.

## What this establishes

The model can participate through the existing protocol and reach the same required interface contract in this captured case. It also writes additional acceptance cases and longer explanations. More cases do not by themselves establish higher quality, and this single run does not show general superiority, learning, or a performance benefit.

The subsequent [verification-and-repair implementation](design-verification.md)
adds explicit transitions and structured case assertions, checks them before
agreement, and sends failures back to their owner. Prompt version `test-review-v2`
includes the assertion model; repair requests include diagnostics and the rejected
artifact. Its output budget is 4,096 tokens to accommodate the structured cases.
The table above describes the earlier implementation and is not a benchmark of
the new verifier. Application generation remains a separate step.

## Reproduce without accidental API traffic

```sh
# Offline regression suite (fake provider transports only)
python3 -m unittest discover -s tests -v

# Replay the captured model run without credentials or network requests
python3 -m lemon replay runs/comparison/design-anthropic-negotiated-seed-7.json

# Explicitly start another paid comparison
python3 -m lemon compare
```

Fresh model output may differ. This document describes the captured run above; regenerating files under the same output path can replace that run. Use `--output runs/another-comparison` to preserve it during another experiment.
