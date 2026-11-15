from typing import Literal
from app.workflow.state import ResearchState

def route_after_model(
    state: ResearchState,
) -> Literal["stop", "tools", "validate"]:
    if state["status"] != "running":
        return "stop"

    reply = state["latest_reply"]
    if reply is None:
        raise ValueError("Model routing requires a model response.")

    if reply.get("tool_calls"):
        return "tools"

    return "validate"

def route_after_tools(
    state: ResearchState,
) -> Literal["stop", "model"]:
    if state["status"] != "running":
        return "stop"

    return "model"