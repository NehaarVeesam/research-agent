# 13 — One bounded, evidence-driven follow-up cycle

## Purpose

The agent can now act on its own evaluation feedback. Previously, weak claim support ended the run at the verification gate. Now the controller can schedule one targeted investigation, synthesize an updated report, and verify the updated claims again.

This is a deliberately small feedback loop. It is not an unrestricted retry-until-success policy, and a second report can still need review.

## Architecture

```text
Plan → Select task → Research ⇄ MCP tools → Collect → Coverage
                        ↑                              |
                        └──── next selected task ──────┘

All tasks concluded → Synthesize → Validate quotes → Verify claim support
                                                        |
                                                Follow-up decision
                                            /                         \
                       Valid report + actionable gap              END
                       + allowance + no prior cycle       clean / disabled / limit /
                                      |                   insufficient budget / failure
                            Add followup_001 task
                                      |
                              Select → Research …
                                      |
                         Synthesize → Validate → Verify → END
```

The host chooses the follow-up target deterministically from structured feedback. Qwen chooses research actions and writes task results, coverage assessments, synthesis and verification. We do not add another model call just to schedule the retry.

## Files

| File | Responsibility |
|---|---|
| `app/planning/followup.py` | Select targets, check allowances, create a task, snapshot prior results, route and summarize history |
| `app/workflow/graph.py` | Connect verification to the follow-up decision and route back to task selection |
| `app/workflow/state.py` | Follow-up counter, cycle limit, decision and history |
| `app/workflow/runner.py` | Configure the cycle limit and persist `followup.json` |
| `app/workflow/nodes.py` | Supply prior verifier feedback to the second synthesis |
| `checks/check_followup.py` | Scheduling and complete-graph acceptance/failure cases |

The existing model/tool/collection/coverage/repair/synthesis/verifier nodes are reused. We add one pending task rather than reopening or mutating the original tasks.

## Trigger and target selection

A follow-up is eligible only when:

1. Deterministic report validation passed.
2. Claim verification completed, or a gaps-only report had no claims to assess.
3. At least one claim is partial/unsupported, or an original task has unresolved coverage.
4. The single cycle has not been used or disabled.
5. The configured model/tool budgets have sufficient remaining allowance.

The task contains at most two targets: the first weak claim and the first unaddressed criterion from an unresolved original task. It retains the original claim, review reason, task ID and criterion index for inspection. A weak claim is a question to investigate, not a fact to assume. This selection is intentionally simple; it does not optimize impact across all gaps or promise to repair every claim.

Missing evidence recorded as an adequately addressed availability criterion does not automatically trigger another search. A task must actually be unresolved, or a claim must have a weak verdict.

## Bounds and stopping

- Default: one cycle. `--max-followup-cycles 0` disables it; only 0 or 1 are accepted.
- At most one added task: `followup_001`.
- Follow-up uses the bounded task controller for both local and web retrieval: three research turns then a tool-free conclusion; existing per-task search/tool allowances and JSON repair limits still apply.
- Global counts are not reset. Planning, both synthesis passes, both verification passes and any repair all consume the same run's model budget.
- Starting allowance: four research calls, coverage, synthesis, one possible repair, and an estimate of verification batches for the prior findings plus up to three follow-up findings. At least two global tool requests must remain. This is a conservative admission estimate, not guaranteed capacity for arbitrary model output.
- Invalid JSON/report references, verifier transport failure or incomplete verification do not trigger this research retry. Their existing failure outcomes remain visible.
- After the cycle, stop even if support or coverage remains weak. No second cycle is silently created.

If the second pass hits a handled budget/validation failure, the normal run output retains the prior report in follow-up history and available task/tool records. Unexpected process failure still has the existing limitations of in-memory graph state; these snapshots are not durable resume checkpoints.

## Second synthesis and verification

The second synthesis receives the new task results plus the earlier report, targets and verifier judgments. It must:

- Keep supported findings.
- Add new citations only from successfully read sources.
- Avoid repeating a flagged assertion unless its missing parts have supporting evidence.
- Narrow unsupported wording or move the unsupported detail into an explicit gap when necessary.

The updated report passes through Pydantic, exact-quote validation, and Qwen claim verification again. The old verdicts are not carried forward as verdicts on newly worded claims.

If a cycle fails without producing an updated report, claim tracking says `no_updated_report`; it does not claim the old assertion was removed or resolved.

Original task statuses remain historical. The follow-up gets its own coverage assessment; an answered follow-up task does not automatically mark all original criteria answered. Similarly, a removed or changed claim is recorded as `changed_or_removed`, not automatically “resolved.”

## Saved output

Each normal graph CLI run now also saves `followup.json`:

```text
cycles_used
 decision: action and stop reason
 history:
   cycle, task_id, targets
   before: original report, checks and claim verdicts
   coverage_before
   after: updated outcome when the graph finishes
   model_calls_used, tool_calls_used
   original_claim_tracking
```

These fields also appear in `result.json`. All model exchanges and tool traces remain in the existing records. New results do not overwrite the earlier report snapshot. Model judgments may change between passes; the history allows that change to be inspected.

## Commands

```bash
# Full Qwen workflow with the default one-cycle allowance:
python -m app.workflow.runner --backend web \
  --question "What are Python generators and how does yield differ from return?"

# Baseline without follow-up (claim verification still enabled):
python -m app.workflow.runner --backend web --max-followup-cycles 0 \
  --question "What are Python generators and how does yield differ from return?"

# Controlled checks, no Qwen or external HTTP:
python -m checks.check_followup
```

Both graph APIs accept `max_followup_cycles=0` or `1`. When claim verification is explicitly disabled for baseline checks, follow-up is disabled as well. The original Python-loop controller and the standalone saved-report verifier do not run follow-up research.

## Checks and interview concepts

Twelve focused tests cover target creation, unresolved criteria, clean reports, disabled/invalid limits, insufficient budgets, invalid/incomplete verification, immutable prior snapshots, changed-claim tracking, a successful complete cycle, persistent weak support, and a coverage-triggered cycle. Complete-graph cases use real in-process MCP with simulated model/HTTP responses; they test orchestration, not judge accuracy. All 23 deterministic check modules passed.

**What makes this adaptive?** The task is generated from observed coverage or semantic-verification feedback after research, rather than only from the initial plan.

**Why one cycle?** It provides a testable improvement attempt with explicit resource limits and a definite stopping point. More retries do not guarantee better evidence.

**Does a supported second report prove the original claim?** No. The wording may have changed, the evidence may differ, and Qwen's assessments are fallible. Inspect the before/after records.

**What remains?** A labelled benchmark, baseline comparisons, judge calibration and portfolio packaging. More sophisticated target ranking, information-gain stopping, conflict analysis and durable resume remain extensions.


## Live Qwen acceptance run

Run `20261117T104559_905417Z_4e2b6590` completed with `status: answered`, **22 model calls and 10 tool requests**. The first verification assessed five claims supported and one partially supported. One follow-up cycle targeted that claim and an unresolved criterion, searched/read more evidence, then repeated synthesis and verification. The revised report had **eight claims assessed supported**, zero partial/unsupported verdicts, and explicit remaining gaps.

The follow-up portion used 8 model calls and 3 tool requests. The controller stopped at `cycle_limit_reached`. Before/after report references, verdict indices, saved history consistency and source-text hashes were independently checked from artifacts. Inspect `runs/20261117T104559_905417Z_4e2b6590/validation.md`, `followup.json`, `claim_verification.json`, `result.json` and `run.log` locally.

This demonstrates one working feedback cycle, not benchmarked accuracy or guaranteed improvement. Original task coverage remains historical; the final report contains limitations, and changed/removed claims are distinguished from newly supported claims.
