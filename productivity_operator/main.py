from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from productivity_operator.commands import akiflow_ai_command
from productivity_operator.inbox import review_inbox
from productivity_operator.manual import PRODUCTIVITY_MANUAL
from productivity_operator.models import DayPlanRequest, DayPlanResponse, InboxReviewRequest, InboxReviewResponse
from productivity_operator.planning.day_planner import plan_day

app = FastAPI(title="Operator", version="0.3.0")


class CommandResponse(BaseModel):
    command: str
    plan: DayPlanResponse


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    index_path = Path(__file__).parent / "web" / "index.html"
    return index_path.read_text(encoding="utf-8")


@app.get("/sample")
def sample() -> dict:
    sample_path = Path(__file__).parent.parent / "sample_day_request.json"
    return json.loads(sample_path.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0"}


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
