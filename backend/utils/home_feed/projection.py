"""Write-time compact display construction; no database, providers or transcripts.

Keep this outside utils.conversations: it is also used by the episode writer.
Content is encrypted separately even for standard-protection conversations.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
import json

from utils.encryption import encrypt, decrypt

SCHEMA = 1
DISPLAY = 'home_display'
VERSION = 'home_display_version'
SORT = 'home_sort_at'
DISPLAY_FIELDS = frozenset({DISPLAY, VERSION, SORT, 'home_started_at', 'home_projection_schema', 'home_has_tasks'})


def text(value: Any, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ''


def utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    # Normalize Firestore nanosecond subclasses to the API's microsecond clock
    # before indexing, so a cursor round trip cannot truncate its sort value.
    return datetime(
        aware.year,
        aware.month,
        aware.day,
        aware.hour,
        aware.minute,
        aware.second,
        aware.microsecond,
        tzinfo=timezone.utc,
    )


def content(row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    structured = row.get('structured') or {}
    structured = structured if isinstance(structured, Mapping) else {}
    title = row.get('title') if kind == 'episode' else row.get('user_title') or structured.get('title')
    preview = row.get('lede') if kind == 'episode' else structured.get('gist') or structured.get('overview')
    # Fail closed on paid locks: Home needs no speech-derived preview to render
    # the existing lock/paywall affordance. Never infer access from a blob.
    if row.get('home_content_invalidated'):
        title, preview = row.get('user_title') or '', ''
    if row.get('is_locked'):
        title, preview = '', ''
    return {
        'schema': SCHEMA,
        'title': text(title, 240),
        'emoji': text(row.get('emoji') if kind == 'episode' else structured.get('emoji'), 32),
        'preview': text(preview, 320),
        'summary_available': bool(preview) and not bool(row.get('is_locked')),
    }


def seal_display(uid: str, value: Mapping[str, Any]) -> str:
    return encrypt(json.dumps(dict(value), ensure_ascii=False, separators=(',', ':')), uid)


def reveal_display(uid: str, blob: Any) -> dict[str, Any] | None:
    if not isinstance(blob, str) or len(blob) > 8192:
        return None
    # decrypt historically returns ciphertext on authentication failure. Never
    # serialize that return value as display text.
    try:
        value = json.loads(decrypt(blob, uid))
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        return None
    return value


def stamp(uid: str, row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Only a full logical row can establish projection coverage."""
    recorded_at = utc(row.get('recorded_start')) or utc(row.get('started_at'))
    # Arrival orders unknown-origin history without claiming a recording clock.
    at = recorded_at or utc(row.get('created_at'))
    if at is None:
        return {}
    value = content(row, kind)
    structured = row.get('structured') or {}
    structured = structured if isinstance(structured, Mapping) else {}
    return {
        DISPLAY: seal_display(uid, value),
        VERSION: uuid4().hex,
        SORT: at,
        'home_started_at': recorded_at,
        'home_projection_schema': SCHEMA,
        'home_has_tasks': (
            bool(structured.get('action_items'))
            if kind == 'conversation'
            else bool(row.get('provisional_items') or row.get('follow_ups'))
        ),
    }
