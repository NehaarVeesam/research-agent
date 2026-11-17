import asyncio
import json

from app.planning.coverage import assess_task_coverage
from app.planning.results import TaskResearchResult
from app.planning.tasks import TrackedTask
from langgraph.graph import END, START, StateGraph

from app.workflow.nodes import make_coverage_node
from app.workflow.state import ResearchState

def fake_model(messages: list[dict], tools: list[dict]) -> dict:
    assert tools == []

    supplied_data = json.loads(messages[1]["content"])

    assert supplied_data["task_id"] == "task_001"
    assert len(supplied_data["coverage_criteria"]) == 2
    assert supplied_data["findings"][0]["finding_index"] == 0

    return {
        "content": json.dumps({
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
                        "The result contains no documented limitations."
                    ),
                    "finding_indices": [],
                    "gap_indices": [],
                },
            ],
        })
    }


async def main():
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

    assessment = await assess_task_coverage(
        task=task,
        task_result=task_result,
        model_call=fake_model,
    )
    state: ResearchState = {
        "messages": [],
        "trace": [],
        "tasks": [task.model_dump()],
        "active_task_id": task.task_id,
        "task_results": {
            task.task_id: task_result.model_dump(),
        },
        "coverage_assessments": {},
        "latest_reply": None,
        "model_count": 2,
        "tool_count": 1,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }

    builder = StateGraph(ResearchState)
    builder.add_node("assess", make_coverage_node(fake_model))
    builder.add_edge(START, "assess")
    builder.add_edge("assess", END)

    graph = builder.compile()
    final_state = await graph.ainvoke(state)

    assert final_state["model_count"] == 3
    assert final_state["tasks"][0]["status"] == "unresolved"
    assert final_state["active_task_id"] is None
    assert task.task_id in final_state["coverage_assessments"]
    assert final_state["status"] == "running"

    print("\nCoverage-node state updates passed.")
    assert assessment.criteria[0].verdict == "addressed"
    assert assessment.criteria[1].verdict == "not_addressed"

    # Assessing coverage must not mutate execution status.
    assert task.status == "in_progress"

    print(assessment.model_dump_json(indent=2))
    print("\nCoverage-assessor check passed.")


if __name__ == "__main__":
    asyncio.run(main())