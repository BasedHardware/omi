"""Redis marker for the episodes client capability (``utils/episodes/client_gate.py``).

``episodes:client_seen:{uid}`` exists while the user's app has called a
``/v1/episodes`` route within the marker TTL. Uses the shared ``redis_db``
connection, looked up at call time.
"""

from __future__ import annotations

import logging
from typing import Optional

from database import redis_db

logger = logging.getLogger(__name__)


def _key(uid: str) -> str:
    return f'episodes:client_seen:{uid}'


def has_client_seen(uid: str) -> bool:
    """True while the marker exists. Fails closed: a Redis fault reads as "no capable client"."""
    try:
        return bool(redis_db.r.exists(_key(uid)))
    except Exception as exc:
        logger.warning('event=episodes_client_seen_read outcome=error exception_type=%s', type(exc).__name__)
        return False


def get_client_seen_ttl(uid: str) -> Optional[int]:
    """Seconds left on the marker; None when absent or unreadable."""
    try:
        ttl = redis_db.r.ttl(_key(uid))
    except Exception as exc:
        logger.warning('event=episodes_client_seen_ttl outcome=error exception_type=%s', type(exc).__name__)
        return None
    return ttl if isinstance(ttl, int) and ttl >= 0 else None


def set_client_seen(uid: str, ttl: int) -> bool:
    """Writes (or refreshes) the marker. Never raises; False when the write did not land."""
    try:
        redis_db.r.set(_key(uid), '1', ex=ttl)
        return True
    except Exception as exc:
        logger.warning('event=episodes_client_seen_write outcome=error exception_type=%s', type(exc).__name__)
        return False
