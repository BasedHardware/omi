"""Durable Firestore ledger for once-only sync processing and metering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, cast

from google.cloud import firestore

from config.sync_telemetry import SYNC_REPEAT_FAILURE_PERSISTENCE_FINGERPRINTS
from database._client import get_firestore_client
from database.sync_jobs import get_sync_job
from utils.sync import stage as sync_stage

LEDGER_RETENTION_DAYS = 45
# Terminal batch_v1 ledger state: every failed unit is held with no recovery
# path left; projected siblings are published, the held span is counted.
BATCH_PARTIAL_STATUS = 'partial'
CLAIM_STALE_SECONDS = 2 * 24 * 60 * 60
REPEAT_FAILURE_LIMIT = 3
REPEAT_FAILURE_WINDOW = timedelta(hours=24)
REPEAT_FAILURE_PAUSE = timedelta(hours=24)
_INVALID_AUDIO_FINGERPRINT = 'decode:sync_invalid_audio'


def _validated_failure_fingerprint(key: str | None, fingerprint: str | None) -> str | None:
    if key == 'invalid_audio':
        return _INVALID_AUDIO_FINGERPRINT
    if key == 'persistent_persistence' and fingerprint in SYNC_REPEAT_FAILURE_PERSISTENCE_FINGERPRINTS:
        return fingerprint
    return None


def _repeat_failure_capped(existing: Dict[str, Any], now: datetime) -> bool:
    # The pause is always bounded: once ``repeat_failure_pause_until`` passes,
    # the same content is admitted again without operator action.
    until = existing.get('repeat_failure_pause_until')
    return isinstance(until, datetime) and until > now


def _repeat_failure_updates(
    existing: Dict[str, Any], key: str | None, fingerprint: str | None, now: datetime
) -> Dict[str, Any]:
    fingerprint = _validated_failure_fingerprint(key, fingerprint)
    if fingerprint is None:
        return {
            'repeat_failure_key': firestore.DELETE_FIELD,
            'repeat_failure_fingerprint': firestore.DELETE_FIELD,
            'repeat_failure_count': firestore.DELETE_FIELD,
            'repeat_failure_first_at': firestore.DELETE_FIELD,
            'repeat_failure_pause_until': firestore.DELETE_FIELD,
        }
    first = existing.get('repeat_failure_first_at')
    same_window = (
        existing.get('repeat_failure_key') == key
        and existing.get('repeat_failure_fingerprint') == fingerprint
        and isinstance(first, datetime)
        and first <= now < first + REPEAT_FAILURE_WINDOW
    )
    count = min(REPEAT_FAILURE_LIMIT, int(existing.get('repeat_failure_count') or 0) + 1) if same_window else 1
    return {
        'repeat_failure_key': key,
        'repeat_failure_fingerprint': fingerprint,
        'repeat_failure_count': count,
        'repeat_failure_first_at': first if same_window else now,
        'repeat_failure_pause_until': (
            now + REPEAT_FAILURE_PAUSE if count >= REPEAT_FAILURE_LIMIT else firestore.DELETE_FIELD
        ),
    }


class SyncContentRunBindingOutcome(str, Enum):
    """Ownership result when a Redis run token enters the durable ledger."""

    BOUND = 'bound'
    COMPLETED = 'completed'
    HELD = 'held'
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

    @property
    def held(self) -> bool:
        return self.outcome is SyncContentRunBindingOutcome.HELD


def _ledger_ref(client: Any, uid: str, content_id: str) -> Any:
    collection = sync_stage.collection_name('sync_content_ledger')
    return client.collection('users').document(uid).collection(collection).document(content_id)


def _ledger_owner_matches(
    existing: Dict[str, Any],
    job_id: str,
    run_token: str | None,
    run_epoch: int | None = None,
    *,
    allow_batch: bool = False,
) -> bool:
    """Return whether a worker still owns this ledger mutation boundary.

    Tokenless callers are admission/recovery exceptions only. They may mutate a
    claim that has never been bound, but can never overwrite a live worker that
    has recorded a run token.
    """
    if existing.get('dispatch_protocol') == 'batch_v1' and not allow_batch:
        return False
    # A batch partial is terminal for the client but still owned by its batch
    # job: recovery, operator redrive and the ordinary completion upgrade it.
    owned = {'processing', BATCH_PARTIAL_STATUS} if allow_batch else {'processing'}
    if existing.get('status') not in owned or existing.get('job_id') != job_id:
        return False
    bound_token = existing.get('ledger_run_token')
    bound_epoch = existing.get('ledger_run_epoch')
    if run_token is None:
        return bound_token is None and bound_epoch is None
    return bound_token == run_token and bound_epoch == run_epoch


def sync_content_reference(client: Any, uid: str, content_id: str) -> Any:
    """Share the canonical owner-scoped reference with a custody transfer."""
    return _ledger_ref(client, uid, content_id)


def sync_content_owner_matches(
    existing: Dict[str, Any], job_id: str, run_token: str | None, run_epoch: int | None = None
) -> bool:
    """Custody transfer uses the same token/epoch fence as normal completion."""
    return _ledger_owner_matches(existing, job_id, run_token, run_epoch)


def is_valid_completed_sync_content_result(result: Any) -> bool:
    """A ledger completion may converge Redis only for an all-success result."""
    if not isinstance(result, dict):
        return False
    if result.get('held_audio') is True:
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


def is_valid_partial_sync_content_result(result: Any) -> bool:
    """A batch partial: every failed segment is a held unit, none is an error.

    Never an all-success result, so no legacy path converges Redis from it.
    """
    if not isinstance(result, dict) or result.get('outcome') != 'partial' or result.get('held_audio') is True:
        return False
    failed, held, total = result.get('failed_segments'), result.get('held_segments'), result.get('total_segments')
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (failed, held, total)):
        return False
    assert isinstance(failed, int) and isinstance(held, int) and isinstance(total, int)
    return (
        0 < held == failed <= total
        and result.get('errors') == []
        and all(isinstance(result.get(key), list) for key in ('new_memories', 'updated_memories'))
    )


def batch_ledger_owes_held_units(ledger: Dict[str, Any]) -> bool:
    """Operator redrive precondition: nothing is charged yet, or a partial still counts held units.

    A partial charged only its projected siblings, so a reviewed redrive of a
    held unit stays allowed; its ordinary completion charges the remainder.
    """
    if ledger.get('status') == BATCH_PARTIAL_STATUS:
        return is_valid_partial_sync_content_result(ledger.get('result'))
    return ledger.get('status') != 'completed' and ledger.get('usage_committed_at') is None


def is_valid_held_sync_content_result(result: Any) -> bool:
    if not isinstance(result, dict) or result.get('held_audio') is not True:
        return False
    return is_valid_completed_sync_content_result({**result, 'held_audio': False})


def _processing_claim_updates(
    job_id: str,
    lane: str,
    now: datetime,
    *,
    existing: Optional[Dict[str, Any]] = None,
    clear_invalid_completion: bool = False,
) -> Dict[str, Any]:
    """Move a claim to processing without discarding valid retry checkpoints.

    Only emit ``DELETE_FIELD`` for keys that already exist. Real Firestore no-ops
    missing deletes, but hermetic fakes and sparse first-time claims should not
    depend on that quirk for every admission.
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
            updates[field] = firestore.DELETE_FIELD
    if clear_invalid_completion:
        # A malformed historical completion is not a retry checkpoint: keeping
        # its result/markers could recreate the false-completed state we are
        # explicitly repairing. Normal retryable claims preserve both fields.
        for field in ('result', 'partial_result', 'processed_segment_ids'):
            if field in existing:
                updates[field] = firestore.DELETE_FIELD
    return updates


@firestore.transactional
def _claim_transaction(
    transaction: Any, ref: Any, job_id: str, lane: str, now: datetime, missing_owner: Optional[str] = None
) -> Dict[str, Any]:
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('dispatch_protocol') == 'stt_cap_hold_v1' and existing.get('status') == 'held':
        if is_valid_held_sync_content_result(existing.get('result')):
            return {'outcome': 'held', 'result': existing['result'], 'job_id': existing.get('job_id')}
        return {'outcome': 'busy', 'job_id': existing.get('job_id')}
    if existing.get('dispatch_protocol') == 'batch_v1':
        result = existing.get('result')
        if existing.get('status') == 'completed' and is_valid_completed_sync_content_result(result):
            return {'outcome': 'completed', 'result': result}
        return {
            'outcome': 'busy',
            'job_id': existing.get('job_id'),
            'dispatch_protocol': 'batch_v1',
            'batch_pipeline': existing.get('batch_pipeline'),
        }
    if existing.get('status') == 'completed':
        result = existing.get('result')
        if is_valid_completed_sync_content_result(result):
            return {'outcome': 'completed', 'result': result}
        transaction.set(
            ref,
            _processing_claim_updates(job_id, lane, now, existing=existing, clear_invalid_completion=True),
            merge=True,
        )
        return {'outcome': 'owned'}
    if _repeat_failure_capped(existing, now):
        pause_until = cast(datetime, existing['repeat_failure_pause_until'])
        return {
            'outcome': 'capped',
            'failure_key': existing.get('repeat_failure_key'),
            'retry_after': max(1, min(86400, int((pause_until - now).total_seconds()) + 1)),
        }
    if existing.get('job_id') == job_id:
        return {'outcome': 'owned'}

    if existing.get('status') == 'retryable':
        transaction.set(
            ref,
            _processing_claim_updates(job_id, lane, now, existing=existing),
            merge=True,
        )
        return {'outcome': 'owned'}

    updated_at = existing.get('updated_at')
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if (now - updated_at).total_seconds() < CLAIM_STALE_SECONDS and not (
            missing_owner is not None and existing.get('job_id') == missing_owner
        ):
            return {'outcome': 'busy', 'job_id': existing.get('job_id')}

    transaction.set(
        ref,
        _processing_claim_updates(job_id, lane, now, existing=existing),
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
    now = datetime.now(timezone.utc)
    claim = _claim_transaction(client.transaction(), ref, job_id, lane, now)
    owner = claim.get('job_id')
    if (
        claim.get('outcome') == 'busy'
        and claim.get('dispatch_protocol') != 'batch_v1'
        and owner
        and get_sync_job(owner) is None
    ):
        # Redis expires at 24h, before the 48h ledger claim. Re-read the ledger
        # transactionally: only replace the owner whose absence we observed.
        # A concurrent completion/new owner wins; processing checkpoints survive
        # and old worker run tokens are invalidated by the ordinary claim update.
        claim = _claim_transaction(client.transaction(), ref, job_id, lane, now, missing_owner=owner)
    return claim


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
    if existing.get('dispatch_protocol') == 'stt_cap_hold_v1' and existing.get('status') == 'held':
        if is_valid_held_sync_content_result(existing.get('result')):
            return SyncContentRunBinding(SyncContentRunBindingOutcome.HELD, existing['result'])
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
    if existing.get('dispatch_protocol') == 'batch_v1':
        result = existing.get('result')
        if existing.get('status') == 'completed' and is_valid_completed_sync_content_result(result):
            return SyncContentRunBinding(SyncContentRunBindingOutcome.COMPLETED, result)
        return SyncContentRunBinding(SyncContentRunBindingOutcome.LOST)
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
    staging_custody: Dict[str, Any] | None = None,
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
            **({'staging_custody': staging_custody} if staging_custody else {}),
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
    staging_custody: Dict[str, Any] | None = None,
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
        staging_custody,
    )


@firestore.transactional
def _release_claim_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    now: datetime,
    run_token: str | None = None,
    run_epoch: int | None = None,
    failure_key: str | None = None,
    failure_fingerprint: str | None = None,
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
            **_repeat_failure_updates(existing, failure_key, failure_fingerprint, now),
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
    failure_key: str | None = None,
    failure_fingerprint: str | None = None,
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
        failure_key,
        failure_fingerprint,
    )


@firestore.transactional
def _release_claim_after_job_retired_transaction(
    transaction: Any,
    ref: Any,
    job_id: str,
    now: datetime,
    failure_key: str | None = None,
    failure_fingerprint: str | None = None,
) -> bool:
    """Release a matching claim after Redis has proved its job is retired.

    This intentionally does not compare ``ledger_run_token``. It is only safe
    after a successful fenced Redis terminal transition, or after Redis has
    expired the job entirely. The exact job-id comparison remains transactional
    so it cannot erase a newer upload's claim.
    """
    snapshot = ref.get(transaction=transaction)
    existing = cast(Dict[str, Any], snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
    if existing.get('dispatch_protocol') == 'batch_v1':
        return False
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
            **_repeat_failure_updates(existing, failure_key, failure_fingerprint, now),
        },
        merge=True,
    )
    return True


def release_sync_content_claim_after_job_retired(
    uid: str,
    content_id: str,
    job_id: str,
    *,
    failure_key: str | None = None,
    failure_fingerprint: str | None = None,
    firestore_client: Any = None,
) -> bool:
    """Free an exact retired job claim without treating it as a live worker write."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _release_claim_after_job_retired_transaction(
        client.transaction(),
        _ledger_ref(client, uid, content_id),
        job_id,
        datetime.now(timezone.utc),
        failure_key,
        failure_fingerprint,
    )


def complete_batch_projection_in_transaction(
    transaction: Any,
    ref: Any,
    existing: Dict[str, Any],
    job_id: str,
    result: Dict[str, Any],
    now: datetime,
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> None:
    """Write-only completion after the caller reads all projected sibling receipts.

    Kept here beside legacy completion validation/ownership; the batch consumer
    supplies a snapshot from this same transaction, before assignment writes.
    """
    if (
        existing.get('dispatch_protocol') != 'batch_v1'
        or not is_valid_completed_sync_content_result(result)
        or not _ledger_owner_matches(
            existing,
            job_id,
            run_token,
            run_epoch,
            allow_batch=True,
        )
    ):
        raise RuntimeError('batch projection lost content ledger ownership')
    transaction.update(
        ref,
        {
            'status': 'completed',
            'result': result,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
    )


def complete_batch_partial_in_transaction(
    transaction: Any,
    ref: Any,
    existing: Dict[str, Any],
    job_id: str,
    result: Dict[str, Any],
    now: datetime,
    *,
    run_token: str | None = None,
    run_epoch: int | None = None,
) -> None:
    """Write-only partial completion; the batch owner keeps the row for an upgrade."""
    if (
        existing.get('dispatch_protocol') != 'batch_v1'
        or not is_valid_partial_sync_content_result(result)
        or not _ledger_owner_matches(existing, job_id, run_token, run_epoch, allow_batch=True)
    ):
        raise RuntimeError('batch partial lost content ledger ownership')
    transaction.update(
        ref,
        {
            'status': BATCH_PARTIAL_STATUS,
            'result': result,
            'updated_at': now,
            'expires_at': now + timedelta(days=LEDGER_RETENTION_DAYS),
        },
    )


def sync_content_ledger_ref(client: Any, uid: str, content_id: str) -> Any:
    """Shared transaction address for atomic batch admission/projection."""
    return _ledger_ref(client, uid, content_id)


def batch_projection_ledger_owner_matches(
    existing: Dict[str, Any],
    job_id: str,
    run_token: str | None,
    run_epoch: int | None,
) -> bool:
    """Explicit batch owner check; ordinary legacy mutations never use it."""
    return _ledger_owner_matches(existing, job_id, run_token, run_epoch, allow_batch=True)
