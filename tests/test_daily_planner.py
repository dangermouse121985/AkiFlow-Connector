from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from productivity_operator.models import SchedulingRules
from productivity_operator.planning.context import PlanningContext
from productivity_operator.planning.daily_planner import DailyPlannerService
from productivity_operator.task_registry import OperatorTask, TaskRegistry


def make_context() -> PlanningContext:
    return PlanningContext(
        current_datetime=datetime(2026, 6, 30, 8, 0),
        available_minutes_today=480,
        tasks=[],
        analyzed_tasks=[],
        scored_tasks=[],
        calendar_events=[],
        source="akiflow",
        rules=SchedulingRules(),
    )


def make_registry(tasks: list[OperatorTask]) -> TaskRegistry:
    registry = TaskRegistry()
    registry.load_from_akiflow(tasks)
    return registry


def make_task(
    task_id: str,
    title: str,
    *,
    duration: int = 60,
    priority: str = "medium",
    project_name: str | None = "Work",
    tags: list[str] | None = None,
    scheduled_start: str | None = None,
) -> OperatorTask:
    return OperatorTask(
        task_id=task_id,
        title=title,
        project_name=project_name,
        duration=duration,
        priority=priority,
        tags=tags or [],
        scheduled_start=scheduled_start,
        last_synced_at=datetime(2026, 6, 30, 7, 30),
    )


class DailyPlannerServiceTests(unittest.TestCase):
    def test_does_not_schedule_work_outside_workday(self) -> None:
        registry = make_registry(
            [
                make_task("task-1", "Deep work", duration=90, priority="high"),
                make_task("task-2", "Quick work", duration=30, priority="medium"),
            ]
        )

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        for task in plan.recommended_plan:
            start = datetime.fromisoformat(task.new_scheduled_time)
            end = start + timedelta(minutes=task.duration)
            self.assertGreaterEqual(start.hour, 9)
            self.assertLessEqual(end.hour, 17)

    def test_does_not_schedule_personal_after_9_pm(self) -> None:
        registry = make_registry(
            [
                make_task("task-1", "Personal errand", duration=120, project_name="Personal"),
                make_task("task-2", "Family admin", duration=120, project_name="Personal"),
                make_task("task-3", "Home workout", duration=120, project_name="Personal"),
            ]
        )

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        for task in plan.recommended_plan:
            start = datetime.fromisoformat(task.new_scheduled_time)
            end = start + timedelta(minutes=task.duration)
            if "Personal" in (task.project or ""):
                self.assertLessEqual(end.hour, 21)

    def test_leaves_one_hour_workday_buffer(self) -> None:
        registry = make_registry(
            [
                make_task(f"task-{index}", f"Work task {index}", duration=60)
                for index in range(1, 8)
            ]
        )

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)
        work_minutes = sum(task.duration for task in plan.recommended_plan if task.project == "Work")

        self.assertLessEqual(work_minutes, 360)

    def test_uses_only_valid_task_ids(self) -> None:
        registry = make_registry([make_task("task-1", "Valid work")])

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        self.assertEqual([task.task_id for task in plan.recommended_plan], ["task-1"])

    def test_skips_unresolved_tasks(self) -> None:
        registry = TaskRegistry()
        registry._tasks_by_id[""] = make_task("", "No id")

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        self.assertEqual(plan.recommended_plan, [])
        self.assertEqual(plan.skipped_tasks[0].reason, "Missing task_id.")

    def test_preview_does_not_write(self) -> None:
        registry = make_registry([make_task("task-1", "Valid work")])
        service = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0))

        plan = service.build_plan(make_context(), registry)

        self.assertEqual(len(plan.recommended_plan), 1)

    def test_never_schedules_before_today_when_context_is_stale(self) -> None:
        registry = make_registry([make_task("task-1", "Valid work")])
        context = make_context()
        context.current_datetime = datetime(2025, 1, 1, 8, 0)

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(context, registry)

        scheduled_day = datetime.fromisoformat(plan.recommended_plan[0].new_scheduled_time).date()
        self.assertGreaterEqual(scheduled_day, date(2026, 6, 30))

    def test_rolls_work_tasks_to_next_day_after_work_buffer_cutoff(self) -> None:
        registry = make_registry([make_task("task-1", "Valid work")])
        context = make_context()
        context.current_datetime = datetime(2026, 6, 30, 16, 30)

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 16, 30)).build_plan(context, registry)

        scheduled_start = datetime.fromisoformat(plan.recommended_plan[0].new_scheduled_time)
        self.assertEqual(scheduled_start.date(), date(2026, 7, 1))
        self.assertEqual(scheduled_start.hour, 9)

    def test_scheduled_incomplete_task_is_replanned_with_original_time_preserved(self) -> None:
        registry = make_registry(
            [
                make_task(
                    "task-1",
                    "Carry over unfinished scheduled task",
                    scheduled_start="2026-06-29T10:00:00",
                )
            ]
        )

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        self.assertEqual(plan.recommended_plan[0].task_id, "task-1")
        self.assertEqual(plan.recommended_plan[0].old_scheduled_time, "2026-06-29T10:00:00")
        self.assertGreaterEqual(
            datetime.fromisoformat(plan.recommended_plan[0].new_scheduled_time),
            datetime(2026, 6, 30, 9, 0),
        )

    def test_duration_values_that_look_like_seconds_are_coerced_to_minutes(self) -> None:
        registry = make_registry([make_task("task-1", "One hour task", duration=3600)])

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        self.assertEqual(len(plan.recommended_plan), 1)
        self.assertEqual(plan.recommended_plan[0].duration, 60)

    def test_existing_scheduled_task_blocks_that_time_slot(self) -> None:
        registry = make_registry(
            [
                make_task("task-1", "Already scheduled", duration=60, scheduled_start="2026-06-30T09:00:00"),
                make_task("task-2", "New task", duration=60, priority="high"),
            ]
        )

        plan = DailyPlannerService(now_provider=lambda: datetime(2026, 6, 30, 8, 0)).build_plan(make_context(), registry)

        proposed_starts = {
            task.task_id: datetime.fromisoformat(task.new_scheduled_time)
            for task in plan.recommended_plan
        }
        self.assertNotEqual(proposed_starts.get("task-2"), datetime(2026, 6, 30, 9, 0))
        self.assertEqual(len(set(proposed_starts.values())), len(proposed_starts))


if __name__ == "__main__":
    unittest.main()
