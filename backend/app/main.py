from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import Database
from app.routers import health, issues, photos, planning
from app.services.classification import Classifier, OpenAIClassifier
from app.storage import Store
from app.services.osrm import OSRMClient


def create_app(settings: Settings | None = None, *, classifier: Classifier | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        try:
            yield
        finally:
            database.close()

    app = FastAPI(title="Civic issue reporting", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.store = Store(database)
    app.state.travel_provider = OSRMClient(settings.osrm_url, settings.osrm_timeout_seconds)
    app.state.classifier = classifier if classifier is not None else OpenAIClassifier(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(issues.router)
    app.include_router(photos.router)
    app.include_router(planning.router)
    return app


app = create_app()
