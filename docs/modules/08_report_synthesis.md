# 08 — Final report synthesis and completion

[Module index](README.md)

## Purpose

Combine independently collected task results into one coherent response to the original question, preserving missing evidence and unresolved coverage.

## Files

- [app/workflow/nodes.py](../../app/workflow/nodes.py): `make_synthesis_node()` and `validate_report_node()`.
- [app/workflow/graph.py](../../app/workflow/graph.py): selection-to-synthesis and validation edges.
- [app/workflow/runner.py](../../app/workflow/runner.py): final output assembly.
- [checks/check_synthesis.py](../../checks/check_synthesis.py), [checks/check_report_node.py](../../checks/check_report_node.py).

## Processing sequence

1. Selection finds no pending or active task and returns `active_task_id=None`.
2. Routing selects synthesis.
3. The synthesis node checks remaining model budget.
4. It creates a separate conversation containing the original question, task records, task results, and coverage assessments.
5. The model is asked for `ResearchReport` JSON without tools, external facts, or changed quotes.
6. Its response becomes `latest_reply` and is passed to final validation.
7. Final validation applies report schema and source/quote checks against the run trace.
8. The runner closes MCP and returns the result with records, counts, and trace.

The separate synthesis context avoids simply replaying the entire research conversation. Prompt instructions ask the model to retain gaps; there is no independent validator guaranteeing that every gap survives synthesis.

## Output

The graph runner returns the outcome plus:

```text
plan
 tasks[]
task_results{task_id: result}
coverage_assessments{task_id: assessment}
task_repair_attempts{task_id: count}
model_calls
 tool_calls
trace[]
```

A report contains findings and evidence gaps. Schema and evidence-reference checks are reported separately from `claim_support`, which remains `not_checked`.

`status="answered"` means the final report passed implemented checks. It does not mean every task is answered or every statement is true. Inspect task statuses and assessments separately.

## Budgets and failures

Planning, research, repair, assessment, and synthesis share one model-call budget. There is no synthesis reservation. Reaching the budget before synthesis returns an explicit budget outcome with available task records instead of fabricating a report.

A live synthesis request previously timed out after the then-configured read timeout. That was a transport failure, not invalid JSON. Raising a timeout is not retry/recovery or checkpointing. The current timeout is documented in the monitoring module.

## Run and interview question

```bash
python -m checks.check_synthesis
python -m checks.check_report_node
python -m app.workflow.runner  # Contacts the model endpoint.
```

**Why synthesize after task research?** It separates evidence collection for individual questions from whole-question presentation, while retaining inspectable intermediate results.
