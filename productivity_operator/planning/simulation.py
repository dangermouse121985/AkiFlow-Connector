from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from productivity_operator.planning.context import PlanningContext
from productivity_operator.planning.schedule_optimizer import ScheduleRecommendation


class ChangesSummary(BaseModel):
    recommended_count: int
    deferred_count: int
    would_modify_akiflow: bool = False


class PlanningSimulation(BaseModel):
    current_plan: list[dict[str, Any]] = Field(default_factory=list)
    recommended_plan: list[dict[str, Any]] = Field(default_factory=list)
    deferred_tasks: list[dict[str, Any]] = Field(default_factory=list)
    remaining_minutes: int
    explanation: str
    changes_summary: ChangesSummary


def build_planning_simulation(
    context: PlanningContext,
    recommendation: ScheduleRecommendation,
) -> PlanningSimulation:
    current_plan = [task.model_dump(mode="json") for task in context.tasks]

    return PlanningSimulation(
        current_plan=current_plan,
        recommended_plan=recommendation.recommended_tasks,
        deferred_tasks=recommendation.deferred_tasks,
        remaining_minutes=recommendation.remaining_minutes,
        explanation=recommendation.explanation,
        changes_summary=ChangesSummary(
            recommended_count=len(recommendation.recommended_tasks),
            deferred_count=len(recommendation.deferred_tasks),
            would_modify_akiflow=False,
        ),
    )
