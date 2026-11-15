import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from langgraph.graph import END, START, StateGraph

from app.workflow.nodes import make_tool_node
from app.workflow.state import ResearchState


PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def main():
    request = {
        "id": "call_read_1",
        "type": "function",
        "function": {
            "name": "read_source",
            "arguments": json.dumps({"source_id": "doc_1"}),
        },
    }

    initial_state: ResearchState = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [request],
            }
        ],
        "trace": [],
        "latest_reply": {
            "content": None,
            "tool_calls": [request],
        },
        "model_count": 1,
        "tool_count": 0,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=str(PROJECT_ROOT),
    )

    async with Client(parameters) as client:
        builder = StateGraph(ResearchState)
        builder.add_node("tools", make_tool_node(client))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)

        graph = builder.compile()
        final_state = await graph.ainvoke(initial_state)

    assert final_state["tool_count"] == 1
    assert len(final_state["trace"]) == 1
    assert len(final_state["messages"]) == 2

    tool_message = final_state["messages"][-1]

    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_read_1"

    document = json.loads(tool_message["content"])
    assert document["source_id"] == "doc_1"

    print(json.dumps(final_state, indent=2))
    print("\nTool-node check passed.")


if __name__ == "__main__":
    asyncio.run(main())