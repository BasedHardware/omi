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

_local: Dict[str, tuple[Dict[str, Any], float]] = {}
# The mirror is read and written from the shared db/postprocess executors, so
# every access is guarded: two workers expiring the same entry must not turn
# `del` into a KeyError that aborts the mentor pipeline.
_local_lock = threading.Lock()


def _clean_uid(uid: object) -> Optional[str]:
    if isinstance(uid, str):
        cleaned = uid.strip()
        return cleaned if cleaned else None
    return None


def _safe_ttl(ttl: object, default: int) -> int:
    try:
        val = int(ttl)  # type: ignore[arg-type]
        return val if val > 0 else default
    except (TypeError, ValueError):
        return default


def _redis_key(uid: str) -> str:
    return f'{uid}:mentor_gate_eval_state'


def _claim_key(uid: str) -> str:
    return f'{uid}:mentor_gate_eval_claim'


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
    if not isinstance(state, dict):
        return
    now = time.time()
    with _local_lock:
        _local[uid] = (dict(state), now + ttl)
        if len(_local) > _MAX_LOCAL_ENTRIES:
            for key in [k for k, (_s, expires_at) in _local.items() if expires_at < now]:
                _local.pop(key, None)
            overflow = len(_local) - _MAX_LOCAL_ENTRIES
            if overflow > 0:
                for key in list(_local.keys())[:overflow]:
                    _local.pop(key, None)


def _read_shared(uid: str) -> Optional[Dict[str, Any]]:
    try:
        from database.redis_db import r

        raw = r.get(_redis_key(uid))
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception as e:
        logger.warning(f"mentor_gate_state read failed, falling open: {e}")
        return None


def _write_shared(uid: str, state: Dict[str, Any], ttl: int) -> bool:
    if not isinstance(state, dict):
        return False
    try:
        from database.redis_db import r

        r.set(_redis_key(uid), json.dumps(state), ex=ttl)
        return True
    except Exception as e:
        logger.warning(f"mentor_gate_state write failed: {e}")
        return False


def _claim_shared(uid: str, ttl: int) -> bool:
    try:
        from database.redis_db import r

        return bool(r.set(_claim_key(uid), '1', nx=True, ex=ttl))
    except Exception as e:
        logger.warning(f"mentor_gate_state claim failed, falling open: {e}")
        return True


def _release_shared(uid: str) -> None:
    try:
        from database.redis_db import r

        r.delete(_claim_key(uid))
    except Exception as e:
        logger.warning(f"mentor_gate_state release failed: {e}")


def read(uid: str) -> Optional[Dict[str, Any]]:
    """Last gate-evaluation record for a user, or None when there is none."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return None
    state = _read_local(clean_uid)
    if state is not None:
        return state
    remote = _read_shared(clean_uid)
    if remote is not None:
        _write_local(clean_uid, remote, STATE_TTL_SECONDS)
    return remote


def read_authoritative(uid: str) -> Optional[Dict[str, Any]]:
    """Shared-tier read that bypasses (and refreshes) the local mirror.

    The mirror can be stale the moment any other host records an evaluation,
    so an eligibility decision must be made against the authority, not against
    a possibly-outdated copy. Only the "evaluated recently -> skip" answer is
    allowed to come from the mirror.
    """
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return None
    remote = _read_shared(clean_uid)
    if remote is not None:
        _write_local(clean_uid, remote, STATE_TTL_SECONDS)
    return remote


def claim(uid: str, ttl: int = CLAIM_TTL_SECONDS) -> bool:
    """Try to become the one worker evaluating this user right now."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return True
    return _claim_shared(clean_uid, _safe_ttl(ttl, CLAIM_TTL_SECONDS))


def release(uid: str) -> None:
    """Best-effort release; the TTL bounds a holder that crashes first."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return
    _release_shared(clean_uid)


def record(uid: str, state: Dict[str, Any], ttl: int = STATE_TTL_SECONDS) -> None:
    """Persist a gate evaluation.

    Shared tier first, mirror only after it succeeds: an evaluation that never
    reached the shared tier must not throttle this pod either, or a Redis
    outage would silently tighten the debounce instead of falling open.
    """
    clean_uid = _clean_uid(uid)
    if not clean_uid or not isinstance(state, dict):
        logger.warning("mentor_gate_state record ignored invalid uid or state")
        return
    safe_ttl = _safe_ttl(ttl, STATE_TTL_SECONDS)
    if _write_shared(clean_uid, state, safe_ttl):
        _write_local(clean_uid, state, safe_ttl)
    else:
        with _local_lock:
            _local.pop(clean_uid, None)
