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


class ApplyPlanRequest(BaseModel):
    confirm: bool = False


class ApplyPlanService:
    """Safe dry-run apply layer for optimized plans."""

    def apply(self, simulation: PlanningSimulation, confirm: bool = False) -> ApplyPlanResponse:
        if confirm:
            return self.confirm_apply(simulation)

        return self.preview_apply(simulation)

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

    def confirm_apply(self, simulation: PlanningSimulation) -> ApplyPlanResponse:
        return ApplyPlanResponse(
            applied=True,
            dry_run=False,
            would_modify_akiflow=True,
            actions=[],
            message="Plan confirmation received, but no Akiflow write actions are implemented yet.",
        )
