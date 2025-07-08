import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pytz

from database.calendar import (
    get_user_calendar_integration,
    save_user_calendar_integration,
    get_user_calendar_config,
    save_calendar_event
)
from models.calendar import CalendarIntegration, CalendarEvent, CalendarEventCreate, CalendarConfig


class GoogleCalendarService:
    def __init__(self):
        self.scopes = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/v1/calendar/oauth/callback')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")

    def get_auth_url(self, uid: str) -> str:
        """Generate Google OAuth authorization URL."""
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uris": [self.redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            scopes=self.scopes
        )
        flow.redirect_uri = self.redirect_uri
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=uid,
            prompt='consent'
        )
        
        return auth_url

    def exchange_code_for_tokens(self, code: str, uid: str) -> Optional[CalendarIntegration]:
        """Exchange authorization code for access tokens."""
        try:
            flow = Flow.from_client_config(
                client_config={
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uris": [self.redirect_uri],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                },
                scopes=self.scopes
            )
            flow.redirect_uri = self.redirect_uri
            
            flow.fetch_token(code=code)
            
            credentials = flow.credentials
            
            # Get user's primary calendar info
            service = build('calendar', 'v3', credentials=credentials)
            calendar_list = service.calendarList().list().execute()
            
            primary_calendar = None
            for calendar in calendar_list.get('items', []):
                if calendar.get('primary'):
                    primary_calendar = calendar
                    break
            
            if not primary_calendar:
                raise ValueError("No primary calendar found")
            
            # Create integration record
            integration = CalendarIntegration(
                uid=uid,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry,
                calendar_id=primary_calendar['id'],
                calendar_name=primary_calendar['summary'],
                timezone=primary_calendar.get('timeZone', 'UTC'),
                created_at=datetime.utcnow()
            )
            
            # Save to database
            if save_user_calendar_integration(uid, integration):
                return integration
            
            return None
            
        except Exception as e:
            print(f"Error exchanging code for tokens: {e}")
            return None

    def get_credentials(self, uid: str) -> Optional[Credentials]:
        """Get valid Google credentials for user."""
        integration = get_user_calendar_integration(uid)
        if not integration:
            return None
        
        credentials = Credentials(
            token=integration.access_token,
            refresh_token=integration.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes
        )
        
        # Check if token needs refresh
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                
                # Update stored tokens
                integration.access_token = credentials.token
                integration.token_expiry = credentials.expiry
                save_user_calendar_integration(uid, integration)
                
            except Exception as e:
                print(f"Error refreshing credentials for user {uid}: {e}")
                return None
        
        return credentials

    def create_event(self, uid: str, event_data: CalendarEventCreate) -> Optional[CalendarEvent]:
        """Create a calendar event."""
        try:
            credentials = self.get_credentials(uid)
            if not credentials:
                return None
            
            service = build('calendar', 'v3', credentials=credentials)
            integration = get_user_calendar_integration(uid)
            
            if not integration:
                return None
            
            # Convert to timezone-aware datetime
            tz = pytz.timezone(event_data.timezone)
            start_time = event_data.start_time.astimezone(tz)
            end_time = event_data.end_time.astimezone(tz)
            
            # Create event
            event = {
                'summary': event_data.summary,
                'description': event_data.description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': event_data.timezone,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': event_data.timezone,
                },
            }
            
            if event_data.location:
                event['location'] = event_data.location
            
            if event_data.attendees:
                event['attendees'] = [{'email': email} for email in event_data.attendees]
            
            created_event = service.events().insert(
                calendarId=integration.calendar_id,
                body=event
            ).execute()
            
            # Save event record
            calendar_event = CalendarEvent(
                id=created_event['id'],
                summary=event_data.summary,
                description=event_data.description,
                start_time=start_time,
                end_time=end_time,
                calendar_id=integration.calendar_id,
                event_id=created_event['id'],
                created_at=datetime.utcnow()
            )
            
            if save_calendar_event(uid, calendar_event):
                return calendar_event
            
            return None
            
        except HttpError as e:
            print(f"Google Calendar API error: {e}")
            return None
        except Exception as e:
            print(f"Error creating calendar event: {e}")
            return None

    def get_events(self, uid: str, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get upcoming calendar events."""
        try:
            credentials = self.get_credentials(uid)
            if not credentials:
                return []
            
            service = build('calendar', 'v3', credentials=credentials)
            integration = get_user_calendar_integration(uid)
            
            if not integration:
                return []
            
            # Get events from now to days_ahead
            now = datetime.utcnow()
            time_max = now + timedelta(days=days_ahead)
            
            events_result = service.events().list(
                calendarId=integration.calendar_id,
                timeMin=now.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                maxResults=100,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                formatted_events.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No Title'),
                    'description': event.get('description', ''),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'attendees': event.get('attendees', []),
                    'htmlLink': event.get('htmlLink', '')
                })
            
            return formatted_events
            
        except HttpError as e:
            print(f"Google Calendar API error: {e}")
            return []
        except Exception as e:
            print(f"Error getting calendar events: {e}")
            return []

    def create_memory_event(self, uid: str, memory_data: Dict[str, Any]) -> Optional[CalendarEvent]:
        """Create a calendar event from a memory/conversation."""
        try:
            config = get_user_calendar_config(uid)
            if not config.auto_create_events:
                return None
            
            # Extract relevant information from memory
            title = memory_data.get('structured', {}).get('title', 'Conversation')
            summary = memory_data.get('structured', {}).get('summary', '')
            started_at = memory_data.get('started_at')
            finished_at = memory_data.get('finished_at')
            transcript = memory_data.get('transcript', '')
            
            if not started_at:
                return None
            
            # Parse dates
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            
            if finished_at:
                end_time = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            else:
                end_time = start_time + timedelta(minutes=config.event_duration_minutes)
            
            # Build description
            description_parts = []
            if config.include_summary and summary:
                description_parts.append(f"Summary: {summary}")
            
            if config.include_transcript and transcript:
                # Limit transcript length
                transcript_preview = transcript[:500] + "..." if len(transcript) > 500 else transcript
                description_parts.append(f"\nTranscript:\n{transcript_preview}")
            
            description = "\n\n".join(description_parts) if description_parts else "Conversation recorded by Omi"
            
            # Create event
            event_data = CalendarEventCreate(
                summary=f"Omi: {title}",
                description=description,
                start_time=start_time,
                end_time=end_time,
                timezone=config.default_timezone
            )
            
            return self.create_event(uid, event_data)
            
        except Exception as e:
            print(f"Error creating memory event: {e}")
            return None


# Global service instance
calendar_service = GoogleCalendarService()