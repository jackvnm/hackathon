from typing import Literal

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    source: Literal["photo_gps", "map_pin", "csv", "none"] = "none"
    confirmed: bool = False
    crs_detected: str | None = None


class Assignment(BaseModel):
    crew: Literal["roads", "cleanup", "graffiti", "lighting", "arborist", "drainage", "manual_triage"] = "manual_triage"
    task_type: Literal["repair", "removal", "inspection", "manual_triage"] = "manual_triage"
    estimated_minutes: int | None = Field(default=None, gt=0)


class IssueResponse(BaseModel):
    id: int
    reference: str
    original: dict[str, str] | None = None
    created_at: str
    incident_date: str
    description: str
    photo_url: str
    analysis_state: Literal["pending", "complete", "failed"] = "pending"
    review_state: Literal["needs_review", "approved"] = "needs_review"
    analysis: dict | None = None
    assignment: Assignment = Field(default_factory=Assignment)
    location: Location
    address: str | None = None
    routable: bool = False
    is_synthetic: bool = False
