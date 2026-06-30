from __future__ import annotations

from productivity_operator.models import DayPlanRequest, DayPlanResponse
from productivity_operator.planning.context import PlanningContext
from productivity_operator.planning.day_planner import plan_day


class PlannerEngine:
    """
    Central planning engine for Operator.

    Pipeline:
    1. Collect
    2. Filter
    3. Prioritize
    4. Schedule
    5. Explain
    """

    def plan_day(self, context: PlanningContext) -> DayPlanResponse:
        collected = self.collect(context)
        filtered = self.filter(collected)
        prioritized = self.prioritize(filtered)
        scheduled = self.schedule(prioritized)
        explained = self.explain(scheduled)
        return explained

    def plan_day_request(self, request: DayPlanRequest) -> DayPlanResponse:
        return self.plan_day(PlanningContext(
            current_datetime=request.current_time,
            available_minutes_today=0,
            tasks=request.tasks,
            calendar_events=request.calendar,
            source="sample",
            rules=request.rules,
        ))

    def collect(self, context: PlanningContext) -> PlanningContext:
        return context

    def filter(self, context: PlanningContext) -> PlanningContext:
        return context

    def prioritize(self, context: PlanningContext) -> PlanningContext:
        return context

    def schedule(self, context: PlanningContext) -> DayPlanResponse:
        return plan_day(context.to_day_plan_request())

    def explain(self, response: DayPlanResponse) -> DayPlanResponse:
        return response
