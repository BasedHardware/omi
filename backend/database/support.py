"""Support allowlist, field-masked activity reads, and mandatory audit persistence."""

import hashlib
import logging
from datetime import datetime
from typing import Any, Literal

from google.cloud import firestore

from database._client import get_firestore_client

logger = logging.getLogger(__name__)


def _sanitize_uid(uid: Any) -> str | None:
    """Sanitize and validate an identifier string; returns stripped UID or None if invalid."""
    if not uid or not isinstance(uid, str):
        return None
    cleaned = uid.strip()
    if not cleaned or '/' in cleaned:
        return None
    return cleaned


def get_support_access(caller_uid: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    cleaned_uid = _sanitize_uid(caller_uid)
    if not cleaned_uid:
        return None

    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = client.collection('supportData').document(cleaned_uid).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def get_support_activity(target_uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    cleaned_uid = _sanitize_uid(target_uid)
    if not cleaned_uid:
        return {}

    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = (
        client.collection('users').document(cleaned_uid).get(field_paths=['last_active_at', 'last_active_platform'])
    )
    if not getattr(snapshot, 'exists', False):
        return {}
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else {}


def write_support_audit(
    actor_uid: str,
    action: Literal['lookup', 'trace'],
    target_uid: str,
    email: str,
    *,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
    firestore_client: Any = None,
) -> None:
    cleaned_actor = _sanitize_uid(actor_uid)
    if not cleaned_actor:
        raise ValueError('Invalid actor_uid')

    if action not in ('lookup', 'trace'):
        raise ValueError(f'Invalid support audit action: {action}')

    cleaned_target = _sanitize_uid(target_uid)
    if not cleaned_target:
        raise ValueError('Invalid target_uid')

    if not email or not isinstance(email, str) or not email.strip():
        raise ValueError('Invalid email')

    client = firestore_client if firestore_client is not None else get_firestore_client()
    row: dict[str, Any] = {
        'actor_uid': cleaned_actor,
        'action': action,
        'target_uid': cleaned_target,
        'email_sha256': hashlib.sha256(email.encode('utf-8')).hexdigest(),
        'at': firestore.SERVER_TIMESTAMP,
    }
    if action == 'trace':
        row.update(window_from=window_from, window_to=window_to)

    client.collection('support_audit_log').document().set(row)
