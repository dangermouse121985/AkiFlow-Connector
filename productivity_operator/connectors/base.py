from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from datetime import date

from productivity_operator.models import Task, CalendarBlock, ScheduledTask


class ProductivityConnector(ABC):
    """Interface for future real connectors such as Akiflow, Google Calendar, Gmail, Slack."""

    @abstractmethod
    async def list_tasks(self) -> List[Task]:
        raise NotImplementedError

    @abstractmethod
    async def list_calendar(self, start: date, end: date) -> List[CalendarBlock]:
        raise NotImplementedError

    @abstractmethod
    async def schedule_task(self, scheduled_task: ScheduledTask) -> None:
        raise NotImplementedError
