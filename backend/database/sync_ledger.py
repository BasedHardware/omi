"""Durable Firestore ledger for once-only sync processing and metering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, cast

from google.cloud import firestore

from database._client import get_firestore_client

LEDGER_RETENTION_DAYS = 45
CLAIM_STALE_SECONDS = 2 * 24 * 60 * 60


class SyncContentRunBindingOutcome(str, Enum):
    """Ownership result when a Redis run token enters the durable ledger."""

    BOUND = 'bound'
    COMPLETED = 'completed'
    LOST = 'lost'


@dataclass(frozen=True)
class SyncContentRunBinding:
    """A ledger run-token bind result, optionally carrying durable completion."""

    outcome: SyncContentRunBindingOutcome
    result: Optional[Dict[str, Any]] = None

    @property
    def bound(self) -> bool:
        return self.outcome is SyncContentRunBindingOutcome.BOUND

    @property
    def completed(self) -> bool:
        return self.outcome is SyncContentRunBindingOutcome.COMPLETED


def _ledger_ref(client: Any, uid: str, content_id: str) -> Any:
    return client.collection('users').document(uid).collection('sync_content_ledger').document(content_id)


def _ledger_owner_matches(
    existing: Dict[str, Any],
    job_id: str,
    run_token: str | None,
    run_epoch: int | None = None,
) -> bool:
    """Return whether a worker still owns this ledger mutation boundary.

    Tokenless callers are admission/recovery exceptions only. They may mutate a
    claim that has never been bound, but can never overwrite a live worker that
    has recorded a run token.
    """
    if existing.get('status') != 'processing' or existing.get('job_id') != job_id:
        return False
    bound_token = existing.get('ledger_run_token')
    bound_epoch = existing.get('ledger_run_epoch')
    if run_token is None:
        return bound_token is None and bound_epoch is None
    return bound_token == run_token and bound_epoch == run_epoch


def is_valid_completed_sync_content_result(result: Any) -> bool:
    """A ledger completion may converge Redis only for an all-success result."""
    if not isinstance(result, dict):
        return False
    failed_segments = result.get('failed_segments')
    total_segments = result.get('total_segments')
    errors = result.get('errors')
    base_valid = (
        isinstance(failed_segments, int)
        and not isinstance(failed_segments, bool)
        and failed_segments == 0
        and isinstance(total_segments, int)
        and not isinstance(total_segments, bool)
        and total_segments >= 0
        and failed_segments <= total_segments
        and isinstance(errors, list)
        and not errors
    )
    if not base_valid:
        return False
    if not isinstance(total_segments, int):
        return False
    outcome = result.get('outcome')
    if outcome is None:
        # Pre-outcome ledgers can prove a nonzero all-success batch, but their
        # zero-segment records predate the silence-vs-decode-failure contract.
        return total_segments > 0
    return outcome in {'success', 'expected_silence'}


def _processing_claim_updates(
    job_id: str,
    lane: str,
    now: datetime,
    *,
    clear_invalid_completion: bool = False,
) -> Dict[str, Any]:
    """Move a claim to processing without discarding valid retry checkpoints."""
    updates: Dict[str, Any] = {
        'status': 'processing',
        'job_id': job_id,
        'ledger_run_token': firestore.DELETE_FIELD,
        'ledger_run_epoch': firestore.DELETE_FIELD,
        'lane': lane,
        'updated_at': now,
        'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
    }
    if clear_invalid_completion:
        # A malformed historical completion is not a retry checkpoint: keeping
        # its result/markers could recreate the false-completed state we are
        # explicitly repairing. Normal retryable claims preserve both fields.
        updates.update(
            {
                'result': firestore.DELETE_FIELD,
                'partial_result': firestore.DELETE_FIELD,
                'processed_segment_ids': firestore.DELETE_FIELD,
            }
        )
    return updates


@firestore.transactional
def _claim_transaction(transaction: Any, ref: Any, job_id: str, lane: str, now: datetime) -> Dict[str, Any]:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('status') == 'completed':
        result = existing.get('result')
        if is_valid_completed_sync_content_result(result):
            return {'outcome': 'completed', 'result': result}
        transaction.set(ref, _processing_claim_updates(job_id, lane, now, clear_invalid_completion=True), merge=True)
        return {'outcome': 'owned'}
    if existing.get('job_id') == job_id:
        return {'outcome': 'owned'}

    if existing.get('status') == 'retryable':
        transaction.set(
            ref,
            _processing_claim_updates(job_id, lane, now),
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
        _processing_claim_updates(job_id, lane, now),
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


@firestore.transactional
def _bind_run_token_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    run_token: str,
    run_epoch: int,
    now: datetime,
) -> SyncContentRunBinding:
    """Bind one Redis lease token or expose a durable completed result.

    A replacement worker uses a fresh token for the same job id. Once it binds,
    every mutation from the old token rejects. A previously committed success
    is returned rather than overwritten so the replacement can converge its
    Redis job state without re-running provider work.
    """
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('status') == 'completed':
        result = existing.get('result')
        if is_valid_completed_sync_content_result(result):
            return SyncContentRunBinding(
                SyncContentRunBindingOutcome.COMPLETED,
                cast(Dict[str, Any], result),
            )
        if existing.get('job_id') != job_id:
            return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
        transaction.set(
            ref,
            {
                **_processing_claim_updates(
                    job_id,
                    str(existing.get('lane') or 'legacy'),
                    now,
                    clear_invalid_completion=True,
                ),
                'ledger_run_token': run_token,
                'ledger_run_epoch': run_epoch,
            },
            merge=True,
        )
        return SyncContentRunBinding(SyncContentRunBindingOutcome.BOUND)
    if existing.get('status') != 'processing' or existing.get('job_id') != job_id:
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
    stored_epoch = existing.get('ledger_run_epoch')
    stored_token = existing.get('ledger_run_token')
    if stored_epoch is None:
        # Legacy in-flight claims have no durable lease generation. The first
        # epoch-aware owner adopts them; any later epoch supersedes it.
        pass
    elif not isinstance(stored_epoch, int) or isinstance(stored_epoch, bool):
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
    elif stored_epoch > run_epoch:
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
    elif stored_epoch == run_epoch:
        if stored_token == run_token:
            return SyncContentRunBinding(SyncContentRunBindingOutcome.BOUND)
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
    transaction.set(
        ref,
        {'ledger_run_token': run_token, 'ledger_run_epoch': run_epoch, 'updated_at': now},
        merge=True,
    )
    return SyncContentRunBinding(SyncContentRunBindingOutcome.BOUND)


def bind_sync_content_run_token(
    uid: str,
    content_id: str,
    job_id: str,
    run_token: str,
    run_epoch: int,
    *,
    firestore_client: Any = None,
) -> SyncContentRunBinding:
    """Transactionally bind a live Redis run token to its ledger claim."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _bind_run_token_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        run_token,
        run_epoch,
        datetime.now(timezone.utc),
    )


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
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    timestamp_field = _SIDE_EFFECT_FIELDS[tag]
    if existing.get(timestamp_field) is not None:
        return False
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
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
    run_token: str | None = None,
    run_epoch: int | None = None,
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
        run_token,
        run_epoch,
    )


def try_mark_sync_content_metered(
    uid: str,
    content_id: str,
    job_id: str,
    speech_ms: int,
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
    firestore_client: Any = None,
) -> bool:
    return try_mark_sync_content_side_effect(
        uid,
        content_id,
        job_id,
        'speech_ms',
        speech_ms,
        run_token=run_token,
        run_epoch=run_epoch,
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


@firestore.transactional
def _checkpoint_partial_result_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    partial_result: Dict[str, Any],
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Checkpoint only while the same ledger job still owns the content."""
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    transaction.set(ref, {'partial_result': partial_result, 'updated_at': now}, merge=True)
    return True


def checkpoint_sync_content_partial_result(
    uid: str,
    content_id: str,
    job_id: str,
    partial_result: Dict[str, Any],
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
    firestore_client: Any = None,
) -> bool:
    """Atomically checkpoint a partial result for its current ledger owner."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    return _checkpoint_partial_result_transaction(
        client.transaction(),
        ref,
        job_id,
        partial_result,
        datetime.now(timezone.utc),
        run_token,
        run_epoch,
    )


@firestore.transactional
def _processed_segment_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    segment_id: str,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    processed = existing.get('processed_segment_ids') or []
    if segment_id in processed:
        return False
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
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
    run_token: str | None = None,
    run_epoch: int | None = None,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _processed_segment_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        segment_id,
        datetime.now(timezone.utc),
        run_token,
        run_epoch,
    )


@firestore.transactional
def _mark_completed_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    result: Dict[str, Any],
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Publish completion only while ``job_id`` still owns the ledger entry."""
    # The caller-side pipeline checks this too, but completion is a durable
    # cross-worker proof that a replacement owner may converge. Keep the
    # validation at the transaction boundary so an alternate caller cannot
    # publish a malformed/partial result that later looks terminal.
    if not is_valid_completed_sync_content_result(result):
        return False
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    transaction.set(
        ref,
        {
            'status': 'completed',
            'result': result,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
        merge=True,
    )
    return True


def mark_sync_content_completed(
    uid: str,
    content_id: str,
    job_id: str,
    result: Dict[str, Any],
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
    firestore_client: Any = None,
) -> bool:
    """Atomically publish a completed result for the matching ledger owner."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ledger_ref(client, uid, content_id)
    now = datetime.now(timezone.utc)
    return _mark_completed_transaction(
        client.transaction(),
        ref,
        job_id,
        result,
        now,
        run_token,
        run_epoch,
    )


@firestore.transactional
def _release_claim_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Release only the claim that is still owned by ``job_id``.

    This must be transactional: a stale worker can otherwise read an old claim,
    let a newer upload acquire it, then overwrite that newer owner with a plain
    Firestore ``set``. The transaction re-reads on contention and makes the
    old release a no-op once ownership has changed.
    """
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('status') == 'completed' or not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    transaction.set(
        ref,
        {
            'status': 'retryable',
            'job_id': firestore.DELETE_FIELD,
            'ledger_run_token': firestore.DELETE_FIELD,
            'ledger_run_epoch': firestore.DELETE_FIELD,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
        merge=True,
    )
    return True


def release_sync_content_claim(
    uid: str,
    content_id: str,
    job_id: str,
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
    firestore_client: Any = None,
) -> bool:
    """Atomically free the matching retry claim, returning whether it changed."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _release_claim_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        datetime.now(timezone.utc),
        run_token,
        run_epoch,
    )


@firestore.transactional
def _release_claim_after_job_retired_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    now: datetime,
) -> bool:
    """Release a matching claim after Redis has proved its job is retired.

    This intentionally does not compare ``ledger_run_token``. It is only safe
    after a successful fenced Redis terminal transition, or after Redis has
    expired the job entirely. The exact job-id comparison remains transactional
    so it cannot erase a newer upload's claim.
    """
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('status') != 'processing' or existing.get('job_id') != job_id:
        return False
    transaction.set(
        ref,
        {
            'status': 'retryable',
            'job_id': firestore.DELETE_FIELD,
            'ledger_run_token': firestore.DELETE_FIELD,
            'ledger_run_epoch': firestore.DELETE_FIELD,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
        merge=True,
    )
    return True


def release_sync_content_claim_after_job_retired(
    uid: str,
    content_id: str,
    job_id: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Free an exact retired job claim without treating it as a live worker write."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _release_claim_after_job_retired_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        datetime.now(timezone.utc),
    )
