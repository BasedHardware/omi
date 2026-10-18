"""Support allowlist, field-masked activity reads, and mandatory audit persistence."""

import hashlib
from datetime import datetime
from typing import Any, Literal

from google.cloud import firestore

from database._client import get_firestore_client


def _validate_uid(uid: Any) -> str:
    """Validate and sanitize a document UID.

    Rejects non-string types, empty/whitespace-only strings, path traversal delimiters ('/', '\\'),
    and invalid Firestore document names.
    """
    if not isinstance(uid, str):
        raise ValueError(f"Invalid uid type: {type(uid).__name__}")
    cleaned = uid.strip()
    if (
        not cleaned
        or '/' in cleaned
        or '\\' in cleaned
        or cleaned in {'.', '..'}
        or (cleaned.startswith('__') and cleaned.endswith('__'))
    ):
        raise ValueError(f"Invalid uid: {uid!r}")
    return cleaned


def get_support_access(caller_uid: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    try:
        sanitized_uid = _validate_uid(caller_uid)
    except ValueError:
        return None

    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = client.collection('supportData').document(sanitized_uid).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def get_support_activity(target_uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    try:
        sanitized_uid = _validate_uid(target_uid)
    except ValueError:
        return {}

    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = (
        client.collection('users').document(sanitized_uid).get(field_paths=['last_active_at', 'last_active_platform'])
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
    if action not in ('lookup', 'trace'):
        raise ValueError(f"Invalid action: {action!r}")
    sanitized_actor = _validate_uid(actor_uid)
    sanitized_target = _validate_uid(target_uid)
    if not isinstance(email, str) or not email.strip():
        raise ValueError("Invalid email: must be a non-empty string")

    row: dict[str, Any] = {
        'actor_uid': sanitized_actor,
        'action': action,
        'target_uid': sanitized_target,
        'email_sha256': hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest(),
        'at': firestore.SERVER_TIMESTAMP,
    }
    if action == 'trace':
        row.update(window_from=window_from, window_to=window_to)

    client = firestore_client if firestore_client is not None else get_firestore_client()
    client.collection('support_audit_log').document().set(row)
