"""Durable ledger for once-only sync processing and metering (storage-port backed)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, cast

from database.store import get_document_store
from database.store.sentinels import ArrayUnion, DELETE

LEDGER_RETENTION_DAYS = 45
CLAIM_STALE_SECONDS = 2 * 24 * 60 * 60


def _store():
    return get_document_store()


def _ledger_path(uid: str, content_id: str) -> str:
    return f'users/{uid}/sync_content_ledger/{content_id}'


def _existing(snapshot: Any) -> Dict[str, Any]:
    """Neutral read → the document body, or an empty dict when it is absent."""
    return cast(Dict[str, Any], snapshot.to_dict() or {}) if snapshot.exists else {}


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
    existing: Optional[Dict[str, Any]] = None,
    clear_invalid_completion: bool = False,
) -> Dict[str, Any]:
    """Move a claim to processing without discarding valid retry checkpoints.

    Only emit ``DELETE`` for keys that already exist. Real backends no-op missing
    deletes, but hermetic fakes and sparse first-time claims should not depend on
    that quirk for every admission.
    """
    existing = existing or {}
    updates: Dict[str, Any] = {
        'status': 'processing',
        'job_id': job_id,
        'lane': lane,
        'updated_at': now,
        'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
    }
    for field in ('ledger_run_token', 'ledger_run_epoch'):
        if field in existing:
            updates[field] = DELETE
    if clear_invalid_completion:
        # A malformed historical completion is not a retry checkpoint: keeping
        # its result/markers could recreate the false-completed state we are
        # explicitly repairing. Normal retryable claims preserve both fields.
        for field in ('result', 'partial_result', 'processed_segment_ids'):
            if field in existing:
                updates[field] = DELETE
    return updates


def _claim_transaction(tx: Any, path: str, job_id: str, lane: str, now: datetime) -> Dict[str, Any]:
    existing = _existing(tx.get(path))
    if existing.get('status') == 'completed':
        result = existing.get('result')
        if is_valid_completed_sync_content_result(result):
            return {'outcome': 'completed', 'result': result}
        tx.set(
            path,
            _processing_claim_updates(job_id, lane, now, existing=existing, clear_invalid_completion=True),
            merge=True,
        )
        return {'outcome': 'owned'}
    if existing.get('job_id') == job_id:
        return {'outcome': 'owned'}

    if existing.get('status') == 'retryable':
        tx.set(
            path,
            _processing_claim_updates(job_id, lane, now, existing=existing),
            merge=True,
        )
        return {'outcome': 'owned'}

    updated_at = existing.get('updated_at')
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if (now - updated_at).total_seconds() < CLAIM_STALE_SECONDS:
            return {'outcome': 'busy'}

    tx.set(
        path,
        _processing_claim_updates(job_id, lane, now, existing=existing),
        merge=True,
    )
    return {'outcome': 'owned'}


def claim_sync_content(
    uid: str,
    content_id: str,
    job_id: str,
    lane: str,
) -> Dict[str, Any]:
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(lambda tx: _claim_transaction(tx, path, job_id, lane, now))


def _bind_run_token_transaction(
    tx: Any,
    path: str,
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
    existing = _existing(tx.get(path))
    if existing.get('status') == 'completed':
        result = existing.get('result')
        if is_valid_completed_sync_content_result(result):
            return SyncContentRunBinding(
                SyncContentRunBindingOutcome.COMPLETED,
                cast(Dict[str, Any], result),
            )
        if existing.get('job_id') != job_id:
            return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
        tx.set(
            path,
            {
                **_processing_claim_updates(
                    job_id,
                    str(existing.get('lane') or 'legacy'),
                    now,
                    existing=existing,
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
    tx.set(
        path,
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
) -> SyncContentRunBinding:
    """Transactionally bind a live Redis run token to its ledger claim."""
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _bind_run_token_transaction(tx, path, job_id, run_token, run_epoch, now)
    )


_SIDE_EFFECT_FIELDS = {
    'speech_ms': 'metered_at',
    'usage': 'usage_recorded_at',
    'dg_ms': 'dg_recorded_at',
}


def _side_effect_transaction(
    tx: Any,
    path: str,
    job_id: str,
    tag: str,
    value: int,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    existing = _existing(tx.get(path))
    timestamp_field = _SIDE_EFFECT_FIELDS[tag]
    if existing.get(timestamp_field) is not None:
        return False
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    tx.set(path, {timestamp_field: now, f'{tag}_value': value, 'updated_at': now}, merge=True)
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
) -> bool:
    if tag not in _SIDE_EFFECT_FIELDS:
        raise ValueError('unsupported sync content side-effect tag')
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _side_effect_transaction(tx, path, job_id, tag, value, now, run_token, run_epoch)
    )


def try_mark_sync_content_metered(
    uid: str,
    content_id: str,
    job_id: str,
    speech_ms: int,
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    return try_mark_sync_content_side_effect(
        uid,
        content_id,
        job_id,
        'speech_ms',
        speech_ms,
        run_token=run_token,
        run_epoch=run_epoch,
    )


def get_processed_sync_segment_ids(
    uid: str,
    content_id: str,
) -> set[str]:
    existing = _existing(_store().get(_ledger_path(uid, content_id)))
    values = existing.get('processed_segment_ids') or []
    return {value for value in values if isinstance(value, str)}


def get_sync_content_partial_result(
    uid: str,
    content_id: str,
) -> Dict[str, Any]:
    existing = _existing(_store().get(_ledger_path(uid, content_id)))
    partial = existing.get('partial_result')
    return cast(Dict[str, Any], partial) if isinstance(partial, dict) else {}


def _checkpoint_partial_result_transaction(
    tx: Any,
    path: str,
    job_id: str,
    partial_result: Dict[str, Any],
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Checkpoint only while the same ledger job still owns the content."""
    existing = _existing(tx.get(path))
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    tx.set(path, {'partial_result': partial_result, 'updated_at': now}, merge=True)
    return True


def checkpoint_sync_content_partial_result(
    uid: str,
    content_id: str,
    job_id: str,
    partial_result: Dict[str, Any],
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Atomically checkpoint a partial result for its current ledger owner."""
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _checkpoint_partial_result_transaction(
            tx, path, job_id, partial_result, now, run_token, run_epoch
        )
    )


def _processed_segment_transaction(
    tx: Any,
    path: str,
    job_id: str,
    segment_id: str,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    existing = _existing(tx.get(path))
    processed = existing.get('processed_segment_ids') or []
    if segment_id in processed:
        return False
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    tx.set(
        path,
        {'processed_segment_ids': ArrayUnion([segment_id]), 'updated_at': now},
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
) -> bool:
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _processed_segment_transaction(tx, path, job_id, segment_id, now, run_token, run_epoch)
    )


def _mark_completed_transaction(
    tx: Any,
    path: str,
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
    existing = _existing(tx.get(path))
    if not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    tx.set(
        path,
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
) -> bool:
    """Atomically publish a completed result for the matching ledger owner."""
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _mark_completed_transaction(tx, path, job_id, result, now, run_token, run_epoch)
    )


def _release_claim_transaction(
    tx: Any,
    path: str,
    job_id: str,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> bool:
    """Release only the claim that is still owned by ``job_id``.

    This must be transactional: a stale worker can otherwise read an old claim,
    let a newer upload acquire it, then overwrite that newer owner with a plain
    ``set``. The transaction re-reads on contention and makes the old release a
    no-op once ownership has changed.
    """
    existing = _existing(tx.get(path))
    if existing.get('status') == 'completed' or not _ledger_owner_matches(existing, job_id, run_token, run_epoch):
        return False
    tx.set(
        path,
        {
            'status': 'retryable',
            'job_id': DELETE,
            'ledger_run_token': DELETE,
            'ledger_run_epoch': DELETE,
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
) -> bool:
    """Atomically free the matching retry claim, returning whether it changed."""
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _release_claim_transaction(tx, path, job_id, now, run_token, run_epoch)
    )


def _release_claim_after_job_retired_transaction(
    tx: Any,
    path: str,
    job_id: str,
    now: datetime,
) -> bool:
    """Release a matching claim after Redis has proved its job is retired.

    This intentionally does not compare ``ledger_run_token``. It is only safe
    after a successful fenced Redis terminal transition, or after Redis has
    expired the job entirely. The exact job-id comparison remains transactional
    so it cannot erase a newer upload's claim.
    """
    existing = _existing(tx.get(path))
    if existing.get('status') != 'processing' or existing.get('job_id') != job_id:
        return False
    tx.set(
        path,
        {
            'status': 'retryable',
            'job_id': DELETE,
            'ledger_run_token': DELETE,
            'ledger_run_epoch': DELETE,
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
) -> bool:
    """Free an exact retired job claim without treating it as a live worker write."""
    path = _ledger_path(uid, content_id)
    now = datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _release_claim_after_job_retired_transaction(tx, path, job_id, now)
    )
