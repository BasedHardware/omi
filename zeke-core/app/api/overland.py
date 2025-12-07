from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from ..services.location_service import LocationService
from ..models.location import (
    OverlandPayload, 
    LocationResponse, 
    LocationContext
)
from ..core.config import get_settings

router = APIRouter(prefix="/overland", tags=["overland"], redirect_slashes=False)
logger = logging.getLogger(__name__)
settings = get_settings()


class OverlandResponse(BaseModel):
    result: str


class LocationHistoryRequest(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    motion_filter: Optional[str] = None
    limit: int = 100


def get_location_service() -> LocationService:
    return LocationService()


def verify_overland_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    expected_token = getattr(settings, 'overland_api_key', None)
    
    if not expected_token:
        if getattr(settings, 'debug', False):
            logger.warning("Overland API key not configured - endpoint is unauthenticated in debug mode")
            return None
        else:
            logger.error("Overland API key not configured - rejecting request in production")
            raise HTTPException(status_code=503, detail="GPS tracking endpoint not configured")
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    
    return token


@router.post("/", response_model=OverlandResponse)
@router.post("", response_model=OverlandResponse, include_in_schema=False)
async def receive_overland_data(
    request: Request,
    authorization: Optional[str] = Header(None),
    location_service: LocationService = Depends(get_location_service)
):
    verify_overland_token(authorization)
    
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Overland request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    try:
        payload = OverlandPayload(**body)
    except Exception as e:
        logger.error(f"Failed to validate Overland payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload structure: {e}")
    
    user_id = "default_user"
    device_id = None
    
    if payload.locations:
        first_loc = payload.locations[0]
        if isinstance(first_loc, dict):
            props = first_loc.get("properties", {})
            device_id = props.get("device_id")
    
    locations_stored = await location_service.process_overland_batch(
        user_id=user_id,
        payload=payload,
        device_id=device_id
    )
    
    logger.info(f"Received Overland batch: {len(payload.locations)} locations, stored {locations_stored}")
    
    return OverlandResponse(result="ok")


@router.get("/current", response_model=Optional[LocationResponse])
async def get_current_location(
    location_service: LocationService = Depends(get_location_service)
):
    location = await location_service.get_current("default_user")
    if not location:
        raise HTTPException(status_code=404, detail="No location data available")
    return location


@router.get("/context", response_model=Optional[LocationContext])
async def get_location_context(
    location_service: LocationService = Depends(get_location_service)
):
    context = await location_service.get_location_context("default_user")
    if not context:
        raise HTTPException(status_code=404, detail="No location context available")
    return context


@router.get("/recent", response_model=List[LocationResponse])
async def get_recent_locations(
    hours: int = 24,
    limit: int = 100,
    location_service: LocationService = Depends(get_location_service)
):
    locations = await location_service.get_recent(
        user_id="default_user",
        hours=hours,
        limit=limit
    )
    return locations


@router.post("/history", response_model=List[LocationResponse])
async def get_location_history(
    request: LocationHistoryRequest,
    location_service: LocationService = Depends(get_location_service)
):
    locations = await location_service.get_location_history(
        user_id="default_user",
        start_date=request.start_date,
        end_date=request.end_date,
        motion_filter=request.motion_filter,
        limit=request.limit
    )
    return locations


@router.get("/summary")
async def get_motion_summary(
    hours: int = 24,
    location_service: LocationService = Depends(get_location_service)
):
    summary = await location_service.get_motion_summary(
        user_id="default_user",
        hours=hours
    )
    return summary


@router.delete("/cleanup")
async def cleanup_old_locations(
    days_to_keep: int = 90,
    location_service: LocationService = Depends(get_location_service)
):
    deleted_count = await location_service.delete_old_locations(
        user_id="default_user",
        days_to_keep=days_to_keep
    )
    return {"deleted": deleted_count, "days_to_keep": days_to_keep}
