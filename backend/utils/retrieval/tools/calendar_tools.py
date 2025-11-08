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

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def refresh_google_calendar_token(uid: str, integration: dict) -> Optional[str]:
    """
    Refresh Google Calendar access token using refresh token.

    Returns:
        New access token or None if refresh failed
    """
    refresh_token = integration.get('refresh_token')
    if not refresh_token:
        return None

    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return None

    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            },
            timeout=10.0,
        )

        if response.status_code == 200:
            token_data = response.json()
            new_access_token = token_data.get('access_token')

            if new_access_token:
                # Update stored token
                integration['access_token'] = new_access_token
                users_db.set_integration(uid, 'google_calendar', integration)
                return new_access_token
    except Exception as e:
        print(f"Error refreshing Google Calendar token: {e}")

    return None


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
    print(f"🔍 Searching Google Contacts for: {query}")

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

        print(f"📇 Google Contacts API (My Contacts) response status: {response.status_code}")

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
                    print(f"✅ Found contact in My Contacts: {name} -> {email}")
                    return email
                else:
                    print(f"⚠️ Found contact '{query}' in My Contacts but no email address")
        elif response.status_code == 401:
            print(f"❌ Google Contacts API 401 - token expired")
            return None
        elif response.status_code == 403:
            print(f"⚠️ Google Contacts API 403 - insufficient permissions for My Contacts, will try Other Contacts")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"⚠️ Google Contacts API error {response.status_code}: {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error searching My Contacts: {e}")
    except Exception as e:
        print(f"⚠️ Error searching My Contacts: {e}")

    # If not found in My Contacts, search in "Other Contacts"
    print(f"🔍 Searching Other Contacts for: {query}")
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
            print(f"📇 Other Contacts warm-up response status: {warmup_response.status_code}")
            # Wait a moment for cache to update (not strictly necessary but recommended)
            time.sleep(0.5)
        except Exception as warmup_error:
            print(f"⚠️ Other Contacts warm-up failed (non-critical): {warmup_error}")

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

        print(f"📇 Google Contacts API (Other Contacts) response status: {response.status_code}")

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
                    print(f"✅ Found contact in Other Contacts: {name} -> {email}")
                    return email
                else:
                    print(f"⚠️ Found contact '{query}' in Other Contacts but no email address")
            else:
                print(f"⚠️ No contacts found in Other Contacts for: {query}")
        elif response.status_code == 401:
            print(f"❌ Google Contacts API 401 - token expired")
            return None
        elif response.status_code == 403:
            print(f"❌ Google Contacts API 403 - insufficient permissions (Other Contacts access required)")
            return None
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"⚠️ Google Contacts API (Other Contacts) error {response.status_code}: {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error searching Other Contacts: {e}")
    except Exception as e:
        print(f"⚠️ Error searching Other Contacts: {e}")

    print(f"⚠️ No contacts found in My Contacts or Other Contacts for: {query}")
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
        print(f"📧 '{attendee}' appears to be an email address")
        return attendee

    # It's a name, search Google Contacts
    print(f"👤 '{attendee}' appears to be a name, searching Google Contacts...")
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

    print(f"📅 Creating Google Calendar event: {summary} from {start_time_str} to {end_time_str}")

    try:
        response = requests.post(
            'https://www.googleapis.com/calendar/v3/calendars/primary/events',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            json=event_body,
            timeout=10.0,
        )

        print(f"📅 Google Calendar API create response status: {response.status_code}")

        if response.status_code == 200:
            event_data = response.json()
            print(f"✅ Successfully created calendar event: {event_data.get('id')}")
            return event_data
        elif response.status_code == 401:
            print(f"❌ Google Calendar API 401 - token expired")
            raise Exception("Authentication failed - token may be expired")
        elif response.status_code == 403:
            print(f"❌ Google Calendar API 403 - insufficient permissions")
            raise Exception("Insufficient permissions - calendar write access required")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Google Calendar API error {response.status_code}: {error_body}")
            raise Exception(f"Google Calendar API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error creating Google Calendar event: {e}")
        raise
    except Exception as e:
        print(f"❌ Error creating Google Calendar event: {e}")
        raise


def delete_google_calendar_event(access_token: str, event_id: str) -> bool:
    """
    Delete a calendar event by event ID.

    Args:
        access_token: Google Calendar access token
        event_id: Event ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    print(f"🗑️ Deleting Google Calendar event: {event_id}")

    try:
        response = requests.delete(
            f'https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10.0,
        )

        print(f"📅 Google Calendar API delete response status: {response.status_code}")

        if response.status_code == 204:
            print(f"✅ Successfully deleted calendar event: {event_id}")
            return True
        elif response.status_code == 401:
            print(f"❌ Google Calendar API 401 - token expired")
            raise Exception("Authentication failed - token may be expired")
        elif response.status_code == 403:
            print(f"❌ Google Calendar API 403 - insufficient permissions")
            raise Exception("Insufficient permissions - calendar write access required")
        elif response.status_code == 404:
            print(f"❌ Google Calendar API 404 - event not found")
            raise Exception(f"Event not found: {event_id}")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Google Calendar API error {response.status_code}: {error_body}")
            raise Exception(f"Google Calendar API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error deleting Google Calendar event: {e}")
        raise
    except Exception as e:
        print(f"❌ Error deleting Google Calendar event: {e}")
        raise


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
    if time_min is None:
        time_min = datetime.now(timezone.utc)
    if time_max is None:
        time_max = time_min + timedelta(days=7)

    # Convert to UTC if timezone-aware, otherwise assume UTC
    if time_min.tzinfo is not None:
        time_min_utc = time_min.astimezone(timezone.utc)
    else:
        time_min_utc = time_min.replace(tzinfo=timezone.utc)

    if time_max.tzinfo is not None:
        time_max_utc = time_max.astimezone(timezone.utc)
    else:
        time_max_utc = time_max.replace(tzinfo=timezone.utc)

    # Format times in RFC3339 format (UTC)
    time_min_str = time_min_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    time_max_str = time_max_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'timeMin': time_min_str,
        'timeMax': time_max_str,
        'maxResults': max_results,
        'singleEvents': 'true',
        'orderBy': 'startTime',
    }

    # Add search query if provided
    if search_query:
        params['q'] = search_query
        print(
            f"📅 Calling Google Calendar API with timeMin={time_min_str}, timeMax={time_max_str}, search_query='{search_query}'"
        )
    else:
        print(f"📅 Calling Google Calendar API with timeMin={time_min_str}, timeMax={time_max_str}")

    try:
        response = requests.get(
            'https://www.googleapis.com/calendar/v3/calendars/primary/events',
            headers={'Authorization': f'Bearer {access_token}'},
            params=params,
            timeout=10.0,
        )

        print(f"📅 Google Calendar API response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            events = data.get('items', [])
            print(f"📅 Google Calendar API returned {len(events)} events")
            return events
        elif response.status_code == 401:
            # Token might be expired
            print(f"❌ Google Calendar API 401 - token expired")
            raise Exception("Authentication failed - token may be expired")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Google Calendar API error {response.status_code}: {error_body}")
            raise Exception(f"Google Calendar API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Google Calendar events: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Google Calendar events: {e}")
        raise


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
    print(
        f"🔧 get_calendar_events_tool called - start_date: {start_date}, "
        f"end_date: {end_date}, max_results: {max_results}, search_query: {search_query}"
    )

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 get_calendar_events_tool - got config from context variable")
        except LookupError:
            print(f"❌ get_calendar_events_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ get_calendar_events_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(
            f"❌ get_calendar_events_tool - error accessing config: {e}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not a dict'}"
        )
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ get_calendar_events_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_calendar_events_tool - uid: {uid}, max_results: {max_results}")

    try:
        # Cap at 50 per call
        if max_results > 50:
            print(f"⚠️ get_calendar_events_tool - max_results capped from {max_results} to 50")
            max_results = 50

        # Check if user has Google Calendar connected
        print(f"📅 Checking Google Calendar connection for user {uid}...")
        try:
            integration = users_db.get_integration(uid, 'google_calendar')
            print(f"📅 Integration data retrieved: {integration is not None}")
            if integration:
                print(f"📅 Integration connected status: {integration.get('connected')}")
                print(f"📅 Integration has access_token: {bool(integration.get('access_token'))}")
            else:
                print(f"❌ No integration found for user {uid}")
                return "Google Calendar is not connected. Please connect your Google Calendar from settings to view your events."
        except Exception as e:
            print(f"❌ Error checking calendar integration: {e}")
            import traceback

            traceback.print_exc()
            return f"Error checking Google Calendar connection: {str(e)}"

        if not integration or not integration.get('connected'):
            print(f"❌ Google Calendar not connected for user {uid}")
            return "Google Calendar is not connected. Please connect your Google Calendar from settings to view your events."

        access_token = integration.get('access_token')
        if not access_token:
            print(f"❌ No access token found in integration data")
            return "Google Calendar access token not found. Please reconnect your Google Calendar from settings."

        print(f"✅ Access token found, length: {len(access_token)}")

        # Parse dates if provided
        time_min = None
        time_max = None

        if start_date:
            try:
                time_min = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if time_min.tzinfo is None:
                    return f"Error: start_date must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T00:00:00-08:00'): {start_date}"
                print(f"📅 Parsed start_date '{start_date}' as {time_min.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            except ValueError as e:
                return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {start_date} - {str(e)}"

        if end_date:
            try:
                time_max = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if time_max.tzinfo is None:
                    return f"Error: end_date must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-27T23:59:59-08:00'): {end_date}"
                print(f"📅 Parsed end_date '{end_date}' as {time_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            except ValueError as e:
                return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {end_date} - {str(e)}"

        # If search_query is provided, expand date range to ensure we don't miss events
        # Default to searching back 1 year if no dates provided, or expand range if dates are too narrow
        if search_query:
            now = datetime.now(timezone.utc)
            if time_max is None:
                time_max = now
            if time_min is None:
                # Default to 1 year back when searching
                time_min = time_max - timedelta(days=365)
                print(
                    f"📅 search_query provided, defaulting to 1 year range: {time_min.strftime('%Y-%m-%d')} to {time_max.strftime('%Y-%m-%d')}"
                )
            else:
                # If dates are provided but range is less than 6 months, expand to at least 6 months
                days_range = (time_max - time_min).days
                if days_range < 180:  # Less than 6 months
                    # Expand backwards from time_max to ensure at least 6 months
                    time_min = time_max - timedelta(days=180)
                    print(
                        f"📅 search_query provided, expanding date range to 6 months: {time_min.strftime('%Y-%m-%d')} to {time_max.strftime('%Y-%m-%d')}"
                    )
                elif days_range < 365:  # Less than 1 year, expand to 1 year
                    time_min = time_max - timedelta(days=365)
                    print(
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
                print(f"📅 search_query provided, using single API call for {days_range} day range")
                events = get_google_calendar_events(
                    access_token=access_token,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=max_results,
                    search_query=search_query,
                )
            elif days_range > 30:
                print(f"📅 Large date range ({days_range} days), using iterative search starting from most recent")

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

                    print(
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
                print(
                    f"📅 Found {len(events)} most recent events from {len(all_events)} total across {months_back + 1} search windows"
                )
            else:
                # For smaller ranges (<=30 days), fetch normally
                print(f"📅 Fetching calendar events with time_min={time_min}, time_max={time_max}")
                events = get_google_calendar_events(
                    access_token=access_token,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=max_results,
                    search_query=search_query,
                )

            print(f"✅ Successfully fetched {len(events)} events")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error fetching calendar events: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                print(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_calendar_token(uid, integration)
                if new_token:
                    print(f"✅ Token refreshed, retrying...")
                    try:
                        events = get_google_calendar_events(
                            access_token=new_token,
                            time_min=time_min,
                            time_max=time_max,
                            max_results=max_results,
                            search_query=search_query,
                        )
                        print(f"✅ Successfully fetched {len(events)} events after token refresh")
                    except Exception as retry_error:
                        print(f"❌ Error after token refresh: {str(retry_error)}")
                        import traceback

                        traceback.print_exc()
                        return f"Error fetching calendar events: {str(retry_error)}"
                else:
                    print(f"❌ Token refresh failed")
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            else:
                print(f"❌ Non-auth error: {error_msg}")
                return f"Error fetching calendar events: {error_msg}"

        events_count = len(events) if events else 0
        print(f"📊 get_calendar_events_tool - found {events_count} events")

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
        print(f"❌ Unexpected error in get_calendar_events_tool: {e}")
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
    print(
        f"🔧 create_calendar_event_tool called - title: {title}, "
        f"start_time: {start_time}, end_time: {end_time}, location: {location}"
    )

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 create_calendar_event_tool - got config from context variable")
        except LookupError:
            print(f"❌ create_calendar_event_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ create_calendar_event_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ create_calendar_event_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ create_calendar_event_tool - no user_id in config")
        return "Error: User ID not found in configuration"

    print(f"✅ create_calendar_event_tool - uid: {uid}")

    try:
        # Check if user has Google Calendar connected
        print(f"📅 Checking Google Calendar connection for user {uid}...")
        try:
            integration = users_db.get_integration(uid, 'google_calendar')
            if not integration:
                print(f"❌ No integration found for user {uid}")
                return "Google Calendar is not connected. Please connect your Google Calendar from settings to create events."
        except Exception as e:
            print(f"❌ Error checking calendar integration: {e}")
            import traceback

            traceback.print_exc()
            return f"Error checking Google Calendar connection: {str(e)}"

        if not integration or not integration.get('connected'):
            print(f"❌ Google Calendar not connected for user {uid}")
            return (
                "Google Calendar is not connected. Please connect your Google Calendar from settings to create events."
            )

        access_token = integration.get('access_token')
        if not access_token:
            print(f"❌ No access token found in integration data")
            return "Google Calendar access token not found. Please reconnect your Google Calendar from settings."

        print(f"✅ Access token found, length: {len(access_token)}")

        # Parse start and end times
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_time must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T14:00:00-08:00'): {start_time}"
            print(f"📅 Parsed start_time '{start_time}' as {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid start_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {start_time} - {str(e)}"

        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_time must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T15:00:00-08:00'): {end_time}"
            print(f"📅 Parsed end_time '{end_time}' as {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid end_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {end_time} - {str(e)}"

        # Validate that end_time is after start_time
        if end_dt <= start_dt:
            return f"Error: end_time must be after start_time. Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}, End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"

        # Parse and resolve attendees if provided
        attendee_list = None
        if attendees:
            attendee_strings = [a.strip() for a in attendees.split(',') if a.strip()]
            print(f"📅 Parsed {len(attendee_strings)} attendee(s)")

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
                print(f"✅ Resolved {len(resolved_emails)} attendee(s) to email addresses")

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
            print(f"❌ Error creating calendar event: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                print(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_calendar_token(uid, integration)
                if new_token:
                    print(f"✅ Token refreshed, retrying...")
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
                        print(f"❌ Error after token refresh: {str(retry_error)}")
                        import traceback

                        traceback.print_exc()
                        return f"Error creating calendar event: {str(retry_error)}"
                else:
                    print(f"❌ Token refresh failed")
                    return (
                        "Google Calendar authentication expired. Please reconnect your Google Calendar from settings."
                    )
            elif "Insufficient permissions" in error_msg or "403" in error_msg:
                return "Google Calendar write access is not available. Please reconnect your Google Calendar from settings with proper permissions."
            else:
                return f"Error creating calendar event: {error_msg}"

    except Exception as e:
        print(f"❌ Unexpected error in create_calendar_event_tool: {e}")
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
    print(
        f"🔧 delete_calendar_event_tool called - event_title: {event_title}, "
        f"start_date: {start_date}, end_date: {end_date}, event_id: {event_id}"
    )

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 delete_calendar_event_tool - got config from context variable")
        except LookupError:
            print(f"❌ delete_calendar_event_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ delete_calendar_event_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ delete_calendar_event_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ delete_calendar_event_tool - no user_id in config")
        return "Error: User ID not found in configuration"

    print(f"✅ delete_calendar_event_tool - uid: {uid}")

    try:
        # Check if user has Google Calendar connected
        print(f"📅 Checking Google Calendar connection for user {uid}...")
        try:
            integration = users_db.get_integration(uid, 'google_calendar')
            if not integration:
                print(f"❌ No integration found for user {uid}")
                return "Google Calendar is not connected. Please connect your Google Calendar from settings to delete events."
        except Exception as e:
            print(f"❌ Error checking calendar integration: {e}")
            import traceback

            traceback.print_exc()
            return f"Error checking Google Calendar connection: {str(e)}"

        if not integration or not integration.get('connected'):
            print(f"❌ Google Calendar not connected for user {uid}")
            return (
                "Google Calendar is not connected. Please connect your Google Calendar from settings to delete events."
            )

        access_token = integration.get('access_token')
        if not access_token:
            print(f"❌ No access token found in integration data")
            return "Google Calendar access token not found. Please reconnect your Google Calendar from settings."

        print(f"✅ Access token found, length: {len(access_token)}")

        # If event_id is provided, delete directly
        if event_id:
            try:
                delete_google_calendar_event(access_token, event_id)
                return f"✅ Successfully deleted calendar event (ID: {event_id})"
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Error deleting event by ID: {error_msg}")

                # Try to refresh token if authentication failed
                if "Authentication failed" in error_msg or "401" in error_msg:
                    print(f"🔄 Attempting to refresh Google Calendar token...")
                    new_token = refresh_google_calendar_token(uid, integration)
                    if new_token:
                        print(f"✅ Token refreshed, retrying...")
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

        if start_date:
            try:
                time_min = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if time_min.tzinfo is None:
                    return f"Error: start_date must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T18:00:00-08:00'): {start_date}"
                print(f"📅 Parsed start_date '{start_date}' as {time_min.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            except ValueError as e:
                return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {start_date} - {str(e)}"

        if end_date:
            try:
                time_max = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if time_max.tzinfo is None:
                    return f"Error: end_date must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T19:00:00-08:00'): {end_date}"
                print(f"📅 Parsed end_date '{end_date}' as {time_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            except ValueError as e:
                return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: {end_date} - {str(e)}"

        # If only start_date provided, set end_date to 1 day later
        if time_min and not time_max:
            time_max = time_min + timedelta(days=1)
            print(f"📅 Auto-set end_date to 1 day after start_date: {time_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

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

            print(f"📅 Found {len(matching_events)} matching event(s) to delete")

            # Delete all matching events
            deleted_count = 0
            failed_deletions = []

            for event in matching_events:
                event_id = event.get('id')
                event_title_found = event.get('summary', 'Untitled')

                if not event_id:
                    print(f"⚠️ Event missing ID, skipping: {event_title_found}")
                    continue

                try:
                    delete_google_calendar_event(access_token, event_id)
                    deleted_count += 1
                    print(f"✅ Deleted: {event_title_found} (ID: {event_id})")
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Failed to delete {event_title_found}: {error_msg}")
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
            print(f"❌ Error searching for events to delete: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                print(f"🔄 Attempting to refresh Google Calendar token...")
                new_token = refresh_google_calendar_token(uid, integration)
                if new_token:
                    print(f"✅ Token refreshed, retrying...")
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
        print(f"❌ Unexpected error in delete_calendar_event_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error deleting calendar events: {str(e)}"
