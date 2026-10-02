"""Response-only titles. Never feed this projection back into lifecycle decisions."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.observability.fallback import record_fallback


def apply_display_title(conversation: dict[str, Any]) -> dict[str, Any]:
    """Fill an empty title on an unlocked, visible completed API response only.

    No database access, decoding, model call, or persistence. In particular, an
    unreadable/encrypted transcript is never interpreted as text. The raw title
    remains authoritative for recovery admission and summary retryability.
    """
    if conversation.get('status') != 'completed' or any(
        conversation.get(key) for key in ('discarded', 'deleted', 'is_locked')
    ):
        return conversation
    structured = conversation.get('structured')
    fields = dict(structured) if isinstance(structured, dict) else {}
    title = fields.get('title')
    if isinstance(title, str) and title.strip():
        return conversation
    user_title = conversation.get('user_title')
    if isinstance(user_title, str) and user_title.strip():
        fields['title'] = user_title
    else:
        raw_segments = conversation.get('transcript_segments')
        segments = raw_segments if isinstance(raw_segments, list) else []
        texts = [s['text'] for s in segments if isinstance(s, dict) and isinstance(s.get('text'), str)]
        if any(text.strip() for text in texts):
            fields['title'] = deterministic_minimum_title(
                SimpleNamespace(transcript_segments=[SimpleNamespace(text=text) for text in texts])
            )
        else:
            # No user-zone lookup on a list response. Label UTC explicitly;
            # clients with only cached data format their own local date/time.
            moment = conversation.get('started_at') or conversation.get('created_at')
            if isinstance(moment, str):
                try:
                    moment = datetime.fromisoformat(moment.replace('Z', '+00:00'))
                except ValueError:
                    moment = None
            fields['title'] = 'Recording'
            if isinstance(moment, datetime):
                moment = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment
                fields['title'] += f" · {moment.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC"
        record_fallback(
            component='conversation_title',
            from_mode='none',
            to_mode='deterministic',
            reason='malformed_doc',
            outcome='degraded',
        )
    # Replace the map rather than mutating a nested object shared with a cache.
    conversation['structured'] = fields
    return conversation
