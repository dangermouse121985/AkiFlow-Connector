from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
from productivity_operator.planning import (
    ApplyPlanRequest,
    ApplyPlanResponse,
    ApplyPlanService,
    PlanningContext,
    PlanningContextBuilder,
    PlanningSimulation,
    ScheduleOptimizer,
    ScheduleRecommendation,
    build_planning_simulation,
)
from productivity_operator.planner import PlannerEngine
from productivity_operator.scoring import TaskScorer

app = FastAPI(title="Operator", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = load_settings()
planning_context_builder = PlanningContextBuilder(source=settings.data_source)
planner = PlannerEngine()
schedule_optimizer = ScheduleOptimizer()
apply_plan_service = ApplyPlanService()
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
    return planning_context_builder.build("sample").to_day_plan_request().model_dump(mode="json")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0"}


@app.get("/manual")
def manual() -> dict[str, str]:
    return {"manual": PRODUCTIVITY_MANUAL}


@app.get("/planning/context", response_model=PlanningContext)
def planning_context() -> PlanningContext:
    return planning_context_builder.build()


@app.get("/planning/recommendation", response_model=ScheduleRecommendation)
def planning_recommendation() -> ScheduleRecommendation:
    context = planning_context_builder.build()
    return schedule_optimizer.optimize(context)


@app.get("/planning/simulation", response_model=PlanningSimulation)
def planning_simulation() -> PlanningSimulation:
    context = planning_context_builder.build()
    recommendation = schedule_optimizer.optimize(context)
    return build_planning_simulation(context, recommendation)


@app.post("/planning/apply", response_model=ApplyPlanResponse)
def apply_plan(req: ApplyPlanRequest | None = None) -> ApplyPlanResponse:
    context = planning_context_builder.build()
    recommendation = schedule_optimizer.optimize(context)
    simulation = build_planning_simulation(context, recommendation)
    return apply_plan_service.apply(simulation, confirm=req.confirm if req else False)


@app.post("/plan/day", response_model=DayPlanResponse)
def plan_day_endpoint(req: DayPlanRequest) -> DayPlanResponse:
    context = planning_context_builder.from_day_plan_request(req)
    return planner.plan_day(context)


@app.post("/commands/akiflow-ai", response_model=CommandResponse)
def akiflow_command_endpoint(req: DayPlanRequest) -> CommandResponse:
    context = planning_context_builder.from_day_plan_request(req)
    plan = planner.plan_day(context)
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
