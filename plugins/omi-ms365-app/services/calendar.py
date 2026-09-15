"""Outlook Calendar operations via Microsoft Graph."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.graph_client import GraphClient

# Page size for each calendarView request ($top is per-page, not a total cap).
CALENDAR_PAGE_SIZE = 50
# Default and hard cap for list_upcoming's `limit` — see issue #13913.
MAX_UPCOMING_EVENTS = 500
# Sanity ceiling on the lookahead window.
MAX_UPCOMING_DAYS = 366


def _safe_int(value: Any, default: int, *, max_value: int) -> int:
    """Coerce an optional tool argument; explicit JSON null/blank/non-numeric
    values fall back to ``default`` instead of raising TypeError downstream."""
    if value is None or value == "":
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, max_value))


def _slim_event(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": e.get("id"),
        "subject": e.get("subject"),
        "start": (e.get("start") or {}).get("dateTime"),
        "end": (e.get("end") or {}).get("dateTime"),
        "tz": (e.get("start") or {}).get("timeZone"),
        "location": (e.get("location") or {}).get("displayName"),
        "organizer": (e.get("organizer") or {}).get("emailAddress", {}).get("address"),
        "is_online": e.get("isOnlineMeeting"),
        "join_url": e.get("onlineMeeting", {}).get("joinUrl") if e.get("onlineMeeting") else None,
        "web_link": e.get("webLink"),
    }


async def list_upcoming(
    user_id: str,
    days: int = 1,
    limit: int = MAX_UPCOMING_EVENTS,
) -> list[dict[str, Any]]:
    days = _safe_int(days, 1, max_value=MAX_UPCOMING_DAYS)
    limit = _safe_int(limit, MAX_UPCOMING_EVENTS, max_value=MAX_UPCOMING_EVENTS)
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    async with GraphClient(user_id) as g:
        events = await g.get_all(
            "/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime",
                "$top": CALENDAR_PAGE_SIZE,
            },
            max_items=limit,
        )
        return [_slim_event(e) for e in events]


async def create_event(
    user_id: str,
    subject: str,
    start_iso: str,
    end_iso: str,
    *,
    attendees: list[str] | None = None,
    body: str = "",
    online: bool = True,
    timezone_str: str = "UTC",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body},
        "start": {"dateTime": start_iso, "timeZone": timezone_str},
        "end": {"dateTime": end_iso, "timeZone": timezone_str},
        "isOnlineMeeting": online,
        "onlineMeetingProvider": "teamsForBusiness" if online else None,
    }
    if attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": a}, "type": "required"} for a in attendees
        ]

    async with GraphClient(user_id) as g:
        data = await g.post("/me/events", json=payload)
        return _slim_event(data)


async def find_free_slots(
    user_id: str,
    duration_minutes: int,
    attendees: list[str],
    *,
    within_days: int = 5,
) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=within_days)
    payload = {
        "attendees": [
            {"emailAddress": {"address": a}, "type": "required"} for a in attendees
        ],
        "timeConstraint": {
            "timeslots": [
                {
                    "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                }
            ]
        },
        "meetingDuration": f"PT{duration_minutes}M",
        "maxCandidates": 10,
    }
    async with GraphClient(user_id) as g:
        data = await g.post("/me/findMeetingTimes", json=payload)
        return [
            {
                "start": s["meetingTimeSlot"]["start"]["dateTime"],
                "end": s["meetingTimeSlot"]["end"]["dateTime"],
                "confidence": s.get("confidence"),
            }
            for s in data.get("meetingTimeSuggestions", [])
        ]
