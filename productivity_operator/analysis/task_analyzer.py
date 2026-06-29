from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TimeOfDay = Literal["morning", "afternoon", "evening", "anytime"]
EffortLevel = Literal["low", "medium", "high"]


@dataclass
class TaskAnalysis:
    estimated_duration_minutes: int
    requires_deep_work: bool
    can_split: bool
    recommended_chunks: list[str]
    best_time_of_day: TimeOfDay
    energy_required: EffortLevel
    context_switch_cost: EffortLevel


class TaskAnalyzer:
    """Deterministic task intelligence layer for early Operator planning."""

    quick_keywords = {
        "call",
        "email",
        "follow up",
        "ping",
        "reply",
        "send",
        "schedule",
        "text",
    }
    deep_work_keywords = {
        "analyze",
        "build",
        "create",
        "design",
        "draft",
        "implement",
        "learn",
        "plan",
        "research",
        "review",
        "strategy",
        "write",
    }
    evening_keywords = {"personal", "home", "exercise", "read", "reading", "learn"}
    afternoon_keywords = {"call", "email", "follow up", "meeting", "reply", "review", "send"}

    def analyze_task(self, task: Any) -> TaskAnalysis:
        title = str(self._get(task, "title", "") or "")
        title_text = title.lower()
        priority = self._normalize(self._get(task, "priority", ""))
        tags = self._tag_values(task)
        estimated_duration = self._estimated_duration(task, title_text, priority, tags)

        requires_deep_work = self._requires_deep_work(title_text, priority, tags, estimated_duration)
        can_split = self._can_split(title_text, estimated_duration)
        energy_required = self._energy_required(priority, estimated_duration, requires_deep_work)
        context_switch_cost = self._context_switch_cost(title_text, tags, estimated_duration, requires_deep_work)
        best_time_of_day = self._best_time_of_day(
            title_text=title_text,
            tags=tags,
            estimated_duration=estimated_duration,
            requires_deep_work=requires_deep_work,
            priority=priority,
        )

        return TaskAnalysis(
            estimated_duration_minutes=estimated_duration,
            requires_deep_work=requires_deep_work,
            can_split=can_split,
            recommended_chunks=self._recommended_chunks(title, can_split, requires_deep_work),
            best_time_of_day=best_time_of_day,
            energy_required=energy_required,
            context_switch_cost=context_switch_cost,
        )

    def _estimated_duration(
        self,
        task: Any,
        title_text: str,
        priority: str,
        tags: set[str],
    ) -> int:
        raw_duration = self._get(task, "duration", None)
        if raw_duration is None:
            raw_duration = self._get(task, "estimated_duration_minutes", None)

        try:
            duration = int(raw_duration)
            if duration > 0:
                return duration
        except (TypeError, ValueError):
            pass

        if self._contains_any(title_text, self.quick_keywords) or "quick win" in tags:
            return 15
        if priority in {"high", "goal"} or self._contains_any(title_text, self.deep_work_keywords):
            return 60
        return 30

    def _requires_deep_work(
        self,
        title_text: str,
        priority: str,
        tags: set[str],
        estimated_duration: int,
    ) -> bool:
        return (
            "deep work" in tags
            or estimated_duration >= 60
            or priority == "goal"
            or (priority == "high" and self._contains_any(title_text, self.deep_work_keywords))
        )

    def _can_split(self, title_text: str, estimated_duration: int) -> bool:
        return (
            estimated_duration >= 75
            or " and " in title_text
            or "/" in title_text
            or "&" in title_text
            or self._contains_any(title_text, {"knowledge base", "migration", "project", "strategy"})
        )

    def _recommended_chunks(self, title: str, can_split: bool, requires_deep_work: bool) -> list[str]:
        if not can_split:
            return []

        label = title.strip() or "task"
        chunks = [f"Clarify outcome for {label}"]
        if requires_deep_work:
            chunks.append("Draft or build the first pass")
        else:
            chunks.append("Complete the main action")
        chunks.append("Review and finalize")
        return chunks

    def _best_time_of_day(
        self,
        title_text: str,
        tags: set[str],
        estimated_duration: int,
        requires_deep_work: bool,
        priority: str,
    ) -> TimeOfDay:
        if estimated_duration <= 15 and not requires_deep_work:
            return "anytime"
        if self._contains_any(title_text, self.evening_keywords) or {"personal", "reading"} & tags:
            return "evening"
        if requires_deep_work or priority in {"high", "goal"}:
            return "morning"
        if self._contains_any(title_text, self.afternoon_keywords):
            return "afternoon"
        return "anytime"

    def _energy_required(self, priority: str, estimated_duration: int, requires_deep_work: bool) -> EffortLevel:
        if requires_deep_work or priority in {"high", "goal"} or estimated_duration >= 90:
            return "high"
        if priority == "medium" or estimated_duration >= 30:
            return "medium"
        return "low"

    def _context_switch_cost(
        self,
        title_text: str,
        tags: set[str],
        estimated_duration: int,
        requires_deep_work: bool,
    ) -> EffortLevel:
        if requires_deep_work or "deep work" in tags or estimated_duration >= 60:
            return "high"
        if estimated_duration >= 30 or self._contains_any(title_text, {"research", "review", "write"}):
            return "medium"
        return "low"

    def _tag_values(self, task: Any) -> set[str]:
        raw_tags = self._get(task, "tags", []) or []
        if not isinstance(raw_tags, list):
            return set()
        return {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}

    def _get(self, task: Any, key: str, default: Any = None) -> Any:
        if isinstance(task, dict):
            return task.get(key, default)
        return getattr(task, key, default)

    def _normalize(self, value: Any) -> str:
        return str(value or "").strip().lower()

    def _contains_any(self, text: str, keywords: set[str]) -> bool:
        return any(keyword in text for keyword in keywords)
