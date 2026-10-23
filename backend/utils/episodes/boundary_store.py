"""Durable, idempotent meeting signals and a bounded edge index (document gets only).

Payloads are encrypted; the index contains opaque keys and timestamps only.
The user's subtree is owned by the existing account erasure path. No new query
or index is needed. Historical payloads retain idempotency after index eviction.
"""

from __future__ import annotations

import hashlib
from threading import RLock
from cachetools import TTLCache
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from config.occasion_conversations import EPISODE_BOUNDARIES_MODE_ENV
from config.refactor_modes import shadow_or_serve, serving_for, shadow_sampled
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from models.boundary_evidence import BoundarySignal
from utils.encryption import encrypt, decrypt

MAX_SIGNALS = 128
RETENTION = timedelta(days=7)
SHADOW_SAMPLE_PERCENT = 5.0
# Shadow observations may lag one calendar-poll period; serving always reads fresh.
_shadow_windows: TTLCache = TTLCache(maxsize=1024, ttl=60)
_seen_contexts: TTLCache = TTLCache(maxsize=2048, ttl=60)
_cache_lock = RLock()


class BoundaryCapacityError(ValueError):
    pass


def signal_id(signal: BoundarySignal) -> str:
    identity = signal.external_id or f'{signal.started_at.isoformat()}:{signal.source_device or ""}'
    return hashlib.sha256(f'{signal.kind}\0{identity}'.encode()).hexdigest()


def _refs(uid: str, client: Any):
    user = client.collection('users').document(uid)
    return user.collection('capture_boundary_signals'), user.collection('capture_boundary_state').document('v1')


def record(
    uid: str, signals: list[BoundarySignal], *, firestore_client: Any = None, allow_reschedule: bool = True
) -> int:
    if not shadow_sampled(EPISODE_BOUNDARIES_MODE_ENV, uid, SHADOW_SAMPLE_PERCENT):
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
                moved = old.started_at != signal.started_at
                if moved and signal.kind == 'calendar_event' and not allow_reschedule:
                    continue  # A saved conversation context cannot rewind current calendar truth.
                if moved and signal.kind != 'calendar_event':
                    raise ValueError('boundary start is immutable for an external identity')
                # A rescheduled calendar identity replaces its old window. Within
                # one start, a delayed retry still cannot reopen a closed edge.
                if not moved and old.ended_at is not None:
                    signal = signal.model_copy(update={'ended_at': min(old.ended_at, signal.ended_at or old.ended_at)})
                if old == signal:
                    continue
            writes[key] = signal
            entries[key] = {'started_at': signal.started_at, 'ended_at': signal.ended_at}
        entries = {k: v for k, v in entries.items() if v.get('ended_at') is None or v['ended_at'] >= now - RETENTION}
        if len(entries) > MAX_SIGNALS:
            # Payloads remain durable after index eviction. The occasion/merge
            # horizon is three hours; preserve every active or recent edge.
            oldest = sorted(
                (
                    key
                    for key, window in entries.items()
                    if window.get('ended_at') is not None and window['ended_at'] < now - timedelta(hours=3)
                ),
                key=lambda key: entries[key]['ended_at'],
            )
            for key in oldest[: max(0, len(entries) - MAX_SIGNALS)]:
                del entries[key]
        if len(entries) > MAX_SIGNALS:
            raise BoundaryCapacityError('too many active or recent boundary signals')
        for key, signal in writes.items():
            transaction.set(
                records.document(key), {'content': encrypt(signal.model_dump_json(), uid), 'updated_at': now}
            )
        if writes:
            transaction.set(state_ref, {'entries': entries, 'updated_at': now})
        return len(writes)

    written = write(client.transaction())
    if written:
        with _cache_lock:
            _shadow_windows.pop((uid, id(client)), None)
    return written


def record_context(
    uid: str, signal: BoundarySignal, *, firestore_client: Any = None, allow_reschedule: bool = False
) -> None:
    """In shadow, ingest an unchanged row context at most once per minute."""
    if not shadow_sampled(EPISODE_BOUNDARIES_MODE_ENV, uid, SHADOW_SAMPLE_PERCENT):
        return
    client = firestore_client if firestore_client is not None else get_firestore_client()
    shadow = not serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid)
    key = (uid, id(client), hashlib.sha256(signal.model_dump_json().encode()).hexdigest(), allow_reschedule)
    if shadow:
        with _cache_lock:
            if _seen_contexts.get(key) is client:
                return
    record(uid, [signal], firestore_client=client, allow_reschedule=allow_reschedule)
    if shadow:
        with _cache_lock:
            # Holding the bounded client reference prevents object-id reuse.
            _seen_contexts[key] = client


def windows(uid: str, *, firestore_client: Any = None) -> dict[str, dict]:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return {}
    client = firestore_client if firestore_client is not None else get_firestore_client()
    key = (uid, id(client))
    shadow = not serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid)
    if shadow:
        with _cache_lock:
            cached = _shadow_windows.get(key)
            if cached is not None and cached[0] is client:
                return {k: dict(v) for k, v in cached[1].items()}
    _, ref = _refs(uid, client)
    result = (ref.get().to_dict() or {}).get('entries') or {}
    if shadow:
        with _cache_lock:
            _shadow_windows[key] = (client, result)
    return {k: dict(v) for k, v in result.items()}


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
