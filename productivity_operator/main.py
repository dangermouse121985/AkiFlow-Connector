from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from productivity_operator.commands import akiflow_ai_command
from productivity_operator.inbox import review_inbox
from productivity_operator.manual import PRODUCTIVITY_MANUAL
from productivity_operator.models import DayPlanRequest, DayPlanResponse, InboxReviewRequest, InboxReviewResponse
from productivity_operator.planning.day_planner import plan_day

app = FastAPI(title="Operator MCP Server", version="0.2.0")


class CommandResponse(BaseModel):
    command: str
    plan: DayPlanResponse


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/manual")
def manual() -> dict[str, str]:
    return {"manual": PRODUCTIVITY_MANUAL}


@app.post("/plan/day", response_model=DayPlanResponse)
def plan_day_endpoint(req: DayPlanRequest) -> DayPlanResponse:
    return plan_day(req)


@app.post("/commands/akiflow-ai", response_model=CommandResponse)
def akiflow_command_endpoint(req: DayPlanRequest) -> CommandResponse:
    plan = plan_day(req)
    command = akiflow_ai_command(plan)
    plan.command = command
    return CommandResponse(command=command, plan=plan)


@app.post("/inbox/review", response_model=InboxReviewResponse)
def inbox_review_endpoint(req: InboxReviewRequest) -> InboxReviewResponse:
    return review_inbox(req)


def main() -> None:
    import uvicorn

    uvicorn.run("productivity_operator.main:app", host="127.0.0.1", port=8000, reload=True)
