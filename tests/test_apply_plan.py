from __future__ import annotations

import unittest
from datetime import datetime
from typing import Any

from productivity_operator.planning.apply_plan import ApplyPlanService
from productivity_operator.planning.simulation import ChangesSummary, PlanningSimulation
from productivity_operator.services import AkiflowServiceError
from productivity_operator.task_registry import OperatorTask, TaskRegistry


class FakeAkiflowService:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def plan_task(self, task_id: str, start_datetime: str) -> dict[str, Any]:
        self.calls.append((task_id, start_datetime))
        if self.fail:
            raise AkiflowServiceError("planning failed")
        return {"ok": True}


def make_operator_task(
    task_id: str,
    title: str,
    scheduled_start: str | None = "2026-06-30T09:00:00",
) -> OperatorTask:
    return OperatorTask(
        task_id=task_id,
        title=title,
        duration=30,
        scheduled_start=scheduled_start,
        last_synced_at=datetime(2026, 6, 30, 8, 0),
    )


def make_simulation(tasks: list[dict[str, Any]]) -> PlanningSimulation:
    return PlanningSimulation(
        current_plan=[],
        recommended_plan=tasks,
        deferred_tasks=[],
        remaining_minutes=120,
        explanation="test",
        changes_summary=ChangesSummary(
            recommended_count=len(tasks),
            deferred_count=0,
            would_modify_akiflow=False,
        ),
    )


class ApplyPlanServiceTests(unittest.TestCase):
    def test_valid_task_id_schedules_successfully(self) -> None:
        registry = TaskRegistry()
        registry.load_from_akiflow([make_operator_task("task-1", "Write update")])
        akiflow = FakeAkiflowService()
        service = ApplyPlanService(akiflow, registry)

        response = service.apply(
            make_simulation([{"title": "Write update", "duration": 30}]),
            datetime(2026, 6, 30, 10, 0),
            confirm=True,
        )

        self.assertEqual(akiflow.calls, [("task-1", "2026-06-30T10:00:00")])
        self.assertEqual(len(response.succeeded_actions), 1)
        self.assertEqual(response.succeeded_actions[0]["status"], "succeeded")

    def test_missing_task_id_skips(self) -> None:
        registry = TaskRegistry()
        akiflow = FakeAkiflowService()
        service = ApplyPlanService(akiflow, registry)

        response = service.apply(
            make_simulation([{"title": "Missing task", "duration": 30}]),
            datetime(2026, 6, 30, 10, 0),
            confirm=True,
        )

        self.assertEqual(akiflow.calls, [])
        self.assertEqual(len(response.skipped_actions), 1)
        self.assertEqual(response.skipped_actions[0]["reason"], "No matching task in registry")
        self.assertEqual(response.skipped_actions[0]["status"], "skipped")

    def test_ambiguous_title_skips(self) -> None:
        registry = TaskRegistry()
        registry.load_from_akiflow(
            [
                make_operator_task("task-1", "Duplicate"),
                make_operator_task("task-2", "Duplicate"),
            ]
        )
        akiflow = FakeAkiflowService()
        service = ApplyPlanService(akiflow, registry)

        response = service.apply(
            make_simulation([{"title": "Duplicate", "duration": 30}]),
            datetime(2026, 6, 30, 10, 0),
            confirm=True,
        )

        self.assertEqual(akiflow.calls, [])
        self.assertEqual(len(response.skipped_actions), 1)
        self.assertEqual(response.skipped_actions[0]["reason"], "Multiple matching tasks in registry")

    def test_dry_run_makes_zero_writes(self) -> None:
        registry = TaskRegistry()
        registry.load_from_akiflow([make_operator_task("task-1", "Write update")])
        akiflow = FakeAkiflowService()
        service = ApplyPlanService(akiflow, registry)

        response = service.apply(
            make_simulation([{"title": "Write update", "duration": 30}]),
            datetime(2026, 6, 30, 10, 0),
            confirm=False,
        )

        self.assertEqual(akiflow.calls, [])
        self.assertTrue(response.dry_run)
        self.assertEqual(response.actions[0]["task_id"], "task-1")
        self.assertEqual(response.actions[0]["status"], "proposed")

    def test_confirm_true_calls_plan_task_only_for_valid_actions(self) -> None:
        registry = TaskRegistry()
        registry.load_from_akiflow([make_operator_task("task-1", "Valid task")])
        akiflow = FakeAkiflowService()
        service = ApplyPlanService(akiflow, registry)

        response = service.apply(
            make_simulation(
                [
                    {"title": "Valid task", "duration": 30},
                    {"title": "Unknown task", "duration": 30},
                ]
            ),
            datetime(2026, 6, 30, 10, 0),
            confirm=True,
        )

        self.assertEqual(akiflow.calls, [("task-1", "2026-06-30T10:00:00")])
        self.assertEqual(len(response.succeeded_actions), 1)
        self.assertEqual(len(response.skipped_actions), 1)


if __name__ == "__main__":
    unittest.main()
