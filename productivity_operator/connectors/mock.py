from __future__ import annotations

from datetime import date
from typing import List

from productivity_operator.connectors.base import ProductivityConnector
from productivity_operator.models import Task, CalendarBlock, ScheduledTask


class MockConnector(ProductivityConnector):
    def __init__(self) -> None:
        self.tasks: List[Task] = []
        self.calendar: List[CalendarBlock] = []

    async def list_tasks(self) -> List[Task]:
        return self.tasks

    async def list_calendar(self, start: date, end: date) -> List[CalendarBlock]:
        return [b for b in self.calendar if start <= b.start.date() <= end]

    async def schedule_task(self, scheduled_task: ScheduledTask) -> None:
        self.calendar.append(CalendarBlock(
            title=scheduled_task.task.title,
            start=scheduled_task.start,
            end=scheduled_task.end,
            movable=True,
            kind="task",
        ))
