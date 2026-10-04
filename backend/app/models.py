from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    category: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    required_capabilities: list[str]
    time_cost_minutes: int | None = Field(gt=0)
    needs_inspection: bool
    needs_review: bool


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
    analysis: Analysis | None = None
    analysis_error: str | None = None
    assignment: Assignment = Field(default_factory=Assignment)
    location: Location
    address: str | None = None
    routable: bool = False
    is_synthetic: bool = False
