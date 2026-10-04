from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.database import Database, Issue
from app.models import Analysis, Assignment, IssueResponse, Location, IssuePatch, Crew


class Store:
    def __init__(self, database: Database):
        self.database = database
        self.settings = database.settings

    def create_issue(
        self, *, photo: bytes, extension: str, media_type: str,
        description: str, email: str, address: str | None, location: Location,
    ) -> IssueResponse:
        filename = f"{uuid4().hex}.{extension}"
        path = self.settings.photo_dir / filename
        created_at = datetime.now(timezone.utc).isoformat()
        # Original bytes are saved before analysis without modifying EXIF.
        try:
            with path.open("xb") as file:
                file.write(photo)
            with self.database.sessions.begin() as session:
                issue = Issue(
                    created_at=created_at, incident_date=created_at[:10],
                    description=description, reporter_email=email,
                    photo_filename=filename, photo_media_type=media_type,
                    address=address, lat=location.lat, lng=location.lng,
                    location_source=location.source,
                    location_confirmed=location.confirmed, is_active=True,
                )
                session.add(issue)
                session.flush()
                issue.reference = f"CIV-{issue.id:06d}"
                response = self.public_issue(issue)
        except Exception:
            # A failed transaction must not leave an orphan photo.
            path.unlink(missing_ok=True)
            raise
        return response

    def get_issue(self, issue_id: int) -> Issue | None:
        with self.database.sessions() as session:
            return session.get(Issue, issue_id)

    def list_issues(self, crew: Crew | None = None) -> list[IssueResponse]:
        with self.database.sessions() as session:
            query = select(Issue).order_by(Issue.id.desc())
            if crew is not None:
                query = query.where(Issue.crew == crew)
            return [self.public_issue(issue) for issue in session.scalars(query)]

    def patch_issue(self, issue_id: int, patch: IssuePatch) -> IssueResponse | None:
        with self.database.sessions.begin() as session:
            issue = session.get(Issue, issue_id)
            if issue is None:
                return None
            changed = False
            task_changed = "task_type" in patch.model_fields_set and patch.task_type != issue.task_type
            for field in ("crew", "task_type", "estimated_minutes"):
                if field in patch.model_fields_set:
                    value = getattr(patch, field)
                    changed |= getattr(issue, field) != value
                    setattr(issue, field, value)
            # A duration for repair must never implicitly become an inspection estimate.
            if task_changed and "estimated_minutes" not in patch.model_fields_set:
                issue.estimated_minutes = None
            if patch.location is not None:
                location = patch.location
                coordinates_changed = (issue.lat, issue.lng) != (location.lat, location.lng)
                changed |= coordinates_changed or issue.location_confirmed != location.confirmed
                issue.lat, issue.lng = location.lat, location.lng
                issue.location_confirmed = location.confirmed
                if coordinates_changed:
                    issue.location_source = "map_pin" if location.lat is not None else "none"
            if changed:
                issue.review_state = "needs_review"
            if patch.review_state is not None:
                issue.review_state = patch.review_state
            if issue.review_state == "approved":
                from app.eligibility import task_blockers
                blockers = task_blockers(issue, require_approval=False)
                if blockers:
                    raise ReviewValidationError(blockers[0].field, blockers[0].message)
            return self.public_issue(issue)

    def save_analysis(self, issue_id: int, analysis: Analysis | None, assignment: Assignment | None = None) -> IssueResponse:
        with self.database.sessions.begin() as session:
            issue = session.get(Issue, issue_id)
            if issue is None:
                raise ValueError("Saved issue not found")
            issue.analysis_state = "complete" if analysis else "failed"
            issue.analysis_json = analysis.model_dump() if analysis else None
            issue.review_state = "needs_review"
            assignment = assignment or Assignment()
            issue.crew = assignment.crew
            issue.task_type = assignment.task_type
            issue.estimated_minutes = assignment.estimated_minutes
            return self.public_issue(issue)

    @staticmethod
    def public_issue(issue: Issue) -> IssueResponse:
        from app.eligibility import task_blockers

        # Explicit allowlist excludes email and internal paths.
        return IssueResponse(
            id=issue.id, reference=issue.reference, original=issue.original_json,
            created_at=issue.created_at, incident_date=issue.incident_date,
            description=issue.description, photo_url=f"/api/issues/{issue.id}/photo",
            analysis_state=issue.analysis_state, review_state=issue.review_state,
            analysis=issue.analysis_json,
            analysis_error="Analysis unavailable; dispatcher review required" if issue.analysis_state == "failed" else None,
            assignment=Assignment(
                crew=issue.crew, task_type=issue.task_type,
                estimated_minutes=issue.estimated_minutes,
            ),
            location=Location(
                lat=issue.lat, lng=issue.lng, source=issue.location_source,
                confirmed=issue.location_confirmed,
            ),
            address=issue.address, is_synthetic=issue.is_synthetic,
            routable=not task_blockers(issue),
        )


class ReviewValidationError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message
