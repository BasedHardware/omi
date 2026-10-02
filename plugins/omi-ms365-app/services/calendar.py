"""Outlook Calendar operations via Microsoft Graph."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from services.graph_client import GraphClient


def _normalize_attendees(attendees: Any) -> list[str]:
    """Normalize attendee input (single string, comma/semicolon-separated string, or list) into a list of emails."""
    if not attendees:
        return []
    if isinstance(attendees, str):
        return [a.strip() for a in re.split(r"[,;]", attendees) if a.strip()]
    if isinstance(attendees, (list, tuple, set)):
        result: list[str] = []
        for item in attendees:
            if isinstance(item, str):
                for p in re.split(r"[,;]", item):
                    if p.strip():
                        result.append(p.strip())
            elif isinstance(item, dict):
                addr = item.get("address")
                if not addr and isinstance(item.get("emailAddress"), dict):
                    addr = item["emailAddress"].get("address")
                if addr and str(addr).strip():
                    result.append(str(addr).strip())
        return result
    return []


def _slim_event(e: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(e, dict):
        return {}
    start_obj = e.get("start") if isinstance(e.get("start"), dict) else {}
    end_obj = e.get("end") if isinstance(e.get("end"), dict) else {}
    location_obj = e.get("location") if isinstance(e.get("location"), dict) else {}
    organizer_obj = e.get("organizer") if isinstance(e.get("organizer"), dict) else {}
    org_email = organizer_obj.get("emailAddress") if isinstance(organizer_obj.get("emailAddress"), dict) else {}
    meeting_obj = e.get("onlineMeeting") if isinstance(e.get("onlineMeeting"), dict) else {}
    return {
        "id": e.get("id"),
        "subject": e.get("subject"),
        "start": start_obj.get("dateTime"),
        "end": end_obj.get("dateTime"),
        "tz": start_obj.get("timeZone"),
        "location": location_obj.get("displayName"),
        "organizer": org_email.get("address"),
        "is_online": e.get("isOnlineMeeting"),
        "join_url": meeting_obj.get("joinUrl") if meeting_obj else None,
        "web_link": e.get("webLink"),
    }


# calendarView is server-paged: $top is the page size, and anything past it
# only arrives via @odata.nextLink. Events are ordered by start, so a single
# page silently drops the *later* events in the window — exactly the ones a
# "what's on next month" question is about.
CALENDAR_PAGE_SIZE = 50
MAX_EVENTS = 500


async def list_upcoming(user_id: str, days: int = 1, limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    try:
        safe_days = max(1, min(int(days), 365))
    except (ValueError, TypeError):
        safe_days = 1
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=safe_days)
    try:
        limit = max(1, min(int(limit), MAX_EVENTS))
    except (ValueError, TypeError):
        limit = MAX_EVENTS
    async with GraphClient(user_id) as g:
        events = await g.get_all(
            "/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime",
                "$top": min(CALENDAR_PAGE_SIZE, limit),
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
    attendees: list[str] | str | None = None,
    body: str = "",
    online: bool = True,
    timezone_str: str = "UTC",
) -> dict[str, Any]:
    is_online = online is True or str(online).lower() in ("true", "1", "yes")
    payload: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body},
        "start": {"dateTime": start_iso, "timeZone": timezone_str},
        "end": {"dateTime": end_iso, "timeZone": timezone_str},
        "isOnlineMeeting": is_online,
        "onlineMeetingProvider": "teamsForBusiness" if is_online else None,
    }
    norm_attendees = _normalize_attendees(attendees)
    if norm_attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": a}, "type": "required"} for a in norm_attendees
        ]

    async with GraphClient(user_id) as g:
        data = await g.post("/me/events", json=payload)
        return _slim_event(data)


async def find_free_slots(
    user_id: str,
    duration_minutes: int = 30,
    attendees: list[str] | str | None = None,
    *,
    within_days: int = 5,
) -> list[dict[str, Any]]:
    try:
        safe_within_days = max(1, min(int(within_days), 60))
    except (ValueError, TypeError):
        safe_within_days = 5
    try:
        safe_duration = max(1, min(int(duration_minutes), 1440))
    except (ValueError, TypeError):
        safe_duration = 30
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=safe_within_days)
    norm_attendees = _normalize_attendees(attendees)
    payload = {
        "attendees": [
            {"emailAddress": {"address": a}, "type": "required"} for a in norm_attendees
        ],
        "timeConstraint": {
            "timeslots": [
                {
                    "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                }
            ]
        },
        "meetingDuration": f"PT{safe_duration}M",
        "maxCandidates": 10,
    }
    async with GraphClient(user_id) as g:
        data = await g.post("/me/findMeetingTimes", json=payload)
        raw_suggestions = (data.get("meetingTimeSuggestions") or []) if isinstance(data, dict) else []
        slots = []
        for s in raw_suggestions:
            if not isinstance(s, dict):
                continue
            slot = s.get("meetingTimeSlot") if isinstance(s.get("meetingTimeSlot"), dict) else {}
            start_dict = slot.get("start") if isinstance(slot.get("start"), dict) else {}
            end_dict = slot.get("end") if isinstance(slot.get("end"), dict) else {}
            slots.append({
                "start": start_dict.get("dateTime"),
                "end": end_dict.get("dateTime"),
                "confidence": s.get("confidence"),
            })
        return slots
