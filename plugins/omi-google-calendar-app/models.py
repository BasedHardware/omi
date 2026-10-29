"""
Pydantic models for the Google Calendar Omi plugin.
"""
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: str | None = None
    error: str | None = None


class CalendarEvent(BaseModel):
    """Google Calendar event."""
    id: str
    summary: str
    description: str | None = None
    location: str | None = None
    start: str  # ISO datetime or date
    end: str  # ISO datetime or date
    all_day: bool = False
    attendees: list[str] = []
    html_link: str | None = None
    status: str = "confirmed"


class Calendar(BaseModel):
    """Google Calendar."""
    id: str
    summary: str
    description: str | None = None
    primary: bool = False
    background_color: str | None = None


class GoogleUserInfo(BaseModel):
    """Google user information."""
    email: str
    name: str | None = None
    picture: str | None = None
