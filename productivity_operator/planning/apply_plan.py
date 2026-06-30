from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from productivity_operator.planning.simulation import PlanningSimulation
from productivity_operator.services import AkiflowService, AkiflowServiceError


class ApplyPlanResponse(BaseModel):
    applied: bool = False
    dry_run: bool = True
    would_modify_akiflow: bool = False
    actions: list[dict[str, Any]] = Field(default_factory=list)
    skipped_actions: list[dict[str, Any]] = Field(default_factory=list)
    succeeded_actions: list[dict[str, Any]] = Field(default_factory=list)
    failed_actions: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class ApplyPlanRequest(BaseModel):
    confirm: bool = False


class ApplyPlanService:
    """Safe dry-run apply layer for optimized plans."""

    def __init__(self, akiflow_service: AkiflowService) -> None:
        self.akiflow_service = akiflow_service

    def apply(
        self,
        simulation: PlanningSimulation,
        current_datetime: datetime,
        confirm: bool = False,
    ) -> ApplyPlanResponse:
        actions, skipped_actions = self._build_schedule_actions(simulation, current_datetime)
        if confirm:
            return self.confirm_apply(actions, skipped_actions)

        return self.preview_apply(actions, skipped_actions)

    def preview_apply(
        self,
        actions: list[dict[str, Any]],
        skipped_actions: list[dict[str, Any]],
    ) -> ApplyPlanResponse:
        return ApplyPlanResponse(
            actions=actions,
            skipped_actions=skipped_actions,
            message="Dry run only. Review the proposed scheduling actions before confirming.",
        )

    def confirm_apply(
        self,
        actions: list[dict[str, Any]],
        skipped_actions: list[dict[str, Any]],
    ) -> ApplyPlanResponse:
        if not actions:
            return ApplyPlanResponse(
                applied=True,
                dry_run=False,
                would_modify_akiflow=True,
                actions=[],
                skipped_actions=skipped_actions,
                message="Plan confirmation received, but no supported Akiflow scheduling actions were available.",
            )

        succeeded_actions: list[dict[str, Any]] = []
        failed_actions: list[dict[str, Any]] = []
        for action in actions:
            try:
                result = self.akiflow_service.plan_task(
                    str(action["task_id"]),
                    str(action["start_datetime"]),
                )
                succeeded_actions.append({**action, "result": result})
            except AkiflowServiceError as exc:
                failed_actions.append({**action, "error": str(exc)})

        message = (
            f"Confirmed apply complete. Scheduled {len(succeeded_actions)} task(s); "
            f"{len(failed_actions)} failed and {len(skipped_actions)} were skipped."
        )
        return ApplyPlanResponse(
            applied=True,
            dry_run=False,
            would_modify_akiflow=True,
            actions=actions,
            skipped_actions=skipped_actions,
            succeeded_actions=succeeded_actions,
            failed_actions=failed_actions,
            message=message,
        )

    def _build_schedule_actions(
        self,
        simulation: PlanningSimulation,
        current_datetime: datetime,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        cursor = current_datetime.replace(second=0, microsecond=0)
        actions: list[dict[str, Any]] = []
        skipped_actions: list[dict[str, Any]] = []

        for task in simulation.recommended_plan:
            task_id = task.get("id")
            title = str(task.get("title") or "Untitled task")
            duration = self._duration_minutes(task)

            if not isinstance(task_id, str) or not task_id.strip():
                skipped_actions.append(
                    {
                        "type": "schedule_task",
                        "title": title,
                        "duration": duration,
                        "reason": "Missing task_id; cannot safely schedule an existing Akiflow task.",
                    }
                )
                cursor += timedelta(minutes=duration)
                continue

            start_datetime = cursor.isoformat()
            actions.append(
                {
                    "type": "schedule_task",
                    "task_id": task_id,
                    "title": title,
                    "start_datetime": start_datetime,
                    "duration": duration,
                    "reason": "Recommended by ScheduleOptimizer and fits remaining available time.",
                }
            )
            cursor += timedelta(minutes=duration)

        return actions, skipped_actions

    def _duration_minutes(self, task: dict[str, Any]) -> int:
        value = task.get("duration")
        try:
            duration = int(value)
        except (TypeError, ValueError):
            return 30
        return duration if duration > 0 else 30
