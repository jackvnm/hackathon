"""Greedy single-crew daily planning with indivisible activities and fixed lunch."""
from typing import Protocol

from app.database import Issue
from app.eligibility import task_blockers
from app.services.osrm import PlanningError


class TravelProvider(Protocol):
    def duration_matrix(self, coordinates: list[tuple[float, float]]) -> list[list[int]]: ...


def _time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _activity(start: int, duration: int) -> tuple[int, int, bool]:
    # Every activity is indivisible. A zero-minute leg does not cross lunch.
    delayed = duration > 0 and start < 780 and start + duration > 720
    if delayed:
        start = 780
    return start, start + duration, delayed


def plan_day(
    issues: list[Issue], crew: str, depot: tuple[float, float], travel_provider: TravelProvider,
) -> dict:
    eligible = []
    omitted = []
    for issue in sorted(issues, key=lambda item: item.id):
        blockers = task_blockers(issue, crew)
        if blockers:
            # Report the concrete correction before asking for approval of it.
            priorities = {reason: rank for rank, reason in enumerate((
                "inactive", "manual_triage", "incompatible_crew", "unlocated", "unknown_duration", "unapproved",
            ))}
            blocker = min(blockers, key=lambda entry: priorities.get(entry.reason, 99))
            omitted.append({"report_id": issue.id, "reason": blocker.reason, "message": blocker.message})
        else:
            eligible.append(issue)
    coordinates = [depot] + [(issue.lat, issue.lng) for issue in eligible]
    if len(coordinates) > 100:
        raise PlanningError("Too many eligible reports for OSRM: at most 99 active jobs can be planned at once")
    matrix = travel_provider.duration_matrix(coordinates) if eligible else [[0]]
    if len(matrix) != len(coordinates) or any(
        len(row) != len(coordinates) or any(type(value) is not int or value < 0 for value in row)
        for row in matrix
    ):
        raise PlanningError("Road travel provider returned an invalid duration matrix")
    pending = list(range(1, len(coordinates)))
    current = 0
    now = 480
    travel_total = task_total = 0
    lunch_location = None
    stops = []
    while pending:
        feasible = []
        for index in pending:
            issue = eligible[index - 1]
            travel = matrix[current][index]
            duration = issue.estimated_minutes
            _, arrive, travel_delayed = _activity(now, travel)
            _, complete, task_delayed = _activity(arrive, duration)
            _, returned, _ = _activity(complete, matrix[index][0])
            if returned <= 960 and travel_total + task_total + travel + duration + matrix[index][0] <= 420:
                feasible.append((travel + duration, issue.id, index, arrive, complete, travel_delayed, task_delayed))
        if not feasible:
            break
        _, _, index, arrive, complete, travel_delayed, task_delayed = min(feasible)
        issue = eligible[index - 1]
        if lunch_location is None:
            if travel_delayed:
                lunch_location = coordinates[current]
            elif task_delayed:
                lunch_location = coordinates[index]
        travel = matrix[current][index]
        stops.append({
            "order": len(stops) + 1, "report_id": issue.id,
            "lat": issue.lat, "lng": issue.lng,
            "arrive": _time(arrive), "complete": _time(complete),
            "travel_minutes": travel, "task_minutes": issue.estimated_minutes,
        })
        travel_total += travel
        task_total += issue.estimated_minutes
        current, now = index, complete
        pending.remove(index)
    return_travel = matrix[current][0]
    _, returned, return_delayed = _activity(now, return_travel)
    if lunch_location is None:
        lunch_location = coordinates[current] if return_delayed else depot
    travel_total += return_travel
    for index in pending:
        omitted.append({
            "report_id": eligible[index - 1].id, "reason": "oversized",
            "message": "Task cannot fit with lunch, the seven-hour work limit and return to depot by 16:00",
        })
    return {
        "crew": crew, "label": "Suggested feasible route",
        "depot": {"lat": depot[0], "lng": depot[1]}, "stops": stops,
        "lunch": {"lat": lunch_location[0], "lng": lunch_location[1], "start": "12:00", "end": "13:00"},
        "depot_return": _time(returned),
        "totals": {"travel_minutes": travel_total, "task_minutes": task_total},
        "omitted": sorted(omitted, key=lambda item: item["report_id"]),
    }
