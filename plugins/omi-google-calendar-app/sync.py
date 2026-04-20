"""
Google Calendar Auto-Sync Module for Omi.

Provides automatic synchronization of Google Calendar events into Omi's
memory system. Events are transformed into natural language memories and
pushed via the Omi Facts API.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Set

import requests

from db import get_user_setting, store_user_setting

# Omi Facts API configuration
OMI_API_BASE = os.getenv("OMI_API_BASE", "https://api.omi.me/v2")
OMI_APP_ID = os.getenv("OMI_APP_ID", "")
OMI_API_KEY = os.getenv("OMI_API_KEY", "")

# Sync defaults
DEFAULT_SYNC_INTERVAL_MINUTES = 30
MAX_EVENTS_PER_SYNC = 50
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
        if response.status_code in (200, 201):
            log(f"Sync: Pushed memory for {uid}: {memory_text[:80]}...")
            return True
        else:
            log(f"Sync: Push failed {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log(f"Sync: Error pushing memory: {e}")
        return False


async def sync_user_calendar(
    uid: str,
    get_valid_access_token_fn: Callable,
    calendar_api_request_fn: Callable,
    get_default_calendar_fn: Callable,
) -> Dict:
    """
    Sync a user's upcoming Google Calendar events to Omi memories.

    Merges new event IDs into the cumulative set of already-synced IDs
    to prevent duplicate memories across runs.
    """
    log(f"Sync: Starting for user {uid}")

    access_token = get_valid_access_token_fn(uid)
    if not access_token:
        return {"success": False, "error": "Not authenticated with Google Calendar"}

    # Load cumulative set of previously synced event IDs
    stored_ids_raw = get_user_setting(uid, "synced_event_ids")
    synced_ids: Set[str] = set(stored_ids_raw) if stored_ids_raw else set()

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

    for event in events:
        event_id = event.get("id", "")

        if event_id in synced_ids:
            skipped += 1
            continue

        memory_text = format_event_as_memory(event)
        if push_memory_to_omi(uid, memory_text):
            synced += 1
            synced_ids.add(event_id)
        else:
            log(f"Sync: Failed to push event {event_id}")

    # Persist the merged cumulative set
    store_user_setting(uid, "last_sync_at", datetime.utcnow().isoformat())
    store_user_setting(uid, "synced_event_ids", list(synced_ids))

    summary = f"Synced {synced} new events, skipped {skipped} already synced"
    log(f"Sync: Completed for {uid} — {summary}")

    return {
        "success": True,
        "synced": synced,
        "skipped": skipped,
        "total_events": len(events),
        "message": summary,
    }


# ============================================
# Background scheduler for auto-sync
# ============================================

_scheduler_tasks: Dict[str, asyncio.Task] = {}


async def _run_periodic_sync(
    uid: str,
    interval_minutes: int,
    get_valid_access_token_fn: Callable,
    calendar_api_request_fn: Callable,
    get_default_calendar_fn: Callable,
):
    """Background coroutine that syncs a user's calendar on a fixed interval."""
    log(f"Scheduler: Started periodic sync for {uid} every {interval_minutes}m")
    while True:
        await asyncio.sleep(interval_minutes * 60)
        enabled = get_user_setting(uid, "auto_sync_enabled")
        if not enabled:
            log(f"Scheduler: Auto-sync disabled for {uid}, stopping")
            break
        try:
            await sync_user_calendar(
                uid,
                get_valid_access_token_fn,
                calendar_api_request_fn,
                get_default_calendar_fn,
            )
        except Exception as e:
            log(f"Scheduler: Error during periodic sync for {uid}: {e}")


def start_auto_sync(
    uid: str,
    get_valid_access_token_fn: Callable,
    calendar_api_request_fn: Callable,
    get_default_calendar_fn: Callable,
    interval_minutes: int = DEFAULT_SYNC_INTERVAL_MINUTES,
):
    """Start a background auto-sync task for a user."""
    stop_auto_sync(uid)
    loop = asyncio.get_event_loop()
    task = loop.create_task(
        _run_periodic_sync(
            uid,
            interval_minutes,
            get_valid_access_token_fn,
            calendar_api_request_fn,
            get_default_calendar_fn,
        )
    )
    _scheduler_tasks[uid] = task
    log(f"Scheduler: Auto-sync task created for {uid}")


def stop_auto_sync(uid: str):
    """Cancel a user's background auto-sync task if running."""
    task = _scheduler_tasks.pop(uid, None)
    if task and not task.done():
        task.cancel()
        log(f"Scheduler: Cancelled auto-sync for {uid}")


async def auto_sync_loop(
    get_valid_access_token_fn: Callable,
    calendar_api_request_fn: Callable,
    get_default_calendar_fn: Callable,
    get_all_users_fn: Callable,
):
    """
    Global background task that periodically syncs all users with auto_sync_enabled=True.
    Register this in the FastAPI app lifespan.
    """
    log("AutoSyncLoop: Started global auto-sync background task")
    while True:
        await asyncio.sleep(DEFAULT_SYNC_INTERVAL_MINUTES * 60)
        try:
            users = get_all_users_fn()
            for uid in users:
                enabled = get_user_setting(uid, "auto_sync_enabled")
                if enabled:
                    try:
                        await sync_user_calendar(
                            uid,
                            get_valid_access_token_fn,
                            calendar_api_request_fn,
                            get_default_calendar_fn,
                        )
                    except Exception as e:
                        log(f"AutoSyncLoop: Error syncing {uid}: {e}")
        except Exception as e:
            log(f"AutoSyncLoop: Error during loop iteration: {e}")
