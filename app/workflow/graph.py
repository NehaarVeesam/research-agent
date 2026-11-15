from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from mcp import Client

from app.workflow.nodes import (
    make_model_node,
    make_tool_node,
    validate_report_node,
)
from app.workflow.routing import route_after_model, route_after_tools
from app.workflow.state import ResearchState


def build_research_graph(
    client: Client,
    tools: list[dict],
    model_call: Callable[[list[dict], list[dict]], dict],
):
    builder = StateGraph(ResearchState)

    # Configure and register the work functions.
    builder.add_node("model", make_model_node(model_call, tools))
    builder.add_node("tools", make_tool_node(client))
    builder.add_node("validate", validate_report_node)

    # Entry point.
    builder.add_edge(START, "model")

    # Decide what follows each model response.
    builder.add_conditional_edges(
        "model",
        route_after_model,
        {
            "stop": END,
            "tools": "tools",
            "validate": "validate",
        },
    )

    # Continue research only if tool execution left the run active.
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "stop": END,
            "model": "model",
        },
    )

    # Validation records the final outcome.
    builder.add_edge("validate", END)

    return builder.compile()