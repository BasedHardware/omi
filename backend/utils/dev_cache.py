"""Tiny, dependency-light cache of developer status (does a user hold at least
one developer API key).

This lives in its own module, separate from the heavyweight ``app_integrations``,
so the developer/dev-key router can invalidate it on a key change without pulling
the notification/LLM import chain into that lightweight surface. The proactive
notification cap exempts developers and is checked on every attempt, so caching
keeps the check off the Firestore hot path; the short TTL bounds staleness and the
explicit invalidate makes a create/delete take effect immediately.
"""

import threading
from typing import Optional

from cachetools import TTLCache

_DEV_STATUS_CACHE: TTLCache[str, bool] = TTLCache(maxsize=4096, ttl=300)
_lock = threading.Lock()


def get_cached_developer(uid: str) -> Optional[bool]:
    """Cached developer status, or None when not cached."""
    with _lock:
        return _DEV_STATUS_CACHE.get(uid)


def set_cached_developer(uid: str, is_developer: bool) -> None:
    with _lock:
        _DEV_STATUS_CACHE[uid] = is_developer


def invalidate_developer_cache(uid: str) -> None:
    """Drop a user's cached developer status so a dev-key create/delete takes
    effect immediately instead of waiting out the TTL — otherwise a brand-new
    developer could stay capped, or a just-revoked one stay exempt, until the
    entry expires."""
    with _lock:
        _DEV_STATUS_CACHE.pop(uid, None)
