from pydantic import ValidationError

from app.planning.schemas import ResearchPlan


plan_data = {
    "objective": (
        "Compare scanned-PDF and table capabilities, limitations, "
        "and the available evidence for comparative accuracy."
    ),
    "tasks": [
        {
            "question": (
                "What scanned-PDF and table capabilities does "
                "each library document?"
            ),
            "coverage_criteria": [
                "Identify built-in OCR or required integrations.",
                "Describe table support and documented limitations.",
                "Identify aspects for which documentation is missing.",
            ],
        },
        {
            "question": (
                "Does the available evidence establish which "
                "library is more accurate?"
            ),
            "coverage_criteria": [
                "Look for accuracy measurements and evaluation conditions.",
                "Determine whether results use comparable workloads.",
                "State explicitly when comparative evidence is insufficient.",
            ],
        },
    ],
}


if __name__ == "__main__":
    plan = ResearchPlan.model_validate(plan_data)

    print("Objective:", plan.objective)

    for number, task in enumerate(plan.tasks, start=1):
        print(f"\nTask {number}: {task.question}")

        for criterion in task.coverage_criteria:
            print(f"  - {criterion}")

    try:
        ResearchPlan.model_validate({
            "objective": "Compare the libraries.",
            "tasks": [],
        })
    except ValidationError:
        print("\nCorrectly rejected a plan with no tasks.")
    else:
        raise AssertionError("Expected an empty plan to fail validation.")

    print("\nPlan-schema check passed.")