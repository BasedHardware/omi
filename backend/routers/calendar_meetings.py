from datetime import datetime
from typing import List, Optional

from fastapi import Request, APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database.calendar_meetings as calendar_db
from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from utils.other import endpoints as auth
from utils.auth_middleware import require_firebase

router = APIRouter(dependencies=[Depends(require_firebase)])


class StoreMeetingRequest(BaseModel):
    """Request to store/update a calendar meeting"""

    calendar_event_id: str = Field(description="External calendar system ID (macOS/Google/Outlook event ID)")
    calendar_source: str = Field(description="Source: 'macos_calendar', 'google_calendar', 'outlook_calendar'")
    title: str = Field(description="Meeting title")
    start_time: datetime = Field(description="Meeting start time")
    end_time: datetime = Field(description="Meeting end time")
    platform: Optional[str] = Field(default=None, description="Platform: 'Zoom', 'Teams', 'Google Meet', etc.")
    meeting_link: Optional[str] = Field(default=None, description="URL to join the meeting")
    participants: List[MeetingParticipant] = Field(default_factory=list, description="Meeting participants")
    notes: Optional[str] = Field(default=None, description="Meeting notes/description")


class StoreMeetingResponse(BaseModel):
    """Response after storing a meeting"""

    meeting_id: str = Field(description="Firestore document ID for this meeting")
    calendar_event_id: str
    message: str = "Meeting stored successfully"


@router.post('/v1/calendar/meetings', response_model=StoreMeetingResponse, tags=['calendar'])
def store_calendar_meeting(request: Request, data: StoreMeetingRequest):
    uid = request.state.uid
    """
    Store or update a calendar meeting in Firestore.
    If a meeting with the same calendar_event_id and calendar_source exists, it will be updated.
    """
    # Calculate duration
    duration_minutes = int((data.end_time - data.start_time).total_seconds() / 60)

    # Create CalendarMeetingContext for storage
    meeting_context = CalendarMeetingContext(
        calendar_event_id=data.calendar_event_id,
        title=data.title,
        participants=data.participants,
        platform=data.platform,
        meeting_link=data.meeting_link,
        start_time=data.start_time,
        duration_minutes=duration_minutes,
        notes=data.notes,
        calendar_source=data.calendar_source,
    )

    meeting_dict = meeting_context.dict()
    meeting_dict['end_time'] = data.end_time

    # Check if meeting already exists (by calendar_event_id + calendar_source)
    existing_meeting_id = calendar_db.get_meeting_id_by_calendar_event(
        uid, data.calendar_event_id, data.calendar_source
    )

    if existing_meeting_id:
        # Update existing meeting
        calendar_db.update_meeting(uid, existing_meeting_id, meeting_dict)
        meeting_id = existing_meeting_id
    else:
        # Create new meeting
        meeting_id = calendar_db.create_meeting(uid, meeting_dict)

    return StoreMeetingResponse(meeting_id=meeting_id, calendar_event_id=data.calendar_event_id)


@router.get('/v1/calendar/meetings/{meeting_id}', response_model=CalendarMeetingContext, tags=['calendar'])
def get_calendar_meeting(request: Request, meeting_id: str):
    uid = request.state.uid
    """Get a calendar meeting by its Firestore document ID"""
    meeting = calendar_db.get_meeting(uid, meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return CalendarMeetingContext(**meeting)


@router.get('/v1/calendar/meetings', response_model=List[CalendarMeetingContext], tags=['calendar'])
def list_calendar_meetings(
    request: Request, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, limit: int = 50
):
    uid = request.state.uid
    """List calendar meetings within a date range"""
    meetings = calendar_db.list_meetings(uid, start_date=start_date, end_date=end_date, limit=limit)
    return [CalendarMeetingContext(**m) for m in meetings]
