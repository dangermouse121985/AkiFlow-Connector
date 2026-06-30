from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from productivity_operator.models import CalendarBlock, SchedulingRules
from productivity_operator.planning.context import PlanningContext
from productivity_operator.task_registry import OperatorTask, TaskRegistry


class DailyPlanTask(BaseModel):
    task_id: str
    title: str
    project: str | None = None
    duration: int
    old_scheduled_time: str | None = None
    new_scheduled_time: str
    reason: str


class DailyPlanSkippedTask(BaseModel):
    task_id: str | None = None
    title: str
    reason: str


class AvailableBlock(BaseModel):
    start: datetime
    end: datetime
    kind: Literal["work", "personal"]
    minutes: int


class DailyPlanRecommendation(BaseModel):
    recommended_plan: list[DailyPlanTask] = Field(default_factory=list)
    skipped_tasks: list[DailyPlanSkippedTask] = Field(default_factory=list)
    available_blocks: list[AvailableBlock] = Field(default_factory=list)
    explanation: str


@dataclass
class _MutableBlock:
    start: datetime
    end: datetime
    kind: Literal["work", "personal"]

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() / 60))


@dataclass
class _Candidate:
    task: OperatorTask
    duration: int
    task_type: Literal["work", "personal"]
    priority_score: int
    is_blocking: bool
    is_deep_work: bool
    is_quick_win: bool


class DailyPlannerService:
    """Read-only registry-backed daily planner."""

    def __init__(self, now_provider: object | None = None) -> None:
        self._now_provider = now_provider

    def build_plan(self, context: PlanningContext, registry: TaskRegistry) -> DailyPlanRecommendation:
        selected_day = self._selected_day(context)
        candidates, skipped_tasks = self._candidates(registry)
        scheduled_blocks = self._scheduled_task_blocks(registry, selected_day)
        work_blocks = self._available_blocks(context, selected_day, "work", scheduled_blocks)
        personal_blocks = self._available_blocks(context, selected_day, "personal", scheduled_blocks)
        available_blocks = [
            self._block_model(block)
            for block in [*work_blocks, *personal_blocks]
            if block.minutes > 0
        ]

        recommended_plan: list[DailyPlanTask] = []
        work_capacity = max(
            0,
            sum(block.minutes for block in work_blocks) - context.rules.daily_work_buffer_minutes,
        )

        work_candidates = [candidate for candidate in candidates if candidate.task_type == "work"]
        personal_candidates = [candidate for candidate in candidates if candidate.task_type == "personal"]

        work_capacity = self._place_tasks(
            candidates=work_candidates,
            blocks=work_blocks,
            recommended_plan=recommended_plan,
            skipped_tasks=skipped_tasks,
            capacity_minutes=work_capacity,
        )

        self._place_tasks(
            candidates=personal_candidates,
            blocks=personal_blocks,
            recommended_plan=recommended_plan,
            skipped_tasks=skipped_tasks,
            capacity_minutes=sum(block.minutes for block in personal_blocks),
        )

        self._place_tasks(
            candidates=[candidate for candidate in personal_candidates if candidate.task.task_id not in self._planned_ids(recommended_plan)],
            blocks=work_blocks,
            recommended_plan=recommended_plan,
            skipped_tasks=skipped_tasks,
            capacity_minutes=work_capacity,
            reason_suffix="Personal task filling remaining workday gap after work tasks were placed.",
        )

        planned_ids = self._planned_ids(recommended_plan)
        for candidate in candidates:
            if candidate.task.task_id not in planned_ids and not self._already_skipped(candidate, skipped_tasks):
                skipped_tasks.append(
                    DailyPlanSkippedTask(
                        task_id=candidate.task.task_id,
                        title=candidate.task.title,
                        reason="No available block fit this task while preserving planner rules.",
                    )
                )

        explanation = (
            f"Built a read-only daily plan with {len(recommended_plan)} task(s), "
            f"using registry task ids and preserving at least {context.rules.daily_work_buffer_minutes} "
            "minute(s) of workday buffer."
        )
        return DailyPlanRecommendation(
            recommended_plan=recommended_plan,
            skipped_tasks=skipped_tasks,
            available_blocks=available_blocks,
            explanation=explanation,
        )

    def _place_tasks(
        self,
        *,
        candidates: list[_Candidate],
        blocks: list[_MutableBlock],
        recommended_plan: list[DailyPlanTask],
        skipped_tasks: list[DailyPlanSkippedTask],
        capacity_minutes: int,
        reason_suffix: str | None = None,
    ) -> int:
        planned_ids = self._planned_ids(recommended_plan)
        remaining_capacity = capacity_minutes

        for block in blocks:
            while block.minutes > 0 and remaining_capacity > 0:
                candidate = self._best_candidate_for_block(
                    [
                        item
                        for item in candidates
                        if item.task.task_id not in planned_ids
                        and item.duration <= block.minutes
                        and item.duration <= remaining_capacity
                    ],
                    block,
                )
                if candidate is None:
                    break

                start = block.start
                block.start = block.start + timedelta(minutes=candidate.duration)
                remaining_capacity -= candidate.duration
                planned_ids.add(candidate.task.task_id)
                recommended_plan.append(
                    DailyPlanTask(
                        task_id=candidate.task.task_id,
                        title=candidate.task.title,
                        project=candidate.task.project_name,
                        duration=candidate.duration,
                        old_scheduled_time=candidate.task.scheduled_start,
                        new_scheduled_time=start.isoformat(),
                        reason=reason_suffix or self._reason(candidate, block),
                    )
                )

        return remaining_capacity

    def _best_candidate_for_block(
        self,
        candidates: list[_Candidate],
        block: _MutableBlock,
    ) -> _Candidate | None:
        if not candidates:
            return None

        large_block = block.minutes >= 60
        return max(
            candidates,
            key=lambda item: (
                item.priority_score,
                1 if item.is_blocking else 0,
                1 if large_block and item.is_deep_work else 0,
                1 if not large_block and item.is_quick_win else 0,
                -item.duration,
                item.task.title.lower(),
            ),
        )

    def _available_blocks(
        self,
        context: PlanningContext,
        selected_day: date,
        kind: Literal["work", "personal"],
        scheduled_blocks: list[_MutableBlock],
    ) -> list[_MutableBlock]:
        rules = context.rules
        if kind == "work":
            blocks = [
                _MutableBlock(
                    self._at(selected_day, rules.workday_start_hour),
                    self._at(selected_day, rules.lunch_start_hour),
                    "work",
                ),
                _MutableBlock(
                    self._at(selected_day, rules.lunch_end_hour),
                    self._at(selected_day, rules.workday_end_hour),
                    "work",
                ),
            ]
        else:
            blocks = [
                _MutableBlock(
                    self._at(selected_day, rules.workday_end_hour),
                    self._at(selected_day, rules.personal_end_hour),
                    "personal",
                )
            ]

        planning_start = max(context.current_datetime.replace(tzinfo=None), self._now())
        if planning_start.date() == selected_day:
            blocks = [
                _MutableBlock(max(block.start, planning_start.replace(second=0, microsecond=0)), block.end, block.kind)
                for block in blocks
                if block.end > planning_start
            ]

        busy_events = [
            event
            for event in context.calendar_events
            if event.start.date() <= selected_day <= event.end.date()
        ]
        for event in busy_events:
            blocks = self._subtract_event(blocks, event)
        for scheduled_block in scheduled_blocks:
            blocks = self._subtract_block(blocks, scheduled_block)
        return [block for block in blocks if block.minutes > 0]

    def _subtract_event(self, blocks: list[_MutableBlock], event: CalendarBlock) -> list[_MutableBlock]:
        return self._subtract_block(
            blocks,
            _MutableBlock(event.start.replace(tzinfo=None), event.end.replace(tzinfo=None), "work"),
        )

    def _subtract_block(self, blocks: list[_MutableBlock], busy_block: _MutableBlock) -> list[_MutableBlock]:
        updated: list[_MutableBlock] = []
        for block in blocks:
            start = max(block.start, busy_block.start)
            end = min(block.end, busy_block.end)
            if end <= block.start or start >= block.end:
                updated.append(block)
                continue
            if block.start < start:
                updated.append(_MutableBlock(block.start, start, block.kind))
            if end < block.end:
                updated.append(_MutableBlock(end, block.end, block.kind))
        return updated

    def _scheduled_task_blocks(self, registry: TaskRegistry, selected_day: date) -> list[_MutableBlock]:
        blocks: list[_MutableBlock] = []
        for task in registry.all():
            if task.done or str(task.status or "").lower() in {"done", "completed", "complete"}:
                continue
            start = self._parse_datetime(task.scheduled_start)
            if start is None or start.date() != selected_day:
                continue
            duration = self._duration(task)
            blocks.append(_MutableBlock(start, start + timedelta(minutes=duration), self._task_type(task)))
        return blocks

    def _candidates(self, registry: TaskRegistry) -> tuple[list[_Candidate], list[DailyPlanSkippedTask]]:
        candidates: list[_Candidate] = []
        skipped: list[DailyPlanSkippedTask] = []
        for task in registry.all():
            if not task.task_id:
                skipped.append(DailyPlanSkippedTask(title=task.title, reason="Missing task_id."))
                continue
            if task.done or str(task.status or "").lower() in {"done", "completed", "complete"}:
                skipped.append(DailyPlanSkippedTask(task_id=task.task_id, title=task.title, reason="Completed task."))
                continue
            duration = self._duration(task)
            if duration <= 0:
                skipped.append(DailyPlanSkippedTask(task_id=task.task_id, title=task.title, reason="Missing duration."))
                continue
            candidates.append(
                _Candidate(
                    task=task,
                    duration=duration,
                    task_type=self._task_type(task),
                    priority_score=self._priority_score(task),
                    is_blocking=self._has_any(task, {"block", "blocking", "unblock", "waiting"}),
                    is_deep_work=duration >= 60 or self._has_any(task, {"draft", "write", "research", "design", "strategy", "build"}),
                    is_quick_win=duration <= 30 or self._has_any(task, {"quick", "email", "reply", "review", "send"}),
                )
            )
        return candidates, skipped

    def _task_type(self, task: OperatorTask) -> Literal["work", "personal"]:
        if self._has_any(task, {"personal", "home", "family", "errand", "grocery", "workout", "doctor"}):
            return "personal"
        return "work"

    def _priority_score(self, task: OperatorTask) -> int:
        priority = str(task.priority or "").strip().lower()
        if priority in {"goal", "highest", "urgent"}:
            return 4
        if priority in {"high", "important", "p1"}:
            return 3
        if priority in {"medium", "normal", "p2"}:
            return 2
        if priority in {"low", "p3"}:
            return 1
        return 0

    def _has_any(self, task: OperatorTask, keywords: set[str]) -> bool:
        haystack = " ".join(
            [
                task.title,
                task.description or "",
                task.project_name or "",
                " ".join(task.tags),
            ]
        ).lower()
        return any(keyword in haystack for keyword in keywords)

    def _reason(self, candidate: _Candidate, block: _MutableBlock) -> str:
        labels: list[str] = []
        if candidate.priority_score >= 3:
            labels.append("High priority")
        if candidate.is_blocking:
            labels.append("Blocking/unblocking work")
        if candidate.is_deep_work and block.minutes >= 60:
            labels.append("Deep Work in a large block")
        if candidate.is_quick_win and block.minutes < 60:
            labels.append("Quick Win in a small gap")
        if candidate.task_type == "personal":
            labels.append("Personal task after work hours")
        return " · ".join(labels) if labels else "Fits available time and planner rules"

    def _duration(self, task: OperatorTask) -> int:
        if not isinstance(task.duration, int) or task.duration <= 0:
            return 30
        if task.duration >= 10000:
            return max(1, round(task.duration / 60000))
        if task.duration > 1440:
            return max(1, round(task.duration / 60))
        return task.duration

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _planned_ids(self, recommended_plan: list[DailyPlanTask]) -> set[str]:
        return {task.task_id for task in recommended_plan}

    def _already_skipped(self, candidate: _Candidate, skipped_tasks: list[DailyPlanSkippedTask]) -> bool:
        return any(task.task_id == candidate.task.task_id for task in skipped_tasks)

    def _block_model(self, block: _MutableBlock) -> AvailableBlock:
        return AvailableBlock(start=block.start, end=block.end, kind=block.kind, minutes=block.minutes)

    def _at(self, selected_day: date, hour: int) -> datetime:
        return datetime.combine(selected_day, time(hour=hour))

    def _selected_day(self, context: PlanningContext) -> date:
        planning_start = max(context.current_datetime.replace(tzinfo=None), self._now())
        work_cutoff = self._at(planning_start.date(), context.rules.workday_end_hour) - timedelta(
            minutes=context.rules.daily_work_buffer_minutes
        )
        if planning_start >= work_cutoff:
            return planning_start.date() + timedelta(days=1)
        return planning_start.date()

    def _now(self) -> datetime:
        if callable(self._now_provider):
            return self._now_provider().replace(tzinfo=None)
        return datetime.now().replace(tzinfo=None)
