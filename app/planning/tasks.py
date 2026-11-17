from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.planning.schemas import ResearchPlan


class TrackedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    question: str
    coverage_criteria: list[str]

    status: Literal[
        "pending",
        "in_progress",
        "answered",
        "unresolved",
    ] = "pending"

    evidence_ids: list[str] = Field(default_factory=list)


def initialize_tasks(plan: ResearchPlan) -> list[TrackedTask]:
    return [
        TrackedTask(
            task_id=f"task_{number:03d}",
            question=task.question,
            coverage_criteria=list(task.coverage_criteria),
        )
        for number, task in enumerate(plan.tasks, start=1)
    ]