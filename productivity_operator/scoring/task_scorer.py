from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


@dataclass
class TaskScore:
    id: str | None
    title: str
    score: int
    reasons: list[str]


class TaskScorer:
    def score_task(self, task: Any, now: datetime | None = None) -> TaskScore:
        score = 0
        reasons: list[str] = []

        priority = self._normalize(self._get(task, "priority", ""))
        tags = [str(tag).lower() for tag in self._get(task, "tags", [])]
        title = str(self._get(task, "title", ""))
        duration = self._get(task, "duration", None)
        deadline = self._get(task, "deadline", None)

        if priority == "high":
            score += 40
            reasons.append("High priority")
        elif priority == "medium":
            score += 25
            reasons.append("Medium priority")
        elif priority == "low":
            score += 10
            reasons.append("Low priority")

        if "waiting" in tags:
            score -= 100
            reasons.append("Waiting/blocking")

        if "deep work" in tags:
            score += 20
            reasons.append("Deep work")

        if "quick win" in tags:
            score += 15
            reasons.append("Quick win")

        if "research" in tags:
            score += 8
            reasons.append("Research")

        if "reading" in tags:
            score += 3
            reasons.append("Reading")

        if now:
            days_until_deadline = self._days_until_deadline(deadline, now)
            if days_until_deadline is not None and 0 <= days_until_deadline <= 3:
                score += 15
                reasons.append("Due soon")

        if isinstance(duration, int):
            if duration <= 15:
                score += 8
                reasons.append("Short task")
            elif duration <= 45:
                score += 5
                reasons.append("Medium task")
            elif duration <= 120:
                score += 3
                reasons.append("Focused task")
            else:
                score -= 50
                reasons.append("Over two hours")

        title_lower = title.lower()
        if any(word in title_lower for word in ["follow up", "send", "publish", "review"]):
            score += 10
            reasons.append("Waiting/blocking")

        return TaskScore(id=self._get(task, "id", None), title=title, score=score, reasons=list(dict.fromkeys(reasons)))

    def _get(self, task: Any, field: str, default: Any = None) -> Any:
        if isinstance(task, dict):
            return task.get(field, default)

        return getattr(task, field, default)

    def _normalize(self, value: Any) -> str:
        if isinstance(value, Enum):
            return str(value.value).lower()

        return str(value).lower()

    def _days_until_deadline(self, deadline: Any, now: datetime) -> int | None:
        if deadline is None:
            return None

        if isinstance(deadline, datetime):
            due_date = deadline.date()
        elif isinstance(deadline, date):
            due_date = deadline
        elif isinstance(deadline, str):
            try:
                due_date = datetime.fromisoformat(deadline).date()
            except ValueError:
                try:
                    due_date = date.fromisoformat(deadline)
                except ValueError:
                    return None
        else:
            return None

        return (due_date - now.date()).days
