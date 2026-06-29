from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import List, Tuple

from productivity_operator.models import (
    CalendarBlock,
    DayPlanRequest,
    DayPlanResponse,
    Priority,
    ScheduledTask,
    Task,
    TaskType,
)

STRATEGIC_PROJECTS = {"Qu Pay Enablement", "Qu Pay Automation", "Operational Excellence", "AI Lab"}


def _localize_naive(dt: datetime) -> datetime:
    """Treat incoming datetimes as Akiflow local wall-clock time.

    Swagger examples and some calendar exports may include a Z/UTC offset.
    For this app, we do NOT convert those timestamps; we strip timezone info so
    12:50 stays 12:50 in the user's Akiflow calendar. This avoids Python
    comparing offset-aware and offset-naive datetimes and matches David's
    scheduling rule: use local time shown in Akiflow as source of truth.
    """
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _normalize_block(block: CalendarBlock) -> CalendarBlock:
    return block.model_copy(update={
        "start": _localize_naive(block.start),
        "end": _localize_naive(block.end),
    })


def score_task(task: Task, now: datetime) -> int:
    """Score tasks using David's decision framework."""
    score = 0
    if task.priority == Priority.goal:
        score += 500
    elif task.priority == Priority.high:
        score += 400
    elif task.priority == Priority.medium:
        score += 250
    elif task.priority == Priority.low:
        score += 100

    tagset = {t.lower() for t in task.tags}
    if "waiting" in tagset:
        score -= 1000
    if "quick win" in tagset:
        score += 40
    if "deep work" in tagset:
        score += 35
    if "research" in tagset:
        score -= 10
    if "reading" in tagset:
        score -= 80

    if task.project in STRATEGIC_PROJECTS:
        score += 60

    # Blocker hints in titles/descriptions get prime placement.
    text = f"{task.title} {task.description or ''}".lower()
    if any(word in text for word in ["follow up", "waiting", "unblock", "blocked", "send", "publish"]):
        score += 45

    if task.deadline:
        days = (task.deadline - now.date()).days
        if days <= 0:
            score += 300
        elif days <= 2:
            score += 200
        elif days <= 7:
            score += 100

    # Slight preference for shorter tasks when scores are close.
    score += max(0, 120 - task.duration) // 10
    return score


def rationale_for(task: Task, now: datetime) -> str:
    tagset = {t.lower() for t in task.tags}
    reasons: list[str] = []
    if task.priority in {Priority.goal, Priority.high}:
        reasons.append("high priority")
    if task.project in STRATEGIC_PROJECTS:
        reasons.append("strategic work")
    if "quick win" in tagset:
        reasons.append("quick win")
    if "deep work" in tagset:
        reasons.append("focus work")
    if task.deadline:
        days = (task.deadline - now.date()).days
        if days <= 7:
            reasons.append("deadline-sensitive")
    return ", ".join(reasons) or "best available fit"


def _merge_blocks(blocks: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not blocks:
        return []
    blocks = sorted(blocks)
    merged = [blocks[0]]
    for start, end in blocks[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def free_windows(day_start: datetime, day_end: datetime, busy: List[CalendarBlock], min_gap: int) -> List[Tuple[datetime, datetime]]:
    busy_ranges = _merge_blocks([(b.start, b.end) for b in busy if b.end > day_start and b.start < day_end])
    cursor = day_start
    windows: List[Tuple[datetime, datetime]] = []
    for start, end in busy_ranges:
        if start > cursor and (start - cursor).total_seconds() / 60 >= min_gap:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end and (day_end - cursor).total_seconds() / 60 >= min_gap:
        windows.append((cursor, day_end))
    return windows


def _place_tasks(tasks: List[Task], windows: List[Tuple[datetime, datetime]], min_gap: int, now: datetime) -> Tuple[List[ScheduledTask], List[Task]]:
    scheduled: List[ScheduledTask] = []
    remaining = list(tasks)
    mutable_windows = list(windows)

    for task in list(remaining):
        needed = timedelta(minutes=task.duration)
        for idx, (start, end) in enumerate(mutable_windows):
            if end - start >= needed:
                task_start = start
                task_end = start + needed
                scheduled.append(ScheduledTask(task=task, start=task_start, end=task_end, rationale=rationale_for(task, now)))
                next_start = task_end + timedelta(minutes=min_gap)
                if next_start < end:
                    mutable_windows[idx] = (next_start, end)
                else:
                    mutable_windows.pop(idx)
                remaining.remove(task)
                break
    return scheduled, remaining


def _add_lunch_if_missing(calendar: list[CalendarBlock], now: datetime, rules) -> list[CalendarBlock]:
    day = now.date()
    lunch_start = datetime.combine(day, time(rules.lunch_start_hour, 0))
    lunch_end = datetime.combine(day, time(rules.lunch_end_hour, 0))
    has_lunch = any(b.start <= lunch_start and b.end >= lunch_end and "lunch" in b.title.lower() for b in calendar)
    if has_lunch:
        return calendar
    return calendar + [CalendarBlock(title="Lunch", start=lunch_start, end=lunch_end, kind="event")]


def plan_day(req: DayPlanRequest) -> DayPlanResponse:
    now = _localize_naive(req.current_time)
    rules = req.rules
    day = now.date()

    work_start = datetime.combine(day, time(rules.workday_start_hour, 0))
    work_end = datetime.combine(day, time(rules.workday_end_hour, 0))
    personal_end = datetime.combine(day, time(rules.personal_end_hour, 0))

    effective_work_start = max(now, work_start)
    effective_personal_start = max(now, work_end)

    normalized_calendar = [_normalize_block(b) for b in req.calendar]
    busy = [b for b in _add_lunch_if_missing(normalized_calendar, now, rules) if b.end > now]

    open_tasks = [t for t in req.tasks if not t.done and "waiting" not in {x.lower() for x in t.tags}]
    work_tasks = [t for t in open_tasks if t.task_type == TaskType.work]
    personal_tasks = [t for t in open_tasks if t.task_type == TaskType.personal]

    work_tasks.sort(key=lambda t: score_task(t, now), reverse=True)
    personal_tasks.sort(key=lambda t: score_task(t, now), reverse=True)

    notes: List[str] = []
    scheduled: List[ScheduledTask] = []

    if effective_work_start < work_end:
        work_windows = free_windows(effective_work_start, work_end, busy, rules.min_gap_minutes)
        work_scheduled, unplaced_work = _place_tasks(work_tasks, work_windows, rules.min_gap_minutes, now)
        scheduled.extend(work_scheduled)
        total_scheduled = sum(item.task.duration for item in work_scheduled)
        if total_scheduled > 0 and total_scheduled + rules.daily_work_buffer_minutes > sum(int((e - s).total_seconds() / 60) for s, e in work_windows):
            notes.append("The workday is tight; the one-hour buffer may not be fully preserved.")
    else:
        unplaced_work = work_tasks
        notes.append("Workday window has already passed; no work tasks scheduled after 5:00 PM.")

    scheduled_blocks = [CalendarBlock(title=s.task.title, start=s.start, end=s.end, kind="task") for s in scheduled]
    personal_busy = busy + scheduled_blocks

    # Personal tasks can fill gaps during workday only if work tasks are already placed/deferred.
    personal_windows: list[tuple[datetime, datetime]] = []
    if effective_work_start < work_end:
        # Remaining daytime gaps after work tasks, for personal quick wins.
        daytime_gaps = free_windows(effective_work_start, work_end, personal_busy, rules.min_gap_minutes)
        personal_windows.extend(daytime_gaps)
    if effective_personal_start < personal_end:
        evening_gaps = free_windows(effective_personal_start, personal_end, personal_busy, rules.min_gap_minutes)
        personal_windows.extend(evening_gaps)

    if personal_windows:
        personal_scheduled, unplaced_personal = _place_tasks(personal_tasks, personal_windows, rules.min_gap_minutes, now)
        scheduled.extend(personal_scheduled)
    else:
        unplaced_personal = personal_tasks
        if now >= personal_end:
            notes.append("Personal planning window has already passed; no personal tasks scheduled after 9:00 PM.")

    deferred = unplaced_work + unplaced_personal
    return DayPlanResponse(scheduled=scheduled, deferred=deferred, notes=notes)
