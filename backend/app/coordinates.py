"""Per-record Dublin dataset CRS detection; never guess outside known ranges."""
from functools import lru_cache
from math import isfinite

from pyproj import Transformer

from app.models import Location


def detect_crs(x_value: str | None, y_value: str | None) -> str | None:
    try:
        x, y = float(x_value), float(y_value)
    except (ValueError, TypeError):
        return None
    if not isfinite(x) or not isfinite(y) or x == 999999 or y == 999999:
        return None
    if 700000 <= x <= 730000 and 720000 <= y <= 750000:
        return "ITM"
    if 290000 <= x <= 330000 and 220000 <= y <= 255000:
        return "Irish Grid"
    return None


@lru_cache(maxsize=2)
def transformer(crs: str) -> Transformer:
    return Transformer.from_crs(2157 if crs == "ITM" else 29902, 4326, always_xy=True, allow_ballpark=False)


def csv_location(row: dict[str, str], *, confirmed: bool = False) -> Location:
    crs = detect_crs(row.get("ATTRIBUTE5"), row.get("ATTRIBUTE6"))
    if crs is None:
        return Location(source="csv")
    lng, lat = transformer(crs).transform(float(row["ATTRIBUTE5"]), float(row["ATTRIBUTE6"]), errcheck=True)
    if not (53.2 <= lat <= 53.5 and -6.5 <= lng <= -6.0):
        return Location(source="csv", crs_detected=crs)
    return Location(lat=lat, lng=lng, source="csv", confirmed=confirmed, crs_detected=crs)
