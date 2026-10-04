from datetime import datetime, timezone
from uuid import uuid4

from app.database import Database, Issue
from app.models import Assignment, IssueResponse, Location


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
                    location_confirmed=location.confirmed,
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

    @staticmethod
    def public_issue(issue: Issue) -> IssueResponse:
        # Explicit allowlist excludes email and internal paths.
        return IssueResponse(
            id=issue.id, reference=issue.reference, original=issue.original_json,
            created_at=issue.created_at, incident_date=issue.incident_date,
            description=issue.description, photo_url=f"/api/issues/{issue.id}/photo",
            analysis_state=issue.analysis_state, review_state=issue.review_state,
            analysis=issue.analysis_json,
            assignment=Assignment(
                crew=issue.crew, task_type=issue.task_type,
                estimated_minutes=issue.estimated_minutes,
            ),
            location=Location(
                lat=issue.lat, lng=issue.lng, source=issue.location_source,
                confirmed=issue.location_confirmed,
            ),
            address=issue.address, is_synthetic=issue.is_synthetic,
            # These tasks remain unapproved until the review milestone.
            routable=False,
        )
