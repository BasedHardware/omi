"""Identifier-only EXP-004 measurements. Client rules deny this server-owned collection."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_data_plane_firestore_client

RETENTION_DAYS = 60
# Same plane the auth fence reads (database/account_deletion_marker.py); spelled
# literally to keep this module's import chain stub-friendly, as
# transcription_shadow does.
_ACCOUNT_DELETION_COLLECTION = 'account_deletions'


def write_jev_shadow(
    uid: str, record_id: str, record: dict[str, Any], *, deadline: float, firestore_client: Any = None
) -> bool:
    """No prompts, transcript, quotes, candidate content or user names belong here.

    Returns ``False`` when the account is being deleted: the deletion marker is
    read in the same transaction as the write, so a shadow record racing the
    deletion sweep cannot recreate ``users/{uid}/jev_shadow`` after the wipe.
    """
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    now = datetime.now(timezone.utc)
    ref = client.collection('users').document(uid).collection('jev_shadow').document(record_id)
    deletion_marker = client.collection(_ACCOUNT_DELETION_COLLECTION).document(uid)

    @firestore.transactional
    def write_if_not_deleting(transaction: Any) -> bool:
        # Account deletion persists this marker before its recursive sweep.
        # Reading it in the same transaction fences a commit that would
        # otherwise land after the sweep has passed this subcollection.
        if deletion_marker.get(transaction=transaction).exists:
            return False
        transaction.set(ref, {**record, 'created_at': now, 'expire_at': now + timedelta(days=RETENTION_DAYS)})
        return True

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return write_if_not_deleting(client.transaction())
