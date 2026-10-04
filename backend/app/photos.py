from io import BytesIO

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError


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
            return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, detail={"field": "photo", "message": "Photo is not a valid supported image"}) from exc
