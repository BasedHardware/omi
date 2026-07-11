"""Durable Firestore ledger for once-only sync processing and metering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, cast

from google.cloud import firestore

from database._client import get_firestore_client

LEDGER_RETENTION_DAYS = 45
CLAIM_STALE_SECONDS = 2 * 24 * 60 * 60


def _ledger_ref(client: Any, uid: str, content_id: str) -> Any:
    return client.collection('users').document(uid).collection('sync_content_ledger').document(content_id)


@firestore.transactional
def _claim_transaction(transaction: Any, ref: Any, job_id: str, lane: str, now: datetime) -> Dict[str, Any]:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('status') == 'completed':
        return {'outcome': 'completed', 'result': existing.get('result') or {}}
    if existing.get('job_id') == job_id:
        return {'outcome': 'owned'}

    if existing.get('status') == 'retryable':
        transaction.set(
            ref,
            {
                'status': 'processing',
                'job_id': job_id,
                'lane': lane,
                'updated_at': now,
                'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
            },
            merge=True,
        )
        return {'outcome': 'owned'}

    updated_at = existing.get('updated_at')
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if (now - updated_at).total_seconds() < CLAIM_STALE_SECONDS:
            return {'outcome': 'busy'}

    transaction.set(
        ref,
        {
            'status': 'processing',
            'job_id': job_id,
            'lane': lane,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
        merge=True,
    )
    return {'outcome': 'owned'}


def claim_sync_content(
    uid: str,
    content_id: str,
    job_id: str,
    lane: str,
    *,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    return _claim_transaction(client.transaction(), ref, job_id, lane, datetime.now(timezone.utc))


_SIDE_EFFECT_FIELDS = {
    'speech_ms': 'metered_at',
    'usage': 'usage_recorded_at',
    'dg_ms': 'dg_recorded_at',
}


@firestore.transactional
def _side_effect_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    tag: str,
    value: int,
    now: datetime,
) -> bool:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    timestamp_field = _SIDE_EFFECT_FIELDS[tag]
    if existing.get(timestamp_field) is not None:
        return False
    if existing.get('job_id') != job_id:
        return False
    transaction.set(ref, {timestamp_field: now, f'{tag}_value': value, 'updated_at': now}, merge=True)
    return True


def try_mark_sync_content_side_effect(
    uid: str,
    content_id: str,
    job_id: str,
    tag: str,
    value: int,
    *,
    firestore_client: Any = None,
) -> bool:
    if tag not in _SIDE_EFFECT_FIELDS:
        raise ValueError('unsupported sync content side-effect tag')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _side_effect_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        tag,
        value,
        datetime.now(timezone.utc),
    )


def try_mark_sync_content_metered(
    uid: str,
    content_id: str,
    job_id: str,
    speech_ms: int,
    *,
    firestore_client: Any = None,
) -> bool:
    return try_mark_sync_content_side_effect(
        uid,
        content_id,
        job_id,
        'speech_ms',
        speech_ms,
        firestore_client=firestore_client,
    )


def get_processed_sync_segment_ids(
    uid: str,
    content_id: str,
    *,
    firestore_client: Any = None,
) -> set[str]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = _ledger_ref(client, uid, content_id).get()
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    values = existing.get('processed_segment_ids') or []
    return {value for value in values if isinstance(value, str)}


def get_sync_content_partial_result(
    uid: str,
    content_id: str,
    *,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = _ledger_ref(client, uid, content_id).get()
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    partial = existing.get('partial_result')
    return cast(Dict[str, Any], partial) if isinstance(partial, dict) else {}


def checkpoint_sync_content_partial_result(
    uid: str,
    content_id: str,
    job_id: str,
    partial_result: Dict[str, Any],
    *,
    firestore_client: Any = None,
) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    snapshot = ref.get()
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('job_id') != job_id:
        return
    ref.set(
        {'partial_result': partial_result, 'updated_at': datetime.now(timezone.utc)},
        merge=True,
    )


@firestore.transactional
def _processed_segment_transaction(transaction: Any, ref: Any, job_id: str, segment_id: str, now: datetime) -> bool:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    processed = existing.get('processed_segment_ids') or []
    if segment_id in processed:
        return False
    if existing.get('job_id') != job_id:
        return False
    transaction.set(
        ref,
        {'processed_segment_ids': firestore.ArrayUnion([segment_id]), 'updated_at': now},
        merge=True,
    )
    return True


def add_processed_sync_segment_id(
    uid: str,
    content_id: str,
    job_id: str,
    segment_id: str,
    *,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _processed_segment_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        segment_id,
        datetime.now(timezone.utc),
    )


def mark_sync_content_completed(
    uid: str,
    content_id: str,
    job_id: str,
    result: Dict[str, Any],
    *,
    firestore_client: Any = None,
) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    snapshot = ref.get()
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('job_id') != job_id:
        return
    now = datetime.now(timezone.utc)
    ref.set(
        {
            'status': 'completed',
            'result': result,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
        merge=True,
    )


def release_sync_content_claim(
    uid: str,
    content_id: str,
    job_id: str,
    *,
    firestore_client: Any = None,
) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    snapshot = ref.get()
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('job_id') == job_id and existing.get('status') != 'completed':
        now = datetime.now(timezone.utc)
        ref.set(
            {
                'status': 'retryable',
                'job_id': firestore.DELETE_FIELD,
                'updated_at': now,
                'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
            },
            merge=True,
        )
