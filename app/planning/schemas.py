from pydantic import BaseModel, ConfigDict, Field

class PlannedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    coverage_criteria: list[str] = Field(
        min_length = 1,
        max_length = 5
    )

class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=1)
    tasks: list[PlannedTask] = Field(
        min_length = 1,
        max_length = 6
    )

