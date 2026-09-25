from typing import Dict, Optional
import logging

from fastapi import HTTPException

from backend.database.sync_jobs import (
    get_sync_job,
    is_sync_job_stale,
    release_backfill_slot,
    _backfill_dead_letter_pending,
)
from backend.schemas.sync import SyncJobStatusResponse
from backend.utils.redis import redis_client

logger = logging.getLogger(__name__)

# ... (existing imports and constants)

def get_sync_job_status(job_id: str, uid: str) -> SyncJobStatusResponse:
    job = get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Early exit for non-backfill jobs
    if job.get("dispatch_mode") != "cloud_tasks" or not job.get("is_backfill"):
        return SyncJobStatusResponse(**job)

    # Handle stale jobs (processing/queued)
    if is_sync_job_stale(job) and job.get("status") in ("processing", "queued"):
        job["status"] = "failed"
        _backfill_dead_letter_pending(job_id, uid)
        redis_client.hset(f"sync_job:{job_id}", mapping=job)
        release_backfill_slot(uid, job_id)
        return SyncJobStatusResponse(**job)

    # Verify dead-letter state for terminal jobs
    if job.get("status") in ("failed", "partial_failure"):
        dead_letter_key = f"sync_job_dead_letter:{job_id}"
        if redis_client.exists(dead_letter_key):
            dead_letter = redis_client.hgetall(dead_letter_key)
            if dead_letter.get(b"status") in (b"pending", b"dead_letter"):
                # Release slot for terminal dead-letter jobs
                release_backfill_slot(uid, job_id)
        return SyncJobStatusResponse(**job)

    # ... (rest of the function remains unchanged)