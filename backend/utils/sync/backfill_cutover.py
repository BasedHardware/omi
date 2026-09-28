"""Bounded mixed-revision guard for direct and sequenced backfill tasks."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from database.redis_db import r

# Cloud Tasks' 25-minute request deadline is below the 30-minute run-lock TTL.
# Direct jobs reserve only their own UID. A global missing/evicted mode key
# must not put every production UID back into a quiet window.
QUIET_SECONDS = 30 * 60
LEGACY_QUIET_KEY = 'sync_backfill:uid_sequencer:quiet_until'
DIRECT_KEY_PREFIX = 'sync_backfill:uid_sequencer:direct:'
WAIT_LOG_PREFIX = 'sync_backfill:uid_sequencer:wait_log:'
WAKE_KEY_PREFIX = 'sync_backfill:uid_sequencer:wake:'


def _key(key: str) -> str:
    # Prod retains its live Redis keys through the mixed-revision deployment.
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    return key if stage == 'prod' else f'{stage or "local"}:{key}'


def uid_hash(uid: str) -> str:
    secret = os.getenv('SYNC_CONTENT_ID_SECRET') or os.getenv('ENCRYPTION_SECRET')
    if not secret:
        raise RuntimeError('sync identity secret is required')
    return hmac.new(secret.encode(), f'sync-uid-log:{uid}'.encode(), hashlib.sha256).hexdigest()[:16]


def note_direct_admission(uid: str, job_id: str) -> None:
    """A direct job may start later; reserve its UID for a bounded run time."""
    r.set(_key(DIRECT_KEY_PREFIX + uid), job_id, ex=QUIET_SECONDS)


def refresh_direct_run(uid: str, job_id: str) -> None:
    """A queued direct task can start long after admission; renew from start."""
    r.set(_key(DIRECT_KEY_PREFIX + uid), job_id, ex=QUIET_SECONDS)


def quiet_remaining(uid: str) -> tuple[int, str]:
    """Return a conservative wait and the direct job ID, if registered."""
    now = int(time.time())
    # Honor an already-written prod quiet deadline once. Never manufacture or
    # extend one because the old global mode key is absent or was evicted.
    deadline = r.get(LEGACY_QUIET_KEY) if os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'prod' else None
    remaining = max(0, int(deadline or 0) - now)
    direct_remaining, direct_id = direct_remaining_for_uid(uid)
    return max(remaining, direct_remaining), direct_id


def direct_remaining_for_uid(uid: str) -> tuple[int, str]:
    key = _key(DIRECT_KEY_PREFIX + uid)
    direct = r.get(key)
    if not direct:
        return 0, ''
    direct_id = direct.decode() if isinstance(direct, bytes) else str(direct)
    return max(0, int(r.ttl(key))), direct_id


def should_log_wait(uid: str) -> bool:
    return bool(r.set(_key(WAIT_LOG_PREFIX + uid), '1', ex=300, nx=True))


def claim_wake(uid: str, deadline: int) -> bool:
    return bool(r.set(_key(f'{WAKE_KEY_PREFIX}{uid}:{deadline}'), '1', ex=QUIET_SECONDS + 300, nx=True))


def release_wake(uid: str, deadline: int) -> None:
    r.delete(_key(f'{WAKE_KEY_PREFIX}{uid}:{deadline}'))
