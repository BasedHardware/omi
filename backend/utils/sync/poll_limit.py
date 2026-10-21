"""Account-wide hot-loop ceiling, independent of generic rate-limit settings."""

from config.repeat_work import poll_backoff
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


def with_poll_hint(status: dict, *, surface_open: bool = False) -> dict:
    """Use already loaded state only; never query all of an owner's work.

    Unknown/active jobs remain quick. A terminal job has no remaining work;
    queued work may wait 60s. A new/active job immediately selects the short
    interval, independent of previous hints. Surface-open callers can explicitly
    request foreground cadence on this read-only endpoint.
    """
    if not poll_backoff():
        return status
    result = dict(status)
    state = status.get('status')
    result['poll_after_ms'] = (
        0
        if state in {'completed', 'failed', 'partial_failure'}
        else 60000 if state == 'queued' and not surface_open else 20000
    )
    return result
