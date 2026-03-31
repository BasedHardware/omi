"""
Google Calendar Auto-Sync Module for Omi.

Provides automatic synchronization of Google Calendar events into Omi's
memory system. Events are transformed into natural language memories and
pushed via the Omi Facts API.

Key features:
- Periodic background sync (configurable interval)
- Deduplication via event ID tracking
- Natural language event formatting
- Handles token refresh automatically
"""
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from db import get_user_setting, store_user_setting

# Omi Facts API configuration
OMI_API_BASE = os.getenv("OMI_API_BASE", "https://api.omi.me/v2")
OMI_APP_ID = os.getenv("OMI_APP_ID", "")
OMI_API_KEY = os.getenv("OMI_API_KEY", "")

# Sync defaults
DEFAULT_SYNC_INTERVAL_MINUTES = 30
MAX_EVENTS_PER_SYNC = 20
SYNC_LOOKFORWARD_DAYS = 7


def log(msg: str):
    """Print and flush for Railway/production logging."""
    print(msg)
    sys.stdout.flush()


def format_event_as_memory(event: dict) -> str:
    """
    Transform a Google Calendar event into a natural language memory string
    suitable for Omi's memory system.
    """
    summary = event.get("summary", "Untitled event")
    start = event.get("start", {})
    end = event.get("end", {})
    location = event.get("location", "")
    description = event.get("description", "")
    attendees = event.get("attendees", [])

    if "date" in start:
        time_str = f"all day on {start['date']}"
    else:
        start_dt_str = start.get("dateTime", "")
        end_dt_str = end.get("dateTime", "")
        try:
            start_parsed = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
            end_parsed = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))
            date_str = start_parsed.strftime("%B %d, %Y")
            start_time = start_parsed.strftime("%I:%M %p")
            end_time = end_parsed.strftime("%I:%M %p")
            time_str = f"on {date_str} from {start_time} to {end_time}"
        except Exception:
            time_str = f"at {start_dt_str}"

    parts = [f"Calendar event: {summary} {time_str}"]

    if location:
        parts.append(f"Location: {location}")

    if attendees:
        emails = [a.get("email", "") for a in attendees[:5] if a.get("email")]
        if emails:
            parts.append(f"With: {', '.join(emails)}")

    if description:
        desc_clean = description[:200].strip().replace("\n", " ")
        if desc_clean:
            parts.append(f"Notes: {desc_clean}")

    return ". ".join(parts)


def push_memory_to_omi(uid: str, memory_text: str) -> bool:
    """Push a single memory to the Omi Facts API."""
    if not OMI_APP_ID or not OMI_API_KEY:
        log("Sync: OMI_APP_ID or OMI_API_KEY not configured, skipping push")
        return False

    url = f"{OMI_API_BASE}/integrations/{OMI_APP_ID}/user/facts"
    headers = {
        "Authorization": f"Bearer {OMI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": memory_text,
        "text_source": "integration",
        "text_source_spec": "google_calendar_sync",
    }

    try:
        response = requests.post(
            url, headers=headers, json=payload, params={"uid": uid}, timeout=10
        )
        if response.status_code == 200:
            log(f"Sync: Pushed memory for {uid}: {memory_text[:80]}...")
            return True
        else:
            log(f"Sync: Push failed {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log(f"Sync: Error pushing memory: {e}")
        return False


def sync_user_calendar(
    uid: str,
    get_valid_access_token_fn,
    calendar_api_request_fn,
    get_default_calendar_fn,
) -> Dict:
    """
    Sync a user's upcoming Google Calendar events to Omi memories.

    Args:
        uid: User ID
        get_valid_access_token_fn: Function to get valid OAuth token
        calendar_api_request_fn: Function to make Calendar API requests
        get_default_calendar_fn: Function to get user's default calendar

    Returns:
        Dict with sync results (success, synced count, skipped count, etc.)
    """
    log(f"Sync: Starting for user {uid}")

    access_token = get_valid_access_token_fn(uid)
    if not access_token:
        return {"success": False, "error": "Not authenticated with Google Calendar"}

    # Load previously synced event IDs for deduplication
    stored_ids_raw = get_user_setting(uid, "synced_event_ids")
    synced_ids = set(stored_ids_raw) if stored_ids_raw else set()

    calendar_id = get_default_calendar_fn(uid)
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=SYNC_LOOKFORWARD_DAYS)).isoformat() + "Z"

    result = calendar_api_request_fn(
        uid,
        "GET",
        f"/calendars/{calendar_id}/events",
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": MAX_EVENTS_PER_SYNC,
            "singleEvents": True,
            "orderBy": "startTime",
        },
    )

    if not result or "error" in result:
        error_msg = result.get("error", "Unknown error") if result else "No response"
        return {"success": False, "error": f"Failed to fetch events: {error_msg}"}

    events = result.get("items", [])
    if not events:
        return {"success": True, "synced": 0, "skipped": 0, "message": "No upcoming events"}

    synced = 0
    skipped = 0
    new_ids: set = set()

    for event in events:
        event_id = event.get("id", "")
        new_ids.add(event_id)

        if event_id in synced_ids:
            skipped += 1
            continue

        memory_text = format_event_as_memory(event)
        if push_memory_to_omi(uid, memory_text):
            synced += 1
        else:
            log(f"Sync: Failed to push event {event_id}")

        time.sleep(0.3)

    store_user_setting(uid, "last_sync_at", datetime.utcnow().isoformat())
    store_user_setting(uid, "synced_event_ids", list(new_ids))

    summary = f"Synced {synced} new events, skipped {skipped} already synced"
    log(f"Sync: Completed for {uid} — {summary}")

    return {
        "success": True,
        "synced": synced,
        "skipped": skipped,
        "total_events": len(events),
        "message": summary,
    }
