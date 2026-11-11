"""Developer webhook contracts and sample events.

An Omi app receives events on an endpoint the user configures in Developer
Settings. The shapes below mirror what ``backend/utils/webhooks.py`` posts, so
a developer can exercise a receiver without a device, a tunnel, or waiting for
the day-summary cron tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, Union

JsonBody = dict[str, Any]
WebhookBody = Union[JsonBody, bytes]

SAMPLE_UID = "omi_dev_sample_uid"
AUDIO_SAMPLE_RATE = 16000
JSON_CONTENT_TYPE = "application/json"
AUDIO_CONTENT_TYPE = "application/octet-stream"

# Mirrors the backend default schedule (DEV_WEBHOOK_RETRY_DELAYS overrides it),
# so a failing receiver is told what Omi would really do next.
RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 5.0, 30.0)

# A 4xx other than 408 or 429 is a deterministic rejection: Omi posts it once
# and stops, because a repeat cannot converge.
NO_RETRY_STATUSES = frozenset(range(400, 500)) - {408, 429}

# Consecutive failures that pause a URL, how long the pause lasts, and the
# count that disables the webhook for the user.
CIRCUIT_BREAKER_FAILURES = 5
CIRCUIT_BREAKER_PAUSE_SECONDS = 30
AUTO_DISABLE_FAILURES = 100

# A real-time transcript receiver can answer with {"message": "..."}; Omi pushes
# it to the user as a notification, but only past this length.
NOTIFICATION_MIN_MESSAGE_LENGTH = 5


@dataclass(frozen=True)
class WebhookEvent:
    """One developer webhook, as the backend sends it."""

    name: str
    summary: str
    content_type: str
    query_params: tuple[str, ...]
    body: str
    builder: Callable[[str, datetime], WebhookBody]
    response_note: Optional[str] = None


def _conversation_payload(uid: str, now: datetime) -> WebhookBody:
    stamp = now.isoformat()
    return {
        "id": "sample-conversation-1",
        "created_at": stamp,
        "started_at": stamp,
        "finished_at": stamp,
        "source": "omi",
        "language": "en",
        "folder_id": None,
        "folder_name": None,
        "structured": {
            "title": "Standup with the design team",
            "overview": "Agreed to ship the new onboarding on Friday and to cut the second survey.",
            "emoji": "🗓️",
            "category": "business",
            "action_items": [
                {"description": "Send the onboarding copy to design", "completed": False},
            ],
            "events": [],
        },
        "transcript_segments": [
            {
                "id": "sample-segment-1",
                "text": "Let us ship the new onboarding on Friday.",
                "speaker": "SPEAKER_00",
                "speaker_id": 0,
                "speaker_name": "Nik",
                "is_user": False,
                "start": 0.0,
                "end": 2.6,
            },
            {
                "id": "sample-segment-2",
                "text": "I will send the copy to design today.",
                "speaker": "SPEAKER_01",
                "speaker_id": 1,
                "speaker_name": "You",
                "is_user": True,
                "start": 2.8,
                "end": 5.1,
            },
        ],
    }


def _realtime_transcript_payload(uid: str, now: datetime) -> WebhookBody:
    return {
        "segments": [
            {
                "text": "Remind me to send the onboarding copy to design.",
                "speaker": "SPEAKER_00",
                "speaker_id": 0,
                "is_user": True,
                "start": 0.0,
                "end": 2.9,
            }
        ],
        "session_id": uid,
    }


def _day_summary_payload(uid: str, now: datetime) -> WebhookBody:
    summary_json = {
        "title": "A day of shipping",
        "summary": "Three conversations, two of them about onboarding.",
        "conversations_count": 3,
    }
    return {
        "summary": str(summary_json),
        "summary_json": summary_json,
        "uid": uid,
        "created_at": now.isoformat(),
    }


def _audio_bytes_payload(uid: str, now: datetime) -> WebhookBody:
    # One second of 16 kHz signed 16-bit PCM, the chunk size the backend sends.
    return b"\x00" * (AUDIO_SAMPLE_RATE * 2)


def _button_event_payload(uid: str, now: datetime) -> WebhookBody:
    return {
        "event_type": "button_event",
        "button_event": "single_tap",
        "device_id": "sample-device-1",
        "event_id": "sample-button-event-1",
        "timestamp": now.isoformat(),
        "session_id": None,
    }


EVENTS: dict[str, WebhookEvent] = {
    "memory_created": WebhookEvent(
        name="memory_created",
        summary="A conversation finished processing.",
        content_type=JSON_CONTENT_TYPE,
        query_params=("uid",),
        body="The conversation, with speaker and folder names resolved.",
        builder=_conversation_payload,
    ),
    "realtime_transcript": WebhookEvent(
        name="realtime_transcript",
        summary="Transcript segments while the user is still speaking.",
        content_type=JSON_CONTENT_TYPE,
        query_params=("uid",),
        body="{segments, session_id}",
        builder=_realtime_transcript_payload,
        response_note=(
            'Answer with {"message": "..."} and Omi shows it to the user as a notification, '
            f"as long as the message is longer than {NOTIFICATION_MIN_MESSAGE_LENGTH} characters."
        ),
    ),
    "day_summary": WebhookEvent(
        name="day_summary",
        summary="The daily summary, on the delivery hour the user picked.",
        content_type=JSON_CONTENT_TYPE,
        query_params=("uid",),
        body="{summary, summary_json, uid, created_at}",
        builder=_day_summary_payload,
    ),
    "audio_bytes": WebhookEvent(
        name="audio_bytes",
        summary="Raw audio while the user is recording.",
        content_type=AUDIO_CONTENT_TYPE,
        query_params=("sample_rate", "uid"),
        body=f"One second of {AUDIO_SAMPLE_RATE} Hz signed 16-bit PCM per request.",
        builder=_audio_bytes_payload,
    ),
    "button_event": WebhookEvent(
        name="button_event",
        summary="A hardware button gesture the user opted to forward.",
        content_type=JSON_CONTENT_TYPE,
        query_params=("uid",),
        body="{event_type, button_event, device_id, event_id, timestamp, session_id}",
        builder=_button_event_payload,
    ),
}


def event_names() -> list[str]:
    return list(EVENTS)


def get_event(name: str) -> Optional[WebhookEvent]:
    return EVENTS.get(name)


def is_retried(status_code: int) -> bool:
    """Whether Omi would post the delivery again after this status."""
    return status_code not in NO_RETRY_STATUSES


def request_params(event: WebhookEvent, uid: str) -> dict[str, str]:
    """The query parameters Omi appends to the configured webhook URL."""
    params: dict[str, str] = {}
    if "sample_rate" in event.query_params:
        params["sample_rate"] = str(AUDIO_SAMPLE_RATE)
    if "uid" in event.query_params:
        params["uid"] = uid
    return params


def idempotency_key(event: WebhookEvent, payload: WebhookBody) -> Optional[str]:
    """Button events key on the event id; the rest get a fresh key per attempt."""
    if event.name == "button_event" and isinstance(payload, dict):
        value = payload.get("event_id")
        if isinstance(value, str):
            return value
    return None
