from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: Optional[List[str]] = None
    is_all_day: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "description": self.description,
            "attendees": self.attendees or [],
            "is_all_day": self.is_all_day
        }
    
    def summary(self) -> str:
        time_str = self.start.strftime("%I:%M %p") if not self.is_all_day else "All day"
        location_str = f" at {self.location}" if self.location else ""
        return f"{time_str}: {self.title}{location_str}"


class GoogleCalendarClient:
    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
    
    def __init__(self, credentials_json: Optional[str] = None):
        self.credentials_json = credentials_json or settings.google_calendar_credentials
        self._service = None
    
    def _get_service(self):
        if not self.credentials_json:
            logger.warning("Google Calendar credentials not configured")
            return None
        
        if self._service is not None:
            return self._service
        
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            
            creds_data = json.loads(self.credentials_json)
            creds = Credentials.from_authorized_user_info(creds_data, self.SCOPES)
            self._service = build("calendar", "v3", credentials=creds)
            return self._service
            
        except ImportError:
            logger.error("Google API client libraries not installed")
            return None
        except Exception as e:
            logger.error(f"Error initializing calendar service: {e}")
            return None
    
    async def get_upcoming_events(
        self, 
        days: int = 7,
        max_results: int = 20
    ) -> List[CalendarEvent]:
        service = self._get_service()
        if not service:
            return []
        
        try:
            now = datetime.utcnow()
            time_min = now.isoformat() + "Z"
            time_max = (now + timedelta(days=days)).isoformat() + "Z"
            
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            events = []
            for item in events_result.get("items", []):
                start_data = item.get("start", {})
                end_data = item.get("end", {})
                
                is_all_day = "date" in start_data
                if is_all_day:
                    start = datetime.fromisoformat(start_data["date"])
                    end = datetime.fromisoformat(end_data["date"])
                else:
                    start = datetime.fromisoformat(
                        start_data["dateTime"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(
                        end_data["dateTime"].replace("Z", "+00:00")
                    )
                
                attendees = [
                    a.get("email") for a in item.get("attendees", [])
                    if a.get("email")
                ]
                
                events.append(CalendarEvent(
                    id=item["id"],
                    title=item.get("summary", "Untitled"),
                    start=start,
                    end=end,
                    location=item.get("location"),
                    description=item.get("description"),
                    attendees=attendees,
                    is_all_day=is_all_day
                ))
            
            return events
            
        except Exception as e:
            logger.error(f"Error fetching calendar events: {e}")
            return []
    
    async def get_today_events(self) -> List[CalendarEvent]:
        service = self._get_service()
        if not service:
            return []
        
        try:
            now = datetime.utcnow()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            time_min = start_of_day.isoformat() + "Z"
            time_max = end_of_day.isoformat() + "Z"
            
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            events = []
            for item in events_result.get("items", []):
                start_data = item.get("start", {})
                end_data = item.get("end", {})
                
                is_all_day = "date" in start_data
                if is_all_day:
                    start = datetime.fromisoformat(start_data["date"])
                    end = datetime.fromisoformat(end_data["date"])
                else:
                    start = datetime.fromisoformat(
                        start_data["dateTime"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(
                        end_data["dateTime"].replace("Z", "+00:00")
                    )
                
                events.append(CalendarEvent(
                    id=item["id"],
                    title=item.get("summary", "Untitled"),
                    start=start,
                    end=end,
                    location=item.get("location"),
                    description=item.get("description"),
                    is_all_day=is_all_day
                ))
            
            return events
            
        except Exception as e:
            logger.error(f"Error fetching today's events: {e}")
            return []
    
    async def get_next_event(self) -> Optional[CalendarEvent]:
        events = await self.get_upcoming_events(days=7, max_results=1)
        return events[0] if events else None
    
    async def check_conflicts(
        self, 
        start: datetime, 
        end: datetime
    ) -> List[CalendarEvent]:
        service = self._get_service()
        if not service:
            return []
        
        try:
            time_min = start.isoformat() + "Z"
            time_max = end.isoformat() + "Z"
            
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            conflicts = []
            for item in events_result.get("items", []):
                start_data = item.get("start", {})
                end_data = item.get("end", {})
                
                is_all_day = "date" in start_data
                if is_all_day:
                    event_start = datetime.fromisoformat(start_data["date"])
                    event_end = datetime.fromisoformat(end_data["date"])
                else:
                    event_start = datetime.fromisoformat(
                        start_data["dateTime"].replace("Z", "+00:00")
                    )
                    event_end = datetime.fromisoformat(
                        end_data["dateTime"].replace("Z", "+00:00")
                    )
                
                conflicts.append(CalendarEvent(
                    id=item["id"],
                    title=item.get("summary", "Untitled"),
                    start=event_start,
                    end=event_end,
                    is_all_day=is_all_day
                ))
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Error checking calendar conflicts: {e}")
            return []
