"""
Tools for accessing Google Calendar events.
"""

import os
import time
import contextvars
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import requests
from utils.retrieval.tools.integration_base import (
    ensure_capped,
    parse_iso_with_tz,
    prepare_access,
)
from utils.retrieval.tools.google_utils import google_api_request

# Import shared Google utilities
from utils.retrieval.tools.google_utils import refresh_google_token
import logging

logger = logging.getLogger(__name__)

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def search_google_contacts(access_token: str, query: str) -> Optional[str]:
    """
    Search Google Contacts (People API) for a contact by name and return email address.
    Searches both "My Contacts" and "Other Contacts" (auto-created from emails, calendar, etc.).

    Args:
        access_token: Google access token (can be from Calendar or Contacts)
        query: Name to search for (e.g., "Riddhi Gupta")

    Returns:
        Email address if found, None otherwise
    """
    # First, search in "My Contacts"
    try:
        response = requests.get(
            'https://people.googleapis.com/v1/people:searchContacts',
            headers={'Authorization': f'Bearer {access_token}'},
            params={
                'query': query,
                'readMask': 'emailAddresses,names',
                'pageSize': 10,
            },
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])

            if results:
                # Get the first result's email
                person = results[0].get('person', {})
                email_addresses = person.get('emailAddresses', [])

                if email_addresses:
                    email = email_addresses[0].get('value')
                    return email
        elif response.status_code == 401:
            logger.warning(f"❌ Google Contacts API 401 - token expired")
            return None
        elif response.status_code == 403:
            # Will try Other Contacts
            pass
        else:
            error_body = response.text[:200] if response.text else "No error body"
            logger.error(f"⚠️ Google Contacts API error {response.status_code}: {error_body}")
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️ Network error searching My Contacts: {e}")
    except Exception as e:
        logger.error(f"⚠️ Error searching My Contacts: {e}")

    # If not found in My Contacts, search in "Other Contacts"
    try:
        # First, warm up the cache with an empty query (recommended by Google)
        try:
            warmup_response = requests.get(
                'https://people.googleapis.com/v1/otherContacts:search',
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'query': '',
                    'readMask': 'names,emailAddresses',
                },
                timeout=10.0,
            )
            logger.info(f"📇 Other Contacts warm-up response status: {warmup_response.status_code}")
            # Wait a moment for cache to update (not strictly necessary but recommended)
            time.sleep(0.5)
        except Exception as warmup_error:
            logger.error(f"⚠️ Other Contacts warm-up failed (non-critical): {warmup_error}")

        # Now perform the actual search
        response = requests.get(
            'https://people.googleapis.com/v1/otherContacts:search',
            headers={'Authorization': f'Bearer {access_token}'},
            params={
                'query': query,
                'readMask': 'names,emailAddresses',
            },
            timeout=10.0,
        )

        logger.info(f"📇 Google Contacts API (Other Contacts) response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])

            if results:
                # Get the first result's email
                person = results[0].get('person', {})
                email_addresses = person.get('emailAddresses', [])

                if email_addresses:
                    email = email_addresses[0].get('value')
                    name = person.get('names', [{}])[0].get('displayName', query)
                    logger.info(f"✅ Found contact in Other Contacts: {name} -> {email}")
                    return email
                else:
                    logger.info(f"⚠️ Found contact '{query}' in Other Contacts but no email address")
            else:
                logger.info(f"⚠️ No contacts found in Other Contacts for: {query}")
        elif response.status_code == 401:
            logger.warning(f"❌ Google Contacts API 401 - token expired")
            return None
        elif response.status_code == 403:
            logger.info(f"❌ Google Contacts API 403 - insufficient permissions (Other Contacts access required)")
            return None
        else:
            error_body = response.text[:200] if response.text else "No error body"
            logger.error(f"⚠️ Google Contacts API (Other Contacts) error {response.status_code}: {error_body}")
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️ Network error searching Other Contacts: {e}")
    except Exception as e:
        logger.error(f"⚠️ Error searching Other Contacts: {e}")

    logger.info(f"⚠️ No contacts found in My Contacts or Other Contacts for: {query}")
    return None


def resolve_attendee_to_email(access_token: str, attendee: str) -> Optional[str]:
    """
    Resolve an attendee string to an email address.
    If it's already an email, return it. If it's a name, search Google Contacts.

    Args:
        access_token: Google access token
        attendee: Either an email address or a name

    Returns:
        Email address or None if not found
    """
    # Check if it's already an email address (simple check)
    if '@' in attendee and '.' in attendee.split('@')[1]:
        # Looks like an email, return as-is
        logger.info(f"📧 '{attendee}' appears to be an email address")
        return attendee

    # It's a name, search Google Contacts
    logger.info(f"👤 '{attendee}' appears to be a name, searching Google Contacts...")
    return search_google_contacts(access_token, attendee)


def create_google_calendar_event(
    access_token: str,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list] = None,
) -> dict:
    """
    Create a new event in Google Calendar.

    Args:
        access_token: Google Calendar access token
        summary: Event title/summary
        start_time: Event start time (datetime with timezone)
        end_time: Event end time (datetime with timezone)
        description: Optional event description
        location: Optional event location
        attendees: Optional list of attendee email addresses

    Returns:
        Created event data
    """
    # Convert to UTC if timezone-aware, otherwise assume UTC
    if start_time.tzinfo is not None:
        start_time_utc = start_time.astimezone(timezone.utc)
    else:
        start_time_utc = start_time.replace(tzinfo=timezone.utc)

    if end_time.tzinfo is not None:
        end_time_utc = end_time.astimezone(timezone.utc)
    else:
        end_time_utc = end_time.replace(tzinfo=timezone.utc)

    # Format times in RFC3339 format (UTC)
    start_time_str = start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time_str = end_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Build event body
    event_body = {
        'summary': summary,
        'start': {
            'dateTime': start_time_str,
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_time_str,
            'timeZone': 'UTC',
        },
    }

    if description:
        event_body['description'] = description

    if location:
        event_body['location'] = location

    if attendees:
        event_body['attendees'] = [{'email': email} for email in attendees]

    logger.info(f"📅 Creating Google Calendar event: {summary} from {start_time_str} to {end_time_str}")

    event = google_api_request(
        "POST",
        'https://www.googleapis.com/calendar/v3/calendars/primary/events',
        access_token,
        body=event_body,
    )
    return event


def get_google_calendar_event(access_token: str, event_id: str) -> dict:
    """
    Get a single calendar event by event ID.

    Args:
        access_token: Google Calendar access token
        event_id: Event ID to retrieve

    Returns:
        Event data
    """
    logger.info(f"📅 Getting Google Calendar event: {event_id}")

    event_data = google_api_request(
        "GET",
        f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}',
        access_token,
    )
    return event_data


def update_google_calendar_event(
    access_token: str,
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list] = None,
) -> dict:
    """
    Update an existing calendar event.

    Args:
        access_token: Google Calendar access token
        event_id: Event ID to update
        summary: Optional new event title/summary
        start_time: Optional new start time (datetime with timezone)
        end_time: Optional new end time (datetime with timezone)
        description: Optional new description
        location: Optional new location
        attendees: Optional new list of attendee email addresses (replaces existing attendees)

    Returns:
        Updated event data
    """
    logger.info(f"📅 Updating Google Calendar event: {event_id}")

    # Build update body with only provided fields
    event_body = {}

    if summary is not None:
        event_body['summary'] = summary

    if start_time is not None:
        if start_time.tzinfo is not None:
            start_time_utc = start_time.astimezone(timezone.utc)
        else:
            start_time_utc = start_time.replace(tzinfo=timezone.utc)
        start_time_str = start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        event_body['start'] = {
            'dateTime': start_time_str,
            'timeZone': 'UTC',
        }

    if end_time is not None:
        if end_time.tzinfo is not None:
            end_time_utc = end_time.astimezone(timezone.utc)
        else:
            end_time_utc = end_time.replace(tzinfo=timezone.utc)
        end_time_str = end_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        event_body['end'] = {
            'dateTime': end_time_str,
            'timeZone': 'UTC',
        }

    if description is not None:
        event_body['description'] = description

    if location is not None:
        event_body['location'] = location

    if attendees is not None:
        event_body['attendees'] = [{'email': email} for email in attendees]

    if not event_body:
        raise Exception("No fields provided to update")

    logger.info(f"📅 Updating event with fields: {list(event_body.keys())}")

    updated = google_api_request(
        "PATCH",
        f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}',
        access_token,
        body=event_body,
    )
    return updated


def delete_google_calendar_event(access_token: str, event_id: str) -> bool:
    """
    Delete a calendar event by event ID.

    Args:
        access_token: Google Calendar access token
        event_id: Event ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    logger.info(f"🗑️ Deleting Google Calendar event: {event_id}")

    google_api_request(
        "DELETE",
        f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}',
        access_token,
        allow_204=True,
    )
    return True


def get_google_calendar_events(
    access_token: str,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    max_results: int = 10,
    search_query: Optional[str] = None,
) -> list:
    """
    Fetch events from Google Calendar API.

    Args:
        access_token: Google Calendar access token
        time_min: Minimum time for events (defaults to now)
        time_max: Maximum time for events (defaults to 7 days from now)
        max_results: Maximum number of events to return
        search_query: Optional search query to filter events by title, description, attendees, etc.

    Returns:
        List of calendar events
    """
    now = datetime.now(timezone.utc)
    time_min = (time_min or now).astimezone(timezone.utc)
    time_max = (time_max or (time_min + timedelta(days=7))).astimezone(timezone.utc)

    # Format times in RFC3339 format (UTC)
    time_min_str = time_min.strftime('%Y-%m-%dT%H:%M:%SZ')
    time_max_str = time_max.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'timeMin': time_min_str,
        'timeMax': time_max_str,
        'singleEvents': 'true',
        'orderBy': 'startTime',
        'maxResults': 2500,
    }
    if search_query:
        params['q'] = search_query

    events = []
    page = None

    while True:
        if page:
            params['pageToken'] = page

        data = google_api_request(
            "GET",
            'https://www.googleapis.com/calendar/v3/calendars/primary/events',
            access_token,
            params=params,
        )
        events.extend(data.get('items', []))

        if len(events) >= max_results:
            return events[:max_results]

        page = data.get('nextPageToken')
        if not page:
            break

    return events[:max_results]


@tool
def get_calendar_events_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 10,
    search_query: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve calendar events from the user's Google Calendar.

    Use this tool when:
    - User asks "what's on my calendar?" or "show me my events"
    - User asks about upcoming meetings or appointments
    - User wants to know what they have scheduled for a specific day/week
    - User asks "do I have anything scheduled?" or "what's coming up?"
    - User mentions checking their calendar or schedule
    - **ALWAYS use this tool when the user asks about their calendar or events**
    - **When user asks about a specific person (e.g., "when did I meet with Andy?") or topic, use search_query parameter**

    Date formatting:
    - Dates should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T00:00:00-08:00" for January 20, 2024 at midnight in PST
    - If start_date is not provided, defaults to now
    - If end_date is not provided, defaults to 7 days from start_date

    Search query:
    - Use search_query when user asks about a specific person, company, or topic
    - Examples: "Andy", "Deepgram", "project review", "team meeting"
    - Searches in event title, description, and attendees
    - For person names, use just the first name or full name (e.g., "Andy" or "Andy Smith")

    Args:
        start_date: Start date/time for events in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-20T00:00:00-08:00"). Defaults to now if not provided.
        end_date: End date/time for events in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-27T23:59:59-08:00"). Defaults to 7 days from start_date if not provided.
        max_results: Maximum number of events to return (default: 10, max: 50)
        search_query: Optional search term to filter events (e.g., person name like "Andy", company name like "Deepgram", or topic). Searches in event title, description, and attendees.

    Returns:
        Formatted list of calendar events with their details.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'google_calendar',
        'Google Calendar',
        'Google Calendar is not connected. Please connect your Google Calendar from settings to view your events.',
        'Google Calendar access token not found. Please reconnect your Google Calendar from settings.',
        'Error checking Google Calendar connection',
    )
    if access_err:
        return access_err

    try:
        max_results = ensure_capped(max_results, 50, "⚠️ get_calendar_events_tool - max_results capped from {} to {}")

        # Parse dates if provided
        time_min = None
        time_max = None

        time_min, err = parse_iso_with_tz(
            'start_date',
            start_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T00:00:00-08:00')",
        )
        if err:
            return err
        time_max, err = parse_iso_with_tz(
            'end_date',
            end_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-27T23:59:59-08:00')",
        )
        if err:
            return err

        # If search_query is provided, expand date range to ensure we don't miss events
        # Default to searching back 1 year if no dates provided, or expand range if dates are too narrow
        if search_query:
            now = datetime.now(timezone.utc)
            if time_max is None:
                time_max = now
            if time_min is None:
                # Default to 1 year back when searching
                time_min = time_max - timedelta(days=365)
                logger.info(
                    f"📅 search_query provided, defaulting to 1 year range: {time_min.strftime('%Y-%m-%d')} to {time_max.strftime('%Y-%m-%d')}"
                )
            else:
                # If dates are provided but range is less than 6 months, expand to at least 6 months
                days_range = (time_max - time_min).days
                if days_range < 180:  # Less than 6 months
                    # Expand backwards from time_max to ensure at least 6 months
                    time_min = time_max - timedelta(days=180)
                    logger.info(
                        f"📅 search_query provided, expanding date range to 6 months: {time_min.strftime('%Y-%m-%d')} to {time_max.strftime('%Y-%m-%d')}"
                    )
                elif days_range < 365:  # Less than 1 year, expand to 1 year
                    time_min = time_max - timedelta(days=365)
                    logger.info(
                        f"📅 search_query provided, expanding date range to 1 year: {time_min.strftime('%Y-%m-%d')} to {time_max.strftime('%Y-%m-%d')}"
                    )

        # Fetch events with smart date range handling
        try:
            # Calculate date range
            days_range = (time_max - time_min).days if time_min and time_max else 0

            # If search_query is provided, use single API call (server-side filtering is efficient)
            # Otherwise, for large date ranges (>30 days), use iterative search
            if search_query:
                # With search_query, Google Calendar API filters server-side, so we can search entire range at once
                logger.info(f"📅 search_query provided, using single API call for {days_range} day range")
                events = get_google_calendar_events(
                    access_token=access_token,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=max_results,
                    search_query=search_query,
                )
            elif days_range > 30:
                logger.info(
                    f"📅 Large date range ({days_range} days), using iterative search starting from most recent"
                )

                # Start with last 30 days, then expand backwards month by month
                all_events = []
                search_end = time_max
                months_back = 0
                max_months = 6  # Don't search more than 6 months back

                while months_back < max_months and len(all_events) < max_results:
                    # Calculate search window: go back 30 days from current end
                    search_start = search_end - timedelta(days=30)

                    # Don't go before the original time_min
                    if time_min and search_start < time_min:
                        search_start = time_min

                    logger.info(
                        f"📅 Searching window {months_back + 1}: {search_start.strftime('%Y-%m-%d')} to {search_end.strftime('%Y-%m-%d')}"
                    )

                    # Fetch events for this window
                    window_events = get_google_calendar_events(
                        access_token=access_token,
                        time_min=search_start,
                        time_max=search_end,
                        max_results=max_results,  # Fetch enough for this window
                        search_query=search_query,
                    )

                    # Add events to our collection (they're already sorted chronologically)
                    all_events.extend(window_events)

                    # If we've reached the original time_min or got enough events, stop
                    if (time_min and search_start <= time_min) or len(all_events) >= max_results:
                        break

                    # Move search window backwards
                    search_end = search_start
                    months_back += 1

                # Sort all events by start time (most recent first) and take max_results
                events_with_time = []
                for event in all_events:
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        try:
                            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                            events_with_time.append((start_dt, event))
                        except:
                            events_with_time.append((datetime.min.replace(tzinfo=timezone.utc), event))
                    elif 'date' in start:
                        try:
                            start_dt = datetime.fromisoformat(start['date'] + 'T00:00:00+00:00')
                            events_with_time.append((start_dt, event))
                        except:
                            events_with_time.append((datetime.min.replace(tzinfo=timezone.utc), event))
                    else:
                        events_with_time.append((datetime.min.replace(tzinfo=timezone.utc), event))

                # Sort by start time descending (most recent first) and take max_results
                events_with_time.sort(key=lambda x: x[0], reverse=True)
                events = [event for _, event in events_with_time[:max_results]]
                logger.info(
                    f"📅 Found {len(events)} most recent events from {len(all_events)} total across {months_back + 1} search windows"
                )
            else:
                # For smaller ranges (<=30 days), fetch normally
                logger.info(f"📅 Fetching calendar events with time_min={time_min}, time_max={time_max}")
                events = get_google_calendar_events(
                    access_token=access_token,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=max_results,
                    search_query=search_query,
                )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error fetching calendar events: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        events = get_google_calendar_events(
                            access_token=new_token,
                            time_min=time_min,
                            time_max=time_max,
                            max_results=max_results,
                            search_query=search_query,
                        )
                    except Exception as retry_error:
                        logger.error(f"❌ Error after token refresh: {str(retry_error)}")
                        import traceback

                        traceback.print_exc()
                        return f"Error fetching calendar events: {str(retry_error)}"
                else:
                    logger.error(f"❌ Token refresh failed")
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            else:
                logger.error(f"❌ Non-auth error: {error_msg}")
                return f"Error fetching calendar events: {error_msg}"

        events_count = len(events) if events else 0

        if not events:
            date_info = ""
            if time_min and time_max:
                date_info = f" between {time_min.strftime('%Y-%m-%d')} and {time_max.strftime('%Y-%m-%d')}"
            elif time_min:
                date_info = f" after {time_min.strftime('%Y-%m-%d')}"
            elif time_max:
                date_info = f" before {time_max.strftime('%Y-%m-%d')}"

            return f"No calendar events found{date_info}."

        # Format events
        result = f"Calendar Events ({len(events)} found):\n\n"

        for i, event in enumerate(events, 1):
            summary = event.get('summary', 'No title')
            result += f"{i}. {summary}\n"

            # Parse start time
            start = event.get('start', {})
            if 'dateTime' in start:
                try:
                    start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                    result += f"   Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                except:
                    result += f"   Start: {start.get('dateTime', 'Unknown')}\n"
            elif 'date' in start:
                result += f"   Date: {start.get('date', 'Unknown')}\n"

            # Parse end time
            end = event.get('end', {})
            if 'dateTime' in end:
                try:
                    end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
                    result += f"   End: {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                except:
                    result += f"   End: {end.get('dateTime', 'Unknown')}\n"
            elif 'date' in end:
                result += f"   End Date: {end.get('date', 'Unknown')}\n"

            # Add location if available
            location = event.get('location')
            if location:
                result += f"   Location: {location}\n"

            # Add description if available (truncated)
            description = event.get('description', '')
            if description:
                desc_preview = description[:100] + '...' if len(description) > 100 else description
                result += f"   Description: {desc_preview}\n"

            result += "\n"

        return result.strip()
    except Exception as e:
        logger.error(f"❌ Unexpected error in get_calendar_events_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching calendar events: {str(e)}"


@tool
def create_calendar_event_tool(
    title: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Create a new calendar event in the user's Google Calendar.

    Use this tool when:
    - User asks to "create a calendar event" or "schedule a meeting"
    - User says "add to my calendar" or "put this on my calendar"
    - User wants to "book a meeting" or "set up an appointment"
    - User mentions creating an event, meeting, or appointment
    - **ALWAYS use this tool when the user wants to create or schedule a calendar event**

    Date/time formatting:
    - Times should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T14:00:00-08:00" for January 20, 2024 at 2:00 PM PST
    - Both start_time and end_time are required

    Attendees:
    - Attendees can be provided as email addresses OR names (e.g., "john@example.com" or "John Smith")
    - If names are provided, the system will automatically search Google Contacts to find their email addresses
    - Multiple attendees should be comma-separated: "email1@example.com,John Smith,email2@example.com"
    - If no attendees, leave as None or empty string

    Args:
        title: Event title/summary (required)
        start_time: Event start time in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-20T14:00:00-08:00")
        end_time: Event end time in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-20T15:00:00-08:00")
        description: Optional event description
        location: Optional event location (address or venue name)
        attendees: Optional comma-separated list of attendee names or email addresses (e.g., "user1@example.com,John Smith,Riddhi Gupta")

    Returns:
        Confirmation message with event details if successful, or error message if failed.
    """
    logger.info(
        f"🔧 create_calendar_event_tool called - title: {title}, "
        f"start_time: {start_time}, end_time: {end_time}, location: {location}"
    )

    uid, integration, access_token, access_err = prepare_access(
        config,
        'google_calendar',
        'Google Calendar',
        'Google Calendar is not connected. Please connect your Google Calendar from settings to create events.',
        'Google Calendar access token not found. Please reconnect your Google Calendar from settings.',
        'Error checking Google Calendar connection',
    )
    if access_err:
        return access_err

    try:

        # Parse start and end times
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_time must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T14:00:00-08:00'): {start_time}"
            logger.info(f"📅 Parsed start_time '{start_time}' as {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid start_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {start_time} - {str(e)}"

        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_time must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T15:00:00-08:00'): {end_time}"
            logger.info(f"📅 Parsed end_time '{end_time}' as {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid end_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {end_time} - {str(e)}"

        # Validate that end_time is after start_time
        if end_dt <= start_dt:
            return f"Error: end_time must be after start_time. Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}, End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"

        # Parse and resolve attendees if provided
        attendee_list = None
        if attendees:
            attendee_strings = [a.strip() for a in attendees.split(',') if a.strip()]
            logger.info(f"📅 Parsed {len(attendee_strings)} attendee(s)")

            # Resolve each attendee (name or email) to an email address
            resolved_emails = []
            unresolved_attendees = []

            for attendee in attendee_strings:
                email = resolve_attendee_to_email(access_token, attendee)
                if email:
                    resolved_emails.append(email)
                else:
                    unresolved_attendees.append(attendee)

            if unresolved_attendees:
                return f"Error: Could not find email addresses for the following attendees: {', '.join(unresolved_attendees)}. Please provide email addresses directly (e.g., 'name@example.com') or ensure these contacts exist in your Google Contacts. If you recently connected Google Calendar, you may need to reconnect it to enable contact lookup."

            if resolved_emails:
                attendee_list = resolved_emails

        # Create the event
        try:
            event = create_google_calendar_event(
                access_token=access_token,
                summary=title,
                start_time=start_dt,
                end_time=end_dt,
                description=description,
                location=location,
                attendees=attendee_list,
            )

            event_id = event.get('id', 'unknown')
            event_link = event.get('htmlLink', '')

            result = f"✅ Successfully created calendar event: {title}\n"
            result += f"   Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            result += f"   End: {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"

            if location:
                result += f"   Location: {location}\n"

            if attendee_list:
                result += f"   Attendees: {', '.join(attendee_list)}\n"

            if event_link:
                result += f"   View event: {event_link}"

            return result.strip()

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error creating calendar event: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        event = create_google_calendar_event(
                            access_token=new_token,
                            summary=title,
                            start_time=start_dt,
                            end_time=end_dt,
                            description=description,
                            location=location,
                            attendees=attendee_list,
                        )

                        event_id = event.get('id', 'unknown')
                        event_link = event.get('htmlLink', '')

                        result = f"✅ Successfully created calendar event: {title}\n"
                        result += f"   Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                        result += f"   End: {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"

                        if location:
                            result += f"   Location: {location}\n"

                        if attendee_list:
                            result += f"   Attendees: {', '.join(attendee_list)}\n"

                        if event_link:
                            result += f"   View event: {event_link}"

                        return result.strip()
                    except Exception as retry_error:
                        logger.error(f"❌ Error after token refresh: {str(retry_error)}")
                        import traceback

                        traceback.print_exc()
                        return f"Error creating calendar event: {str(retry_error)}"
                else:
                    logger.error(f"❌ Token refresh failed")
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            elif "Insufficient permissions" in error_msg or "403" in error_msg:
                return "Google Calendar write access is not available. Please reconnect your Google Calendar from settings with proper permissions."
            else:
                return f"Error creating calendar event: {error_msg}"

    except Exception as e:
        logger.error(f"❌ Unexpected error in create_calendar_event_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error creating calendar event: {str(e)}"


@tool
def delete_calendar_event_tool(
    event_title: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    event_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Delete calendar events from the user's Google Calendar.

    Use this tool when:
    - User asks to "delete" or "remove" a calendar event
    - User says "cancel" a meeting or event
    - User wants to "clear" events from their calendar
    - User mentions deleting or removing something from their schedule
    - **ALWAYS use this tool when the user wants to delete calendar events**

    You can delete events by:
    1. Event ID (if you have it from a previous search)
    2. Event title and date range (searches for matching events and deletes them)
    3. Date range only (deletes all events in that range - use carefully)

    Date/time formatting:
    - Dates should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T18:00:00-08:00" for January 20, 2024 at 6:00 PM PST
    - If searching by date, provide both start_date and end_date to narrow the search

    Args:
        event_title: Optional event title to search for (e.g., "business meeting")
        start_date: Optional start date/time for search range in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
        end_date: Optional end date/time for search range in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
        event_id: Optional specific event ID to delete (if known from previous search)

    Returns:
        Confirmation message with details of deleted events, or error message if failed.
    """
    logger.info(
        f"🔧 delete_calendar_event_tool called - event_title: {event_title}, "
        f"start_date: {start_date}, end_date: {end_date}, event_id: {event_id}"
    )

    uid, integration, access_token, access_err = prepare_access(
        config,
        'google_calendar',
        'Google Calendar',
        'Google Calendar is not connected. Please connect your Google Calendar from settings to delete events.',
        'Google Calendar access token not found. Please reconnect your Google Calendar from settings.',
        'Error checking Google Calendar connection',
    )
    if access_err:
        return access_err

    try:

        # If event_id is provided, delete directly
        if event_id:
            try:
                delete_google_calendar_event(access_token, event_id)
                return f"✅ Successfully deleted calendar event (ID: {event_id})"
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Error deleting event by ID: {error_msg}")

                # Try to refresh token if authentication failed
                if "Authentication failed" in error_msg or "401" in error_msg:
                    logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                    new_token = refresh_google_token(uid, integration)
                    if new_token:
                        try:
                            delete_google_calendar_event(new_token, event_id)
                            return f"✅ Successfully deleted calendar event (ID: {event_id})"
                        except Exception as retry_error:
                            return f"Error deleting calendar event: {str(retry_error)}"
                    else:
                        return "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                else:
                    return f"Error deleting calendar event: {error_msg}"

        # Otherwise, search for events matching criteria
        if not event_title and not start_date:
            return (
                "Error: Please provide either event_id, event_title, or start_date to identify which events to delete."
            )

        # Parse dates if provided
        time_min = None
        time_max = None

        time_min, err = parse_iso_with_tz(
            'start_date',
            start_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T18:00:00-08:00')",
        )
        if err:
            return err
        time_max, err = parse_iso_with_tz(
            'end_date',
            end_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T19:00:00-08:00')",
        )
        if err:
            return err

        # If only start_date provided, set end_date to 1 day later
        if time_min and not time_max:
            time_max = time_min + timedelta(days=1)
            logger.info(f"📅 Auto-set end_date to 1 day after start_date: {time_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Search for matching events
        try:
            events = get_google_calendar_events(
                access_token=access_token,
                time_min=time_min,
                time_max=time_max,
                max_results=50,  # Get more results to find all matches
                search_query=event_title,
            )

            if not events:
                date_info = ""
                if time_min and time_max:
                    date_info = (
                        f" between {time_min.strftime('%Y-%m-%d %H:%M')} and {time_max.strftime('%Y-%m-%d %H:%M')}"
                    )
                elif time_min:
                    date_info = f" on {time_min.strftime('%Y-%m-%d')}"

                title_info = f" matching '{event_title}'" if event_title else ""
                return f"No calendar events found{title_info}{date_info}."

            # Filter events by title if provided
            matching_events = events
            if event_title:
                matching_events = [e for e in events if event_title.lower() in e.get('summary', '').lower()]

            if not matching_events:
                date_info = ""
                if time_min and time_max:
                    date_info = (
                        f" between {time_min.strftime('%Y-%m-%d %H:%M')} and {time_max.strftime('%Y-%m-%d %H:%M')}"
                    )
                elif time_min:
                    date_info = f" on {time_min.strftime('%Y-%m-%d')}"
                return f"No calendar events found matching '{event_title}'{date_info}."

            logger.info(f"📅 Found {len(matching_events)} matching event(s) to delete")

            # Delete all matching events
            deleted_count = 0
            failed_deletions = []

            for event in matching_events:
                event_id = event.get('id')
                event_title_found = event.get('summary', 'Untitled')

                if not event_id:
                    logger.warning(f"⚠️ Event missing ID, skipping: {event_title_found}")
                    continue

                try:
                    delete_google_calendar_event(access_token, event_id)
                    deleted_count += 1
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ Failed to delete {event_title_found}: {error_msg}")
                    failed_deletions.append((event_title_found, error_msg))

            # Build result message
            if deleted_count > 0:
                result = f"✅ Successfully deleted {deleted_count} calendar event(s):\n"
                for event in matching_events[:deleted_count]:
                    summary = event.get('summary', 'Untitled')
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        try:
                            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                            result += f"   - {summary} ({start_dt.strftime('%Y-%m-%d %H:%M')})\n"
                        except:
                            result += f"   - {summary}\n"
                    else:
                        result += f"   - {summary}\n"

                if failed_deletions:
                    result += f"\n⚠️ Failed to delete {len(failed_deletions)} event(s):\n"
                    for title, error in failed_deletions:
                        result += f"   - {title}: {error}\n"

                return result.strip()
            else:
                if failed_deletions:
                    error_msgs = '; '.join([f"{title}: {error}" for title, error in failed_deletions])
                    return f"Error: Failed to delete events: {error_msgs}"
                else:
                    return "No events were deleted."

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error searching for events to delete: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        events = get_google_calendar_events(
                            access_token=new_token,
                            time_min=time_min,
                            time_max=time_max,
                            max_results=50,
                            search_query=event_title,
                        )

                        date_info_retry = ""
                        if time_min and time_max:
                            date_info_retry = f" between {time_min.strftime('%Y-%m-%d %H:%M')} and {time_max.strftime('%Y-%m-%d %H:%M')}"
                        elif time_min:
                            date_info_retry = f" on {time_min.strftime('%Y-%m-%d')}"

                        if not events:
                            return f"No calendar events found matching '{event_title}'{date_info_retry}."

                        matching_events = events
                        if event_title:
                            matching_events = [e for e in events if event_title.lower() in e.get('summary', '').lower()]

                        if not matching_events:
                            return f"No calendar events found matching '{event_title}'{date_info_retry}."

                        deleted_count = 0
                        for event in matching_events:
                            event_id = event.get('id')
                            if event_id:
                                try:
                                    delete_google_calendar_event(new_token, event_id)
                                    deleted_count += 1
                                except:
                                    pass

                        if deleted_count > 0:
                            return f"✅ Successfully deleted {deleted_count} calendar event(s)"
                        else:
                            return "No events were deleted."
                    except Exception as retry_error:
                        return f"Error deleting calendar events: {str(retry_error)}"
                else:
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            else:
                return f"Error searching for calendar events: {error_msg}"

    except Exception as e:
        logger.error(f"❌ Unexpected error in delete_calendar_event_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error deleting calendar events: {str(e)}"


@tool
def update_calendar_event_tool(
    event_id: Optional[str] = None,
    event_title: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    add_attendees: Optional[str] = None,
    remove_attendees: Optional[str] = None,
    set_attendees: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Update an existing calendar event in the user's Google Calendar.
    Can modify event title, description, location, time, or attendees.

    Use this tool when:
    - User asks to "update" or "modify" a calendar event
    - User wants to "change" something about an event
    - User asks to "add" or "remove" attendees from an event
    - User wants to "edit" an event
    - **ALWAYS use this tool when the user wants to modify an existing calendar event**

    To identify the event:
    - If event_id is provided, use it directly
    - Otherwise, search for events matching event_title and date range

    Attendee modifications:
    - add_attendees: Comma-separated list of names or emails to ADD to existing attendees
    - remove_attendees: Comma-separated list of names or emails to REMOVE from existing attendees
    - set_attendees: Comma-separated list of names or emails to REPLACE all attendees
    - Names will be automatically resolved to email addresses via Google Contacts

    Args:
        event_id: Optional specific event ID to update (if known)
        event_title: Optional event title to search for
        start_date: Optional start date/time for search range in ISO format with timezone
        end_date: Optional end date/time for search range in ISO format with timezone
        title: Optional new event title
        description: Optional new event description
        location: Optional new event location
        add_attendees: Optional comma-separated list of attendee names or emails to add
        remove_attendees: Optional comma-separated list of attendee names or emails to remove
        set_attendees: Optional comma-separated list of attendee names or emails to set (replaces all)

    Returns:
        Confirmation message with updated event details if successful, or error message if failed.
    """
    logger.info(
        f"🔧 update_calendar_event_tool called - event_id: {event_id}, event_title: {event_title}, "
        f"add_attendees: {add_attendees}, remove_attendees: {remove_attendees}, set_attendees: {set_attendees}"
    )

    uid, integration, access_token, access_err = prepare_access(
        config,
        'google_calendar',
        'Google Calendar',
        'Google Calendar is not connected. Please connect your Google Calendar from settings to update events.',
        'Google Calendar access token not found. Please reconnect your Google Calendar from settings.',
        'Error checking Google Calendar connection',
    )
    if access_err:
        return access_err

    try:

        # Find the event if event_id not provided
        target_event_id = event_id
        if not target_event_id:
            if not event_title:
                return "Error: Please provide either event_id or event_title to identify which event to update."

            # Parse dates if provided
            time_min = None
            time_max = None

            time_min, err = parse_iso_with_tz('start_date', start_date, "(with timezone)")
            if err:
                return err
            time_max, err = parse_iso_with_tz('end_date', end_date, "(with timezone)")
            if err:
                return err

            # If only start_date provided, set end_date to 1 day later
            if time_min and not time_max:
                time_max = time_min + timedelta(days=1)

            # Search for matching events
            try:
                events = get_google_calendar_events(
                    access_token=access_token,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=10,
                    search_query=event_title,
                )

                if not events:
                    return f"No calendar events found matching '{event_title}'."

                # Filter events by title if provided
                matching_events = [e for e in events if event_title.lower() in e.get('summary', '').lower()]

                if not matching_events:
                    return f"No calendar events found matching '{event_title}'."

                if len(matching_events) > 1:
                    return f"Multiple events found matching '{event_title}'. Please provide the event_id to specify which one to update."

                target_event_id = matching_events[0].get('id')
                if not target_event_id:
                    return f"Event found but missing ID."

                logger.info(f"📅 Found event ID: {target_event_id}")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Error searching for event: {error_msg}")
                return f"Error searching for calendar event: {error_msg}"

        # Get current event to preserve existing data
        try:
            current_event = get_google_calendar_event(access_token, target_event_id)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error getting event: {error_msg}")

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        current_event = get_google_calendar_event(new_token, target_event_id)
                        access_token = new_token
                    except Exception as retry_error:
                        return f"Error getting calendar event: {str(retry_error)}"
                else:
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            else:
                return f"Error getting calendar event: {error_msg}"

        # Prepare update fields
        update_summary = title if title is not None else None
        update_description = description if description is not None else None
        update_location = location if location is not None else None

        # Handle attendees
        update_attendees = None
        if set_attendees is not None:
            # Replace all attendees
            attendee_strings = [a.strip() for a in set_attendees.split(',') if a.strip()]
            resolved_emails = []
            unresolved_attendees = []

            for attendee in attendee_strings:
                email = resolve_attendee_to_email(access_token, attendee)
                if email:
                    resolved_emails.append(email)
                else:
                    unresolved_attendees.append(attendee)

            if unresolved_attendees:
                return f"Error: Could not find email addresses for the following attendees: {', '.join(unresolved_attendees)}. Please provide email addresses directly or ensure these contacts exist in your Google Contacts."

            update_attendees = resolved_emails
        elif add_attendees is not None or remove_attendees is not None:
            # Modify existing attendees
            current_attendees = current_event.get('attendees', [])
            current_emails = [a.get('email') for a in current_attendees if a.get('email')]

            # Add attendees
            if add_attendees:
                attendee_strings = [a.strip() for a in add_attendees.split(',') if a.strip()]
                for attendee in attendee_strings:
                    email = resolve_attendee_to_email(access_token, attendee)
                    if email and email not in current_emails:
                        current_emails.append(email)
                    elif not email:
                        return f"Error: Could not find email address for attendee: {attendee}. Please provide email address directly or ensure this contact exists in your Google Contacts."

            # Remove attendees
            if remove_attendees:
                attendee_strings = [a.strip() for a in remove_attendees.split(',') if a.strip()]
                emails_to_remove = []
                for attendee in attendee_strings:
                    email = resolve_attendee_to_email(access_token, attendee)
                    if email:
                        emails_to_remove.append(email)
                    else:
                        # Try to find by name in current attendees
                        for current_email in current_emails:
                            if attendee.lower() in current_email.lower():
                                emails_to_remove.append(current_email)
                                break

                current_emails = [e for e in current_emails if e not in emails_to_remove]

            update_attendees = current_emails

        # Update the event
        try:
            updated_event = update_google_calendar_event(
                access_token=access_token,
                event_id=target_event_id,
                summary=update_summary,
                description=update_description,
                location=update_location,
                attendees=update_attendees,
            )

            result = f"✅ Successfully updated calendar event: {updated_event.get('summary', 'Untitled')}\n"

            if update_summary:
                result += f"   Title: {update_summary}\n"

            if update_location:
                result += f"   Location: {update_location}\n"

            if update_attendees is not None:
                result += f"   Attendees: {', '.join(update_attendees)}\n"

            event_link = updated_event.get('htmlLink', '')
            if event_link:
                result += f"   View event: {event_link}"

            return result.strip()

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error updating calendar event: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                logger.info(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        updated_event = update_google_calendar_event(
                            access_token=new_token,
                            event_id=target_event_id,
                            summary=update_summary,
                            description=update_description,
                            location=update_location,
                            attendees=update_attendees,
                        )

                        result = f"✅ Successfully updated calendar event: {updated_event.get('summary', 'Untitled')}\n"
                        if update_attendees is not None:
                            result += f"   Attendees: {', '.join(update_attendees)}\n"
                        return result.strip()
                    except Exception as retry_error:
                        return f"Error updating calendar event: {str(retry_error)}"
                else:
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            else:
                return f"Error updating calendar event: {error_msg}"

    except Exception as e:
        logger.error(f"❌ Unexpected error in update_calendar_event_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error updating calendar event: {str(e)}"
