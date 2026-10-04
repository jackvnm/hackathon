from io import BytesIO
from math import isfinite

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.models import Location


FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


def inspect_photo(data: bytes) -> tuple[str, str]:
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in FORMATS:
                raise HTTPException(422, detail={"field": "photo", "message": "Use a JPEG, PNG or WebP photo"})
            if image.width * image.height > 20_000_000:
                raise HTTPException(422, detail={"field": "photo", "message": "Photo must contain at most 20 million pixels"})
            result = FORMATS[image.format]
            image.verify()
        # Some formats only check headers in verify(); decode before accepting.
        with Image.open(BytesIO(data)) as image:
            image.load()
            return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, detail={"field": "photo", "message": "Photo is not a valid supported image"}) from exc


def _degrees(value, reference, positive: str, negative: str, limit: int) -> float:
    if isinstance(reference, bytes):
        reference = reference.decode("ascii")
    if reference not in (positive, negative) or len(value) != 3:
        raise ValueError("Invalid GPS reference or coordinate")
    degrees, minutes, seconds = (float(part) for part in value)
    if not all(isfinite(part) for part in (degrees, minutes, seconds)):
        raise ValueError("Non-finite GPS coordinate")
    if not (0 <= degrees <= limit and 0 <= minutes < 60 and 0 <= seconds < 60):
        raise ValueError("Invalid GPS components")
    result = degrees + minutes / 60 + seconds / 3600
    if result > limit:
        raise ValueError("GPS coordinate out of range")
    return -result if reference == negative else result


def photo_gps(data: bytes) -> tuple[float, float] | None:
    """Inspect original EXIF; missing or malformed metadata is unlocated."""
    try:
        with Image.open(BytesIO(data)) as image:
            gps = image.getexif().get_ifd(34853)
        return (
            _degrees(gps[2], gps[1], "N", "S", 90),
            _degrees(gps[4], gps[3], "E", "W", 180),
        )
    except (KeyError, IndexError, TypeError, ValueError, OSError, ZeroDivisionError, OverflowError):
        return None


def resolve_location(data: bytes, lat: float | None, lng: float | None, confirmed: bool) -> Location:
    gps = photo_gps(data)
    # A supplied pin is the user's canonical location; otherwise retain photo GPS.
    if lat is not None:
        source = "photo_gps" if gps and abs(lat - gps[0]) < 1e-6 and abs(lng - gps[1]) < 1e-6 else "map_pin"
        return Location(lat=lat, lng=lng, source=source, confirmed=confirmed)
    if gps:
        return Location(lat=gps[0], lng=gps[1], source="photo_gps", confirmed=confirmed)
    if confirmed:
        raise HTTPException(422, detail={"field": "location_confirmed", "message": "Coordinates are required to confirm a location"})
    return Location()
