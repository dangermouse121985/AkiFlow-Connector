from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TaskScore:
    title: str
    score: int
    reasons: list[str]


class TaskScorer:
    def score_task(self, task: Any) -> TaskScore:
        score = 0
        reasons: list[str] = []

        priority = str(self._get(task, "priority", "")).lower()
        tags = [str(tag).lower() for tag in self._get(task, "tags", [])]
        title = str(self._get(task, "title", ""))
        duration = self._get(task, "duration", None)

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
            reasons.append("Waiting task should not be scheduled")

        if "deep work" in tags:
            score += 20
            reasons.append("Deep Work task")

        if "quick win" in tags:
            score += 15
            reasons.append("Quick Win")

        if "research" in tags:
            score += 8
            reasons.append("Research task")

        if "reading" in tags:
            score += 3
            reasons.append("Reading task")

        if isinstance(duration, int):
            if duration <= 15:
                score += 8
                reasons.append("Fits a short gap")
            elif duration <= 45:
                score += 5
                reasons.append("Fits a medium gap")
            elif duration <= 120:
                score += 3
                reasons.append("Fits within task size limit")
            else:
                score -= 50
                reasons.append("Task is larger than two hours")

        title_lower = title.lower()
        if any(word in title_lower for word in ["follow up", "send", "publish", "review"]):
            score += 10
            reasons.append("Likely to unblock or move work forward")

        return TaskScore(title=title, score=score, reasons=reasons)

    def _get(self, task: Any, field: str, default: Any = None) -> Any:
        if isinstance(task, dict):
            return task.get(field, default)

        return getattr(task, field, default)