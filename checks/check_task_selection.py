from app.planning.schemas import ResearchPlan
from app.planning.tasks import initialize_tasks
from app.workflow.nodes import select_task_node
from app.workflow.state import ResearchState


if __name__ == "__main__":
    plan = ResearchPlan(
        objective="Compare the libraries.",
        tasks=[
            {
                "question": "What capabilities are documented?",
                "coverage_criteria": ["Identify OCR support."],
            },
            {
                "question": "What limitations are documented?",
                "coverage_criteria": ["Identify documented failure modes."],
            },
        ],
    )

    state: ResearchState = {
        "messages": [],
        "trace": [],
        "tasks": [
            task.model_dump()
            for task in initialize_tasks(plan)
        ],
        "latest_reply": None,
        "model_count": 1,
        "tool_count": 0,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }

    state["latest_reply"] = {"content": "A previous task's response."}
    updates = select_task_node(state)

    assert updates["active_task_id"] == "task_001"
    assert updates["tasks"][0]["status"] == "in_progress"
    assert updates["tasks"][1]["status"] == "pending"
    assert len(updates["messages"]) == 1
    assert updates["latest_reply"] is None

    # Calling the function directly must not mutate its input.
    assert state["tasks"][0]["status"] == "pending"
    assert state["latest_reply"]["content"] == "A previous task's response."

    # Simulate the relevant state updates for a second selection.
    active_state = {
        **state,
        "tasks": updates["tasks"],
        "active_task_id": updates["active_task_id"],
    }

    repeated_updates = select_task_node(active_state)

    assert repeated_updates["active_task_id"] == "task_001"
    assert "messages" not in repeated_updates

    print("Task-selection checks passed.")
