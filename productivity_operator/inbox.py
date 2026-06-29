from __future__ import annotations

import re

from productivity_operator.models import InboxReviewItem, InboxReviewRequest, InboxReviewResponse, Priority, TaskType


def _clean_title(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) > 90:
        one_line = one_line[:87].rstrip() + "..."
    return one_line


def review_inbox(req: InboxReviewRequest) -> InboxReviewResponse:
    recommendations: list[InboxReviewItem] = []
    for item in req.items:
        lower = item.lower()
        project = None
        tags: list[str] = []
        priority = Priority.medium
        duration = 30
        task_type = TaskType.work
        title = _clean_title(item)
        reason = "Converted inbox item into a verb-first task."

        if "qu pay" in lower or "qupay" in lower:
            project = "Qu Pay Enablement"
            title = "Review Qu Pay request and define next action"
        if "script" in lower or "api" in lower or "automate" in lower or "automation" in lower:
            project = "Qu Pay Automation"
            title = "Investigate Qu Pay automation request"
            tags.append("Research")
        if "documentation" in lower or "knowledge base" in lower or "confluence" in lower:
            project = project or "Qu Pay Enablement"
            title = "Review documentation request and update next action"
            tags.append("Deep Work")
            duration = 60
        if "follow up" in lower or "waiting" in lower or "can you" in lower:
            tags.append("Quick Win")
        if "read" in lower or "article" in lower:
            project = "Personal Growth"
            tags = ["Reading"]
            priority = Priority.low
            title = "Read saved article"
            task_type = TaskType.personal
        if "laundry" in lower or "fridge" in lower or "home" in lower:
            project = "Home"
            tags = ["Quick Win"]
            title = _clean_title(item)
            if not title.lower().startswith(("do ", "replace ", "fix ", "clean ", "schedule ")):
                title = f"Complete home task: {title}"
            task_type = TaskType.personal
            duration = 30

        # Guarantee verb-ish title.
        if not title.lower().startswith((
            "review", "create", "draft", "send", "publish", "capture", "follow", "locate", "collect",
            "document", "investigate", "research", "apply", "replace", "do", "complete", "build", "test",
            "design", "define", "deploy", "read", "process", "update"
        )):
            title = f"Process {title}"

        recommendations.append(
            InboxReviewItem(
                original_title=item,
                recommended_title=title,
                project=project,
                duration=duration,
                priority=priority,
                tags=tags or ["Quick Win"],
                task_type=task_type,
                reason=reason,
            )
        )
    return InboxReviewResponse(recommendations=recommendations)
