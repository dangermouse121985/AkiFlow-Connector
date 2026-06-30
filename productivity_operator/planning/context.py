from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from productivity_operator.models import CalendarBlock, DayPlanRequest, SchedulingRules, Task


class PlanningContext(BaseModel):
    current_datetime: datetime
    available_minutes_today: int
    tasks: list[Task]
    analyzed_tasks: list[dict[str, Any]] = Field(default_factory=list)
    scored_tasks: list[dict[str, Any]] = Field(default_factory=list)
    calendar_events: list[CalendarBlock] = Field(default_factory=list)
    source: Literal["sample", "akiflow"] = "sample"
    rules: SchedulingRules = Field(default_factory=SchedulingRules)

    def to_day_plan_request(self) -> DayPlanRequest:
        return DayPlanRequest(
            current_time=self.current_datetime,
            tasks=self.tasks,
            calendar=self.calendar_events,
            rules=self.rules,
        )
