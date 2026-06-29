from __future__ import annotations

from datetime import datetime

from productivity_operator.models import DayPlanResponse


def _format_time(dt: datetime, include_day: bool = False) -> str:
    # Cross-platform hour formatting. Avoid %-I because Windows does not support it.
    hour = dt.strftime("%I").lstrip("0") or "12"
    minute = dt.strftime("%M")
    ampm = dt.strftime("%p")
    time_text = f"{hour}:{minute} {ampm}"
    if include_day:
        return f"{dt.strftime('%A')} {time_text}"
    return time_text


def akiflow_ai_command(plan: DayPlanResponse) -> str:
    lines: list[str] = []
    lines.append("Schedule the rest of my day exactly as listed below.")
    lines.append("")
    lines.append("Use the local time shown in my Akiflow calendar. Do not convert times to or from UTC.")
    lines.append("Do not move existing calendar meetings.")
    lines.append("Do not schedule work tasks after 5:00 PM.")
    lines.append("Personal tasks may be scheduled after 5:00 PM and up to 9:00 PM.")
    lines.append("If a task is already completed, skip it.")
    lines.append("")
    if plan.scheduled:
        lines.append("Move or schedule these tasks:")
        for item in plan.scheduled:
            start = _format_time(item.start, include_day=True)
            end = _format_time(item.end)
            lines.append(f"- {item.task.title}: {start}–{end}")
    else:
        lines.append("No tasks should be scheduled for the remaining day.")

    if plan.deferred:
        lines.append("")
        lines.append("Leave these tasks unscheduled or keep them on their current future dates:")
        for task in plan.deferred:
            lines.append(f"- {task.title}")

    if plan.notes:
        lines.append("")
        lines.append("Notes:")
        for note in plan.notes:
            lines.append(f"- {note}")

    lines.append("")
    lines.append("After scheduling, summarize what moved and what remained unscheduled.")
    return "\n".join(lines)
