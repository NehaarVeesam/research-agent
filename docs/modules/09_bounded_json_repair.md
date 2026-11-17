# 09 — Bounded task-result JSON repair

[Module index](README.md)

This note follows the learning sequence. See the [project README](../../README.md) for the complete current workflow; named live runs below are historical observations.

## Purpose and observed failure

A live model returned explanatory prose before its task JSON. `model_validate_json()` parses the complete answer, so that response failed before source checks or coverage assessment.

```text
All searches return the same documents...
{"task_id": "task_002", ...}
```

Whitespace before JSON is allowed; prose is not. A prompt saying JSON only does not enforce serialization.

## Files

- [app/workflow/nodes.py](../../app/workflow/nodes.py): repairable-error classification and `make_task_repair_node()`.
- [app/workflow/routing.py](../../app/workflow/routing.py): bounded repair routing.
- [app/workflow/state.py](../../app/workflow/state.py): per-task attempt counts.
- [checks/check_graph_agent.py](../../checks/check_graph_agent.py): repair integration scenarios.

## Exact policy

```text
Collect task result
    ├── Valid → Coverage assessment
    ├── Pydantic json_invalid + no prior repair → Repair → Collect again
    └── Other failure or repair already attempted → Stop
```

Only JSON parsing errors trigger repair. Valid JSON with missing/wrong fields, task-ID mismatches, unread sources, or invented quotes do not automatically trigger this path.

The node checks remaining model budget, increments the request count and this task's repair count, and sends an isolated formatting request with the rejected content, validation error, and task-result schema. It exposes no tools and rejects tool requests in the repair response.

The new response is placed in `latest_reply`; collection then repeats the entire schema, identity, and source/quote validation. The original assistant response remains in research conversation history. The isolated repair exchange itself is not appended to that history.

## Bounds and limitations

- At most one repair request per task, including a failed request.
- No budget means no repair request.
- Repeated invalid JSON stops explicitly; no infinite loop.
- Changing a quote to nonexistent text is still rejected.
- The prompt asks for content preservation, but semantic equivalence is not independently checked.
- Planning, coverage, and synthesis output repair are not implemented.
- This is not a transport retry or a research retry.

We do not silently take text between the first opening brace and last closing brace as a universal JSON extraction strategy.

## Check and interview question

```bash
python -m checks.check_graph_agent
```

Tests cover successful repair, per-task limits, repeated malformed output, budget exhaustion, strict quote validation after repair, and forbidden repair tool calls.

**Why revalidate after repair?** A formatting request is another model generation, not a trusted transformation. It can still produce malformed or unsupported content.
