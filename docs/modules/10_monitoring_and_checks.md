# 10 — Terminal monitoring, checks, and current limits

[Module index](README.md)

This note follows the learning sequence. See the [project README](../../README.md) for the complete current workflow; named live runs below are historical observations.

## Purpose

Make long runs visible and verify controller behavior with predictable inputs before relying on live model output.

## Files and responsibilities

- [app/workflow/runner.py](../../app/workflow/runner.py): CLI logging setup, budgets, public output.
- [app/workflow/nodes.py](../../app/workflow/nodes.py): stage, tool, validation, repair, and outcome messages.
- [checks/](../../checks/): controlled behavioral checks.
- [examples/](../../examples/): learning exercises; `preview_plan` calls the live endpoint.

## Logging and output streams

`logging` emits timestamped progress to stderr: MCP startup, plan readiness, selected task, model request counts, tool calls, coverage outcomes, repairs, synthesis, validation, and completion. Ordinary progress does not dump prompts, tool arguments, or document bodies.

The CLI entry point configures workflow logging. Importing the runner as a library does not configure those INFO messages globally.

Final JSON goes to stdout:

```bash
python -m app.workflow.runner > result.json
```

Progress remains visible in the terminal. Redirecting stdout creates a manual artifact; the normal CLI independently saves its automatic run records and SQLite checkpoints (modules 11 and 14). Inspect a saved run's own status and timestamps rather than assuming an old file describes the latest terminal run.

## Current code settings

The current `app/workflow/runner.py` defaults to 60 model calls and 60 tool requests. The original controller defaults to six and eight respectively. `app/agent.py` uses `requests.post(..., timeout=600)`, shared by both implementations. These values changed during learning; inspect the code when reproducing runs.

A scalar Requests timeout configures connection/read waits; it is not a strict overall wall-clock deadline for the research run. LangGraph's `6 * max_model_calls + 20` step allowance is another guard, not token/cost accounting. Failed model request attempts consume the counter.

## Assertions and simulated models

```python
assert result["model_calls"] == 5, result
```

If the condition is true, execution continues. Otherwise Python raises `AssertionError` and includes the optional message. Assertions express test expectations, not essential runtime validation: optimized Python (`-O`) can remove them. The original controller and full graph integration checks also use `unittest` assertions.

Fake model functions return controlled tool requests, task answers, assessments, or reports. Real MCP subprocesses are still exercised by integration checks. This verifies orchestration and error handling, not model intelligence. Live tests are required separately for endpoint compatibility and model behavior.

## Check map

| Area | Modules under `checks/` |
|---|---|
| Original controller / MCP | `check_agent`, `check_mcp` |
| Graph components | `check_model_node`, `check_tool_node`, `check_routing`, `check_report_node` |
| Planning | `check_plan_schema`, `check_planner` |
| Task lifecycle | `check_tasks`, `check_task_selection`, `check_task_result`, `check_task_collection` |
| Coverage / synthesis | `check_coverage`, `check_coverage_assessor`, `check_synthesis` |
| Provenance | `check_validation` |
| Complete graph / repair | `check_graph_agent` |
| Retrieval / research policy | `check_web_retrieval`, `check_web_graph`, `check_research_policy` |
| Saved artifacts | `check_run_artifacts` |
| Semantic verification / follow-up | `check_claim_verification`, `check_followup` |
| Checkpoint recovery | `check_persistence` (uses `checkpoint_worker`) |
| Benchmark framework | `check_evaluation` |

Run a module as `python -m checks.check_graph_agent` from the repository root. The latest regression run passed all 25 deterministic check modules with controlled inputs and no hosted model requests. `check_web_live` is separate and contacts Wikipedia. Some imports still require `.env` model configuration. A passing suite covers its written scenarios, not every possible condition or production reliability.

## Pending observability and interview question

Local run artifacts and SQLite checkpoint recovery are implemented (modules 11 and 14). The benchmark records tokens and optional user-priced cost estimates (module 15); no whole-run time/token/cost cap or external tracing service is implemented. General transport recovery and guaranteed final reports after every failure remain outside scope. Connection-level exceptions can still propagate.

**Why both fake and live tests?** Controlled responses make controller behavior reproducible; live experiments reveal model quality, endpoint compatibility, latency, and operating failures.
