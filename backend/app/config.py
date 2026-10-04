import os
from math import isfinite
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    max_photo_bytes: int = 10 * 1024 * 1024
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str = "gpt-4.1-mini"
    depot_lat: float = 53.34
    depot_lng: float = -6.26
    osrm_url: str = "https://router.project-osrm.org"
    osrm_timeout_seconds: float = 15

    def __post_init__(self):
        if not (isfinite(self.depot_lat) and -90 <= self.depot_lat <= 90):
            raise ValueError("CIVIC_DEPOT_LAT must be a valid latitude")
        if not (isfinite(self.depot_lng) and -180 <= self.depot_lng <= 180):
            raise ValueError("CIVIC_DEPOT_LNG must be a valid longitude")
        if not (isfinite(self.osrm_timeout_seconds) and self.osrm_timeout_seconds > 0):
            raise ValueError("CIVIC_OSRM_TIMEOUT_SECONDS must be positive")
        if not self.osrm_url.startswith(("http://", "https://")):
            raise ValueError("CIVIC_OSRM_URL must be an HTTP(S) base URL")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "issues.sqlite3"

    @property
    def photo_dir(self) -> Path:
        return self.data_dir / "photos"

    @classmethod
    def from_env(cls) -> "Settings":
        default_dir = Path(__file__).resolve().parents[1] / "data"
        return cls(
            data_dir=Path(os.getenv("CIVIC_DATA_DIR", str(default_dir))).resolve(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            depot_lat=float(os.getenv("CIVIC_DEPOT_LAT", "53.34")),
            depot_lng=float(os.getenv("CIVIC_DEPOT_LNG", "-6.26")),
            osrm_url=os.getenv("CIVIC_OSRM_URL", "https://router.project-osrm.org").rstrip("/"),
            osrm_timeout_seconds=float(os.getenv("CIVIC_OSRM_TIMEOUT_SECONDS", "15")),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CIVIC_CORS_ORIGINS", "http://localhost:5173").split(",")
                if origin.strip()
            ),
        )
