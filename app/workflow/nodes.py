import asyncio
import requests
import json
from mcp import Client
from pydantic import ValidationError

from collections.abc import Callable

from app.workflow.state import ResearchState
from app.mcp_tools import execute_mcp_tool
from app.schemas import ResearchReport
from app.validation import validate_evidence_references

def make_model_node(
    model_call: Callable[[list[dict], list[dict]], dict],
    tools: list[dict],
):
    async def model_node(state: ResearchState) -> dict:
        # Enforce the limit before making another request.
        if state["model_count"] >= state["max_model_calls"]:
            return {
                "status": "budget_exhausted",
                "result": {
                    "status": "budget_exhausted",
                    "reason": "max_model_calls",
                },
            }

        next_count = state["model_count"] + 1

        try:
            reply = await asyncio.to_thread(
                model_call,
                state["messages"],
                tools,
            )

            if not isinstance(reply, dict):
                raise ValueError("Expected a model response dictionary.")

        except (
            requests.RequestException,
            KeyError,
            IndexError,
            ValueError,
        ) as exc:
            return {
                "model_count": next_count,
                "status": "failed",
                "result": {
                    "status": "failed",
                    "reason": "model_request_or_response_error",
                    "error": str(exc),
                },
            }

        assistant_message = {
            "role": "assistant",
            "content": reply.get("content"),
        }

        if reply.get("tool_calls"):
            assistant_message["tool_calls"] = reply["tool_calls"]

        return {
            "model_count": next_count,
            "latest_reply": reply,
            "messages": [assistant_message],
        }

    return model_node


def make_tool_node(client: Client):
    async def tool_node(state: ResearchState) -> dict:
        reply = state["latest_reply"]

        if reply is None:
            raise ValueError("Tool execution requires a model response.")

        tool_calls = reply.get("tool_calls") or []

        if not tool_calls:
            raise ValueError("Tool node requires at least one tool request.")

        # Local variables accumulate this node execution's updates.
        new_messages = []
        new_events = []
        tool_count = state["tool_count"]

        for tool_call in tool_calls:
            if tool_count >= state["max_tool_calls"]:
                return {
                    "messages": new_messages,
                    "trace": new_events,
                    "tool_count": tool_count,
                    "status": "budget_exhausted",
                    "result": {
                        "status": "budget_exhausted",
                        "reason": "max_tool_calls",
                    },
                }

            name = tool_call["function"]["name"]
            arguments = tool_call["function"]["arguments"]

            result = await execute_mcp_tool(
                client,
                name,
                arguments,
            )

            tool_count += 1

            new_events.append({
                "model_call": state["model_count"],
                "step": tool_count,
                "transport": "mcp_stdio",
                "tool": name,
                "arguments": arguments,
                "result": result,
            })

            new_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result),
            })

        return {
            "messages": new_messages,
            "trace": new_events,
            "tool_count": tool_count,
        }

    return tool_node

def validate_report_node(state: ResearchState) -> dict:
    reply = state["latest_reply"]

    if reply is None:
        raise ValueError("Report validation requires a model response.")

    answer = reply.get("content")

    if not isinstance(answer, str) or not answer.strip():
        return {
            "status": "failed",
            "result": {
                "status": "failed",
                "reason": "empty_model_response",
            },
        }

    try:
        report = ResearchReport.model_validate_json(answer)
    except ValidationError as exc:
        return {
            "status": "invalid_report",
            "result": {
                "status": "invalid_report",
                "reason": "schema_validation_failed",
                "validation_errors": json.loads(
                    exc.json(include_input=False)
                ),
                "raw_answer": answer,
            },
        }

    evidence_errors = validate_evidence_references(
        report,
        state["trace"],
    )

    if evidence_errors:
        return {
            "status": "invalid_report",
            "result": {
                "status": "invalid_report",
                "reason": "evidence_reference_validation_failed",
                "validation_errors": evidence_errors,
                "report": report.model_dump(),
            },
        }

    return {
        "status": "answered",
        "result": {
            "status": "answered",
            "report": report.model_dump(),
            "checks": {
                "schema": "passed",
                "evidence_references": "passed",
                "claim_support": "not_checked",
            },
        },
    }