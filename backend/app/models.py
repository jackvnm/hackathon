from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


Crew = Literal["roads", "cleanup", "graffiti", "lighting", "arborist", "drainage", "manual_triage"]
TaskType = Literal["repair", "removal", "inspection", "manual_triage"]


class LocationCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    lat: float | None = Field(ge=-90, le=90)
    lng: float | None = Field(ge=-180, le=180)
    confirmed: bool

    @model_validator(mode="after")
    def validate_coordinates(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Supply both lat and lng or clear both")
        if self.confirmed and self.lat is None:
            raise ValueError("Confirmed location requires coordinates")
        return self


class IssuePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    crew: Crew | None = None
    task_type: TaskType | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    location: LocationCorrection | None = None
    review_state: Literal["needs_review", "approved"] | None = None

    @model_validator(mode="after")
    def reject_null_controls(self):
        for field in self.model_fields_set - {"estimated_minutes"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
