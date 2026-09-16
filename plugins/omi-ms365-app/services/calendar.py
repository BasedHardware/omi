"""Outlook Calendar operations via Microsoft Graph."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.graph_client import GraphClient


def _slim_event(e: Any) -> dict[str, Any]:
    if not isinstance(e, dict):
        return {}
    start_obj = e.get("start") if isinstance(e.get("start"), dict) else {}
    end_obj = e.get("end") if isinstance(e.get("end"), dict) else {}
    loc_obj = e.get("location") if isinstance(e.get("location"), dict) else {}
    org_obj = e.get("organizer") if isinstance(e.get("organizer"), dict) else {}
    org_addr = org_obj.get("emailAddress") if isinstance(org_obj.get("emailAddress"), dict) else {}
    online_obj = e.get("onlineMeeting") if isinstance(e.get("onlineMeeting"), dict) else {}
    return {
        "id": e.get("id"),
        "subject": e.get("subject"),
        "start": start_obj.get("dateTime"),
        "end": end_obj.get("dateTime"),
        "tz": start_obj.get("timeZone"),
        "location": loc_obj.get("displayName"),
        "organizer": org_addr.get("address"),
        "is_online": e.get("isOnlineMeeting"),
        "join_url": online_obj.get("joinUrl"),
        "web_link": e.get("webLink"),
    }


# calendarView is server-paged: $top is the page size, and anything past it
# only arrives via @odata.nextLink. Events are ordered by start, so a single
# page silently drops the *later* events in the window — exactly the ones a
# "what's on next month" question is about.
CALENDAR_PAGE_SIZE = 50
MAX_EVENTS = 500


async def list_upcoming(user_id: str, days: int = 1, limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    limit = max(1, min(int(limit), MAX_EVENTS))
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
        raw_items = events if isinstance(events, list) else []
        return [_slim_event(e) for e in raw_items if isinstance(e, dict)]


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
        raw_suggestions = data.get("meetingTimeSuggestions") if isinstance(data, dict) and isinstance(data.get("meetingTimeSuggestions"), list) else []
        slots: list[dict[str, Any]] = []
        for s in raw_suggestions:
            if not isinstance(s, dict):
                continue
            slot = s.get("meetingTimeSlot")
            if not isinstance(slot, dict):
                continue
            start_d = slot.get("start") if isinstance(slot.get("start"), dict) else {}
            end_d = slot.get("end") if isinstance(slot.get("end"), dict) else {}
            start_dt = start_d.get("dateTime")
            end_dt = end_d.get("dateTime")
            if not start_dt or not end_dt:
                continue
            slots.append({
                "start": start_dt,
                "end": end_dt,
                "confidence": s.get("confidence"),
            })
        return slots
