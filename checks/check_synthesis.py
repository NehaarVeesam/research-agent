import asyncio
import json

from app.workflow.nodes import make_synthesis_node
from app.workflow.state import ResearchState


def fake_model(messages: list[dict], tools: list[dict]) -> dict:
    assert tools == []

    supplied = json.loads(messages[1]["content"])

    assert supplied["question"] == "Which library is more accurate?"
    assert supplied["tasks"][0]["status"] == "unresolved"

    return {
        "content": json.dumps({
            "findings": [],
            "evidence_gaps": [
                "The inspected collection provides no comparative benchmark."
            ],
        })
    }


async def main():
    state: ResearchState = {
        "question": "Which library is more accurate?",
        "messages": [],
        "trace": [],
        "latest_reply": None,
        "model_count": 4,
        "tool_count": 0,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
        "tasks": [
            {
                "task_id": "task_001",
                "question": "What comparative accuracy evidence exists?",
                "coverage_criteria": ["Identify comparable measurements."],
                "status": "unresolved",
                "evidence_ids": [],
            }
        ],
        "task_results": {},
        "coverage_assessments": {},
    }

    node = make_synthesis_node(fake_model)
    updates = await node(state)

    assert updates["model_count"] == 5
    assert len(updates["messages"]) == 1

    report = json.loads(updates["latest_reply"]["content"])

    assert report["findings"] == []
    assert report["evidence_gaps"]

    print("Synthesis-node check passed.")


if __name__ == "__main__":
    asyncio.run(main())