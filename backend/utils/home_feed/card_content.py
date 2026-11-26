"""Build the bounded Home card fields without keys, I/O or transcript content."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA = 1


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
