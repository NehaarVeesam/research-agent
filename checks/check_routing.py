from app.workflow.routing import route_after_model
from app.workflow.state import ResearchState


def make_state() -> ResearchState:
    return {
        "messages": [],
        "trace": [],
        "latest_reply": None,
        "model_count": 1,
        "tool_count": 0,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }


if __name__ == "__main__":
    state = make_state()

    # Case 1: The model request failed.
    state["status"] = "failed"

    assert route_after_model(state) == "stop"
    print("Failed model request → stop")

    # Case 2: The model requested a tool.
    state["status"] = "running"
    state["latest_reply"] = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_source",
                    "arguments": '{"source_id": "doc_1"}',
                },
            }
        ],
    }

    assert route_after_model(state) == "tools"
    print("Tool request → tools")

    # Case 3: The model returned answer text.
    state["latest_reply"] = {
        "content": '{"findings": [], "evidence_gaps": []}',
    }

    assert route_after_model(state) == "collect"
    print("Answer returned → collect")

    print("\nRouting checks passed.")
