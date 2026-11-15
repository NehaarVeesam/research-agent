import operator
from typing import Annotated, Literal, TypedDict

class ResearchState(TypedDict):
    # Conversation history: new messages append.
    messages: Annotated[list[dict], operator.add]

    # Tool Execution history: new events append.
    trace: Annotated[list[dict], operator.add]

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
