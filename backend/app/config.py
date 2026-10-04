import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    max_photo_bytes: int = 10 * 1024 * 1024

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
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CIVIC_CORS_ORIGINS", "http://localhost:5173").split(",")
                if origin.strip()
            ),
        )
