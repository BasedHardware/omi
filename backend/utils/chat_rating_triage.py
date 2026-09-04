"""Extract classifiable fields from a rated chat message without reading user text.

`metadata.continuityKey` already encodes `notification:<kind>:<uuid>` in plaintext.
Copying the parsed kind (and `app_id`) onto the analytics row is what makes
thumbs-downs triageable after the message is encrypted or deleted.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

# Desktop notification-shaped codes plus the existing mobile chat codes so one
# column stays an enum. Free text must never enter this field.
RATING_REASON_CODES = frozenset(
    {
        'not_about_me',
        'already_done',
        'wrong_facts',
        'bad_timing',
        'not_useful',
        'other',
        'too_verbose',
        'incorrect_or_hallucination',
        'not_helpful_or_irrelevant',
        'didnt_follow_instructions',
    }
)

RATING_REASON_PATTERN = r'^(' + '|'.join(sorted(RATING_REASON_CODES)) + r')$'

_NOTIFICATION_KEY_RE = re.compile(r'^notification:(?:(?P<kind>[A-Za-z0-9_]+):)?(?P<id>[0-9a-fA-F-]{8,})$')


def parse_notification_kind(
    metadata: Any = None,
    client_message_id: str | None = None,
) -> str | None:
    """Return the notification kind encoded in continuityKey, or None."""
    key = _continuity_key(metadata)
    if not key and isinstance(client_message_id, str):
        key = client_message_id
    if not isinstance(key, str) or not key.startswith('notification:'):
        return None
    match = _NOTIFICATION_KEY_RE.match(key)
    if not match:
        return None
    kind = match.group('kind')
    return kind if kind else 'general'


def extract_rating_triage_fields(message: Any) -> dict[str, str]:
    """Identifiers/enums only — never user-authored strings."""
    payload = _as_mapping(message)
    metadata = payload.get('metadata')
    client_message_id = payload.get('client_message_id') or payload.get('clientTurnId')
    fields: dict[str, str] = {}
    kind = parse_notification_kind(metadata, client_message_id if isinstance(client_message_id, str) else None)
    if kind:
        fields['notification_kind'] = kind
    app_id = payload.get('app_id') or payload.get('plugin_id')
    if isinstance(app_id, str) and app_id:
        fields['app_id'] = app_id
    return fields


def normalize_rating_reason(reason: str | None) -> str | None:
    if not isinstance(reason, str) or not reason:
        return None
    value = reason.strip()
    # Mobile historically concatenated `$reason: $comment` into one column.
    if ':' in value:
        value = value.split(':', 1)[0].strip()
    if value in RATING_REASON_CODES:
        return value
    return None


def _continuity_key(metadata: Any) -> str | None:
    parsed = metadata
    if isinstance(metadata, str) and metadata:
        try:
            parsed = json.loads(metadata)
        except (TypeError, ValueError):
            return metadata if metadata.startswith('notification:') else None
    mapping = _as_mapping(parsed)
    key = mapping.get('continuityKey') or mapping.get('continuity_key')
    return key if isinstance(key, str) else None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, 'model_dump'):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, Mapping) else {}
    if hasattr(value, '__dict__'):
        return {k: v for k, v in vars(value).items() if not k.startswith('_')}
    return {}
