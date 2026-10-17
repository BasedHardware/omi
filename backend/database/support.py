"""Support allowlist, field-masked activity reads, and mandatory audit persistence."""

import hashlib
import logging
from datetime import datetime
from typing import Any, Literal

from google.cloud import firestore

from database._client import get_firestore_client

logger = logging.getLogger(__name__)


def get_support_access(caller_uid: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    clean_uid = (caller_uid or '').strip()
    if not clean_uid:
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = client.collection('supportData').document(clean_uid).get()
        return snapshot.to_dict() if snapshot.exists else None
    except Exception as e:
        logger.warning("Failed to fetch support access for %s: %s", clean_uid, e)
        return None


def get_support_activity(target_uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    clean_uid = (target_uid or '').strip()
    if not clean_uid:
        return {}
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = (
            client.collection('users').document(clean_uid).get(field_paths=['last_active_at', 'last_active_platform'])
        )
        if not snapshot.exists:
            return {}
        return snapshot.to_dict() or {}
    except Exception as e:
        logger.warning("Failed to fetch support activity for %s: %s", clean_uid, e)
        return {}


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
    clean_actor = (actor_uid or '').strip()
    clean_target = (target_uid or '').strip()
    clean_email = (email or '').strip()
    row: dict[str, Any] = {
        'actor_uid': clean_actor,
        'action': action,
        'target_uid': clean_target,
        'email_sha256': hashlib.sha256(clean_email.encode('utf-8')).hexdigest(),
        'at': firestore.SERVER_TIMESTAMP,
    }
    if action == 'trace':
        row.update(window_from=window_from, window_to=window_to)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        client.collection('support_audit_log').document().set(row)
    except Exception as e:
        logger.warning("Failed to persist support audit for actor %s target %s: %s", clean_actor, clean_target, e)
