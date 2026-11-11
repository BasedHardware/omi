"""Support allowlist, field-masked activity reads, and mandatory audit persistence."""

import hashlib
from datetime import datetime
from typing import Any, Literal

from google.cloud import firestore

from database._client import get_firestore_client


def get_support_access(caller_uid: str) -> dict[str, Any] | None:
    snapshot = get_firestore_client().collection('supportData').document(caller_uid).get()
    return snapshot.to_dict() if snapshot.exists else None


def get_support_activity(target_uid: str) -> dict[str, Any]:
    snapshot = (
        get_firestore_client()
        .collection('users')
        .document(target_uid)
        .get(field_paths=['last_active_at', 'last_active_platform'])
    )
    if not snapshot.exists:
        return {}
    return snapshot.to_dict() or {}


def write_support_audit(
    actor_uid: str,
    action: Literal['lookup', 'trace'],
    target_uid: str,
    email: str,
    *,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
) -> None:
    row: dict[str, Any] = {
        'actor_uid': actor_uid,
        'action': action,
        'target_uid': target_uid,
        'email_sha256': hashlib.sha256(email.encode('utf-8')).hexdigest(),
        'at': firestore.SERVER_TIMESTAMP,
    }
    if action == 'trace':
        row.update(window_from=window_from, window_to=window_to)
    get_firestore_client().collection('support_audit_log').document().set(row)
