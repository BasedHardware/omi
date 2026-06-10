# calendar_server.py
"""
Google Calendar MCP Server using FastMCP
Install: pip install mcp google-auth google-auth-oauthlib google-api-python-client
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
# import pytz
from pathlib import Path
import os

CREDS_DIR = Path(__file__).resolve().parent.parent / 'credentials'
TOKEN_PATH = CREDS_DIR / 'token.json'

# Initialize FastMCP server
mcp = FastMCP("google-calendar")

# Google Calendar API scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events'
]

# Global Calendar service instance
_calendar_service = None


def get_calendar_service():
    """Initialize and return Calendar service (singleton pattern)"""
    global _calendar_service
    
    if _calendar_service is None:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(str(TOKEN_PATH), 'w') as token:
                token.write(creds.to_json())
        
        _calendar_service = build('calendar', 'v3', credentials=creds)
    
    return _calendar_service


@mcp.tool()
def list_calendars() -> str:
    """
    List all calendars accessible to the user.
    
    Returns:
        List of calendars with details
    """
    try:
        service = get_calendar_service()
        
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])
        
        if not calendars:
            return "No calendars found."
        
        cal_list = []
        for cal in calendars:
            cal_list.append(
                f"Calendar: {cal['summary']}\n"
                f"ID: {cal['id']}\n"
                f"Primary: {cal.get('primary', False)}\n"
                f"Time Zone: {cal.get('timeZone', 'Unknown')}\n"
            )
        
        return "\n" + "="*60 + "\n".join(cal_list)
        
    except Exception as e:
        return f"❌ Error listing calendars: {str(e)}"


@mcp.tool()
def get_upcoming_events(calendar_id: str = "primary", max_results: int = 10, days_ahead: int = 7) -> str:
    """
    Get upcoming events from a calendar.
    
    Args:
        calendar_id: Calendar ID (default: "primary")
        max_results: Maximum number of events (default: 10)
        days_ahead: Number of days to look ahead (default: 7)
    
    Returns:
        List of upcoming events
    """
    try:
        service = get_calendar_service()
        
        now = datetime.utcnow().isoformat() + 'Z'
        end_time = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            timeMax=end_time,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No upcoming events found in the next {days_ahead} days."
        
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            event_list.append(
                f"Event: {event['summary']}\n"
                f"ID: {event['id']}\n"
                f"Start: {start}\n"
                f"End: {end}\n"
                f"Location: {event.get('location', 'Not specified')}\n"
                f"Description: {event.get('description', 'No description')}\n"
                f"Link: {event.get('htmlLink', 'N/A')}\n"
            )
        
        return "\n" + "="*60 + "\n".join(event_list)
        
    except Exception as e:
        return f"❌ Error getting events: {str(e)}"


@mcp.tool()
def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[str] = None,
    timezone: str = "UTC"
) -> str:
    """
    Create a new calendar event.
    
    Args:
        summary: Event title
        start_time: Start time in ISO format (e.g., "2024-01-15T10:00:00")
        end_time: End time in ISO format
        calendar_id: Calendar ID (default: "primary")
        description: Event description (optional)
        location: Event location (optional)
        attendees: Comma-separated email addresses (optional)
        timezone: Timezone for the event (default: "UTC")
    
    Returns:
        Event creation confirmation
    """
    try:
        service = get_calendar_service()
        
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time,
                'timeZone': timezone,
            },
        }
        
        if description:
            event['description'] = description
        
        if location:
            event['location'] = location
        
        if attendees:
            email_list = [email.strip() for email in attendees.split(',')]
            event['attendees'] = [{'email': email} for email in email_list]
        
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        return (
            f"✅ Event created successfully!\n"
            f"Title: {created_event['summary']}\n"
            f"ID: {created_event['id']}\n"
            f"Start: {start_time}\n"
            f"End: {end_time}\n"
            f"Link: {created_event.get('htmlLink', 'N/A')}"
        )
        
    except Exception as e:
        return f"❌ Error creating event: {str(e)}"


@mcp.tool()
def update_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """
    Update an existing calendar event.
    
    Args:
        event_id: Event ID to update
        calendar_id: Calendar ID (default: "primary")
        summary: New event title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New description (optional)
        location: New location (optional)
    
    Returns:
        Update confirmation
    """
    try:
        service = get_calendar_service()
        
        # Get existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Update fields if provided
        if summary:
            event['summary'] = summary
        if start_time:
            event['start']['dateTime'] = start_time
        if end_time:
            event['end']['dateTime'] = end_time
        if description:
            event['description'] = description
        if location:
            event['location'] = location
        
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event
        ).execute()
        
        return (
            f"✅ Event updated successfully!\n"
            f"Title: {updated_event['summary']}\n"
            f"ID: {updated_event['id']}\n"
            f"Link: {updated_event.get('htmlLink', 'N/A')}"
        )
        
    except Exception as e:
        return f"❌ Error updating event: {str(e)}"


@mcp.tool()
def delete_calendar_event(event_id: str, calendar_id: str = "primary") -> str:
    """
    Delete a calendar event.
    
    Args:
        event_id: Event ID to delete
        calendar_id: Calendar ID (default: "primary")
    
    Returns:
        Deletion confirmation
    """
    try:
        service = get_calendar_service()
        
        # Get event details before deleting
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        event_title = event.get('summary', 'Untitled Event')
        
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        
        return f"✅ Event '{event_title}' deleted successfully"
        
    except Exception as e:
        return f"❌ Error deleting event: {str(e)}"


@mcp.tool()
def search_calendar_events(query: str, calendar_id: str = "primary", max_results: int = 10) -> str:
    """
    Search for calendar events by text query.
    
    Args:
        query: Search query text
        calendar_id: Calendar ID (default: "primary")
        max_results: Maximum number of results (default: 10)
    
    Returns:
        List of matching events
    """
    try:
        service = get_calendar_service()
        
        events_result = service.events().list(
            calendarId=calendar_id,
            q=query,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No events found matching '{query}'"
        
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            event_list.append(
                f"Event: {event['summary']}\n"
                f"ID: {event['id']}\n"
                f"Start: {start}\n"
                f"End: {end}\n"
                f"Location: {event.get('location', 'Not specified')}\n"
                f"Description: {event.get('description', 'No description')}\n"
            )
        
        return "\n" + "="*60 + "\n".join(event_list)
        
    except Exception as e:
        return f"❌ Error searching events: {str(e)}"


@mcp.tool()
def get_events_for_date(date: str, calendar_id: str = "primary") -> str:
    """
    Get all events for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
        calendar_id: Calendar ID (default: "primary")
    
    Returns:
        List of events on that date
    """
    try:
        service = get_calendar_service()
        
        start_time = f"{date}T00:00:00Z"
        end_time = f"{date}T23:59:59Z"
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No events found on {date}"
        
        event_list = [f"Events for {date}:"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            event_list.append(
                f"\n{event['summary']}\n"
                f"Time: {start} to {end}\n"
                f"Location: {event.get('location', 'Not specified')}\n"
                f"ID: {event['id']}"
            )
        
        return "\n".join(event_list)
        
    except Exception as e:
        return f"❌ Error getting events: {str(e)}"


@mcp.tool()
def create_recurring_event(
    summary: str,
    start_time: str,
    end_time: str,
    recurrence_rule: str,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: str = "UTC"
) -> str:
    """
    Create a recurring calendar event.
    
    Args:
        summary: Event title
        start_time: Start time in ISO format
        end_time: End time in ISO format
        recurrence_rule: RRULE string (e.g., "RRULE:FREQ=DAILY;COUNT=10" for daily for 10 days)
        calendar_id: Calendar ID (default: "primary")
        description: Event description (optional)
        location: Event location (optional)
        timezone: Timezone (default: "UTC")
    
    Returns:
        Event creation confirmation
    """
    try:
        service = get_calendar_service()
        
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time,
                'timeZone': timezone,
            },
            'recurrence': [recurrence_rule],
        }
        
        if description:
            event['description'] = description
        
        if location:
            event['location'] = location
        
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        return (
            f"✅ Recurring event created successfully!\n"
            f"Title: {created_event['summary']}\n"
            f"ID: {created_event['id']}\n"
            f"Recurrence: {recurrence_rule}\n"
            f"Link: {created_event.get('htmlLink', 'N/A')}"
        )
        
    except Exception as e:
        return f"❌ Error creating recurring event: {str(e)}"


@mcp.tool()
def get_free_busy_times(
    time_min: str,
    time_max: str,
    calendars: Optional[str] = None
) -> str:
    """
    Check free/busy status for calendars within a time range.
    
    Args:
        time_min: Start time in ISO format
        time_max: End time in ISO format
        calendars: Comma-separated calendar IDs (optional, defaults to primary)
    
    Returns:
        Free/busy information
    """
    try:
        service = get_calendar_service()
        
        calendar_list = calendars.split(',') if calendars else ['primary']
        calendar_ids = [{'id': cal.strip()} for cal in calendar_list]
        
        body = {
            'timeMin': time_min,
            'timeMax': time_max,
            'items': calendar_ids
        }
        
        freebusy_result = service.freebusy().query(body=body).execute()
        
        result_list = []
        for cal_id, cal_data in freebusy_result['calendars'].items():
            busy_times = cal_data.get('busy', [])
            
            result_list.append(f"Calendar: {cal_id}")
            if busy_times:
                result_list.append("Busy times:")
                for busy in busy_times:
                    result_list.append(f"  {busy['start']} to {busy['end']}")
            else:
                result_list.append("  No busy times - completely free!")
            result_list.append("")
        
        return "\n".join(result_list)
        
    except Exception as e:
        return f"❌ Error checking free/busy: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")