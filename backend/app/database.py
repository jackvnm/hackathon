from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String)
    incident_date: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    reporter_email: Mapped[str] = mapped_column(String)
    photo_filename: Mapped[str] = mapped_column(String, unique=True)
    photo_media_type: Mapped[str] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    location_source: Mapped[str] = mapped_column(String)
    location_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    original_json: Mapped[dict | None] = mapped_column(JSON)
    source_status: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_state: Mapped[str] = mapped_column(String, default="pending")
    review_state: Mapped[str] = mapped_column(String, default="needs_review")
    analysis_json: Mapped[dict | None] = mapped_column(JSON)
    crew: Mapped[str] = mapped_column(String, default="manual_triage")
    task_type: Mapped[str] = mapped_column(String, default="manual_triage")
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_engine(
            f"sqlite:///{settings.database_path}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        self.settings.photo_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()
