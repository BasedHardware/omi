"""Which owners have a v3-capable app: required for v3 admission at stages ``beta`` and ``all``.

Only app builds that render recording-derived conversations call ``GET /v1/conversations/live``, on any
release channel. Older builds never do: they show the raw recording a capture ends with as a blank
card that 404s. So admission needs one of the owner's apps to have made that call within
``TTL_SECONDS``; owners with only older builds keep legacy intake until they update.

This is a separate marker from the episodes client-seen marker, which also switches on episode work.
Reads fail closed (no marker: legacy intake); writes never raise.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from database import redis_db

logger = logging.getLogger(__name__)

# Same lifetime as the episodes marker: an owner who has not opened a v3 build for two weeks
# returns to legacy intake for new captures (existing rows keep their layer).
TTL_SECONDS = 14 * 24 * 60 * 60
# The app polls /live every 15 s on Home; rewrite at most this often per uid per process.
REFRESH_SECONDS = 60 * 60
# Admission asks at every new capture; a new install is seen by other processes within this window.
READ_CACHE_SECONDS = 120
_MAX_ENTRIES = 50_000

_lock = threading.Lock()
_written: dict[str, float] = {}
_read_cache: dict[str, tuple[bool, float]] = {}


def _key(uid: str) -> str:
    return f'conversations_v3:client_capable:{uid}'


def _bounded_put(cache: dict, uid: str, value) -> None:
    cache[uid] = value
    if len(cache) > _MAX_ENTRIES:
        cache.clear()
        cache[uid] = value


def note_capable(uid: str, *, now: Optional[float] = None) -> None:
    """Records that ``uid``'s app reached the v3 live route. Never raises."""
    if not uid:
        return
    wall = time.time() if now is None else now
    with _lock:
        last = _written.get(uid)
        if last is not None and wall - last < REFRESH_SECONDS:
            _bounded_put(_read_cache, uid, (True, wall))
            return
    try:
        redis_db.r.set(_key(uid), '1', ex=TTL_SECONDS)
    except Exception as exc:
        # Not memoized: the app's next poll retries. Listen, sync and pusher read only the shared marker,
        # so this process must not answer v3 for an owner whose captures they would still keep legacy.
        logger.warning('event=v3_client_capable_write outcome=error exception_type=%s', type(exc).__name__)
        return
    with _lock:
        _bounded_put(_written, uid, wall)
        # This process just saw the app: its own admission need not wait out the read cache.
        _bounded_put(_read_cache, uid, (True, wall))


def capable_cached(uid: str, *, now: Optional[float] = None) -> bool:
    """True while ``uid`` has a v3-capable app, behind a short per-process cache. Blocking (Redis) on a miss."""
    if not uid:
        return False
    wall = time.time() if now is None else now
    with _lock:
        cached = _read_cache.get(uid)
    if cached is not None and wall - cached[1] < READ_CACHE_SECONDS:
        return cached[0]
    try:
        seen = bool(redis_db.r.exists(_key(uid)))
    except Exception as exc:
        # Fails closed, and caches the miss so a Redis outage is not one round trip per admission.
        logger.warning('event=v3_client_capable_read outcome=error exception_type=%s', type(exc).__name__)
        seen = False
    with _lock:
        _bounded_put(_read_cache, uid, (seen, wall))
    return seen


def reset_for_tests() -> None:
    with _lock:
        _written.clear()
        _read_cache.clear()
