from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OperatorTask(BaseModel):
    task_id: str
    title: str
    description: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    duration: int | None = None
    priority: str | None = None
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    status: str | None = None
    scheduled_start: str | None = None
    scheduled_date: str | None = None
    deadline: str | None = None
    done: bool = False
    source: str = "akiflow"
    last_synced_at: datetime


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks_by_id: dict[str, OperatorTask] = {}

    def load_from_akiflow(self, tasks: list[OperatorTask]) -> None:
        self._tasks_by_id = {
            task.task_id: task
            for task in tasks
            if task.task_id
        }

    def get_by_id(self, task_id: str) -> OperatorTask | None:
        return self._tasks_by_id.get(task_id)

    def find_by_title(self, title: str) -> list[OperatorTask]:
        normalized_title = self._normalize_title(title)
        return [
            task
            for task in self._tasks_by_id.values()
            if self._normalize_title(task.title) == normalized_title
        ]

    def all(self) -> list[OperatorTask]:
        return sorted(self._tasks_by_id.values(), key=lambda task: task.title.lower())

    def unresolved_titles(self, titles: list[str]) -> list[str]:
        return [
            title
            for title in titles
            if len(self.find_by_title(title)) != 1
        ]

    def _normalize_title(self, title: str) -> str:
        return " ".join(title.strip().lower().split())
