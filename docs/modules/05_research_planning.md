# 05 — Environment-aware research planning

[Module index](README.md)

## Purpose

Decompose the original question into explicit research questions and coverage criteria. Tool selection chooses the next action; planning defines what the investigation should address.

## Files

- [app/planning/schemas.py](../../app/planning/schemas.py): `PlannedTask` and `ResearchPlan`.
- [app/planning/planner.py](../../app/planning/planner.py): `generate_plan()`.
- [app/workflow/nodes.py](../../app/workflow/nodes.py): `make_planner_node()`.
- [examples/preview_plan.py](../../examples/preview_plan.py): live plan preview.

## Contract

```text
ResearchPlan
├── objective
└── tasks[]
    ├── question
    └── coverage_criteria[]
```

The schema currently allows one to six tasks and one to five criteria per task. The prompt prefers two or three tasks with one to three criteria for this small collection. Prompt guidance and validation bounds serve different purposes.

## Execution and arguments

```text
generate_plan(question, model_call)
    → Build system/user messages including the JSON schema
    → model_call(messages, []) in a worker thread
    → Reject unexpected tool requests or empty text
    → ResearchPlan.model_validate_json(content)
    → Return validated plan object
```

The model function omits tool-related HTTP fields when the tools list is empty. Planning does not discover evidence or execute tools.

The graph's planner node enforces the shared model budget, counts the request attempt, initializes tracked tasks, stores the plan, and appends plan guidance to the research conversation. Planning failures stop the run explicitly.

## Lesson from the first outputs

The first plan proposed vendor websites, papers, and external benchmarks. Those were beyond the local tool capabilities. We added explicit environment context: the libraries are fictional and only three local documents are accessible. We also guided the planner to avoid redundant tasks and retain all aspects of the user's request.

Evaluate plans for scope coverage, executability, and unnecessary overlap. Valid JSON alone does not establish a good plan. Missing evidence should become a recorded gap, not an invented finding.

## Checks and live preview

```bash
python -m checks.check_plan_schema
python -m checks.check_planner
python -m examples.preview_plan  # Contacts the configured model endpoint.
```

## Boundaries and interview question

The planner prompt currently hardcodes the local environment; dynamically supplied capabilities are future work. The schema does not enforce every string to be nonblank after trimming. Planning consumes model budget and does not reserve capacity for final synthesis.

**Why must a planner know the available tools?** A relevant plan may still be impossible to execute within the sources, permissions, and resources actually available.
