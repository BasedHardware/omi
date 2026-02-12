"""
Google Calendar Integration App for Omi

This app provides Google Calendar integration through OAuth2 authentication
and chat tools for managing calendar events.
"""
import os
import sys
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from db import (
    store_google_tokens,
    get_google_tokens,
    update_google_tokens,
    delete_google_tokens,
    store_oauth_state,
    get_oauth_state,
    delete_oauth_state,
    store_user_setting,
    get_user_setting,
)
from models import ChatToolResponse

load_dotenv()


def log(msg: str):
    """Print and flush immediately for Railway logging."""
    print(msg)
    sys.stdout.flush()


# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")

# Google API endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# Scopes needed for Calendar access
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

app = FastAPI(
    title="Google Calendar Omi Integration",
    description="Google Calendar integration for Omi - Manage your calendar with chat",
    version="1.0.0"
)


# ============================================
# Helper Functions
# ============================================

def get_valid_access_token(uid: str) -> Optional[str]:
    """
    Get a valid access token, refreshing if necessary.
    Returns None if user is not authenticated.
    """
    tokens = get_google_tokens(uid)
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")

    # Check if token is expired (with 5 minute buffer)
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(expiry.tzinfo) >= expiry - timedelta(minutes=5):
                # Token expired or about to expire, refresh it
                log(f"Token expired for {uid}, refreshing...")
                new_token = refresh_access_token(refresh_token)
                if new_token:
                    access_token = new_token["access_token"]
                    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_token.get("expires_in", 3600))).isoformat() + "Z"
                    update_google_tokens(uid, access_token, new_expires_at)
                else:
                    return None
        except Exception as e:
            log(f"Error checking token expiry: {e}")

    return access_token


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh the access token using the refresh token."""
    try:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
        )

        if response.status_code == 200:
            return response.json()
        else:
            log(f"Token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log(f"Error refreshing token: {e}")
        return None


def calendar_api_request(uid: str, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Optional[dict]:
    """Make an authenticated request to the Google Calendar API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return None

    url = f"{GOOGLE_CALENDAR_API}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=json_data)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=json_data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return None

        if response.status_code in [200, 201, 204]:
            if response.status_code == 204:
                return {"success": True}
            return response.json()
        else:
            log(f"Calendar API error: {response.status_code} - {response.text}")
            return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        log(f"Calendar API request error: {e}")
        return {"error": str(e)}


def parse_datetime(dt_str: str) -> tuple[datetime, bool]:
    """
    Parse a datetime string into a datetime object.
    Returns (datetime, is_all_day).
    Handles various formats including natural language.
    """
    dt_str = dt_str.strip().lower()
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Handle relative dates
    if dt_str in ("today", "now"):
        return now, False
    elif dt_str == "tomorrow":
        return today + timedelta(days=1), True
    elif dt_str == "next week":
        return today + timedelta(weeks=1), True

    # Handle time-only strings (assume today)
    time_formats = ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"]
    for fmt in time_formats:
        try:
            time_part = datetime.strptime(dt_str, fmt)
            return now.replace(hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0), False
        except ValueError:
            continue

    # Handle date formats
    date_formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%B %d",
        "%b %d",
    ]

    for fmt in date_formats:
        try:
            parsed = datetime.strptime(dt_str, fmt)
            # If no year in format, use current year
            if "%Y" not in fmt:
                parsed = parsed.replace(year=today.year)
            # If no time in format, it's an all-day event
            is_all_day = "%H" not in fmt and "%I" not in fmt
            return parsed, is_all_day
        except ValueError:
            continue

    # Default: try to parse as ISO format
    try:
        parsed = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None), False
    except:
        pass

    raise ValueError(f"Could not parse datetime: {dt_str}")


def get_user_calendars(uid: str) -> Optional[list]:
    """Fetch list of calendars for UI display."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return None

    result = calendar_api_request(uid, "GET", "/users/me/calendarList")
    if not result or "error" in result:
        return None

    calendars = result.get("items", [])
    return [
        {
            "id": cal.get("id", ""),
            "name": cal.get("summary", "Unnamed"),
            "primary": cal.get("primary", False),
            "access_role": cal.get("accessRole", "")
        }
        for cal in calendars
        if cal.get("accessRole") in ("owner", "writer")  # Only show calendars user can write to
    ]


def get_default_calendar(uid: str) -> str:
    """Get the user's default calendar ID, falling back to 'primary'."""
    saved_cal = get_user_setting(uid, "default_calendar")
    return saved_cal if saved_cal else "primary"


def format_event_time(event: dict) -> str:
    """Format event start/end time for display."""
    start = event.get("start", {})
    end = event.get("end", {})

    if "date" in start:
        # All-day event
        start_date = start["date"]
        end_date = end.get("date", start_date)
        if start_date == end_date:
            return f"All day on {start_date}"
        else:
            return f"All day from {start_date} to {end_date}"
    else:
        # Timed event
        start_dt = start.get("dateTime", "")
        end_dt = end.get("dateTime", "")
        try:
            start_parsed = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
            end_parsed = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
            start_str = start_parsed.strftime("%b %d, %Y %I:%M %p")
            end_str = end_parsed.strftime("%I:%M %p")
            return f"{start_str} - {end_str}"
        except:
            return f"{start_dt} - {end_dt}"


# ============================================
# Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    """
    return {
        "tools": [
            {
                "name": "list_events",
                "description": "List upcoming calendar events. Use this when the user wants to see their schedule, check upcoming meetings, view their calendar, or see what's planned.",
                "endpoint": "/tools/list_events",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look ahead (default: 7, max: 30)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of events to return (default: 10, max: 50)"
                        },
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar ID to list events from (default: primary calendar)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your calendar events..."
            },
            {
                "name": "create_event",
                "description": "Create a new calendar event. Use this when the user wants to schedule a meeting, add an event, create an appointment, or set a reminder.",
                "endpoint": "/tools/create_event",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Event title/summary. Required."
                        },
                        "start": {
                            "type": "string",
                            "description": "Event start time. Supports: 'tomorrow', '2pm', 'Jan 15 3pm', '2026-01-25T14:00:00'. Required."
                        },
                        "end": {
                            "type": "string",
                            "description": "Event end time. If not provided, defaults to 1 hour after start for timed events."
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description or notes."
                        },
                        "location": {
                            "type": "string",
                            "description": "Event location (address, room name, or video call link)."
                        },
                        "attendees": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of attendee email addresses to invite."
                        },
                        "all_day": {
                            "type": "boolean",
                            "description": "If true, create an all-day event."
                        },
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar ID to create event in (default: primary)"
                        }
                    },
                    "required": ["title", "start"]
                },
                "auth_required": True,
                "status_message": "Creating calendar event..."
            },
            {
                "name": "get_event",
                "description": "Get details of a specific calendar event. Use this when the user wants to see event details, check meeting info, or get specifics about an appointment.",
                "endpoint": "/tools/get_event",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "The event ID to get details for. Required."
                        },
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar ID the event is in (default: primary)"
                        }
                    },
                    "required": ["event_id"]
                },
                "auth_required": True,
                "status_message": "Getting event details..."
            },
            {
                "name": "update_event",
                "description": "Update an existing calendar event. Use this when the user wants to change, reschedule, modify, or edit an event.",
                "endpoint": "/tools/update_event",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "The event ID to update. Required."
                        },
                        "title": {
                            "type": "string",
                            "description": "New event title."
                        },
                        "start": {
                            "type": "string",
                            "description": "New start time."
                        },
                        "end": {
                            "type": "string",
                            "description": "New end time."
                        },
                        "description": {
                            "type": "string",
                            "description": "New description."
                        },
                        "location": {
                            "type": "string",
                            "description": "New location."
                        },
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar ID (default: primary)"
                        }
                    },
                    "required": ["event_id"]
                },
                "auth_required": True,
                "status_message": "Updating event..."
            },
            {
                "name": "delete_event",
                "description": "Delete a calendar event. Use this when the user wants to remove, cancel, or delete an event from their calendar.",
                "endpoint": "/tools/delete_event",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "The event ID to delete. Required."
                        },
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar ID (default: primary)"
                        }
                    },
                    "required": ["event_id"]
                },
                "auth_required": True,
                "status_message": "Deleting event..."
            },
            {
                "name": "list_calendars",
                "description": "List all calendars available to the user. Use this when the user wants to see their calendars, check which calendars they have access to, or find a calendar ID.",
                "endpoint": "/tools/list_calendars",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your calendars..."
            }
        ]
    }


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/list_events", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_events(request: Request):
    """List upcoming calendar events."""
    try:
        body = await request.json()
        log(f"=== LIST_EVENTS ===")

        uid = body.get("uid")
        days = min(body.get("days", 7), 30)
        max_results = min(body.get("max_results", 10), 50)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        # Use provided calendar_id or fall back to user's default
        calendar_id = body.get("calendar_id") or get_default_calendar(uid)

        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days)).isoformat() + "Z"

        result = calendar_api_request(uid, "GET", f"/calendars/{calendar_id}/events", params={
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime"
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get events: {result.get('error', 'Unknown error')}")

        events = result.get("items", [])

        if not events:
            return ChatToolResponse(result=f"No events in the next {days} days.")

        result_parts = [f"**Upcoming Events ({len(events)})**", ""]

        for event in events:
            summary = event.get("summary", "No title")
            time_str = format_event_time(event)
            location = event.get("location", "")
            event_id = event.get("id", "")

            line = f"- **{summary}**\n  {time_str}"
            if location:
                line += f"\n  Location: {location}"
            line += f"\n  ID: `{event_id[:20]}...`"
            result_parts.append(line)

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error listing events: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Failed to list events: {str(e)}")


@app.post("/tools/create_event", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_event(request: Request):
    """Create a new calendar event."""
    try:
        body = await request.json()
        log(f"=== CREATE_EVENT ===")
        log(f"Request: {body}")

        uid = body.get("uid")
        title = body.get("title")
        start_str = body.get("start")
        end_str = body.get("end")
        description = body.get("description", "")
        location = body.get("location", "")
        attendees = body.get("attendees", [])
        all_day = body.get("all_day", False)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        # Use provided calendar_id or fall back to user's default
        calendar_id = body.get("calendar_id") or get_default_calendar(uid)

        if not title:
            return ChatToolResponse(error="Event title is required")

        if not start_str:
            return ChatToolResponse(error="Event start time is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        # Parse start time
        try:
            start_dt, is_all_day = parse_datetime(start_str)
            if all_day:
                is_all_day = True
        except ValueError as e:
            return ChatToolResponse(error=str(e))

        # Parse or calculate end time
        if end_str:
            try:
                end_dt, _ = parse_datetime(end_str)
            except ValueError as e:
                return ChatToolResponse(error=f"Invalid end time: {e}")
        else:
            if is_all_day:
                end_dt = start_dt + timedelta(days=1)
            else:
                end_dt = start_dt + timedelta(hours=1)

        # Build event data
        event_data = {
            "summary": title,
        }

        if is_all_day:
            event_data["start"] = {"date": start_dt.strftime("%Y-%m-%d")}
            event_data["end"] = {"date": end_dt.strftime("%Y-%m-%d")}
        else:
            event_data["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "UTC"}
            event_data["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "UTC"}

        if description:
            event_data["description"] = description

        if location:
            event_data["location"] = location

        if attendees:
            event_data["attendees"] = [{"email": email.strip()} for email in attendees]

        log(f"Creating event: {event_data}")

        result = calendar_api_request(uid, "POST", f"/calendars/{calendar_id}/events", json_data=event_data)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to create event: {result.get('error', 'Unknown error')}")

        event_id = result.get("id", "")
        html_link = result.get("htmlLink", "")
        time_str = format_event_time(result)

        result_parts = [
            "**Event Created!**",
            "",
            f"**{title}**",
            f"When: {time_str}",
        ]
        if location:
            result_parts.append(f"Where: {location}")
        if attendees:
            result_parts.append(f"Attendees: {', '.join(attendees)}")
        if html_link:
            result_parts.append(f"Link: {html_link}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error creating event: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Failed to create event: {str(e)}")


@app.post("/tools/get_event", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_event(request: Request):
    """Get details of a specific event."""
    try:
        body = await request.json()
        uid = body.get("uid")
        event_id = body.get("event_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not event_id:
            return ChatToolResponse(error="Event ID is required. Use 'list events' to find event IDs.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        # Use provided calendar_id or fall back to user's default
        calendar_id = body.get("calendar_id") or get_default_calendar(uid)

        result = calendar_api_request(uid, "GET", f"/calendars/{calendar_id}/events/{event_id}")

        if not result or "error" in result:
            return ChatToolResponse(error=f"Event not found: {result.get('error', 'Unknown error')}")

        summary = result.get("summary", "No title")
        description = result.get("description", "")
        location = result.get("location", "")
        status = result.get("status", "confirmed")
        html_link = result.get("htmlLink", "")
        time_str = format_event_time(result)

        attendees = result.get("attendees", [])
        attendee_list = [a.get("email", "") for a in attendees]

        result_parts = [
            f"**{summary}**",
            "",
            f"**When:** {time_str}",
            f"**Status:** {status.title()}",
        ]

        if location:
            result_parts.append(f"**Where:** {location}")

        if description:
            desc_preview = description[:300]
            if len(description) > 300:
                desc_preview += "..."
            result_parts.append(f"**Description:** {desc_preview}")

        if attendee_list:
            result_parts.append(f"**Attendees:** {', '.join(attendee_list)}")

        if html_link:
            result_parts.append(f"**Link:** {html_link}")

        result_parts.append(f"**Event ID:** `{event_id}`")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting event: {e}")
        return ChatToolResponse(error=f"Failed to get event: {str(e)}")


@app.post("/tools/update_event", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_update_event(request: Request):
    """Update an existing calendar event."""
    try:
        body = await request.json()
        log(f"=== UPDATE_EVENT ===")

        uid = body.get("uid")
        event_id = body.get("event_id")
        title = body.get("title")
        start_str = body.get("start")
        end_str = body.get("end")
        description = body.get("description")
        location = body.get("location")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not event_id:
            return ChatToolResponse(error="Event ID is required. Use 'list events' to find event IDs.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        # Use provided calendar_id or fall back to user's default
        calendar_id = body.get("calendar_id") or get_default_calendar(uid)

        # Get existing event first
        existing = calendar_api_request(uid, "GET", f"/calendars/{calendar_id}/events/{event_id}")
        if not existing or "error" in existing:
            return ChatToolResponse(error=f"Event not found: {existing.get('error', 'Unknown error')}")

        # Build update data
        update_data = {}
        updates = []

        if title:
            update_data["summary"] = title
            updates.append(f"Title: {title}")

        if start_str:
            try:
                start_dt, is_all_day = parse_datetime(start_str)
                if is_all_day:
                    update_data["start"] = {"date": start_dt.strftime("%Y-%m-%d")}
                else:
                    update_data["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "UTC"}
                updates.append(f"Start: {start_str}")
            except ValueError as e:
                return ChatToolResponse(error=f"Invalid start time: {e}")

        if end_str:
            try:
                end_dt, is_all_day = parse_datetime(end_str)
                if is_all_day:
                    update_data["end"] = {"date": end_dt.strftime("%Y-%m-%d")}
                else:
                    update_data["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "UTC"}
                updates.append(f"End: {end_str}")
            except ValueError as e:
                return ChatToolResponse(error=f"Invalid end time: {e}")

        if description is not None:
            update_data["description"] = description
            updates.append("Description updated")

        if location is not None:
            update_data["location"] = location
            updates.append(f"Location: {location}")

        if not update_data:
            return ChatToolResponse(error="No updates provided. Specify title, start, end, description, or location.")

        result = calendar_api_request(uid, "PATCH", f"/calendars/{calendar_id}/events/{event_id}", json_data=update_data)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to update event: {result.get('error', 'Unknown error')}")

        result_parts = ["**Event Updated!**", ""] + updates

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error updating event: {e}")
        return ChatToolResponse(error=f"Failed to update event: {str(e)}")


@app.post("/tools/delete_event", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_delete_event(request: Request):
    """Delete a calendar event."""
    try:
        body = await request.json()
        uid = body.get("uid")
        event_id = body.get("event_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not event_id:
            return ChatToolResponse(error="Event ID is required. Use 'list events' to find event IDs.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        # Use provided calendar_id or fall back to user's default
        calendar_id = body.get("calendar_id") or get_default_calendar(uid)

        # Get event title first for confirmation message
        existing = calendar_api_request(uid, "GET", f"/calendars/{calendar_id}/events/{event_id}")
        event_title = existing.get("summary", "Event") if existing and "error" not in existing else "Event"

        result = calendar_api_request(uid, "DELETE", f"/calendars/{calendar_id}/events/{event_id}")

        if result and "error" in result:
            return ChatToolResponse(error=f"Failed to delete event: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Event Deleted**\n\nDeleted: {event_title}")

    except Exception as e:
        log(f"Error deleting event: {e}")
        return ChatToolResponse(error=f"Failed to delete event: {str(e)}")


@app.post("/tools/list_calendars", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_calendars(request: Request):
    """List all calendars available to the user."""
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Google Calendar first in the app settings.")

        result = calendar_api_request(uid, "GET", "/users/me/calendarList")

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to list calendars: {result.get('error', 'Unknown error')}")

        calendars = result.get("items", [])

        if not calendars:
            return ChatToolResponse(result="No calendars found.")

        result_parts = [f"**Your Calendars ({len(calendars)})**", ""]

        for cal in calendars:
            name = cal.get("summary", "Unnamed")
            cal_id = cal.get("id", "")
            primary = " (Primary)" if cal.get("primary") else ""
            access_role = cal.get("accessRole", "")

            result_parts.append(f"- **{name}**{primary}")
            result_parts.append(f"  ID: `{cal_id}`")
            if access_role:
                result_parts.append(f"  Access: {access_role}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error listing calendars: {e}")
        return ChatToolResponse(error=f"Failed to list calendars: {str(e)}")


# ============================================
# OAuth & Setup Endpoints
# ============================================

@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint - Homepage."""
    if not uid:
        return {
            "app": "Google Calendar Omi Integration",
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/auth/google?uid=<user_id>",
                "setup_check": "/setup/google?uid=<user_id>",
                "tools_manifest": "/.well-known/omi-tools.json"
            }
        }

    tokens = get_google_tokens(uid)

    if not tokens:
        auth_url = f"/auth/google?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Google Calendar - Connect</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">📅</div>
                    <h1>Google Calendar</h1>
                    <p>Manage your calendar through Omi chat</p>

                    <a href="{auth_url}" class="btn btn-primary btn-block">
                        Connect Google Calendar
                    </a>

                    <div class="card">
                        <h3>What You Can Do</h3>
                        <ul>
                            <li><strong>View Events</strong> - See your upcoming schedule</li>
                            <li><strong>Create Events</strong> - Schedule meetings and appointments</li>
                            <li><strong>Update Events</strong> - Reschedule or modify events</li>
                            <li><strong>Delete Events</strong> - Remove events from your calendar</li>
                        </ul>
                    </div>

                    <div class="card">
                        <h3>Example Commands</h3>
                        <div class="example">"What's on my calendar today?"</div>
                        <div class="example">"Schedule a meeting tomorrow at 2pm"</div>
                        <div class="example">"Cancel my 3pm appointment"</div>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    # User is connected - fetch calendars for selection
    calendars = get_user_calendars(uid)
    current_calendar = get_default_calendar(uid)

    # Build calendar options HTML
    calendar_options = ""
    current_calendar_name = "Primary Calendar"
    if calendars:
        for cal in calendars:
            selected = "selected" if cal["id"] == current_calendar or (current_calendar == "primary" and cal["primary"]) else ""
            primary_badge = " (Primary)" if cal["primary"] else ""
            calendar_options += f'<option value="{cal["id"]}" {selected}>{cal["name"]}{primary_badge}</option>'
            if selected:
                current_calendar_name = cal["name"] + primary_badge
    else:
        calendar_options = '<option value="primary" selected>Primary Calendar</option>'

    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Google Calendar - Connected</title>
            <style>{get_css()}</style>
        </head>
        <body>
            <div class="container">
                <div class="success-box">
                    <div class="icon" style="font-size: 48px;">✓</div>
                    <h2>Google Calendar Connected</h2>
                    <p>Your Google Calendar is linked to Omi</p>
                </div>

                <div class="card">
                    <h3>Default Calendar</h3>
                    <p style="text-align: left; margin-bottom: 12px;">Choose which calendar to use when creating events:</p>
                    <form action="/update-calendar" method="POST" id="calendarForm">
                        <input type="hidden" name="uid" value="{uid}">
                        <select name="calendar_id" class="select-input" onchange="this.form.submit()">
                            {calendar_options}
                        </select>
                    </form>
                </div>

                <div class="card">
                    <h3>Try These Commands</h3>
                    <div class="example">"Show me my calendar for this week"</div>
                    <div class="example">"Create a meeting with John tomorrow at 3pm"</div>
                    <div class="example">"What do I have scheduled for Friday?"</div>
                </div>

                <a href="/disconnect?uid={uid}" class="btn btn-secondary btn-block">
                    Disconnect Google Calendar
                </a>

                <div class="footer">Powered by <strong>Omi</strong></div>
            </div>
        </body>
    </html>
    """)


@app.get("/auth/google")
async def google_auth(uid: str = Query(...)):
    """Start Google OAuth2 flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth credentials not configured")

    state = f"{uid}:{secrets.token_urlsafe(32)}"
    store_oauth_state(uid, state)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Google OAuth2 callback."""
    if error:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>{error}</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    if not code or not state:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>Missing authorization code or state.</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    # Extract uid from state
    try:
        uid = state.split(":")[0]
    except:
        return HTMLResponse(content="Invalid state", status_code=400)

    # Verify state
    stored_state = get_oauth_state(uid)
    if stored_state != state:
        return HTMLResponse(content="State mismatch", status_code=400)

    delete_oauth_state(uid)

    # Exchange code for tokens
    try:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI
            }
        )

        if response.status_code != 200:
            log(f"Token exchange failed: {response.text}")
            return HTMLResponse(content=f"Token exchange failed: {response.text}", status_code=400)

        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token:
            return HTMLResponse(content="No access token received", status_code=400)

        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

        store_google_tokens(uid, access_token, refresh_token or "", expires_at)

        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Connected!</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="success-box">
                        <div class="icon" style="font-size: 72px;">🎉</div>
                        <h2>Successfully Connected!</h2>
                        <p>Your Google Calendar is now linked to Omi</p>
                    </div>

                    <a href="/?uid={uid}" class="btn btn-primary btn-block">
                        Continue to Settings
                    </a>

                    <div class="card">
                        <h3>Ready to Go!</h3>
                        <p>You can now manage your calendar by chatting with Omi.</p>
                        <p>Try: <strong>"What's on my calendar today?"</strong></p>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    except Exception as e:
        log(f"OAuth error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"Authentication error: {str(e)}", status_code=500)


@app.get("/setup/google")
async def check_setup(uid: str = Query(...)):
    """Check if user has completed Google Calendar setup."""
    tokens = get_google_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect(uid: str = Query(...)):
    """Disconnect Google Calendar."""
    delete_google_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


@app.post("/update-calendar")
async def update_calendar(request: Request):
    """Update the default calendar for a user."""
    form_data = await request.form()
    uid = form_data.get("uid")
    calendar_id = form_data.get("calendar_id")

    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")

    if calendar_id:
        store_user_setting(uid, "default_calendar", calendar_id)
        log(f"Updated default calendar for {uid} to {calendar_id}")

    return RedirectResponse(url=f"/?uid={uid}", status_code=303)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "google-calendar-omi"}


# ============================================
# CSS Styles
# ============================================

def get_css() -> str:
    """Returns Google-inspired dark theme CSS."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .icon { font-size: 64px; text-align: center; margin-bottom: 20px; }
        h1 { color: #fff; font-size: 28px; text-align: center; margin-bottom: 8px; }
        h2 { color: #fff; font-size: 22px; margin-bottom: 12px; }
        h3 { color: #fff; font-size: 18px; margin-bottom: 12px; }
        p { color: #a0a0a0; text-align: center; margin-bottom: 24px; }
        .card {
            background: #252540;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            border: 1px solid #3a3a5c;
        }
        .btn {
            display: inline-block;
            padding: 14px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            font-size: 16px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #4285f4;
            color: #fff;
        }
        .btn-primary:hover { background: #5a9cf5; }
        .btn-secondary {
            background: transparent;
            color: #a0a0a0;
            border: 1px solid #3a3a5c;
        }
        .btn-secondary:hover { background: #3a3a5c; }
        .btn-block { display: block; width: 100%; margin: 12px 0; }
        .success-box {
            background: rgba(52, 168, 83, 0.15);
            border: 1px solid #34a853;
            border-radius: 12px;
            padding: 32px;
            text-align: center;
            margin-bottom: 24px;
        }
        .success-box h2 { color: #34a853; }
        .error-box {
            background: rgba(234, 67, 53, 0.15);
            border: 1px solid #ea4335;
            border-radius: 12px;
            padding: 32px;
            text-align: center;
        }
        .error-box h2 { color: #ea4335; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px 0; border-bottom: 1px solid #3a3a5c; }
        li:last-child { border-bottom: none; }
        .example {
            background: #1a1a2e;
            padding: 12px 16px;
            border-radius: 8px;
            margin: 8px 0;
            font-style: italic;
            color: #a0a0a0;
            border: 1px solid #3a3a5c;
        }
        .footer {
            text-align: center;
            color: #606060;
            margin-top: 40px;
            padding: 20px;
            font-size: 14px;
        }
        .footer strong { color: #4285f4; }
        .select-input {
            width: 100%;
            padding: 12px 16px;
            font-size: 16px;
            border: 1px solid #3a3a5c;
            border-radius: 8px;
            background: #1a1a2e;
            color: #e0e0e0;
            cursor: pointer;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23a0a0a0' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 12px center;
        }
        .select-input:focus {
            outline: none;
            border-color: #4285f4;
        }
        .select-input:hover {
            border-color: #5a5a8c;
        }
        @media (max-width: 480px) {
            body { padding: 12px; }
            .card { padding: 18px; }
            h1 { font-size: 24px; }
        }
    """


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    print("Google Calendar Omi Integration")
    print("=" * 50)
    print(f"Starting on {host}:{port}")
    print("=" * 50)

    uvicorn.run("main:app", host=host, port=port, reload=True)
