from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime

from ..models.context_mode import (
    ContextModeCreate, ContextModeResponse, ContextModeType,
    ParkingLotItemCreate, ParkingLotItemResponse,
    UserContextStateResponse, TimeSensitiveReminderCreate, TimeSensitiveReminderResponse,
    DailyBriefing
)
from ..services.context_service import get_context_service
from ..services.briefing_service import get_briefing_service

router = APIRouter(prefix="/context", tags=["context"])


@router.post("/modes/initialize/{user_id}")
async def initialize_default_modes(user_id: str) -> List[ContextModeResponse]:
    service = get_context_service()
    return await service.initialize_default_modes(user_id)


@router.get("/modes/{user_id}")
async def get_modes(user_id: str) -> List[ContextModeResponse]:
    service = get_context_service()
    return await service.get_modes(user_id)


@router.post("/modes/{user_id}")
async def create_mode(user_id: str, data: ContextModeCreate) -> ContextModeResponse:
    service = get_context_service()
    return await service.create_mode(user_id, data)


@router.get("/current/{user_id}")
async def get_current_mode(user_id: str) -> ContextModeResponse:
    service = get_context_service()
    return await service.get_current_mode(user_id)


@router.post("/override/{user_id}")
async def set_mode_override(
    user_id: str,
    mode_type: ContextModeType,
    duration_minutes: int = Query(default=60, ge=5, le=480)
) -> UserContextStateResponse:
    service = get_context_service()
    return await service.set_mode_override(user_id, mode_type.value, duration_minutes)


@router.delete("/override/{user_id}")
async def clear_mode_override(user_id: str) -> UserContextStateResponse:
    service = get_context_service()
    return await service.clear_mode_override(user_id)


@router.get("/state/{user_id}")
async def get_user_state(user_id: str) -> UserContextStateResponse:
    service = get_context_service()
    return await service.get_user_state(user_id)


@router.post("/interaction/{user_id}")
async def update_interaction(user_id: str, topic: Optional[str] = None) -> dict:
    service = get_context_service()
    await service.update_interaction(user_id, topic)
    
    refocus_prompt = await service.check_refocus_needed(user_id)
    
    return {
        "status": "updated",
        "refocus_prompt": refocus_prompt
    }


@router.post("/parking-lot/{user_id}")
async def add_to_parking_lot(
    user_id: str,
    data: ParkingLotItemCreate
) -> ParkingLotItemResponse:
    service = get_context_service()
    return await service.add_to_parking_lot(user_id, data)


@router.get("/parking-lot/{user_id}")
async def get_parking_lot(
    user_id: str,
    include_processed: bool = False,
    limit: int = Query(default=20, le=100)
) -> List[ParkingLotItemResponse]:
    service = get_context_service()
    return await service.get_parking_lot(user_id, include_processed, limit)


@router.post("/parking-lot/{item_id}/process")
async def process_parking_lot_item(
    item_id: str,
    action: str = Query(description="Action taken: converted_to_task, dismissed, explored, etc.")
) -> ParkingLotItemResponse:
    service = get_context_service()
    try:
        return await service.process_parking_lot_item(item_id, action)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reminders/{user_id}")
async def add_reminder(
    user_id: str,
    data: TimeSensitiveReminderCreate
) -> TimeSensitiveReminderResponse:
    service = get_context_service()
    return await service.add_time_sensitive_reminder(user_id, data)


@router.get("/reminders/{user_id}")
async def get_upcoming_reminders(
    user_id: str,
    hours: int = Query(default=24, le=168)
) -> List[TimeSensitiveReminderResponse]:
    service = get_context_service()
    return await service.get_upcoming_reminders(user_id, hours)


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str) -> TimeSensitiveReminderResponse:
    service = get_context_service()
    try:
        return await service.complete_reminder(reminder_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/briefing/{user_id}")
async def get_daily_briefing(user_id: str) -> DailyBriefing:
    service = get_briefing_service()
    return await service.generate_briefing(user_id)


@router.get("/briefing/{user_id}/evening")
async def get_evening_recap(user_id: str) -> dict:
    service = get_briefing_service()
    return await service.generate_evening_recap(user_id)


@router.get("/refocus/{user_id}")
async def check_refocus_needed(
    user_id: str,
    drift_threshold: int = Query(default=3, ge=1, le=10)
) -> dict:
    service = get_context_service()
    prompt = await service.check_refocus_needed(user_id, drift_threshold)
    
    return {
        "needs_refocus": prompt is not None,
        "prompt": prompt
    }
