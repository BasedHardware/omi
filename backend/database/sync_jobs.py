"""
Redis-backed sync job storage for v2 async sync-local-files.

Jobs are ephemeral — they exist only long enough for the app to poll results.
Redis is the right store: no Firestore costs, automatic TTL cleanup.

Key format: sync_job:{job_id}
TTL: 1 hour (refreshed on each update)
"""

import json
import logging
import time
import uuid
from typing import Optional

from database.redis_db import r

logger = logging.getLogger(__name__)

JOB_KEY_PREFIX = 'sync_job:'
JOB_TTL_SECONDS = 3600  # 1 hour
STALE_THRESHOLD_SECONDS = 600  # 10 minutes — if processing exceeds this, treat as failed


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

    # Stale-job detection: if processing for too long, mark failed
    if job['status'] in ('queued', 'processing'):
        updated_at = job.get('updated_at') or job.get('created_at', 0)
        if time.time() - updated_at > STALE_THRESHOLD_SECONDS:
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
