"""OSRM road-duration adapter. Unavailable road data is an explicit failure."""
import math

import httpx


class PlanningError(RuntimeError):
    pass


class OSRMClient:
    def __init__(self, base_url: str, timeout_seconds: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def duration_matrix(self, coordinates: list[tuple[float, float]]) -> list[list[int]]:
        if not coordinates or len(coordinates) > 100:
            raise PlanningError("Planning requires between 1 and 100 locations; narrow the active demo tasks")
        points = ";".join(f"{lng},{lat}" for lat, lng in coordinates)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    f"{self.base_url}/table/v1/driving/{points}",
                    params={"annotations": "duration"},
                )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict) or payload.get("code") != "Ok":
                raise ValueError("OSRM could not route these locations")
            durations = payload["durations"]
            size = len(coordinates)
            if not isinstance(durations, list) or len(durations) != size:
                raise ValueError("Invalid duration matrix")
            result = []
            for row in durations:
                if not isinstance(row, list) or len(row) != size:
                    raise ValueError("Invalid duration matrix")
                if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in row):
                    raise ValueError("Unreachable location or invalid road duration")
                result.append([math.ceil(value / 60) for value in row])
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise PlanningError("Road travel times unavailable. Check OSRM connectivity and task locations, then retry") from exc
