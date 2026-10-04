"""Read-only metadata inspection before submission; does not save or classify."""
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import Settings
from app.dependencies import get_settings
from app.models import PhotoMetadataResponse
from app.photos import inspect_photo, resolve_location

router = APIRouter(prefix="/api/photos", tags=["photos"])


@router.post("/metadata", response_model=PhotoMetadataResponse)
def inspect_metadata(
    settings: Annotated[Settings, Depends(get_settings)],
    photo: Annotated[UploadFile, File()],
) -> PhotoMetadataResponse:
    data = photo.file.read(settings.max_photo_bytes + 1)
    if len(data) > settings.max_photo_bytes:
        raise HTTPException(413, detail={"field": "photo", "message": "Photo must be 10 MiB or smaller"})
    inspect_photo(data)
    location = resolve_location(data, None, None, False)
    return PhotoMetadataResponse(gps_found=location.source == "photo_gps", location=location)
