import asyncio
import json

from langgraph.graph import END, START, StateGraph

from app.workflow.nodes import make_model_node
from app.workflow.state import ResearchState


# A substitute for the real Qwen request function.
def fake_model_call(messages: list[dict], tools: list[dict]) -> dict:
    print("\nFake model received:")
    print("Last message:", messages[-1])
    print("Available tools:", tools)

    return {
        "content": "This is a simulated model answer.",
    }


async def main():
    # Step 1: Create a configured node.
    # This does not execute fake_model_call().
    model_node = make_model_node(
        model_call=fake_model_call,
        tools=[],
    )

    # Step 2: Register the returned function in a graph.
    builder = StateGraph(ResearchState)
    builder.add_node("model", model_node)
    builder.add_edge(START, "model")
    builder.add_edge("model", END)

    graph = builder.compile()

    initial_state: ResearchState = {
        "messages": [
            {"role": "user", "content": "Explain scanned PDF support."},
        ],
        "trace": [],
        "latest_reply": None,
        "model_count": 0,
        "tool_count": 0,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }

    print("BEFORE:")
    print(json.dumps(initial_state, indent=2))

    # Step 3: Execute the graph.
    final_state = await graph.ainvoke(initial_state)

    print("\nAFTER:")
    print(json.dumps(final_state, indent=2))

    assert final_state["model_count"] == 1
    assert len(final_state["messages"]) == 2
    assert final_state["messages"][0]["role"] == "user"
    assert final_state["messages"][1]["role"] == "assistant"
    assert final_state["latest_reply"]["content"] == (
        "This is a simulated model answer."
    )
    assert final_state["tool_count"] == 0

    print("\nModel-node check passed.")


if __name__ == "__main__":
    asyncio.run(main())