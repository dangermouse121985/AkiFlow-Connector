from __future__ import annotations

from productivity_operator.models import DayPlanRequest, DayPlanResponse
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

    def plan_day(self, request: DayPlanRequest) -> DayPlanResponse:
        collected = self.collect(request)
        filtered = self.filter(collected)
        prioritized = self.prioritize(filtered)
        scheduled = self.schedule(prioritized)
        explained = self.explain(scheduled)
        return explained

    def collect(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def filter(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def prioritize(self, request: DayPlanRequest) -> DayPlanRequest:
        return request

    def schedule(self, request: DayPlanRequest) -> DayPlanResponse:
        return plan_day(request)

    def explain(self, response: DayPlanResponse) -> DayPlanResponse:
        return response
