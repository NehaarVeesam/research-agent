import asyncio

from app.agent import call_model
from app.planning.planner import generate_plan


async def main():
    plan = await generate_plan(
        question=(
            "Compare PaperParse and VisionPages for scanned PDFs "
            "with tables. Determine whether the available evidence "
            "establishes which is more accurate."
        ),
        model_call=call_model,
    )

    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())