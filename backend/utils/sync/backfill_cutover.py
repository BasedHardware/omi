"""Bounded mixed-revision guard for direct and sequenced backfill tasks."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from database.redis_db import r

# Cloud Tasks' 25-minute request deadline is below the 30-minute run-lock TTL.
# Old revisions cannot register their direct work, so an off-to-on transition
# waits one full maximum run-lock lifetime before its first sequenced dispatch.
QUIET_SECONDS = 30 * 60
MODE_KEY = 'sync_backfill:uid_sequencer:mode'
QUIET_KEY = 'sync_backfill:uid_sequencer:quiet_until'
DIRECT_KEY_PREFIX = 'sync_backfill:uid_sequencer:direct:'
WAIT_LOG_PREFIX = 'sync_backfill:uid_sequencer:wait_log:'
WAKE_KEY_PREFIX = 'sync_backfill:uid_sequencer:wake:'


def uid_hash(uid: str) -> str:
    secret = os.getenv('SYNC_CONTENT_ID_SECRET') or os.getenv('ENCRYPTION_SECRET')
    if not secret:
        raise RuntimeError('sync identity secret is required')
    return hmac.new(secret.encode(), f'sync-uid-log:{uid}'.encode(), hashlib.sha256).hexdigest()[:16]


def note_direct_admission(uid: str, job_id: str) -> None:
    """A direct job may start later; reserve its UID for a bounded run time."""
    with r.pipeline(transaction=True) as pipe:
        pipe.set(MODE_KEY, 'off')
        pipe.set(DIRECT_KEY_PREFIX + uid, job_id, ex=QUIET_SECONDS)
        pipe.execute()


def refresh_direct_run(uid: str, job_id: str) -> None:
    """A queued direct task can start long after admission; renew from start."""
    r.set(DIRECT_KEY_PREFIX + uid, job_id, ex=QUIET_SECONDS)


def quiet_remaining(uid: str) -> tuple[int, str]:
    """Return a conservative wait and the direct job ID, if registered."""
    now = int(time.time())
    mode = r.get(MODE_KEY)
    if mode != b'on' and mode != 'on':
        r.set(QUIET_KEY, now + QUIET_SECONDS)
        r.set(MODE_KEY, 'on')
    deadline = r.get(QUIET_KEY)
    remaining = max(0, int(deadline or 0) - now)
    direct_remaining, direct_id = direct_remaining_for_uid(uid)
    return max(remaining, direct_remaining), direct_id


def direct_remaining_for_uid(uid: str) -> tuple[int, str]:
    direct = r.get(DIRECT_KEY_PREFIX + uid)
    if not direct:
        return 0, ''
    direct_id = direct.decode() if isinstance(direct, bytes) else str(direct)
    return max(0, int(r.ttl(DIRECT_KEY_PREFIX + uid))), direct_id


def should_log_wait(uid: str) -> bool:
    return bool(r.set(WAIT_LOG_PREFIX + uid, '1', ex=300, nx=True))


def claim_wake(uid: str, deadline: int) -> bool:
    return bool(r.set(f'{WAKE_KEY_PREFIX}{uid}:{deadline}', '1', ex=QUIET_SECONDS + 300, nx=True))


def release_wake(uid: str, deadline: int) -> None:
    r.delete(f'{WAKE_KEY_PREFIX}{uid}:{deadline}')
