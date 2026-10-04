"""Shared approval and routing rules; travel decisions belong to scheduling."""
from dataclasses import dataclass
from math import isfinite

from app.assignments import CATEGORIES, CREWS
from app.database import Issue


@dataclass(frozen=True)
class TaskBlocker:
    reason: str
    field: str
    message: str


CREW_TASKS = {
    "roads": "repair", "cleanup": "removal", "graffiti": "removal",
    "lighting": "inspection", "arborist": "inspection", "drainage": "inspection",
}


def task_blockers(
    issue: Issue, selected_crew: str | None = None, *, require_approval: bool = True,
) -> list[TaskBlocker]:
    """Return exclusions, or validate task values before explicit approval."""
    blockers = []

    def add(reason, field, message):
        blockers.append(TaskBlocker(reason, field, message))

    original_status = (issue.original_json or {}).get("STATUS", "")
    closed = any(str(status or "").strip().upper() == "CLOSED" for status in (issue.source_status, original_status))
    if not issue.is_active or (closed and not issue.is_synthetic):
        add("inactive", "review_state", "Historical or inactive report is not an active demo task")
    if require_approval and issue.review_state != "approved":
        add("unapproved", "review_state", "Approve the current task before planning")
    if issue.crew == "manual_triage" or issue.task_type == "manual_triage":
        add("manual_triage", "crew", "Assign a supported crew and task before approval")
    if not (
        issue.location_confirmed
        and issue.lat is not None and issue.lng is not None
        and isfinite(issue.lat) and isfinite(issue.lng)
        and -90 <= issue.lat <= 90 and -180 <= issue.lng <= 180
    ):
        add("unlocated", "location", "Confirm valid latitude and longitude before approval")
    if type(issue.estimated_minutes) is not int or issue.estimated_minutes <= 0:
        add("unknown_duration", "estimated_minutes", "Duration must be positive to approve")
    crew = CREWS.get(issue.crew)
    if selected_crew is not None and issue.crew != selected_crew:
        add("incompatible_crew", "crew", "Task is assigned to a different crew")
    if crew is None:
        if issue.crew != "manual_triage":
            add("incompatible_crew", "crew", "Unsupported crew")
    elif issue.task_type != "manual_triage":
        if issue.task_type not in {"inspection", CREW_TASKS[issue.crew]}:
            add("incompatible_crew", "task_type", "Task type is not supported by the assigned crew")
        analysis = issue.analysis_json or {}
        category = CATEGORIES.get(analysis.get("category"))
        if issue.task_type == "inspection":
            # An inspection needs its own capability, not the repair capability.
            required = {CREWS[category[0]].inspection_capability} if category else {crew.inspection_capability}
        else:
            required = set(analysis.get("required_capabilities", []))
            if category:
                required.add(category[2])
        if not required <= crew.capabilities:
            add("incompatible_crew", "crew", "Required capabilities are not supported by the assigned crew")
    return blockers
