from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from mcp import Client

from app.workflow.nodes import (
    collect_task_result_node,
    make_coverage_node,
    make_model_node,
    make_planner_node,
    make_synthesis_node,
    make_task_repair_node,
    make_tool_node,
    select_task_node,
    validate_report_node,
)
from app.workflow.routing import (
    route_after_assessment,
    route_after_collection,
    route_after_model,
    route_after_planner,
    route_after_repair,
    route_after_selection,
    route_after_synthesis,
    route_after_tools,
)
from app.workflow.state import ResearchState


def build_research_graph(
    client: Client,
    tools: list[dict],
    model_call: Callable[[list[dict], list[dict]], dict],
):
    builder = StateGraph(ResearchState)

    builder.add_node("planner", make_planner_node(model_call))
    builder.add_node("select", select_task_node)
    builder.add_node("model", make_model_node(model_call, tools))
    builder.add_node("tools", make_tool_node(client))
    builder.add_node("collect", collect_task_result_node)
    builder.add_node("repair", make_task_repair_node(model_call))
    builder.add_node("assess", make_coverage_node(model_call))
    builder.add_node("synthesize", make_synthesis_node(model_call))
    builder.add_node("validate", validate_report_node)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {"stop": END, "select": "select"},
    )

    builder.add_conditional_edges(
        "select",
        route_after_selection,
        {
            "stop": END,
            "model": "model",
            "synthesize": "synthesize",
        },
    )

    builder.add_conditional_edges(
        "model",
        route_after_model,
        {
            "stop": END,
            "tools": "tools",
            "collect": "collect",
        },
    )

    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {"stop": END, "model": "model"},
    )

    builder.add_conditional_edges(
        "collect",
        route_after_collection,
        {"stop": END, "assess": "assess", "repair": "repair"},
    )

    builder.add_conditional_edges(
        "repair",
        route_after_repair,
        {"stop": END, "collect": "collect"},
    )

    builder.add_conditional_edges(
        "assess",
        route_after_assessment,
        {"stop": END, "select": "select"},
    )

    builder.add_conditional_edges(
        "synthesize",
        route_after_synthesis,
        {"stop": END, "validate": "validate"},
    )

    builder.add_edge("validate", END)

    return builder.compile()
