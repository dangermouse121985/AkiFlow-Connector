from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from productivity_operator.planning.simulation import PlanningSimulation


class ApplyPlanResponse(BaseModel):
    applied: bool = False
    dry_run: bool = True
    would_modify_akiflow: bool = False
    actions: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class ApplyPlanService:
    """Safe dry-run apply layer for optimized plans."""

    def preview_apply(self, simulation: PlanningSimulation) -> ApplyPlanResponse:
        actions = [
            {
                "type": "recommend_task",
                "task_id": task.get("id"),
                "title": task.get("title", "Untitled task"),
                "position": index + 1,
                "dry_run": True,
            }
            for index, task in enumerate(simulation.recommended_plan)
        ]

        actions.extend(
            {
                "type": "defer_task",
                "task_id": task.get("id"),
                "title": task.get("title", "Untitled task"),
                "reason": task.get("defer_reason", "Not selected for today's optimized plan"),
                "dry_run": True,
            }
            for task in simulation.deferred_tasks
        )

        return ApplyPlanResponse(
            actions=actions,
            message="Dry run only. No Akiflow tasks were modified.",
        )
