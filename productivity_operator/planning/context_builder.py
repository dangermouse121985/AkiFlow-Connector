from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from productivity_operator.analysis import TaskAnalyzer
from productivity_operator.models import (
    CalendarBlock,
    DayPlanRequest,
    Priority,
    SchedulingRules,
    Task,
    TaskStatus,
    TaskType,
)
from productivity_operator.planning.context import PlanningContext
from productivity_operator.scoring import TaskScorer
from productivity_operator.services import AkiflowService, AkiflowServiceError


class PlanningContextBuilder:
    def __init__(
        self,
        *,
        source: str = "sample",
        sample_path: Path | None = None,
        akiflow_service: AkiflowService | None = None,
        task_analyzer: TaskAnalyzer | None = None,
        task_scorer: TaskScorer | None = None,
    ) -> None:
        self.source = self._normalize_source(source)
        self.sample_path = sample_path or Path(__file__).parent.parent.parent / "sample_day_request.json"
        self.akiflow_service = akiflow_service or AkiflowService()
        self.task_analyzer = task_analyzer or TaskAnalyzer()
        self.task_scorer = task_scorer or TaskScorer()

    def build(self, source: str | None = None) -> PlanningContext:
        selected_source = self._normalize_source(source or self.source)
        request = self._load_day_request(selected_source)
        return self.from_day_plan_request(request, selected_source)

    def from_day_plan_request(self, request: DayPlanRequest, source: str = "sample") -> PlanningContext:
        available_minutes = self._available_minutes_today(request)
        analyzed_tasks = [
            {**task.model_dump(mode="json"), "analysis": self.task_analyzer.analyze_task(task).__dict__}
            for task in request.tasks
        ]
        scored_tasks = [
            self.task_scorer.score_task(task, request.current_time).__dict__
            for task in request.tasks
        ]
        scored_tasks.sort(key=lambda item: item["score"], reverse=True)

        return PlanningContext(
            current_datetime=request.current_time,
            available_minutes_today=available_minutes,
            tasks=request.tasks,
            analyzed_tasks=analyzed_tasks,
            scored_tasks=scored_tasks,
            calendar_events=request.calendar,
            source=self._normalize_source(source),
            rules=request.rules,
        )

    def _load_day_request(self, source: str) -> DayPlanRequest:
        if source == "akiflow":
            return self._load_akiflow_day_request()

        data = json.loads(self.sample_path.read_text(encoding="utf-8"))
        return DayPlanRequest.model_validate(data)

    def _load_akiflow_day_request(self) -> DayPlanRequest:
        tasks = [self._task_from_akiflow(item) for item in self.akiflow_service.get_today_tasks()]
        try:
            schedule_items = self.akiflow_service.get_today_schedule()
        except AkiflowServiceError:
            schedule_items = []

        calendar = [self._calendar_block_from_akiflow(item) for item in schedule_items]
        return DayPlanRequest(
            current_time=datetime.now().replace(microsecond=0),
            tasks=tasks,
            calendar=[block for block in calendar if block is not None],
            rules=SchedulingRules(),
        )

    def _available_minutes_today(self, request: DayPlanRequest) -> int:
        rules = request.rules
        now = request.current_time.replace(tzinfo=None)
        work_end = now.replace(hour=rules.workday_end_hour, minute=0, second=0, microsecond=0)
        personal_end = now.replace(hour=rules.personal_end_hour, minute=0, second=0, microsecond=0)
        day_end = personal_end if now < personal_end else work_end
        if now >= day_end:
            return 0

        busy_minutes = 0
        for event in request.calendar:
            start = max(event.start.replace(tzinfo=None), now)
            end = min(event.end.replace(tzinfo=None), day_end)
            if end > start:
                busy_minutes += int((end - start).total_seconds() / 60)

        total_minutes = int((day_end - now).total_seconds() / 60)
        return max(0, total_minutes - busy_minutes)

    def _task_from_akiflow(self, item: dict[str, Any]) -> Task:
        deadline = self._parse_datetime(item.get("deadline"))
        return Task(
            id=self._optional_string(item.get("id")),
            title=self._string_or_default(item.get("title"), "Untitled Akiflow task"),
            duration=self._positive_int(item.get("duration"), default=30),
            priority=self._priority_from_akiflow(item.get("priority")),
            project=self._optional_string(item.get("project")),
            tags=["Akiflow"],
            scheduled_start=self._parse_datetime(item.get("start")),
            deadline=deadline.date() if deadline else None,
            task_type=TaskType.work,
            status=self._status_from_akiflow(item.get("status")),
            done=False,
        )

    def _calendar_block_from_akiflow(self, item: dict[str, Any]) -> CalendarBlock | None:
        start = self._parse_datetime(item.get("start"))
        if start is None:
            return None

        end = self._parse_datetime(item.get("end")) or start + timedelta(minutes=self._positive_int(item.get("duration"), 30))
        return CalendarBlock(
            title=self._string_or_default(item.get("title"), "Akiflow event"),
            start=start,
            end=end,
            kind=self._string_or_default(item.get("kind"), "event"),
        )

    def _priority_from_akiflow(self, value: Any) -> Priority:
        normalized = str(value or "").strip().lower()
        if normalized == "goal":
            return Priority.goal
        if normalized in {"high", "important", "urgent", "p1"}:
            return Priority.high
        if normalized in {"medium", "normal", "p2"}:
            return Priority.medium
        if normalized in {"low", "p3"}:
            return Priority.low
        return Priority.none

    def _status_from_akiflow(self, value: Any) -> TaskStatus:
        normalized = str(value or "").strip().lower()
        if normalized in {"done", "completed", "complete"}:
            return TaskStatus.done
        if normalized in {"planned", "scheduled"}:
            return TaskStatus.planned
        if normalized in {"someday", "later"}:
            return TaskStatus.someday
        return TaskStatus.inbox

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _positive_int(self, value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def _optional_string(self, value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    def _string_or_default(self, value: Any, default: str) -> str:
        return value if isinstance(value, str) and value else default

    def _normalize_source(self, source: str) -> str:
        return "akiflow" if source.lower() in {"akiflow", "live"} else "sample"
