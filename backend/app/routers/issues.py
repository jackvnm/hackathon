import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import EmailStr
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.dependencies import get_classifier, get_settings, get_store
from app.models import Crew, IssuePatch, IssueResponse
from app.photos import inspect_photo, resolve_location
from app.storage import ReviewValidationError, Store
from app.services.classification import Classifier
from app.services.submissions import classify_saved_issue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.post("", response_model=IssueResponse, status_code=201)
def submit_issue(
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    classifier: Annotated[Classifier, Depends(get_classifier)],
    photo: Annotated[UploadFile, File()],
    description: Annotated[str, Form(min_length=1, max_length=5000)],
    email: Annotated[EmailStr, Form()],
    address: Annotated[str | None, Form(max_length=500)] = None,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
    location_confirmed: Annotated[bool, Form()] = False,
) -> IssueResponse:
    description = description.strip()
    if not description:
        raise HTTPException(422, detail={"field": "description", "message": "Description must not be blank"})
    if (lat is None) != (lng is None):
        raise HTTPException(422, detail={"field": "location", "message": "Supply both lat and lng"})
    data = photo.file.read(settings.max_photo_bytes + 1)
    if len(data) > settings.max_photo_bytes:
        raise HTTPException(413, detail={"field": "photo", "message": "Photo must be 10 MiB or smaller"})
    extension, media_type = inspect_photo(data)
    location = resolve_location(data, lat, lng, location_confirmed)
    try:
        saved = store.create_issue(
            photo=data, extension=extension, media_type=media_type,
            description=description, email=str(email),
            address=(address.strip() or None) if address else None,
            location=location,
        )
    except (OSError, SQLAlchemyError) as exc:
        logger.error("Submission storage failed (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"message": "Submission not saved; please retry"}) from exc
    return classify_saved_issue(store, classifier, saved, photo=data, media_type=media_type, description=description)


@router.get("/{issue_id}/photo")
def get_photo(
    issue_id: int,
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    issue = store.get_issue(issue_id)
    if issue is None:
        raise HTTPException(404, detail="Photo not found")
    path = settings.photo_dir / issue.photo_filename
    if not path.is_file():
        raise HTTPException(404, detail="Photo not found")
    return FileResponse(path, media_type=issue.photo_media_type, headers={"X-Content-Type-Options": "nosniff"})


@router.get("", response_model=list[IssueResponse])
def list_issues(
    store: Annotated[Store, Depends(get_store)],
    crew: Crew | None = None,
) -> list[IssueResponse]:
    try:
        return store.list_issues(crew)
    except SQLAlchemyError as exc:
        logger.error("Report retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"message": "Reports unavailable; please retry"}) from exc


@router.patch("/{issue_id}", response_model=IssueResponse)
def patch_issue(
    issue_id: int,
    patch: IssuePatch,
    store: Annotated[Store, Depends(get_store)],
) -> IssueResponse:
    try:
        updated = store.patch_issue(issue_id, patch)
    except ReviewValidationError as exc:
        raise HTTPException(422, detail={"field": exc.field, "message": exc.message}) from exc
    except SQLAlchemyError as exc:
        logger.error("Report update failed (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"message": "Update not saved; please retry"}) from exc
    if updated is None:
        raise HTTPException(404, detail="Report not found")
    return updated
