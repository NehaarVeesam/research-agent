import json

from langgraph.graph import END, START, StateGraph

from app.planning.schemas import ResearchPlan
from app.planning.tasks import initialize_tasks
from app.search import read_source
from app.workflow.nodes import collect_task_result_node
from app.workflow.state import ResearchState


if __name__ == "__main__":
    plan = ResearchPlan(
        objective="Investigate PaperParse OCR requirements.",
        tasks=[
            {
                "question": "What OCR integration is required?",
                "coverage_criteria": ["Identify the required integration."],
            }
        ],
    )

    tasks = [
        task.model_dump()
        for task in initialize_tasks(plan)
    ]
    tasks[0]["status"] = "in_progress"

    answer = {
        "task_id": "task_001",
        "findings": [
            {
                "claim": "Scanned PDFs require ScanBridge.",
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

    state: ResearchState = {
        "messages": [],
        "trace": [
            {
                "tool": "read_source",
                "result": read_source("doc_1"),
            }
        ],
        "tasks": tasks,
        "active_task_id": "task_001",
        "task_results": {},
        "latest_reply": {"content": json.dumps(answer)},
        "model_count": 2,
        "tool_count": 1,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }

    builder = StateGraph(ResearchState)
    builder.add_node("collect", collect_task_result_node)
    builder.add_edge(START, "collect")
    builder.add_edge("collect", END)
    graph = builder.compile()

    final_state = graph.invoke(state)

    stored = final_state["task_results"]["task_001"]

    assert stored["task_id"] == "task_001"
    assert len(stored["findings"]) == 1
    assert final_state["tasks"][0]["status"] == "in_progress"
    assert final_state["status"] == "running"

    print(json.dumps(stored, indent=2))
    print("\nTask-collection check passed.")