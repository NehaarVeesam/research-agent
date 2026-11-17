# 12 — Semantic claim verification with Qwen

[Module index](README.md) · [Current project status](../../README.md)

## Why this module exists

An exact quotation can be real and still fail to support the attached claim. For example, “Scans require OCR” does not establish “This tool has 99% OCR accuracy.” Module 02 checks textual occurrence. This module asks whether the cited evidence supports the claim's meaning.

Qwen remains the only live model. This is a model assessment of support, not a proof of truth or an independent fact-checking service.

## Updated workflow

```text
Plan → Research tasks → Collect → Coverage → Synthesize
  → Pydantic + source-read/quote checks
  → Claim verification in batches of four
  → All supported: answered
  → Partial or unsupported: invalid_report / needs_review
  → Missing budget or invalid assessment: explicit incomplete/failed outcome
```

The verifier only runs after deterministic report validation passes. It receives each claim, its cited quotations, source IDs/titles/URLs, and up to 400 characters of source context on either side of each quotation. It does not search or introduce outside knowledge. Several cited passages can jointly support one claim; it does not separately grade every citation's relevance.

## Scripts and concepts

| File | Responsibility |
|---|---|
| `app/verification/claims.py` | Pydantic verdict schemas, source-context extraction, verifier prompt and batch-response validation |
| `app/verification/node.py` | LangGraph verification gate, budget accounting, aggregation and final outcome |
| `app/verification/runner.py` | Verify an existing saved report using Qwen without repeating research |
| `app/workflow/graph.py` | Connect report validation to verification and then END |
| `app/workflow/state.py` | Optional `verify_claims` configuration |
| `app/workflow/research_policy.py` | Estimate completion reserve for synthesis plus verification |
| `app/workflow/runner.py` | Enable verification by default and save `claim_verification.json` |
| `checks/check_claim_verification.py` | Deterministic schema, semantic-gate policy, failure and budget tests |
| `checks/check_web_graph.py` | Complete simulated-model workflow through the real MCP interface and verification gate |

`make_claim_verification_node(model_call)` is a closure: it configures the Qwen callable once, then returns the async node that consumes graph state. The async node offloads the blocking model request with `asyncio.to_thread` and returns state updates.

## Structured assessment

```json
{
  "finding_index": 0,
  "verdict": "partially_supported",
  "reason": "The quote supports state preservation but not the contrast with ordinary return.",
  "evidence_indices": [0]
}
```

- `supported`: the cited evidence jointly supports all material parts, including scope and certainty.
- `partially_supported`: some parts have support, but other clauses or stronger wording are not established.
- `unsupported`: the citations do not establish the central assertion, are irrelevant, or contradict it.

Finding indices refer to the original final report. Evidence indices refer to that finding's evidence list. Every requested finding must appear exactly once. Invalid, duplicate, missing, or extra indices are rejected. Supported and partially supported verdicts must reference evidence. Pydantic checks structure; custom validation checks relationships; Qwen assesses meaning.

## Outcomes and budgets

The original report is retained even when it fails the semantic gate. Claims are not silently deleted, weakened or rewritten. Module 13 adds one bounded follow-up cycle; this module documents the verification gate itself.

| Situation | Result |
|---|---|
| Every claim assessed supported | `status: answered`, `checks.claim_support: passed` |
| Any partial/unsupported claim | `status: invalid_report`, `reason: claim_support_not_established`, `claim_support: needs_review` |
| Model budget exhausted | `status: budget_exhausted`, completed assessments retained, verification `incomplete` |
| Invalid JSON, tool request, empty content, request error or bad indices | `status: failed`, `reason: claim_verification_failed` |
| No findings | No verifier call; `claim_support: not_applicable`, not a vacuous semantic pass |
| Source/quote checks fail | No verifier call; retain the deterministic rejection |

Each batch consumes one model call, including failed requests. There is no hidden verifier retry. In bounded web mode, the completion reserve estimates up to three findings per unfinished task, plus collected findings, to leave room for synthesis and verification batches. It is an estimate, not a guarantee; actual output or earlier failures may still exhaust the budget.

`claim_verification` includes the method, assessment list, completed/total batches, verifier call count and verdict counts when complete. All model requests/responses/errors remain in `model_calls.jsonl`. Verdicts are also written to `claim_verification.json` alongside `result.json`, `trace.json`, `run.json` and `run.log`.

## Run

From the repository root with the virtual environment active:

```bash
# New research automatically includes verification:
python -m app.workflow.runner --backend web \
  --question "What are Python generators and how does yield differ from return?"

# Verify an old saved report without repeating searches:
python -m app.verification.runner \
  --input-run runs/20261117T092012_810828Z_88b1b7de

# Controlled checks; no endpoint calls:
python -m checks.check_claim_verification
python -m checks.check_web_graph
```

The saved-report runner creates a new run folder and records the original run ID/path plus a SHA-256 hash of its input `result.json`. It does not overwrite the original research run. It requires a saved final report and its successful source-read trace, and rechecks citations before using Qwen.

The graph and saved-workflow Python APIs support `verify_claims=False` for explicit baseline experiments. The normal CLI always enables it. The original `python -m app.agent` controller remains the historical baseline and does not include this new gate. Existing baseline graph checks explicitly disable verification; the updated full web-graph check exercises it enabled.

## Limitations and interview questions

**Why use both deterministic and model checks?** Deterministic checks establish JSON structure, source access and exact quote occurrence. The model assesses a different property: whether those passages justify the claim.

**Why can the verifier reject a true statement?** It assesses the provided evidence, not truth from its training knowledge. A true statement still needs relevant citations.

**Does a supported verdict prove correctness?** No. The same Qwen model writes and judges claims, so correlated errors remain possible. Human-labelled cases, judge calibration, adversarial examples and broader evaluation are still needed. No numerical confidence score is presented as calibrated probability.

**Does this detect conflicts across all sources?** No. It may notice contradictions in the cited passages and supplied nearby context, but systematic cross-source conflict discovery and credibility assessment are separate work.

**Why preserve rejected claims?** It keeps the original output and the judgment inspectable and provides a concrete target for the next bounded follow-up module.


## Verification performed

All 22 deterministic check modules passed. The new module has 14 focused checks, including saved-report persistence and invalid citation rejection. The complete web-graph check now includes the verification gate and records seven simulated model calls.

Two live Qwen validations were saved:

| Run | Scope | Result |
|---|---|---|
| `20261117T100322_759551Z_8089e0e1` | Verify the earlier six-finding report, no web research | Two Qwen calls; five supported, one partially supported |
| `20261117T100443_011645Z_134314b3` | Entire updated research workflow | Fourteen Qwen calls, eight tool requests; five supported, one partially supported |

Both correctly returned `invalid_report / claim_support_not_established` under the implemented policy, while retaining the report and verdict explanations. Qwen identified a multi-clause claim whose source supported generator state preservation but did not establish its added statement about a standard function terminating upon return. This is the failure that substring validation alone could not detect.

“Correctly” here describes enforcement of the gate on the returned verdicts. These live examples are not an independently labelled accuracy evaluation of the verifier. Saved `validation.md` files explain each verdict. Next work is bounded follow-up for weak/missing evidence, followed by a labelled evaluation set and baseline comparison.
