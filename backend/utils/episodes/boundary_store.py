"""Durable, idempotent meeting signals and a bounded edge index (document gets only).

Payloads are encrypted; the index contains opaque keys and timestamps only.
The user's subtree is owned by the existing account erasure path. No new query
or index is needed. Historical payloads retain idempotency after index eviction.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from config.occasion_conversations import EPISODE_BOUNDARIES_MODE_ENV
from config.refactor_modes import shadow_or_serve
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from models.boundary_evidence import BoundarySignal
from utils.encryption import encrypt, decrypt

MAX_SIGNALS = 128
RETENTION = timedelta(days=7)


class BoundaryCapacityError(ValueError):
    pass


def signal_id(signal: BoundarySignal) -> str:
    identity = signal.external_id or f'{signal.started_at.isoformat()}:{signal.source_device or ""}'
    return hashlib.sha256(f'{signal.kind}\0{identity}'.encode()).hexdigest()


def _refs(uid: str, client: Any):
    user = client.collection('users').document(uid)
    return user.collection('capture_boundary_signals'), user.collection('capture_boundary_state').document('v1')


def record(uid: str, signals: list[BoundarySignal], *, firestore_client: Any = None) -> int:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return 0
    client = firestore_client if firestore_client is not None else get_firestore_client()
    records, state_ref = _refs(uid, client)
    proposed = {signal_id(s): s for s in signals}
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def write(transaction):
        marker = account_deletion_document(uid, firestore_client=client).get(transaction=transaction)
        if account_deletion_blocks_access(
            normalize_account_deletion_status(
                marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
            )
        ):
            return 0
        state = state_ref.get(transaction=transaction).to_dict() or {}
        entries = dict(state.get('entries') or {})
        snapshots = {key: records.document(key).get(transaction=transaction).to_dict() or {} for key in proposed}
        writes = {}
        for key, signal in proposed.items():
            previous = snapshots[key]
            if previous:
                old = BoundarySignal.model_validate_json(decrypt(previous['content'], uid))
                if old.started_at != signal.started_at:
                    raise ValueError('boundary start is immutable for an external identity')
                # An end edge never reopens or moves later on a delayed retry.
                if old.ended_at is not None:
                    signal = signal.model_copy(update={'ended_at': min(old.ended_at, signal.ended_at or old.ended_at)})
                if old == signal:
                    continue
            writes[key] = signal
            entries[key] = {'started_at': signal.started_at, 'ended_at': signal.ended_at}
        entries = {k: v for k, v in entries.items() if v.get('ended_at') is None or v['ended_at'] >= now - RETENTION}
        if len(entries) > MAX_SIGNALS:
            # Refuse excess active/recent evidence explicitly; never drop a hard edge.
            raise BoundaryCapacityError('too many recent boundary signals')
        for key, signal in writes.items():
            transaction.set(
                records.document(key), {'content': encrypt(signal.model_dump_json(), uid), 'updated_at': now}
            )
        if writes:
            transaction.set(state_ref, {'entries': entries, 'updated_at': now})
        return len(writes)

    return write(client.transaction())


def windows(uid: str, *, firestore_client: Any = None) -> dict[str, dict]:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return {}
    client = firestore_client if firestore_client is not None else get_firestore_client()
    _, ref = _refs(uid, client)
    return (ref.get().to_dict() or {}).get('entries') or {}


def load(uid: str, keys: list[str], *, firestore_client: Any = None) -> list[BoundarySignal]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    records, _ = _refs(uid, client)
    result = []
    for key in keys[:MAX_SIGNALS]:
        data = records.document(key).get().to_dict() or {}
        if data.get('content'):
            result.append(BoundarySignal.model_validate_json(decrypt(data['content'], uid)))
    return result


def end_at(uid: str, keys: list[str], ended_at: datetime, *, firestore_client: Any = None) -> None:
    """A server quiet/window-close decision terminalizes the same evidence identity."""
    signals = load(uid, keys, firestore_client=firestore_client)
    ended = [s.model_copy(update={'ended_at': ended_at}) for s in signals if s.started_at <= ended_at]
    if ended:
        record(uid, ended, firestore_client=firestore_client)
