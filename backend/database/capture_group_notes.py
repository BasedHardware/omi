"""Durable, group-scoped budget and idempotency state for notes refreshes."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional

STATE_COLLECTION = 'capture_group_notes_refresh_state'
REFRESH_LEASE_SECONDS = 1800


def state_ref(uid: str, group_id: str, *, firestore_client: Any = None) -> Any:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    state_id = hashlib.sha256(group_id.encode('utf-8')).hexdigest()
    return client.collection('users').document(uid).collection(STATE_COLLECTION).document(state_id)


def get_state(uid: str, group_id: str, *, firestore_client: Any = None) -> Mapping[str, Any]:
    snapshot = state_ref(uid, group_id, firestore_client=firestore_client).get()
    return snapshot.to_dict() or {} if snapshot.exists else {}


def _clean_fingerprints(values: Mapping[str, Optional[str]]) -> dict[str, str]:
    return {
        member_id: fingerprint
        for member_id, fingerprint in values.items()
        if member_id and isinstance(fingerprint, str) and fingerprint
    }


def claim_refresh(
    uid: str,
    group_id: str,
    primary_id: str,
    revision: int,
    member_fingerprints: Mapping[str, Optional[str]],
    *,
    max_refreshes: int,
    firestore_client: Any = None,
) -> Optional[dict[str, Any]]:
    """Reserve one paid refresh iff new, unconsumed member evidence is present.

    The primary's live membership and the group budget are checked in the same
    transaction. A reservation counts as an attempt, including a failed model
    call, and expires with the existing conversation-processing lease window.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    clean = _clean_fingerprints(member_fingerprints)
    user_ref = client.collection('users').document(uid)
    primary_ref = user_ref.collection('conversations').document(primary_id)
    state_document = state_ref(uid, group_id, firestore_client=client)

    @firestore.transactional
    def reserve(transaction) -> Optional[dict[str, Any]]:
        primary_snapshot = primary_ref.get(transaction=transaction)
        state_snapshot = state_document.get(transaction=transaction)
        primary = primary_snapshot.to_dict() or {} if primary_snapshot.exists else {}
        state = state_snapshot.to_dict() or {} if state_snapshot.exists else {}
        group = primary.get('capture_group') or {}
        if (
            not primary
            or primary.get('deleted')
            or primary.get('discarded')
            or primary.get('status') != 'completed'
            or group.get('id') != group_id
            or group.get('primary_id') != primary_id
            or group.get('revision') != revision
        ):
            return None
        count = int(state.get('refresh_count') or 0)
        if count >= max_refreshes:
            return None
        current = state.get('in_progress') or {}
        lease = current.get('lease_expires_at')
        now = datetime.now(timezone.utc)
        if isinstance(lease, datetime) and lease > now:
            return None

        prior_members = state.get('member_fingerprints') or {}
        seen = set(state.get('seen_evidence_fingerprints') or [])
        candidates = sorted(
            {
                fingerprint
                for member_id, fingerprint in clean.items()
                if prior_members.get(member_id) != fingerprint and fingerprint not in seen
            }
        )
        if not candidates:
            return None

        reservation_id = str(uuid.uuid4())
        operation = {
            'id': reservation_id,
            'group_id': group_id,
            'revision': revision,
            'primary_id': primary_id,
            'evidence_fingerprints': candidates,
            'member_fingerprints': clean,
            'lease_expires_at': now + timedelta(seconds=REFRESH_LEASE_SECONDS),
        }
        transaction.set(
            state_document,
            {
                **state,
                'group_id': group_id,
                'refresh_count': count + 1,
                'in_progress': operation,
                'updated_at': now,
            },
        )
        return operation

    return run_transactional(client, reserve)


def read_success_write(
    transaction: Any,
    uid: str,
    group_id: str,
    reservation_id: str,
    *,
    firestore_client: Any = None,
) -> Optional[tuple[Any, dict[str, Any]]]:
    """Read and stage the exact state update to commit with the primary notes."""
    document = state_ref(uid, group_id, firestore_client=firestore_client)
    snapshot = document.get(transaction=transaction)
    state = snapshot.to_dict() or {} if snapshot.exists else {}
    operation = state.get('in_progress') or {}
    if state.get('group_id') != group_id or operation.get('id') != reservation_id:
        return None
    seen = set(state.get('seen_evidence_fingerprints') or [])
    seen.update(operation.get('evidence_fingerprints') or [])
    updated = {
        'group_id': group_id,
        'refresh_count': int(state.get('refresh_count') or 0),
        'seen_evidence_fingerprints': sorted(seen),
        'member_fingerprints': operation.get('member_fingerprints') or {},
        'last_successful_revision': operation.get('revision'),
        'last_primary_id': operation.get('primary_id'),
        'in_progress': None,
        'updated_at': datetime.now(timezone.utc),
    }
    return document, updated


def release_refresh(
    uid: str,
    group_id: str,
    reservation_id: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Release a failed or stale reservation without consuming its evidence."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    document = state_ref(uid, group_id, firestore_client=client)

    @firestore.transactional
    def release(transaction) -> bool:
        snapshot = document.get(transaction=transaction)
        state = snapshot.to_dict() or {} if snapshot.exists else {}
        operation = state.get('in_progress') or {}
        if operation.get('id') != reservation_id:
            return False
        transaction.set(
            document,
            {
                **state,
                'in_progress': None,
                'last_failed_revision': operation.get('revision'),
                'updated_at': datetime.now(timezone.utc),
            },
        )
        return True

    return run_transactional(client, release)
