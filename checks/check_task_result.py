import json

from app.planning.results import validate_task_result
from app.search import read_source


if __name__ == "__main__":
    trace = [
        {
            "tool": "read_source",
            "result": read_source("doc_1"),
        }
    ]

    answer = {
        "task_id": "task_001",
        "findings": [
            {
                "claim": "PaperParse requires ScanBridge for scanned PDFs.",
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
        "evidence_gaps": [],
    }

    result = validate_task_result(
        raw_answer=json.dumps(answer),
        active_task_id="task_001",
        trace=trace,
    )

    assert result.task_id == "task_001"
    assert len(result.findings) == 1
    print("Accepted a matching task result with a real quote.")

    try:
        validate_task_result(
            raw_answer=json.dumps(answer),
            active_task_id="task_002",
            trace=trace,
        )
    except ValueError as exc:
        print("Rejected a mismatched task:", exc)
    else:
        raise AssertionError("Expected task-ID validation to fail.")

    answer["findings"][0]["evidence"][0]["quote"] = (
        "PaperParse achieved 99% accuracy."
    )

    try:
        validate_task_result(
            raw_answer=json.dumps(answer),
            active_task_id="task_001",
            trace=trace,
        )
    except ValueError as exc:
        print("Rejected an invented quote:", exc)
    else:
        raise AssertionError("Expected quote validation to fail.")

    print("\nTask-result checks passed.")