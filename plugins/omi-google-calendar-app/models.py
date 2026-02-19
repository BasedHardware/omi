"""
Pydantic models for the Google Calendar Omi plugin.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


class CalendarEvent(BaseModel):
    """Google Calendar event."""
    id: str
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    start: str  # ISO datetime or date
    end: str  # ISO datetime or date
    all_day: bool = False
    attendees: List[str] = []
    html_link: Optional[str] = None
    status: str = "confirmed"


class Calendar(BaseModel):
    """Google Calendar."""
    id: str
    summary: str
    description: Optional[str] = None
    primary: bool = False
    background_color: Optional[str] = None


class GoogleUserInfo(BaseModel):
    """Google user information."""
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
