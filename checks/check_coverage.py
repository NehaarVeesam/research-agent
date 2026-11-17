import json

from app.planning.coverage import validate_coverage_assessment
from app.planning.results import TaskResearchResult
from app.planning.tasks import TrackedTask


if __name__ == "__main__":
    task = TrackedTask(
        task_id="task_001",
        question="What scanned-PDF support is documented?",
        coverage_criteria=[
            "Identify the required OCR integration.",
            "Identify documented limitations.",
        ],
        status="in_progress",
    )

    task_result = TaskResearchResult(
        task_id="task_001",
        findings=[
            {
                "claim": "PaperParse requires ScanBridge.",
                "evidence": [
                    {
                        "source_id": "doc_1",
                        "quote": (
                            "Scanned PDFs require the optional "
                            "ScanBridge OCR integration."
                        ),
                    }
                ],
            }
        ],
        evidence_gaps=[],
    )

    answer = {
        "task_id": "task_001",
        "criteria": [
            {
                "criterion_index": 0,
                "verdict": "addressed",
                "rationale": "Finding 0 identifies ScanBridge.",
                "finding_indices": [0],
                "gap_indices": [],
            },
            {
                "criterion_index": 1,
                "verdict": "not_addressed",
                "rationale": (
                    "The result does not describe documented limitations."
                ),
                "finding_indices": [],
                "gap_indices": [],
            },
        ],
    }

    assessment = validate_coverage_assessment(
        raw_answer=json.dumps(answer),
        task=task,
        task_result=task_result,
    )

    assert assessment.criteria[0].verdict == "addressed"
    assert assessment.criteria[1].verdict == "not_addressed"

    print(assessment.model_dump_json(indent=2))

    # Remove one criterion: validation must catch the omission.
    answer["criteria"].pop()

    try:
        validate_coverage_assessment(
            raw_answer=json.dumps(answer),
            task=task,
            task_result=task_result,
        )
    except ValueError as exc:
        print("\nRejected incomplete assessment:", exc)
    else:
        raise AssertionError("Expected missing-criterion validation to fail.")

    print("\nCoverage-contract checks passed.")