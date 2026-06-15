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
import time
import uuid
from typing import Optional

from database.redis_db import r

logger = logging.getLogger(__name__)

JOB_KEY_PREFIX = 'sync_job:'
JOB_TTL_SECONDS = 86400  # 24 hours — reconcile window (see module docstring)
STALE_THRESHOLD_SECONDS = 600  # 10 minutes — if processing exceeds this, treat as failed

TERMINAL_STATUSES = ('completed', 'partial_failure', 'failed')

RUN_LOCK_KEY_PREFIX = 'sync_job_lock:'
# Must stay above the handler's request timeout (HTTP_SYNC_JOBS_RUN_TIMEOUT,
# 1500s) so the lock can never expire while a run is still executing.
RUN_LOCK_TTL_SECONDS = 1800

PROCESSED_SEGMENTS_KEY_PREFIX = 'sync_job_segments:'
ONCE_KEY_PREFIX = 'sync_job_once:'


def create_sync_job(uid: str, total_files: int, total_segments: int, job_id: str | None = None) -> dict:
    """Create a new sync job and store in Redis. Returns the job dict."""
    if job_id is None:
        job_id = str(uuid.uuid4())
    now = time.time()
    job = {
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
    }
    key = f'{JOB_KEY_PREFIX}{job_id}'
    r.set(key, json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    return job


def get_sync_job(job_id: str) -> Optional[dict]:
    """Get a sync job by ID. Returns None if not found or expired."""
    key = f'{JOB_KEY_PREFIX}{job_id}'
    data = r.get(key)
    if not data:
        return None
    job = json.loads(data)

    # Stale-job detection: only a job that was actually picked up by a worker
    # (status='processing') and then went quiet is a real failure. A job still
    # 'queued' has never been picked up — usually because the worker pools are
    # saturated — so it is NOT a failure; leave it queued and let the 24h TTL
    # clean it up. (Flipping queued jobs to 'failed' here caused the client to
    # surface spurious "Couldn't process — retrying" loops; see issue #7469.)
    if job['status'] == 'processing':
        updated_at = job.get('updated_at') or job.get('created_at', 0)
        if time.time() - updated_at > STALE_THRESHOLD_SECONDS:
            logger.warning(
                "sync_job %s (uid=%s) stale after %.0fs in 'processing' — marking failed",
                job_id,
                job.get('uid'),
                time.time() - updated_at,
            )
            job['status'] = 'failed'
            job['error'] = 'Job timed out (background worker likely died)'
            job['completed_at'] = time.time()
            # Persist the failure status
            r.set(key, json.dumps(job, default=str), ex=JOB_TTL_SECONDS)

    return job


def update_sync_job(job_id: str, updates: dict) -> Optional[dict]:
    """Update a sync job. Returns updated job or None if not found."""
    key = f'{JOB_KEY_PREFIX}{job_id}'
    data = r.get(key)
    if not data:
        return None
    job = json.loads(data)
    job.update(updates)
    job['updated_at'] = time.time()
    r.set(key, json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    return job


def mark_job_processing(job_id: str) -> Optional[dict]:
    """Transition job from queued to processing."""
    return update_sync_job(
        job_id,
        {
            'status': 'processing',
            'started_at': time.time(),
        },
    )


def mark_job_completed(job_id: str, result: dict) -> Optional[dict]:
    """Mark job as completed with final result."""
    failed = result.get('failed_segments', 0)
    total = result.get('total_segments', 0)

    if total > 0 and failed >= total:
        status = 'failed'
    elif failed > 0:
        status = 'partial_failure'
    else:
        status = 'completed'

    # Propagate error info when all segments fail so the app gets a meaningful message
    error = None
    if status == 'failed':
        errors = result.get('errors', [])
        if errors:
            error = f'All {total} segments failed. First error: {errors[0]}'
        else:
            error = f'All {total} segments failed processing'

    return update_sync_job(
        job_id,
        {
            'status': status,
            'completed_at': time.time(),
            'result': result,
            'successful_segments': max(0, total - failed),
            'failed_segments': failed,
            'processed_segments': total,
            'error': error,
        },
    )


def mark_job_failed(job_id: str, error: str) -> Optional[dict]:
    """Mark job as failed with error message."""
    return update_sync_job(
        job_id,
        {
            'status': 'failed',
            'completed_at': time.time(),
            'error': error,
        },
    )


def mark_job_queued_for_retry(job_id: str, attempt: int, error: str) -> Optional[dict]:
    """Reset a job to 'queued' before a Cloud Tasks retry.

    'queued' is exempt from the stale detector in get_sync_job(), so the app
    polling during the retry backoff window cannot flip the job to a terminal
    'failed' while a retry is still pending.
    """
    return update_sync_job(
        job_id,
        {
            'status': 'queued',
            'attempt': attempt,
            'last_error': error,
        },
    )


def try_acquire_job_run_lock(job_id: str) -> Optional[str]:
    """Acquire the per-job run lock. Returns a release token, or None if held.

    Fails CLOSED: Redis errors propagate to the caller. An unobtainable lock
    must block execution (the Cloud Tasks retry will come back later), never
    allow two concurrent runs of the same job.
    """
    token = str(uuid.uuid4())
    acquired = r.set(f'{RUN_LOCK_KEY_PREFIX}{job_id}', token, nx=True, ex=RUN_LOCK_TTL_SECONDS)
    return token if acquired else None


_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


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


def get_processed_segments(job_id: str) -> set:
    """Return segment paths already processed for this job."""
    try:
        members = r.smembers(f'{PROCESSED_SEGMENTS_KEY_PREFIX}{job_id}')
        return {m.decode() if isinstance(m, bytes) else m for m in members}
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
