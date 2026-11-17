# 07 — Criterion-level coverage assessment

[Module index](README.md)

This note follows the learning sequence. See the [project README](../../README.md) for the complete current workflow; named live runs below are historical observations.

## Purpose

Judge whether the collected result addresses each task criterion, then apply an explicit controller policy. Coverage is different from factual correctness.

## Files

- [app/planning/coverage.py](../../app/planning/coverage.py): assessment schemas, reference validation, and model assessor.
- [app/workflow/nodes.py](../../app/workflow/nodes.py): `make_coverage_node()`.
- [checks/check_coverage.py](../../checks/check_coverage.py), [checks/check_coverage_assessor.py](../../checks/check_coverage_assessor.py).

## Contract

Each `TaskCoverageAssessment` has a task ID and one entry for each criterion:

```text
criterion_index       # Zero-based position in the task's criteria
verdict               # addressed / partially_addressed / not_addressed
rationale
finding_indices[]     # Positions in this task's findings
 gap_indices[]        # Positions in this task's evidence gaps
```

Indices are local references, not persistent evidence IDs. Validation requires every criterion exactly once, a matching task ID, valid reference bounds, and at least one finding/gap reference for an addressed verdict.

## Model call and transition

```text
assess_task_coverage(task, task_result, model_call)
    → Number criteria, findings, and gaps
    → Send isolated assessment messages without tools
    → Parse and validate the returned assessment
```

The coverage node retrieves the active in-progress task and its collected result, enforces/counts the shared model budget, and stores the assessment by task ID.

The initial controller policy is:

```text
All criteria addressed → task answered
Otherwise              → task unresolved
Then clear active_task_id and select another pending task
```

An individual task concluding does not finish the whole run. Currently no coverage-driven retry edge exists.

## Uncertainty and evidence gaps

A criterion asking whether comparable measurements exist can be addressed with a carefully scoped absence finding. A criterion requiring an actual measurement is not automatically satisfied by saying the measurement is missing. The assessor is prompted to distinguish these cases, but can be overly generous.

The assessment checks the supplied result, not an independent search of all sources. A model verdict is a judgment, not verified truth. Wrong verdicts can pass structural and reference checks.

## Checks and interview question

```bash
python -m checks.check_coverage
python -m checks.check_coverage_assessor
```

Simulated responses test implementation behavior, not real-model judgment quality.

**How do coverage and claim verification differ?** Coverage asks whether the requested aspects were addressed. Claim verification asks whether evidence justifies the statements made. A report can cover every topic and still make unsupported claims.
