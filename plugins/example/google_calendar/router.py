from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from app.lib.utils.features.calendar import CalendarUtil

router = APIRouter()

class Memory(BaseModel):
    title: str
    description: str
    start_time: datetime
    duration_minutes: int

@router.post("/google_calendar")
def create_calendar_event(memory: Memory):
    try:
        success = CalendarUtil().createEvent(
            title=memory.title,
            startsAt=memory.start_time,
            durationMinutes=memory.duration_minutes,
            description=memory.description
        )
        if success:
            return {"message": "Event created successfully"}
        else:
            return {"message": "Failed to create event"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
