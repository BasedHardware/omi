"""The mentor relevance gate's debounce record — one owner for both storage tiers.

The realtime path that evaluates the gate runs on two hosts (`routers/listen/
transcripts.py` and `routers/pusher.py` both reach
`_async_trigger_realtime_integrations`), so the record cannot be process-local:
each host would otherwise evaluate once inside the same debounce window and the
throttle would be worth exactly half of what it claims. Redis is the authority.

The process-local mirror in front of it is a latency choice, not a second source
of truth: the common case is "this pod evaluated this user seconds ago", and that
answer should not cost a Redis round trip on the realtime path. It is only ever
written from a shared read or a shared write, never independently.

Redis failures fall open (return None -> evaluate), matching every other
throttle on this path: a cache outage must not silence the mentor.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# The record carries a per-UTC-day evaluation counter as well as the debounce
# timestamp, so it has to outlive the debounce window and expire just past a day
# boundary. 25 hours matches the daily proactive-notification counter.
STATE_TTL_SECONDS = 90000

# Expired local entries are dropped when their own key is read again, so a churned
# user's key would otherwise sit on a long-lived process forever. Bound the map.
_MAX_LOCAL_ENTRIES = 50000

_local: Dict[str, tuple[Dict[str, Any], float]] = {}


def _redis_key(uid: str) -> str:
    return f'{uid}:mentor_gate_eval_state'


def _read_local(uid: str) -> Optional[Dict[str, Any]]:
    entry = _local.get(uid)
    if entry is None:
        return None
    state, expires_at = entry
    if expires_at < time.time():
        del _local[uid]
        return None
    return state


def _write_local(uid: str, state: Dict[str, Any], ttl: int) -> None:
    now = time.time()
    _local[uid] = (dict(state), now + ttl)
    if len(_local) > _MAX_LOCAL_ENTRIES:
        for key in [k for k, (_s, expires_at) in _local.items() if expires_at < now]:
            del _local[key]
        overflow = len(_local) - _MAX_LOCAL_ENTRIES
        if overflow > 0:
            for key in sorted(_local, key=lambda k: _local[k][1])[:overflow]:
                del _local[key]


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


def _write_shared(uid: str, state: Dict[str, Any], ttl: int) -> None:
    try:
        from database.redis_db import r

        r.set(_redis_key(uid), json.dumps(state), ex=ttl)
    except Exception as e:
        logger.warning(f"mentor_gate_state write failed: {e}")


def read(uid: str) -> Optional[Dict[str, Any]]:
    """Last gate-evaluation record for a user, or None when there is none."""
    state = _read_local(uid)
    if state is not None:
        return state
    remote = _read_shared(uid)
    if remote is not None:
        _write_local(uid, remote, STATE_TTL_SECONDS)
    return remote


def record(uid: str, state: Dict[str, Any], ttl: int = STATE_TTL_SECONDS) -> None:
    """Persist a gate evaluation to both tiers."""
    _write_local(uid, state, ttl)
    _write_shared(uid, state, ttl)
