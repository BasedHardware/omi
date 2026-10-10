from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import hmac
import hashlib

# Import existing whoop utilities
from .whoop_client import (
    get_valid_access_token,
    whoop_api_request,
    WHOOP_CLIENT_ID,
    WHOOP_CLIENT_SECRET,
)
from .whoop_tools_auth import require_whoop_tools_auth

router = APIRouter(prefix="/tools/whoop", tags=["whoop"])

# Pydantic models
class WhoopToolRequest(BaseModel):
    uid: str
    # Add any additional fields per endpoint as needed

# Shared secret configuration
WHOOP_TOOLS_SECRET = os.environ.get("WHOOP_TOOLS_SECRET")


@router.post("/get_recovery", response_model=dict)
async def get_recovery(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop recovery score for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "recovery")
    return data


@router.post("/get_strain", response_model=dict)
async def get_strain(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop strain data for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "strain")
    return data


@router.post("/get_sleep", response_model=dict)
async def get_sleep(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop sleep data for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "sleep")
    return data


@router.post("/get_workouts", response_model=dict)
async def get_workouts(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop workouts data for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "workouts")
    return data


@router.post("/get_weekly_summary", response_model=dict)
async def get_weekly_summary(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop weekly summary for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "weekly_summary")
    return data


@router.post("/get_body_measurements", response_model=dict)
async def get_body_measurements(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop body measurements for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "body_measurements")
    return data


@router.post("/get_profile", response_model=dict)
async def get_profile(
    req: WhoopToolRequest,
    _auth: dict = Depends(require_whoop_tools_auth),
):
    """Get Whoop profile data for the given uid."""
    if not WHOOP_TOOLS_SECRET:
        raise HTTPException(status_code=503, detail="WHOOP_TOOLS_SECRET not configured")
    access_token = await get_valid_access_token(req.uid)
    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or disconnected Whoop account")
    data = await whoop_api_request(access_token, "profile")
    return data
