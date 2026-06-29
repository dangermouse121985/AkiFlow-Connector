from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Priority(str, Enum):
    none = "NONE"
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    goal = "GOAL"


class TaskType(str, Enum):
    work = "work"
    personal = "personal"


class TaskStatus(str, Enum):
    inbox = "inbox"
    planned = "planned"
    someday = "someday"
    done = "done"


class Task(BaseModel):
    id: Optional[str] = None
    title: str
    duration: int = Field(..., description="Duration in minutes")
    priority: Priority = Priority.none
    project: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    deadline: Optional[date] = None
    task_type: TaskType = TaskType.work
    status: TaskStatus = TaskStatus.inbox
    description: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    done: bool = False


class CalendarBlock(BaseModel):
    title: str
    start: datetime
    end: datetime
    movable: bool = False
    kind: str = "event"  # event, task, habit, buffer


class SchedulingRules(BaseModel):
    workday_start_hour: int = 9
    workday_end_hour: int = 17
    personal_end_hour: int = 21
    lunch_start_hour: int = 12
    lunch_end_hour: int = 13
    preserve_morning_for_high_value: bool = True
    daily_work_buffer_minutes: int = 60
    min_gap_minutes: int = 15
    timezone_label: str = "local time shown in Akiflow"


class DayPlanRequest(BaseModel):
    current_time: datetime
    tasks: List[Task]
    calendar: List[CalendarBlock]
    rules: SchedulingRules = Field(default_factory=SchedulingRules)


class ScheduledTask(BaseModel):
    task: Task
    start: datetime
    end: datetime
    rationale: str


class DayPlanResponse(BaseModel):
    scheduled: List[ScheduledTask]
    deferred: List[Task]
    notes: List[str] = Field(default_factory=list)
    command: Optional[str] = None


class InboxReviewItem(BaseModel):
    original_title: str
    recommended_title: str
    project: Optional[str] = None
    duration: int = 30
    priority: Priority = Priority.medium
    tags: List[str] = Field(default_factory=list)
    task_type: TaskType = TaskType.work
    reason: str


class InboxReviewRequest(BaseModel):
    items: List[str]


class InboxReviewResponse(BaseModel):
    recommendations: List[InboxReviewItem]
