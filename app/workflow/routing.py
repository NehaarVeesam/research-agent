from typing import Literal

from app.workflow.state import ResearchState


def route_after_planner(
    state: ResearchState,
) -> Literal["stop", "select"]:
    if state["status"] != "running":
        return "stop"

    return "select"


def route_after_selection(
    state: ResearchState,
) -> Literal["stop", "model", "synthesize"]:
    if state["status"] != "running":
        return "stop"

    if state.get("active_task_id") is not None:
        return "model"

    return "synthesize"


def route_after_model(
    state: ResearchState,
) -> Literal["stop", "tools", "collect"]:
    if state["status"] != "running":
        return "stop"

    reply = state["latest_reply"]

    if reply is None:
        raise ValueError("Model routing requires a model response.")

    if reply.get("tool_calls"):
        return "tools"

    return "collect"


def route_after_tools(
    state: ResearchState,
) -> Literal["stop", "model"]:
    if state["status"] != "running":
        return "stop"

    return "model"


def route_after_collection(
    state: ResearchState,
) -> Literal["stop", "assess", "repair"]:
    if state["status"] == "running":
        return "assess"

    failure = state.get("result") or {}
    task_id = state.get("active_task_id")
    attempts = state.get("task_repair_attempts", {})
    if (
        state["status"] == "invalid_report"
        and failure.get("reason") == "task_result_validation_failed"
        and failure.get("repairable")
        and task_id
        and attempts.get(task_id, 0) < 1
    ):
        return "repair"
    return "stop"


def route_after_repair(
    state: ResearchState,
) -> Literal["stop", "collect"]:
    if state["status"] != "running":
        return "stop"
    return "collect"


def route_after_assessment(
    state: ResearchState,
) -> Literal["stop", "select"]:
    if state["status"] != "running":
        return "stop"

    return "select"


def route_after_synthesis(
    state: ResearchState,
) -> Literal["stop", "validate"]:
    if state["status"] != "running":
        return "stop"

    return "validate"
