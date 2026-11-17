from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Finding, ResearchReport
from app.validation import validate_evidence_references


class TaskResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    findings: list[Finding]
    evidence_gaps: list[str]


def validate_task_result(
    raw_answer: str,
    active_task_id: str,
    trace: list[dict],
) -> TaskResearchResult:
    result = TaskResearchResult.model_validate_json(raw_answer)

    if result.task_id != active_task_id:
        raise ValueError(
            f"Expected result for {active_task_id!r}, "
            f"but received {result.task_id!r}."
        )

    # Reuse our existing source-read and exact-quote validation.
    report = ResearchReport(
        findings=result.findings,
        evidence_gaps=result.evidence_gaps,
    )

    errors = validate_evidence_references(report, trace)

    if errors:
        raise ValueError(
            "Task evidence-reference validation failed: "
            + "; ".join(errors)
        )

    return result