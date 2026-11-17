import operator
from typing import Annotated, Literal, TypedDict, NotRequired

class ResearchState(TypedDict):
    # Conversation history: new messages append.
    messages: Annotated[list[dict], operator.add]
    followup_count: NotRequired[int]
    max_followup_cycles: NotRequired[int]
    followup_history: NotRequired[list[dict]]
    followup_decision: NotRequired[dict]
    verify_claims: NotRequired[bool]
    bounded_web: NotRequired[bool]
    task_model_counts: NotRequired[dict[str, int]]
    task_tool_counts: NotRequired[dict[str, int]]
    plan_scope_adjustments: NotRequired[list[str]]
    research_context: NotRequired[str]
    question: NotRequired[str]
    plan: NotRequired[dict]

    tasks: NotRequired[list[dict]]
    # Tool Execution history: new events append.
    trace: Annotated[list[dict], operator.add]
    active_task_id: NotRequired[str | None]
    task_results: NotRequired[dict[str, dict]]

    coverage_assessments: NotRequired[dict[str, dict]]
    task_repair_attempts: NotRequired[dict[str, int]]

    # Latest model response: each response replaces the previous one.
    latest_reply: dict | None

    # Counters and limits: updates replace previous values
    model_count: int
    tool_count: int
    max_model_calls: int
    max_tool_calls: int

    # workflow outcome
    status: Literal[
        "running",
        "answered",
        "invalid_report",
        "budget_exhausted",
        "failed"
    ]

    # Final application result, including errors when applicable
    result: dict | None
