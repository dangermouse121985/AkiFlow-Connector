from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from productivity_operator.analysis import TaskAnalyzer
from productivity_operator.commands import akiflow_ai_command
from productivity_operator.config import load_settings
from productivity_operator.inbox import review_inbox
from productivity_operator.manual import PRODUCTIVITY_MANUAL
from productivity_operator.models import (
    DayPlanRequest,
    DayPlanResponse,
    InboxReviewRequest,
    InboxReviewResponse,
)
from productivity_operator.planner import PlannerEngine
from productivity_operator.scoring import TaskScorer
from productivity_operator.services import AkiflowService, AkiflowServiceError

app = FastAPI(title="Operator", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = load_settings()
akiflow_service = AkiflowService()
planner = PlannerEngine(akiflow_service=akiflow_service, data_source=settings.data_source)
task_scorer = TaskScorer()
task_analyzer = TaskAnalyzer()


class CommandResponse(BaseModel):
    command: str
    plan: DayPlanResponse


class AnalyzeTasksRequest(BaseModel):
    tasks: list[dict[str, Any]]


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    index_path = Path(__file__).parent / "web" / "index.html"
    return index_path.read_text(encoding="utf-8")


@app.get("/sample")
def sample() -> dict:
    try:
        return planner.load_day_request().model_dump(mode="json")
    except AkiflowServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0"}


@app.get("/manual")
def manual() -> dict[str, str]:
    return {"manual": PRODUCTIVITY_MANUAL}


@app.get("/akiflow/login")
def akiflow_login() -> RedirectResponse:
    try:
        return RedirectResponse(akiflow_service.authorization_url())
    except AkiflowServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/akiflow/oauth/callback", response_class=HTMLResponse)
def akiflow_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> str:
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Akiflow OAuth code or state.")

    try:
        akiflow_service.complete_oauth_callback(code, state)
    except AkiflowServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return """
    <!doctype html>
    <html>
      <head><title>Akiflow Connected</title></head>
      <body>
        <h1>Akiflow connected</h1>
        <p>You can return to Operator.</p>
      </body>
    </html>
    """


@app.post("/plan/day", response_model=DayPlanResponse)
def plan_day_endpoint(req: DayPlanRequest) -> DayPlanResponse:
    return planner.plan_day(req)


@app.post("/commands/akiflow-ai", response_model=CommandResponse)
def akiflow_command_endpoint(req: DayPlanRequest) -> CommandResponse:
    plan = planner.plan_day(req)
    command = akiflow_ai_command(plan)
    plan.command = command
    return CommandResponse(command=command, plan=plan)


@app.post("/score/tasks")
def score_tasks(req: DayPlanRequest) -> dict:
    scores = [task_scorer.score_task(task, req.current_time).__dict__ for task in req.tasks]
    scores.sort(key=lambda item: item["score"], reverse=True)
    return {"scores": scores}


@app.post("/analyze/tasks")
def analyze_tasks(req: AnalyzeTasksRequest) -> dict:
    analyzed_tasks = []

    for task in req.tasks:
        analysis = task_analyzer.analyze_task(task).__dict__
        analyzed_tasks.append({**task, "analysis": analysis})

    return {"tasks": analyzed_tasks}


@app.post("/inbox/review", response_model=InboxReviewResponse)
def inbox_review_endpoint(req: InboxReviewRequest) -> InboxReviewResponse:
    return review_inbox(req)


def main() -> None:
    import uvicorn

    uvicorn.run("productivity_operator.main:app", host="127.0.0.1", port=8000, reload=True)
