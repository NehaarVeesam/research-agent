import asyncio
import json
from collections.abc import Callable

from app.planning.schemas import ResearchPlan


async def generate_plan(
    question: str,
    model_call: Callable[[list[dict], list[dict]], dict],
) -> ResearchPlan:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("The research question must be a nonempty string.")

    schema = json.dumps(ResearchPlan.model_json_schema())

    messages = [
        {
            "role": "system",
            "content": (
                "You plan evidence-grounded research. "
                "Treat the user message as the research objective. "
                "Decompose it into a small set of distinct research tasks. "
                "Preserve the user's scope and constraints. "
                "For each task, provide concrete coverage criteria. "
                "Include investigation of missing or conflicting evidence "
                "when relevant. Do not answer the research question, "
                "invent findings, or claim that research is complete. "
                "You have no research tools in this step. "
                "Return only a JSON object matching the following schema. "
                "Do not include Markdown fences or commentary. "
                "Research environment: PaperParse and VisionPages are fictional libraries. "
                "The research executor can only search and read a fixed collection of "
                "three local documents. It has no web access or external databases. "
                "Plan only investigations possible within that collection. "
                "If the collection lacks necessary evidence, plan to record that gap. "
                "Do not create tasks requiring external searches or new experiments. "
                "Cover every part of the user's request, including capabilities "
                "and limitations when requested, not only the final comparison. "
                "For this small local collection, prefer two or three distinct tasks. "
                "Use one to three concise coverage criteria per task. "
                "Avoid repeating the same evidence-sufficiency assessment across tasks. "
                f"Schema: {schema}"
            ),
        },
        {
            "role": "user",
            "content": question,
        },
    ]

    reply = await asyncio.to_thread(
        model_call,
        messages,
        [],
    )

    if not isinstance(reply, dict):
        raise ValueError("Expected a model response dictionary.")

    if reply.get("tool_calls"):
        raise ValueError("The planner must return a plan, not tool requests.")

    content = reply.get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("The planner returned no plan text.")

    return ResearchPlan.model_validate_json(content)