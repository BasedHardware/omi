"""The mentor relevance gate's debounce record — one owner for both storage tiers.

The realtime path that evaluates the gate runs on two hosts (`routers/listen/
transcripts.py` and `routers/pusher.py` both reach
`_async_trigger_realtime_integrations`), so the record cannot be process-local:
each host would otherwise evaluate once inside the same debounce window and the
throttle would be worth exactly half of what it claims. Redis is the authority.

The process-local mirror in front of it is a latency choice, not a second source
of truth: the common case is "this pod evaluated this user seconds ago", and that
answer should not cost a Redis round trip on the realtime path. It is only ever
written from a shared read or a shared write, never independently — and it is
trusted only for that "evaluated recently" answer. An *eligibility* decision
(the mirror can be stale the moment any other host records) re-reads the shared
authority under a short-lived claim, which also serializes the
check-and-record pair against a concurrent same-user worker on another pod (or
another thread of this one).

Redis failures fall open (return None -> evaluate), matching every other
throttle on this path: a cache outage must not silence the mentor. That
includes writes: an evaluation that fails to persist to the shared tier is not
mirrored locally, so one pod cannot keep throttling on state no other host can
see.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# The record carries a per-UTC-day evaluation counter as well as the debounce
# timestamp, so it has to outlive the debounce window and expire just past a day
# boundary. 25 hours matches the daily proactive-notification counter.
STATE_TTL_SECONDS = 90000

# Cross-worker claim serializing the eligibility check + record for one user.
# It is held for milliseconds; the TTL is only a crash bound for a holder that
# never released. While a claim is held, other workers skip ('claim_busy')
# instead of double-opening the gate.
CLAIM_TTL_SECONDS = 30

# Expired local entries are dropped when their own key is read again, so a churned
# user's key would otherwise sit on a long-lived process forever. Bound the map.
_MAX_LOCAL_ENTRIES = 50000
MAX_ID_LENGTH = 128

_local: Dict[str, tuple[Dict[str, Any], float]] = {}
# The mirror is read and written from the shared db/postprocess executors, so
# every access is guarded: two workers expiring the same entry must not turn
# `del` into a KeyError that aborts the mentor pipeline.
_local_lock = threading.Lock()


def _clean_id(value: Any) -> str:
    """Normalize and validate user identifier."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_ID_LENGTH
        or any(c in cleaned for c in ("\r", "\n", "\0", " ", ":", "/", "\\"))
    ):
        return ""
    return cleaned


def _clean_ttl(ttl: Any, default: int) -> int:
    """Sanitize TTL ensuring it is a positive integer bounded reasonably."""
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
        return default
    return ttl


def _clean_state(state: Any) -> Optional[Dict[str, Any]]:
    """Validate and copy state dictionary."""
    if not isinstance(state, dict):
        return None
    return dict(state)


def _resolve_redis(redis_client: Any = None) -> Any:
    """Resolve Redis client with caller dependency injection support."""
    if redis_client is not None:
        return redis_client
    try:
        from database.redis_db import r

        return r
    except Exception:
        return None


def clear_local_cache() -> None:
    """Thread-safe reset of the process-local mirror (useful for tests and maintenance)."""
    with _local_lock:
        _local.clear()


def _redis_key(uid: str) -> str:
    return f"{uid}:mentor_gate_eval_state"


def _claim_key(uid: str) -> str:
    return f"{uid}:mentor_gate_eval_claim"


def _read_local(uid: str) -> Optional[Dict[str, Any]]:
    with _local_lock:
        entry = _local.get(uid)
        if entry is None:
            return None
        state, expires_at = entry
        if expires_at < time.time():
            _local.pop(uid, None)
            return None
        return state


def _write_local(uid: str, state: Dict[str, Any], ttl: int) -> None:
    now = time.time()
    with _local_lock:
        _local[uid] = (dict(state), now + ttl)
        if len(_local) > _MAX_LOCAL_ENTRIES:
            for key in [k for k, (_s, expires_at) in _local.items() if expires_at < now]:
                _local.pop(key, None)
            overflow = len(_local) - _MAX_LOCAL_ENTRIES
            if overflow > 0:
                for key in sorted(_local, key=lambda k: _local[k][1])[:overflow]:
                    _local.pop(key, None)


def _read_shared(uid: str, redis_client: Any = None) -> Optional[Dict[str, Any]]:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return None
    try:
        r = _resolve_redis(redis_client)
        if r is None:
            return None
        raw = r.get(_redis_key(clean_uid))
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception as e:
        logger.warning("mentor_gate_state read failed, falling open: %s", e)
        return None


def _write_shared(uid: str, state: Dict[str, Any], ttl: int, redis_client: Any = None) -> bool:
    clean_uid = _clean_id(uid)
    clean_state = _clean_state(state)
    if not clean_uid or clean_state is None:
        return False
    valid_ttl = _clean_ttl(ttl, STATE_TTL_SECONDS)
    try:
        r = _resolve_redis(redis_client)
        if r is None:
            return False
        payload = json.dumps(clean_state, default=str)
        r.set(_redis_key(clean_uid), payload, ex=valid_ttl)
        return True
    except Exception as e:
        logger.warning("mentor_gate_state write failed: %s", e)
        return False


def _claim_shared(uid: str, ttl: int = CLAIM_TTL_SECONDS, redis_client: Any = None) -> bool:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False
    valid_ttl = _clean_ttl(ttl, CLAIM_TTL_SECONDS)
    try:
        r = _resolve_redis(redis_client)
        if r is None:
            # Fall open on cache outage: do not block mentor
            return True
        return bool(r.set(_claim_key(clean_uid), "1", nx=True, ex=valid_ttl))
    except Exception as e:
        logger.warning("mentor_gate_state claim failed, falling open: %s", e)
        return True


def _release_shared(uid: str, redis_client: Any = None) -> None:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return
    try:
        r = _resolve_redis(redis_client)
        if r is not None:
            r.delete(_claim_key(clean_uid))
    except Exception as e:
        logger.warning("mentor_gate_state release failed: %s", e)


def read(uid: str, *, redis_client: Any = None) -> Optional[Dict[str, Any]]:
    """Last gate-evaluation record for a user, or None when there is none."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return None
    state = _read_local(clean_uid)
    if state is not None:
        return state
    remote = _read_shared(clean_uid, redis_client=redis_client) if redis_client is not None else _read_shared(clean_uid)
    if remote is not None:
        _write_local(clean_uid, remote, STATE_TTL_SECONDS)
    return remote


def read_authoritative(uid: str, *, redis_client: Any = None) -> Optional[Dict[str, Any]]:
    """Shared-tier read that bypasses (and refreshes) the local mirror.

    The mirror can be stale the moment any other host records an evaluation,
    so an eligibility decision must be made against the authority, not against
    a possibly-outdated copy. Only the "evaluated recently -> skip" answer is
    allowed to come from the mirror.
    """
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return None
    remote = _read_shared(clean_uid, redis_client=redis_client) if redis_client is not None else _read_shared(clean_uid)
    if remote is not None:
        _write_local(clean_uid, remote, STATE_TTL_SECONDS)
    return remote


def claim(uid: str, ttl: int = CLAIM_TTL_SECONDS, *, redis_client: Any = None) -> bool:
    """Try to become the one worker evaluating this user right now."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False
    valid_ttl = _clean_ttl(ttl, CLAIM_TTL_SECONDS)
    return (
        _claim_shared(clean_uid, valid_ttl, redis_client=redis_client)
        if redis_client is not None
        else _claim_shared(clean_uid, valid_ttl)
    )


def release(uid: str, *, redis_client: Any = None) -> None:
    """Best-effort release; the TTL bounds a holder that crashes first."""
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return
    if redis_client is not None:
        _release_shared(clean_uid, redis_client=redis_client)
    else:
        _release_shared(clean_uid)


def record(uid: str, state: Dict[str, Any], ttl: int = STATE_TTL_SECONDS, *, redis_client: Any = None) -> None:
    """Persist a gate evaluation.

    Shared tier first, mirror only after it succeeds: an evaluation that never
    reached the shared tier must not throttle this pod either, or a Redis
    outage would silently tighten the debounce instead of falling open.
    """
    clean_uid = _clean_id(uid)
    clean_state = _clean_state(state)
    if not clean_uid or clean_state is None:
        return
    valid_ttl = _clean_ttl(ttl, STATE_TTL_SECONDS)
    write_ok = (
        _write_shared(clean_uid, clean_state, valid_ttl, redis_client=redis_client)
        if redis_client is not None
        else _write_shared(clean_uid, clean_state, valid_ttl)
    )
    if write_ok:
        _write_local(clean_uid, clean_state, valid_ttl)
    else:
        with _local_lock:
            _local.pop(clean_uid, None)
