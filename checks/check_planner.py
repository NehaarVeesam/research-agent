import asyncio
import json

from app.planning.planner import generate_plan


def fake_model(messages: list[dict], tools: list[dict]) -> dict:
    assert tools == []
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    return {
        "content": json.dumps({
            "objective": "Compare scanned-PDF support.",
            "tasks": [
                {
                    "question": (
                        "What OCR capabilities and requirements "
                        "does each library document?"
                    ),
                    "coverage_criteria": [
                        "Identify built-in OCR or required integrations.",
                        "Record missing information explicitly.",
                    ],
                }
            ],
        })
    }


async def main():
    plan = await generate_plan(
        question="Compare PaperParse and VisionPages for scanned PDFs.",
        model_call=fake_model,
    )

    assert len(plan.tasks) == 1
    assert len(plan.tasks[0].coverage_criteria) == 2

    print(plan.model_dump_json(indent=2))
    print("\nPlanner check passed.")


if __name__ == "__main__":
    asyncio.run(main())