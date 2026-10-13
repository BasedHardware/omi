"""Account-wide hot-loop ceiling, independent of generic rate-limit settings."""

from database import redis_db
from utils.observability.fallback import record_fallback
from utils.sync import stage

# Dart admits at most 18 polls/minute per app instance, with 20s per job.
# Even two instances bursting simultaneously (36 requests) fit this window.
SYNC_POLL_WINDOW_SECONDS = 20
SYNC_POLL_MAX_REQUESTS = 40


def admit_sync_job_poll(uid: str) -> bool:
    """Reserve one poll across all jobs/replicas; Redis outages fail open."""
    try:
        allowed, _, _ = redis_db.reserve_rate_limit(
            uid, stage.redis_key('sync_job_poll'), SYNC_POLL_MAX_REQUESTS, SYNC_POLL_WINDOW_SECONDS
        )
        return allowed
    except Exception:
        record_fallback(
            component='redis_ratelimit',
            from_mode='sync_job_poll',
            to_mode='unlimited',
            reason='gate_unavailable',
            outcome='degraded',
        )
        return True
