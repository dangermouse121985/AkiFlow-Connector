from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from productivity_operator.models import Task, TaskStatus
from productivity_operator.planning.context import PlanningContext


class ScheduleRecommendation(BaseModel):
    recommended_tasks: list[dict[str, Any]] = Field(default_factory=list)
    deferred_tasks: list[dict[str, Any]] = Field(default_factory=list)
    remaining_minutes: int
    explanation: str


class ScheduleOptimizer:
    """Deterministic first-pass task recommendation optimizer."""

    def optimize(self, context: PlanningContext) -> ScheduleRecommendation:
        remaining_minutes = max(0, context.available_minutes_today)
        recommended_tasks: list[dict[str, Any]] = []
        deferred_tasks: list[dict[str, Any]] = []

        task_metadata = self._task_metadata(context)
        sorted_scores = sorted(
            context.scored_tasks,
            key=lambda item: self._score_value(item),
            reverse=True,
        )

        seen_keys: set[str] = set()
        for scored_task in sorted_scores:
            key = self._task_key(scored_task)
            if not key or key in seen_keys:
                continue

            task = task_metadata.get(key)
            if task is None:
                continue

            seen_keys.add(key)
            task_payload = self._merge_metadata(task, scored_task, context)

            if self._is_completed(task):
                deferred_tasks.append({**task_payload, "defer_reason": "Completed"})
                continue

            duration = self._duration_minutes(task)
            if duration > remaining_minutes:
                deferred_tasks.append({**task_payload, "defer_reason": "Does not fit today"})
                continue

            recommended_tasks.append(task_payload)
            remaining_minutes -= duration

        for task in context.tasks:
            key = self._task_key(task)
            if not key or key in seen_keys:
                continue

            task_payload = self._merge_metadata(task, None, context)
            if self._is_completed(task):
                deferred_tasks.append({**task_payload, "defer_reason": "Completed"})
                continue

            duration = self._duration_minutes(task)
            if duration > remaining_minutes:
                deferred_tasks.append({**task_payload, "defer_reason": "Does not fit today"})
                continue

            recommended_tasks.append(task_payload)
            remaining_minutes -= duration

        explanation = (
            f"Recommended {len(recommended_tasks)} task(s) by score while preserving calendar order "
            f"and {remaining_minutes} available minute(s)."
        )
        return ScheduleRecommendation(
            recommended_tasks=recommended_tasks,
            deferred_tasks=deferred_tasks,
            remaining_minutes=remaining_minutes,
            explanation=explanation,
        )

    def _task_metadata(self, context: PlanningContext) -> dict[str, Task]:
        return {
            key: task
            for task in context.tasks
            if (key := self._task_key(task))
        }

    def _merge_metadata(
        self,
        task: Task,
        scored_task: dict[str, Any] | None,
        context: PlanningContext,
    ) -> dict[str, Any]:
        payload = task.model_dump(mode="json")
        analysis = self._find_analysis(task, context)
        if analysis is not None:
            payload["analysis"] = analysis
        if scored_task is not None:
            payload["score"] = scored_task.get("score")
            payload["reasons"] = scored_task.get("reasons", [])
        return payload

    def _find_analysis(self, task: Task, context: PlanningContext) -> dict[str, Any] | None:
        key = self._task_key(task)
        for analyzed_task in context.analyzed_tasks:
            if self._task_key(analyzed_task) == key:
                analysis = analyzed_task.get("analysis")
                return analysis if isinstance(analysis, dict) else None
        return None

    def _score_value(self, item: dict[str, Any]) -> int:
        value = item.get("score")
        return value if isinstance(value, int) else 0

    def _duration_minutes(self, task: Task) -> int:
        return task.duration if task.duration > 0 else 0

    def _is_completed(self, task: Task) -> bool:
        return task.done or task.status == TaskStatus.done

    def _task_key(self, task: Task | dict[str, Any]) -> str | None:
        if isinstance(task, Task):
            return task.id or task.title or None

        task_id = task.get("id")
        title = task.get("title")
        if isinstance(task_id, str) and task_id:
            return task_id
        if isinstance(title, str) and title:
            return title
        return None
