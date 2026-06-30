from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from productivity_operator.planning.simulation import PlanningSimulation
from productivity_operator.services import AkiflowService, AkiflowServiceError
from productivity_operator.task_registry import TaskRegistry


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

    def __init__(self, akiflow_service: AkiflowService, task_registry: TaskRegistry | None = None) -> None:
        self.akiflow_service = akiflow_service
        self.task_registry = task_registry

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
            title = str(task.get("title") or "Untitled task")
            duration = self._duration_minutes(task)
            task_id, skip_reason = self._resolve_task_id(task)

            if skip_reason:
                skipped_actions.append(
                    {
                        "action": "schedule_task",
                        "type": "schedule_task",
                        "title": title,
                        "duration": duration,
                        "reason": skip_reason,
                    }
                )
                cursor += timedelta(minutes=duration)
                continue

            start_datetime = cursor.isoformat()
            actions.append(
                {
                    "action": "schedule_task",
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

    def _resolve_task_id(self, task: dict[str, Any]) -> tuple[str | None, str | None]:
        raw_task_id = task.get("task_id") or task.get("id")
        if isinstance(raw_task_id, str) and raw_task_id.strip():
            return raw_task_id, None

        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            return None, "Missing task_id and title; cannot resolve an existing Akiflow task."
        if self.task_registry is None:
            return None, "No task registry is available."

        matches = self.task_registry.find_by_title(title)
        if not matches:
            return None, "No matching task in registry"
        if len(matches) > 1:
            return None, "Multiple matching tasks in registry"
        return matches[0].task_id, None

    def _duration_minutes(self, task: dict[str, Any]) -> int:
        value = task.get("duration")
        try:
            duration = int(value)
        except (TypeError, ValueError):
            return 30
        return duration if duration > 0 else 30
