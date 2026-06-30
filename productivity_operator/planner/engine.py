from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from productivity_operator.models import (
    CalendarBlock,
    DayPlanRequest,
    DayPlanResponse,
    Priority,
    SchedulingRules,
    Task,
    TaskStatus,
    TaskType,
)
from productivity_operator.planning.day_planner import plan_day
from productivity_operator.services import AkiflowService, AkiflowServiceError


class PlannerEngine:
    """
    Central planning engine for Operator.

    Pipeline:
    1. Collect
    2. Filter
    3. Prioritize
    4. Schedule
    5. Explain
    """

    def __init__(
        self,
        akiflow_service: AkiflowService | None = None,
        data_source: str = "sample",
        sample_path: Path | None = None,
    ) -> None:
        self.akiflow_service = akiflow_service
        self.data_source = data_source.lower()
        self.sample_path = sample_path or Path(__file__).parent.parent.parent / "sample_day_request.json"

    def load_day_request(self, source: str | None = None) -> DayPlanRequest:
        selected_source = (source or self.data_source).lower()
        if selected_source in {"akiflow", "live"}:
            return self._load_akiflow_day_request()

        return self._load_sample_day_request()

    def plan_day(self, request: DayPlanRequest) -> DayPlanResponse:
        collected = self.collect(request)
        filtered = self.filter(collected)
        prioritized = self.prioritize(filtered)
        scheduled = self.schedule(prioritized)
        explained = self.explain(scheduled)
        return explained

    def collect(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def filter(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def prioritize(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def schedule(self, request: DayPlanRequest) -> DayPlanResponse:
        return plan_day(request)

    def explain(self, response: DayPlanResponse) -> DayPlanResponse:
        return response

    def _load_sample_day_request(self) -> DayPlanRequest:
        data = json.loads(self.sample_path.read_text(encoding="utf-8"))
        return DayPlanRequest.model_validate(data)

    def _load_akiflow_day_request(self) -> DayPlanRequest:
        if self.akiflow_service is None:
            self.akiflow_service = AkiflowService()

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

    def _task_from_akiflow(self, item: dict[str, Any]) -> Task:
        return Task(
            id=self._optional_string(item.get("id")),
            title=self._string_or_default(item.get("title"), "Untitled Akiflow task"),
            duration=self._positive_int(item.get("duration"), default=30),
            priority=self._priority_from_akiflow(item.get("priority")),
            project=self._optional_string(item.get("project")),
            tags=["Akiflow"],
            scheduled_start=self._parse_datetime(item.get("start")),
            deadline=self._parse_date(item.get("deadline")),
            task_type=TaskType.work,
            status=self._status_from_akiflow(item.get("status")),
            done=False,
        )

    def _calendar_block_from_akiflow(self, item: dict[str, Any]) -> CalendarBlock | None:
        start = self._parse_datetime(item.get("start"))
        if start is None:
            return None

        end = self._parse_datetime(item.get("end"))
        if end is None:
            end = start + timedelta(minutes=self._positive_int(item.get("duration"), default=30))

        return CalendarBlock(
            title=self._string_or_default(item.get("title"), "Akiflow event"),
            start=start,
            end=end,
            movable=False,
            kind=self._string_or_default(item.get("kind"), "event"),
        )

    def _priority_from_akiflow(self, value: Any) -> Priority:
        normalized = str(value or "").strip().lower()
        if normalized in {"goal"}:
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

    def _parse_date(self, value: Any):
        parsed = self._parse_datetime(value)
        if parsed is not None:
            return parsed.date()
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
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
