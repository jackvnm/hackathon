import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.dependencies import get_settings, get_store, get_travel_provider
from app.models import PlanRequest, PlanResponse
from app.services.osrm import PlanningError
from app.services.planning import plan_day
from app.storage import Store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plan", tags=["planning"])


@router.post("", response_model=PlanResponse)
def generate_plan(
    request: PlanRequest,
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    travel_provider: Annotated[object, Depends(get_travel_provider)],
) -> dict:
    try:
        return plan_day(
            store.planning_issues(), request.crew,
            (settings.depot_lat, settings.depot_lng), travel_provider,
        )
    except PlanningError as exc:
        logger.warning("Road planning unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        logger.error("Planning report retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(503, detail={"message": "Reports unavailable for planning; please retry"}) from exc
