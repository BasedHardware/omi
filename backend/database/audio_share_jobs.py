"""
Redis-backed job storage for async audio-share merge jobs.

Same shape as `sync_jobs.py` but with audio-specific fields. The merge work
takes 4-10+ minutes for long conversations, which used to blow Cloud Run's
600s edge timeout when run inline in /urls (issue #4586). The job model
moves the work off the request thread; the app polls until terminal.

Key format:
  audio_share_job:{job_id}             -> the job dict
  audio_share_active:{uid}:{conv_id}   -> job_id of the active (non-terminal) job, if any

TTL: 1 hour (refreshed on each update). Active-job pointer shares the same TTL.
"""

import json
import logging
import time
import uuid
from typing import Optional

from database.redis_db import r

logger = logging.getLogger(__name__)

JOB_KEY_PREFIX = 'audio_share_job:'
ACTIVE_KEY_PREFIX = 'audio_share_active:'
JOB_TTL_SECONDS = 3600  # 1 hour
# Audio merges can run 4-10+ minutes. Keep stale threshold well above the worst case
# so genuine long merges aren't auto-failed by the safety net.
STALE_THRESHOLD_SECONDS = 1500  # 25 minutes

TERMINAL_STATUSES = ('completed', 'failed')


def _job_key(job_id: str) -> str:
    return f'{JOB_KEY_PREFIX}{job_id}'


def _active_key(uid: str, conversation_id: str) -> str:
    return f'{ACTIVE_KEY_PREFIX}{uid}:{conversation_id}'


def get_active_job_id(uid: str, conversation_id: str) -> Optional[str]:
    """Return the job_id of the active (non-terminal) job for this (uid, conv), if any."""
    job_id = r.get(_active_key(uid, conversation_id))
    if not job_id:
        return None
    if isinstance(job_id, bytes):
        job_id = job_id.decode('utf-8')
    return job_id


def create_audio_share_job(
    uid: str,
    conversation_id: str,
    audio_files: list,
    job_id: Optional[str] = None,
) -> dict:
    """Create a new audio-share job and store in Redis. Returns the job dict.

    `audio_files` is a list of {id, duration} dicts (one per audio file in the conv).
    """
    if job_id is None:
        job_id = str(uuid.uuid4())
    now = time.time()
    job = {
        'job_id': job_id,
        'uid': uid,
        'conversation_id': conversation_id,
        'status': 'queued',
        'progress_pct': 0.0,
        'audio_files': [
            {
                'id': af.get('id'),
                'status': 'pending',
                'signed_url': None,
                'duration': af.get('duration', 0),
            }
            for af in audio_files
        ],
        'error': None,
        'created_at': now,
        'started_at': None,
        'updated_at': now,
        'completed_at': None,
    }
    r.set(_job_key(job_id), json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    r.set(_active_key(uid, conversation_id), job_id, ex=JOB_TTL_SECONDS)
    return job


def get_audio_share_job(job_id: str) -> Optional[dict]:
    """Get a job by ID. Returns None if not found or expired.

    Applies a stale-job safety net: if a queued/processing job hasn't been touched
    within STALE_THRESHOLD_SECONDS, mark it failed (worker likely died).
    """
    data = r.get(_job_key(job_id))
    if not data:
        return None
    job = json.loads(data)

    if job['status'] not in TERMINAL_STATUSES:
        updated_at = job.get('updated_at') or job.get('created_at', 0)
        if time.time() - updated_at > STALE_THRESHOLD_SECONDS:
            job['status'] = 'failed'
            job['error'] = 'Job timed out (background worker likely died)'
            job['completed_at'] = time.time()
            r.set(_job_key(job_id), json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
            _clear_active_pointer(job['uid'], job['conversation_id'], job_id)

    return job


def update_audio_share_job(job_id: str, updates: dict) -> Optional[dict]:
    """Update a job. Returns updated job or None if not found."""
    data = r.get(_job_key(job_id))
    if not data:
        return None
    job = json.loads(data)
    job.update(updates)
    job['updated_at'] = time.time()
    r.set(_job_key(job_id), json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    # Refresh active pointer TTL so it doesn't expire mid-run on long merges
    if job['status'] not in TERMINAL_STATUSES:
        r.expire(_active_key(job['uid'], job['conversation_id']), JOB_TTL_SECONDS)
    return job


def mark_processing(job_id: str) -> Optional[dict]:
    return update_audio_share_job(
        job_id,
        {'status': 'processing', 'started_at': time.time()},
    )


def update_audio_file_url(job_id: str, audio_file_id: str, signed_url: str, progress_pct: float) -> Optional[dict]:
    """Mark one audio_file as ready with its signed URL. Updates progress_pct."""
    data = r.get(_job_key(job_id))
    if not data:
        return None
    job = json.loads(data)
    for af in job.get('audio_files', []):
        if af.get('id') == audio_file_id:
            af['status'] = 'cached'
            af['signed_url'] = signed_url
            break
    job['progress_pct'] = max(0.0, min(100.0, progress_pct))
    job['updated_at'] = time.time()
    r.set(_job_key(job_id), json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    r.expire(_active_key(job['uid'], job['conversation_id']), JOB_TTL_SECONDS)
    return job


def mark_completed(job_id: str) -> Optional[dict]:
    """Transition to terminal completed state and clear the active pointer."""
    job = update_audio_share_job(
        job_id,
        {'status': 'completed', 'progress_pct': 100.0, 'completed_at': time.time()},
    )
    if job:
        _clear_active_pointer(job['uid'], job['conversation_id'], job_id)
    return job


def mark_failed(job_id: str, error: str) -> Optional[dict]:
    job = update_audio_share_job(
        job_id,
        {'status': 'failed', 'error': error, 'completed_at': time.time()},
    )
    if job:
        _clear_active_pointer(job['uid'], job['conversation_id'], job_id)
    return job


def _clear_active_pointer(uid: str, conversation_id: str, expected_job_id: str) -> None:
    """Clear active-job pointer, but only if it still points at this job_id.

    Avoids races where a new job started before we clean up an older completed one.
    """
    try:
        current = r.get(_active_key(uid, conversation_id))
        if isinstance(current, bytes):
            current = current.decode('utf-8')
        if current == expected_job_id:
            r.delete(_active_key(uid, conversation_id))
    except Exception as e:
        logger.warning(f'audio_share_jobs: failed to clear active pointer for {uid}/{conversation_id}: {e}')
