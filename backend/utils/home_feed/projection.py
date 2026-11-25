"""Write-time compact display construction; no database, providers or transcripts.

Keep this outside utils.conversations: it is also used by the episode writer.
Content is encrypted separately even for standard-protection conversations.
"""

from collections.abc import Mapping
from typing import Any
from uuid import uuid4
import json

from utils.encryption import encrypt, decrypt
from utils.conversations.home_titles import notes_pending
from utils.home_feed import card_content
from utils.home_feed.card_content import SCHEMA, utc

DISPLAY = 'home_display'
VERSION = 'home_display_version'
SORT = 'home_sort_at'
DISPLAY_FIELDS = frozenset({DISPLAY, VERSION, SORT, 'home_started_at', 'home_projection_schema', 'home_has_tasks'})


def content(row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    display = card_content.content(row, kind)
    if kind == 'conversation':
        display['notes_pending'] = notes_pending(row.get('structured'))
    return display


def seal_display(uid: str, value: Mapping[str, Any]) -> str:
    return encrypt(json.dumps(dict(value), ensure_ascii=False, separators=(',', ':')), uid)


def reveal_display(uid: str, blob: Any) -> dict[str, Any] | None:
    if not isinstance(blob, str) or len(blob) > 8192:
        return None
    # decrypt historically returns ciphertext on authentication failure. Never
    # serialize that return value as display text.
    try:
        plaintext = decrypt(blob, uid)
        if plaintext == blob:
            return None
        value = json.loads(plaintext)
    except (ValueError, TypeError, RecursionError):
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
