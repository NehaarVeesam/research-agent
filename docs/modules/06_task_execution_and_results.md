# 06 — Sequential task execution and result collection

[Module index](README.md)

This note follows the learning sequence. See the [project README](../../README.md) for the complete current workflow; named live runs below are historical observations.

## Purpose

Turn proposed tasks into controller-managed execution records and collect a separate result for each. The plan describes intended work; tracked tasks record progress.

## Files

- [app/planning/tasks.py](../../app/planning/tasks.py): `TrackedTask`, `initialize_tasks()`.
- [app/planning/results.py](../../app/planning/results.py): `TaskResearchResult`, `validate_task_result()`.
- [app/workflow/nodes.py](../../app/workflow/nodes.py): selection, model, tools, and collection nodes.
- [app/workflow/state.py](../../app/workflow/state.py): tasks, active ID, results, messages, and trace.

## Task record and identity

```text
TrackedTask
├── task_id                 # Assigned by application: task_001, task_002...
├── question
├── coverage_criteria[]
├── status                  # pending / in_progress / answered / unresolved
└── evidence_ids[]           # Currently empty placeholders
```

IDs are stable after assignment within the run, not globally unique. `Field(default_factory=list)` creates a fresh list for each task. The controller initializes status; the planner does not declare its own work finished.

## Execution sequence

1. `initialize_tasks(plan)` preserves planned questions/criteria and adds IDs and pending status.
2. `select_task_node(state)` retains an existing active task or selects the first pending task.
3. It returns copied task records with the selection marked `in_progress`, sets `active_task_id`, clears `latest_reply`, and appends task guidance.
4. The research model receives original-question context, prior observations, and the current task. It produces tool requests or task-result JSON.
5. The generic tool node invokes MCP tools, adds trace events, and appends observations.
6. `collect_task_result_node()` validates the returned task result and stores it under `task_results[task_id]`.
7. Coverage assessment, not collection, determines the next task status.

```text
TaskResearchResult = task_id + findings[] + evidence_gaps[]
```

Findings reuse the final report's claim/source/quote structure. Result validation checks active task identity and the run's source-read/quote rules.

## State update behavior

`tasks` and `task_results` replace their previous values. Updated result dictionaries must retain earlier entries, for example `{**existing_results, task_id: new_result}`. Messages and trace append only new entries.

One task is active at a time; finding multiple in-progress tasks is an invariant error. Shared conversation history allows reuse of sources already read during another task. The trace is run-wide, so this is not yet precise task-to-evidence provenance.

## Checks

```bash
python -m checks.check_tasks
python -m checks.check_task_selection
python -m checks.check_task_result
python -m checks.check_task_collection
python -m checks.check_tool_node
```

## Boundaries and interview question

Evidence IDs are not generated yet. Task records live in graph state and returned output; the normal CLI also persists them in SQLite checkpoints (module 14). A separate task/evidence database is not implemented. Source IDs identify documents; future evidence IDs will identify stored passages/provenance records.

**Why separate collecting results from completing tasks?** A well-formed, correctly cited result may still omit a required part of the task.
