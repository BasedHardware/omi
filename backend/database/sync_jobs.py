"""
Redis-backed sync job storage for v2 async sync-local-files.

Jobs are ephemeral — they exist only long enough for the app to reconcile
results. Redis is the right store: no Firestore costs, automatic TTL cleanup.

Key format: sync_job:{job_id}
TTL: 24 hours (refreshed on each update)

The TTL governs how long a finished job's result stays queryable. The client
uploads audio, marks the recording "uploaded", and reconciles it against this
job_id later. A 24h window covers the common "open the app about once a day"
pattern, so the app can learn a job already succeeded and just fetch the
conversation ids instead of re-uploading and re-transcribing the audio.

This is an efficiency window, NOT a correctness mechanism: the client keeps
the local audio file until the job is confirmed synced, so an expired/unknown
job always falls back to a safe re-upload (server dedups by segment timestamp).

Do NOT conflate with STALE_THRESHOLD_SECONDS below — that is a separate
in-flight processing-liveness guard and must stay short.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set, cast

from database.redis_db import r

logger = logging.getLogger(__name__)

JOB_KEY_PREFIX = 'sync_job:'
JOB_TTL_SECONDS = 86400  # 24 hours — reconcile window (see module docstring)
STALE_THRESHOLD_SECONDS = 600  # 10 minutes — if processing exceeds this, treat as failed

TERMINAL_STATUSES = ('completed', 'partial_failure', 'failed')
_SYNC_JOB_OUTCOMES = (
    'success',
    'expected_silence',
    'empty_unexpected',
    'timeout',
    'upstream_error',
    'config_error',
    'invalid_input',
)
_SYNC_LANES = ('fresh', 'backfill')
_SYNC_PROVIDERS = ('deepgram', 'modulate', 'parakeet')
_SYNC_MODELS = ('nova-3', 'velma-2', 'parakeet')
_SYNC_DISPATCH_MODES = ('inline', 'cloud_tasks')
SYNC_LEDGER_FENCE_MODE_ENV = 'SYNC_LEDGER_FENCE_MODE'

RUN_LOCK_KEY_PREFIX = 'sync_job_lock:'
RUN_LOCK_EPOCH_KEY_PREFIX = 'sync_job_lock_epoch:'
# Must stay above the handler's request timeout (HTTP_SYNC_JOBS_RUN_TIMEOUT,
# 1500s) so the lock can never expire while a run is still executing.
RUN_LOCK_TTL_SECONDS = 1800
# Renew well before both the ten-minute stale detector and lease expiry. The
# heartbeat protects normal inline execution; inline jobs are separately
# excluded from stale-poll terminalization because a lease alone cannot fence a
# threadpool leaf that outlives coordinator cancellation.
RUN_LOCK_HEARTBEAT_SECONDS = 300
# Stop an inline coordinator while its last known-good lease still has this
# much lifetime. A Redis renewal that is unavailable or hung must never let
# un-fenced work continue beyond the token's TTL.
RUN_LOCK_RENEWAL_SAFETY_SECONDS = RUN_LOCK_HEARTBEAT_SECONDS

PROCESSED_SEGMENTS_KEY_PREFIX = 'sync_job_segments:'
ONCE_KEY_PREFIX = 'sync_job_once:'


class FencedSyncJobMutationOutcome(str, Enum):
    """Result of a run-token-fenced Redis job mutation."""

    APPLIED = 'applied'
    CONFLICT = 'conflict'
    MISSING_OWNER = 'missing_owner'
    STALE_OWNER = 'stale_owner'
    MISSING_JOB = 'missing_job'
    INVALID_JOB = 'invalid_job'
    INVALID_STATE = 'invalid_state'


class SyncLedgerFenceMode(str, Enum):
    """Rollout mode for the epoch-aware sync ledger protocol.

    ``legacy`` deliberately uses the pre-fence worker protocol while mixed
    revisions can still exist. ``standby`` is the hard cutover barrier: no
    sync admission or task work may start. ``active`` is safe only after the
    cutover workflow has retired all old revisions.
    """

    LEGACY = 'legacy'
    STANDBY = 'standby'
    ACTIVE = 'active'


def get_sync_ledger_fence_mode() -> SyncLedgerFenceMode:
    """Return the bounded rollout mode, failing closed on invalid config."""
    raw = os.getenv(SYNC_LEDGER_FENCE_MODE_ENV, SyncLedgerFenceMode.LEGACY.value).strip().lower()
    try:
        return SyncLedgerFenceMode(raw)
    except ValueError:
        # A bad rollout setting must preserve on-device audio and queued work,
        # not accidentally run a half-enabled epoch protocol.
        logger.error('event=sync_ledger_fence_mode outcome=invalid_config')
        return SyncLedgerFenceMode.STANDBY


def sync_job_uses_ledger_fence(job: Dict[str, Any]) -> bool:
    """Whether this persisted job was admitted after the active cutover."""
    return job.get('ledger_fence_mode') == SyncLedgerFenceMode.ACTIVE.value


@dataclass(frozen=True)
class FencedSyncJobMutation:
    """The result of changing a job while holding its current run token.

    Callers must treat every non-``APPLIED`` result as no ownership proof: no
    terminal side effects, claim release, cleanup, or retry-material deletion
    may follow it.
    """

    outcome: FencedSyncJobMutationOutcome
    job: Optional[Dict[str, Any]] = None
    raw_job: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def applied(self) -> bool:
        return self.outcome is FencedSyncJobMutationOutcome.APPLIED


def create_sync_job(
    uid: str,
    total_files: int,
    total_segments: int,
    job_id: Optional[str] = None,
    *,
    lane: str = 'fresh',
    capture_time_trust: str = 'legacy',
    recording_age_seconds: Optional[int] = None,
    content_id: Optional[str] = None,
    dispatch_mode: str = 'inline',
    ledger_fence_mode: str = SyncLedgerFenceMode.LEGACY.value,
) -> Dict[str, Any]:
    """Create a new sync job and store in Redis. Returns the job dict."""
    if job_id is None:
        job_id = str(uuid.uuid4())
    now = time.time()
    job: Dict[str, Any] = {
        'job_id': job_id,
        'uid': uid,
        'status': 'queued',
        'created_at': now,
        'started_at': None,
        'updated_at': now,
        'completed_at': None,
        'total_files': total_files,
        'total_segments': total_segments,
        'processed_segments': 0,
        'successful_segments': 0,
        'failed_segments': 0,
        'result': None,
        'error': None,
        'reason_code': None,
        'retry_after': None,
        'lane': lane,
        'capture_time_trust': capture_time_trust,
        'recording_age_seconds': recording_age_seconds,
        'content_id': content_id,
        'dispatch_mode': dispatch_mode if dispatch_mode in _SYNC_DISPATCH_MODES else 'inline',
        # Persist the protocol choice per job. This prevents an active
        # revision from fencing a job started before the hard old-revision
        # retirement, and prevents a later configuration regression from
        # silently downgrading a fenced job to legacy behavior.
        'ledger_fence_mode': (
            SyncLedgerFenceMode.ACTIVE.value
            if ledger_fence_mode == SyncLedgerFenceMode.ACTIVE.value
            else SyncLedgerFenceMode.LEGACY.value
        ),
    }
    key = f'{JOB_KEY_PREFIX}{job_id}'
    r.set(key, json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    return job


def delete_sync_job(job_id: str) -> None:
    r.delete(f'{JOB_KEY_PREFIX}{job_id}')


def get_sync_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a sync job by ID without changing its lifecycle state."""
    key = f'{JOB_KEY_PREFIX}{job_id}'
    data = r.get(key)
    if not data:
        return None
    try:
        raw = json.loads(data)
    except (TypeError, ValueError, json.JSONDecodeError):
        # A corrupt or legacy blob must not 500 the status poll. redis_db is fail-open and the
        # fenced mutation paths below already guard the identical json.loads; an unparseable job
        # is treated as an unknown job.
        return None
    job: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}

    return job


def is_sync_job_stale(job: Dict[str, Any], *, now: Optional[float] = None) -> bool:
    """Return whether a processing job needs an explicit owner-safe finalizer.

    A read must never publish a terminal failure: callers first acquire the
    per-job run lease, re-read, then finalize/release retry material. Queued
    jobs are intentionally never stale because no worker has claimed them.
    """
    if job.get('status') != 'processing':
        return False
    updated_at = job.get('updated_at') or job.get('created_at')
    if not isinstance(updated_at, (int, float)):
        return False
    reference_time = time.time() if now is None else now
    return reference_time - updated_at > STALE_THRESHOLD_SECONDS


def _as_redis_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)


_LEGACY_JOB_MUTATION_MAX_RETRIES = 3

# This intentionally compares opaque JSON rather than parsing it in Lua. The
# job payload includes nested results where Redis Lua cjson can change empty
# array/object shapes. A raw CAS lets Python re-read and re-evaluate the
# terminal-state guard on every conflicting writer instead.
_LEGACY_JOB_MUTATION_SCRIPT = """
local raw_job = redis.call('get', KEYS[1])
if raw_job == false then
    return {'missing_job'}
end
if raw_job ~= ARGV[1] then
    return {'conflict', raw_job}
end
redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
return {'applied', ARGV[2]}
"""


def _decode_legacy_job_mutation(response: Any) -> FencedSyncJobMutation:
    """Decode a raw-CAS response used by the pre-fence compatibility path."""
    if not isinstance(response, (list, tuple)) or not response:
        raise RuntimeError('sync job legacy mutation returned an invalid Redis response')

    try:
        outcome = FencedSyncJobMutationOutcome(_as_redis_text(response[0]))
    except ValueError as error:
        raise RuntimeError('sync job legacy mutation returned an unknown Redis outcome') from error
    if outcome not in (FencedSyncJobMutationOutcome.APPLIED, FencedSyncJobMutationOutcome.CONFLICT):
        return FencedSyncJobMutation(outcome)
    if len(response) < 2:
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
    try:
        raw_text = _as_redis_text(response[1])
        raw_job = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
    if not isinstance(raw_job, dict):
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
    return FencedSyncJobMutation(outcome, cast(Dict[str, Any], raw_job), raw_text)


def update_sync_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atomically update a legacy job without resurrecting a terminal state.

    Mixed revisions cannot share the epoch-aware protocol: an old binary can
    only understand the historical tokenless job document. New binaries still
    make those writes monotone with a raw JSON compare-and-set. If a competing
    worker terminalizes first, this path returns ``None`` rather than changing
    a truthful ``failed``/``partial_failure`` result back to ``completed`` or
    ``queued``. The later protected cutover retires blind old-binary writes
    before epoch fencing is enabled.
    """
    key = f'{JOB_KEY_PREFIX}{job_id}'
    data = r.get(key)
    if not data:
        return None
    current_raw = _as_redis_text(data)
    try:
        decoded = json.loads(current_raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        # Corrupt/legacy blob: treat as an unresolvable job and skip the mutation, matching the
        # isinstance(dict) guard just below and the fenced paths' json.loads handling.
        return None
    if not isinstance(decoded, dict):
        return None
    current_job = cast(Dict[str, Any], decoded)
    payload = dict(updates)
    payload['updated_at'] = time.time()

    for _ in range(_LEGACY_JOB_MUTATION_MAX_RETRIES):
        # This guard runs immediately before the exact JSON CAS. If another
        # writer wins first, the conflict response becomes the new input and
        # is checked again—two stale readers cannot bypass it.
        if current_job.get('status') in TERMINAL_STATUSES:
            return None
        next_job = dict(current_job)
        next_job.update(payload)
        next_raw = json.dumps(next_job, default=str, separators=(',', ':'))
        mutation = _decode_legacy_job_mutation(
            r.eval(
                _LEGACY_JOB_MUTATION_SCRIPT,
                1,
                key,
                current_raw,
                next_raw,
                JOB_TTL_SECONDS,
            )
        )
        if mutation.outcome is FencedSyncJobMutationOutcome.APPLIED:
            return mutation.job
        if mutation.outcome is not FencedSyncJobMutationOutcome.CONFLICT:
            return None
        if mutation.raw_job is None or mutation.job is None:
            return None
        current_raw = mutation.raw_job
        current_job = mutation.job
    return None


_FENCED_JOB_MUTATION_MAX_RETRIES = 3

_FENCED_JOB_MUTATION_SCRIPT = """
local owner = redis.call('get', KEYS[1])
if owner == false then
    return {'missing_owner'}
end
if owner ~= ARGV[1] then
    return {'stale_owner'}
end

local raw_job = redis.call('get', KEYS[2])
if raw_job == false then
    return {'missing_job'}
end
if raw_job ~= ARGV[2] then
    return {'conflict', raw_job}
end
redis.call('set', KEYS[2], ARGV[3], 'EX', ARGV[4])
return {'applied', ARGV[3]}
"""


def _decode_fenced_mutation(response: Any) -> FencedSyncJobMutation:
    if not isinstance(response, (list, tuple)) or not response:
        raise RuntimeError('sync job fenced mutation returned an invalid Redis response')

    try:
        outcome = FencedSyncJobMutationOutcome(_as_redis_text(response[0]))
    except ValueError as error:
        raise RuntimeError('sync job fenced mutation returned an unknown Redis outcome') from error

    if outcome not in (FencedSyncJobMutationOutcome.APPLIED, FencedSyncJobMutationOutcome.CONFLICT):
        return FencedSyncJobMutation(outcome)
    if len(response) < 2:
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)

    try:
        raw_text = _as_redis_text(response[1])
        raw_job = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
    if not isinstance(raw_job, dict):
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
    return FencedSyncJobMutation(outcome, cast(Dict[str, Any], raw_job), raw_text)


def _decode_fence_only_mutation(response: Any) -> FencedSyncJobMutation:
    """Decode an ownership check whose successful operation has no job JSON."""
    if not isinstance(response, (list, tuple)) or not response:
        raise RuntimeError('sync job fenced mutation returned an invalid Redis response')

    try:
        outcome = FencedSyncJobMutationOutcome(_as_redis_text(response[0]))
    except ValueError as error:
        raise RuntimeError('sync job fenced mutation returned an unknown Redis outcome') from error
    return FencedSyncJobMutation(outcome)


def fenced_update_sync_job(
    job_id: str,
    run_lock_token: str,
    updates: Dict[str, Any],
    *,
    now: Optional[float] = None,
    allowed_current_statuses: Optional[Set[str]] = None,
) -> FencedSyncJobMutation:
    """Atomically apply ``updates`` only while ``run_lock_token`` still owns a job.

    Python owns JSON parsing/merging so it can preserve array-vs-object shapes.
    The Lua boundary only compares the current run token and exact raw job JSON
    before atomically replacing it and refreshing the normal job retention TTL.
    A concurrent write causes a bounded Python rebase; a stale/missing owner is
    deliberately observable rather than collapsed into a missing job, so callers
    can stop before publishing durable side effects for a worker that lost its
    lease. ``allowed_current_statuses`` is evaluated immediately before the
    raw-JSON CAS. Because the Lua script requires the exact raw JSON read by
    Python, a concurrent state change conflicts and re-evaluates this guard
    without parsing JSON in Lua (which would corrupt empty arrays).
    """
    payload = dict(updates)
    payload['updated_at'] = time.time() if now is None else now
    lock_key = f'{RUN_LOCK_KEY_PREFIX}{job_id}'
    job_key = f'{JOB_KEY_PREFIX}{job_id}'

    raw_value = r.get(job_key)
    if raw_value is None:
        # Let the script report lock ownership before declaring the job absent.
        initial = _decode_fenced_mutation(
            r.eval(
                _FENCED_JOB_MUTATION_SCRIPT,
                2,
                lock_key,
                job_key,
                run_lock_token,
                '',
                '',
                JOB_TTL_SECONDS,
            )
        )
        if initial.outcome is not FencedSyncJobMutationOutcome.CONFLICT:
            return initial
        current_raw = initial.raw_job
        current_job = initial.job
    else:
        current_raw = _as_redis_text(raw_value)
        try:
            decoded = json.loads(current_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
        if not isinstance(decoded, dict):
            return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
        current_job = cast(Dict[str, Any], decoded)

    if current_raw is None or current_job is None:
        return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)

    mutation = FencedSyncJobMutation(FencedSyncJobMutationOutcome.CONFLICT)
    for _ in range(_FENCED_JOB_MUTATION_MAX_RETRIES):
        current_status = current_job.get('status')
        # No worker path may ever overwrite a terminal result, even while it
        # still owns the Redis token. This is separate from owner fencing:
        # cleanup can fail after a terminal write, and that failure must not
        # resurrect the job into queued/failed/progress state.
        if current_status in TERMINAL_STATUSES or (
            allowed_current_statuses is not None and current_status not in allowed_current_statuses
        ):
            return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_STATE, current_job, current_raw)
        next_job = dict(current_job)
        next_job.update(payload)
        next_raw = json.dumps(next_job, default=str, separators=(',', ':'))
        mutation = _decode_fenced_mutation(
            r.eval(
                _FENCED_JOB_MUTATION_SCRIPT,
                2,
                lock_key,
                job_key,
                run_lock_token,
                current_raw,
                next_raw,
                JOB_TTL_SECONDS,
            )
        )
        if mutation.outcome is not FencedSyncJobMutationOutcome.CONFLICT:
            return mutation
        if mutation.raw_job is None or mutation.job is None:
            return FencedSyncJobMutation(FencedSyncJobMutationOutcome.INVALID_JOB)
        current_raw = mutation.raw_job
        current_job = mutation.job

    return mutation


def fenced_mark_job_processing(
    job_id: str,
    run_lock_token: str,
    *,
    now: Optional[float] = None,
) -> FencedSyncJobMutation:
    """Transition a job to processing only while its worker still owns it."""
    started_at = time.time() if now is None else now
    return fenced_update_sync_job(
        job_id,
        run_lock_token,
        {
            'status': 'processing',
            'started_at': started_at,
        },
        now=started_at,
        allowed_current_statuses={'queued', 'processing'},
    )


def mark_job_processing(job_id: str) -> Optional[Dict[str, Any]]:
    """Transition job from queued to processing."""
    return update_sync_job(
        job_id,
        {
            'status': 'processing',
            'started_at': time.time(),
        },
    )


def _sync_job_finalization_updates(
    result: Dict[str, Any], *, completed_at: float
) -> tuple[str, int, int, Dict[str, Any]]:
    """Build the one terminal-state patch shared by fenced and legacy callers."""
    failed = result.get('failed_segments', 0)
    total = result.get('total_segments', 0)

    if total > 0 and failed >= total:
        status = 'failed'
    elif failed > 0:
        status = 'partial_failure'
    else:
        status = 'completed'

    # Propagate error info when all segments fail so the app gets a meaningful message
    error: Optional[str] = None
    if status == 'failed':
        errors = result.get('errors', [])
        if errors:
            error = f'All {total} segments failed. First error: {errors[0]}'
        else:
            error = f'All {total} segments failed processing'

    return (
        status,
        total,
        failed,
        {
            'status': status,
            'completed_at': completed_at,
            'result': result,
            'successful_segments': max(0, total - failed),
            'failed_segments': failed,
            'processed_segments': total,
            'error': error,
        },
    )


def _log_sync_job_finalized(
    *,
    finalized: Dict[str, Any],
    result: Dict[str, Any],
    status: str,
    total: int,
    failed: int,
) -> None:
    default_outcome = 'success' if status == 'completed' else status
    outcome = result.get('outcome', default_outcome)
    lane = finalized.get('lane', 'unknown')
    provider = result.get('provider', 'unknown')
    model = result.get('model', 'unknown')
    logger.info(
        'event=sync_transcription_job_finalized status=%s outcome=%s '
        'provider=%s model=%s lane=%s total_segments=%d failed_segments=%d',
        status,
        outcome if outcome in _SYNC_JOB_OUTCOMES else 'upstream_error',
        provider if provider in _SYNC_PROVIDERS else 'unknown',
        model if model in _SYNC_MODELS else 'unknown',
        lane if lane in _SYNC_LANES else 'unknown',
        total,
        failed,
    )


def finalize_sync_job(job_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Finalize a sync job with a truthful terminal status.

    ``completed`` is reserved for batches where every speech-eligible segment
    succeeded (including the valid zero-segment result produced when VAD finds
    no speech). Any segment failure keeps the job visibly retryable as either
    ``partial_failure`` or ``failed``.
    """
    status, total, failed, updates = _sync_job_finalization_updates(result, completed_at=time.time())

    finalized = update_sync_job(job_id, updates)
    if finalized is not None:
        _log_sync_job_finalized(
            finalized=finalized,
            result=result,
            status=status,
            total=total,
            failed=failed,
        )
    return finalized


def fenced_finalize_sync_job(
    job_id: str,
    run_lock_token: str,
    result: Dict[str, Any],
    *,
    now: Optional[float] = None,
) -> FencedSyncJobMutation:
    """Publish a terminal result only while the caller retains the run lock.

    Durable terminal side effects must follow only when the returned mutation
    is :attr:`FencedSyncJobMutation.applied`; a stale worker must leave the
    newer owner's status and retry material untouched.
    """
    completed_at = time.time() if now is None else now
    status, total, failed, updates = _sync_job_finalization_updates(result, completed_at=completed_at)
    mutation = fenced_update_sync_job(
        job_id,
        run_lock_token,
        updates,
        now=completed_at,
        allowed_current_statuses={'processing'},
    )
    if mutation.applied and mutation.job is not None:
        _log_sync_job_finalized(
            finalized=mutation.job,
            result=result,
            status=status,
            total=total,
            failed=failed,
        )
    return mutation


def mark_job_completed(job_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compatibility alias for callers not yet migrated to ``finalize_sync_job``."""
    return finalize_sync_job(job_id, result)


def mark_job_failed(
    job_id: str,
    error: str,
    *,
    reason_code: Optional[str] = None,
    retry_after: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Mark job as failed with error message."""
    return update_sync_job(
        job_id,
        {
            'status': 'failed',
            'completed_at': time.time(),
            'error': error,
            'reason_code': reason_code,
            'retry_after': retry_after,
        },
    )


def fenced_mark_job_failed(
    job_id: str,
    run_lock_token: str,
    error: str,
    *,
    reason_code: Optional[str] = None,
    retry_after: Optional[int] = None,
    now: Optional[float] = None,
) -> FencedSyncJobMutation:
    """Publish an explicit failure only while the caller retains the run lock."""
    completed_at = time.time() if now is None else now
    return fenced_update_sync_job(
        job_id,
        run_lock_token,
        {
            'status': 'failed',
            'completed_at': completed_at,
            'error': error,
            'reason_code': reason_code,
            'retry_after': retry_after,
        },
        now=completed_at,
        allowed_current_statuses={'queued', 'processing'},
    )


def mark_job_queued_for_retry(job_id: str, attempt: int, error: str) -> Optional[Dict[str, Any]]:
    """Reset a job to 'queued' before a Cloud Tasks retry.

    Queued jobs are exempt from stale finalization, so app polling during a
    retry backoff cannot flip a pending Cloud Tasks retry to terminal failed.
    """
    return update_sync_job(
        job_id,
        {
            'status': 'queued',
            'attempt': attempt,
            'last_error': error,
        },
    )


def fenced_mark_job_queued_for_retry(
    job_id: str,
    run_lock_token: str,
    attempt: int,
    error: str,
    *,
    now: Optional[float] = None,
) -> FencedSyncJobMutation:
    """Return a job to the Cloud Tasks queue only while its owner is current."""
    return fenced_update_sync_job(
        job_id,
        run_lock_token,
        {
            'status': 'queued',
            'attempt': attempt,
            'last_error': error,
        },
        now=now,
        allowed_current_statuses={'queued', 'processing'},
    )


_ACQUIRE_LOCK_WITH_EPOCH_SCRIPT = """
if redis.call('get', KEYS[1]) ~= false then
    return {0}
end
local epoch = redis.call('incr', KEYS[2])
local token = tostring(epoch) .. ':' .. ARGV[1]
local acquired = redis.call('set', KEYS[1], token, 'NX', 'EX', ARGV[2])
if not acquired then
    return {0}
end
return {1, token, tostring(epoch)}
"""


def get_sync_job_run_lock_epoch(token: str) -> int:
    """Extract the monotonic lease epoch from an opaque run-lock token.

    Plain UUID tokens are a bounded pre-rollout compatibility case. They map to
    epoch zero, so the first epoch-aware replacement always supersedes them in
    the Firestore ledger fence.
    """
    epoch_text, separator, _ = token.partition(':')
    if not separator:
        return 0
    try:
        epoch = int(epoch_text)
    except ValueError:
        return 0
    return epoch if epoch > 0 else 0


def try_acquire_job_run_lock(job_id: str) -> Optional[str]:
    """Acquire a generic compare-delete run lock, or return ``None`` if held.

    Audio merge and account-deletion tasks share this primitive but do not have
    a Firestore sync-content ledger, so they deliberately do not allocate a
    durable lease epoch.
    """
    token = str(uuid.uuid4())
    acquired = r.set(f'{RUN_LOCK_KEY_PREFIX}{job_id}', token, nx=True, ex=RUN_LOCK_TTL_SECONDS)
    return token if acquired else None


def try_acquire_sync_job_run_lock(job_id: str) -> Optional[str]:
    """Acquire a sync job run lock with a monotonically increasing token.

    The epoch counter intentionally has no expiry: a ledger entry can outlive
    the Redis lock, so resetting an epoch while that entry remains would allow
    a delayed old bind to win a durable ownership race. Existing callers keep
    using the opaque token for renew/release/fenced job mutations.
    """
    response = r.eval(
        _ACQUIRE_LOCK_WITH_EPOCH_SCRIPT,
        2,
        f'{RUN_LOCK_KEY_PREFIX}{job_id}',
        f'{RUN_LOCK_EPOCH_KEY_PREFIX}{job_id}',
        str(uuid.uuid4()),
        RUN_LOCK_TTL_SECONDS,
    )
    if not isinstance(response, (list, tuple)) or not response:
        raise RuntimeError('sync job run-lock acquisition returned an invalid Redis response')
    acquired = _as_redis_text(response[0])
    if acquired != '1':
        return None
    if len(response) < 2:
        raise RuntimeError('sync job run-lock acquisition omitted its token')
    token = _as_redis_text(response[1])
    if get_sync_job_run_lock_epoch(token) <= 0:
        raise RuntimeError('sync job run-lock acquisition returned an invalid epoch token')
    return token


def delete_sync_job_run_lock_epoch(job_id: str) -> None:
    """Retire a sync epoch only after its durable ledger becomes terminal/retryable.

    Do not call this when releasing a live lock or resetting a Cloud Tasks
    retry: a delayed executor may still resume and needs the next owner to have
    a greater epoch. Normal terminal/retired-claim paths clean it up; crashes
    leave a harmless counter rather than ever resetting a live generation.
    """
    try:
        r.delete(f'{RUN_LOCK_EPOCH_KEY_PREFIX}{job_id}')
    except Exception as error:
        # A retained counter is safe; resetting it after a terminal result is
        # an optimization only, never a reason to disturb that result.
        logger.warning('sync job run-lock epoch cleanup failed for %s: %s', job_id, type(error).__name__)


_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""


def renew_job_run_lock(job_id: str, token: str) -> bool:
    """Renew a run lease only when *token* still owns it.

    Redis errors deliberately propagate: a caller must distinguish an
    unavailable lease store from a successful renewal, and must never extend a
    possibly stolen lock with an unconditional ``EXPIRE``.
    """
    return bool(
        r.eval(
            _RENEW_LOCK_SCRIPT,
            1,
            f'{RUN_LOCK_KEY_PREFIX}{job_id}',
            token,
            RUN_LOCK_TTL_SECONDS,
        )
    )


def release_job_run_lock(job_id: str, token: str) -> None:
    """Release the run lock if we still own it (compare-and-delete).

    Best-effort: on Redis failure the lock simply expires via its TTL and a
    duplicate delivery in the meantime gets 409-retried.
    """
    try:
        r.eval(_RELEASE_LOCK_SCRIPT, 1, f'{RUN_LOCK_KEY_PREFIX}{job_id}', token)
    except Exception as e:
        logger.warning('release_job_run_lock failed for %s: %s', job_id, e)


def add_processed_segment(job_id: str, segment_path: str) -> None:
    """Record a segment as fully processed (conversation written) for this job.

    Lets a Cloud Tasks retry skip segments that already landed. Best-effort:
    on failure the retry falls back to the timestamp-based segment dedup.
    """
    try:
        key = f'{PROCESSED_SEGMENTS_KEY_PREFIX}{job_id}'
        r.sadd(key, segment_path)
        r.expire(key, JOB_TTL_SECONDS)
    except Exception as e:
        logger.warning('add_processed_segment failed for %s: %s', job_id, e)


_FENCED_ADD_PROCESSED_SEGMENT_SCRIPT = """
local owner = redis.call('get', KEYS[1])
if owner == false then
    return {'missing_owner'}
end
if owner ~= ARGV[1] then
    return {'stale_owner'}
end
redis.call('sadd', KEYS[2], ARGV[2])
redis.call('expire', KEYS[2], ARGV[3])
return {'applied'}
"""


def add_processed_segment_if_run_owner(
    job_id: str,
    run_lock_token: str,
    segment_path: str,
) -> FencedSyncJobMutation:
    """Record a processed segment only while the task still owns its run.

    Unlike the legacy best-effort ledger helper, callers must treat every
    non-applied result as an ownership loss and avoid marking retry material as
    complete. The owner comparison, ``SADD``, and retention refresh share one
    Redis script so a resumed stale worker cannot poison a newer retry's skip
    ledger.
    """
    return _decode_fence_only_mutation(
        r.eval(
            _FENCED_ADD_PROCESSED_SEGMENT_SCRIPT,
            2,
            f'{RUN_LOCK_KEY_PREFIX}{job_id}',
            f'{PROCESSED_SEGMENTS_KEY_PREFIX}{job_id}',
            run_lock_token,
            segment_path,
            JOB_TTL_SECONDS,
        )
    )


def get_processed_segments(job_id: str) -> Set[str]:
    """Return segment paths already processed for this job."""
    try:
        members = r.smembers(f'{PROCESSED_SEGMENTS_KEY_PREFIX}{job_id}')
        decoded: Set[str] = set()
        for m in cast(Set[Any], members):
            if isinstance(m, bytes):
                decoded.add(m.decode())
            else:
                decoded.add(str(m))
        return decoded
    except Exception as e:
        logger.warning('get_processed_segments failed for %s: %s', job_id, e)
        return set()


def try_mark_once(job_id: str, tag: str) -> bool:
    """SETNX guard so per-job side effects (fair-use metering, usage recording)
    run at most once across Cloud Tasks retries.

    Fails OPEN (returns True on Redis error) to match the metering functions'
    own fail-open posture — better to occasionally double-count than to
    silently never count.
    """
    try:
        return bool(r.set(f'{ONCE_KEY_PREFIX}{job_id}:{tag}', '1', nx=True, ex=JOB_TTL_SECONDS))
    except Exception as e:
        logger.warning('try_mark_once failed for %s:%s: %s', job_id, tag, e)
        return True
