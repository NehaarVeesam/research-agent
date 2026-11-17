from app.planning.schemas import ResearchPlan
from app.planning.tasks import initialize_tasks


if __name__ == "__main__":
    plan = ResearchPlan(
        objective="Compare documented PDF capabilities.",
        tasks=[
            {
                "question": "What OCR support is documented?",
                "coverage_criteria": ["Identify OCR requirements."],
            },
            {
                "question": "What limitations are documented?",
                "coverage_criteria": ["Identify stated failure modes."],
            },
        ],
    )

    tasks = initialize_tasks(plan)

    assert [task.task_id for task in tasks] == [
        "task_001",
        "task_002",
    ]
    assert all(task.status == "pending" for task in tasks)
    assert all(task.evidence_ids == [] for task in tasks)

    # Mutating one task's list must not change another task.
    tasks[0].evidence_ids.append("example_evidence_id")
    assert tasks[1].evidence_ids == []

    print("Task initialization checks passed.")