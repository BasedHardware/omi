"""Inferred client capability: episode work runs only for users whose app can show it.

An app that supports episodes calls ``/v1/episodes/live`` at startup and polls
it while a live surface is on screen. Old mobile builds, the desktop app and web
never call any ``/v1/episodes`` route. So every episodes API call by an admitted
uid leaves a sticky Redis marker (``episodes:client_seen:{uid}``, TTL
``CLIENT_SEEN_TTL_SECONDS``), and listen and the finalizer spend money only when
both ``episodes_enabled_for(uid)`` and the marker hold.

The marker is rewritten at most once per ``CLIENT_SEEN_REFRESH_SECONDS`` per
uid: an in-process memo skips Redis entirely between refreshes, and on a memo
miss the marker's remaining TTL shows whether another replica already refreshed
it this hour. Reads fail closed (no marker, no spend); writes never raise.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from config.episodes import CLIENT_SEEN_REFRESH_SECONDS, CLIENT_SEEN_TTL_SECONDS, episodes_enabled_for
from database import episodes_client_seen as marker_db

_MEMO_MAX = 50_000
_memo: dict[str, float] = {}
_memo_lock = threading.Lock()


def _claim(uid: str, wall: float) -> bool:
    """True when this process should consider a refresh now; records the attempt."""
    with _memo_lock:
        last = _memo.get(uid)
        if last is not None and wall - last < CLIENT_SEEN_REFRESH_SECONDS:
            return False
        _memo[uid] = wall
        if len(_memo) > _MEMO_MAX:
            stale = [key for key, seen in _memo.items() if wall - seen >= CLIENT_SEEN_REFRESH_SECONDS]
            for key in stale:
                del _memo[key]
            if len(_memo) > _MEMO_MAX:
                _memo.clear()
                _memo[uid] = wall
        return True


def _release(uid: str) -> None:
    with _memo_lock:
        _memo.pop(uid, None)


def note_client_seen(uid: str, *, now: Optional[float] = None) -> bool:
    """Records that ``uid``'s app reached the episodes API. Returns True only when it wrote."""
    if not uid:
        return False
    wall = time.time() if now is None else now
    if not _claim(uid, wall):
        return False
    remaining = marker_db.get_client_seen_ttl(uid)
    if remaining is not None and remaining > CLIENT_SEEN_TTL_SECONDS - CLIENT_SEEN_REFRESH_SECONDS:
        return False
    if marker_db.set_client_seen(uid, CLIENT_SEEN_TTL_SECONDS):
        return True
    # The write did not land: let the next call retry instead of waiting out the memo.
    _release(uid)
    return False


def client_seen(uid: str) -> bool:
    """True when ``uid``'s app called the episodes API within the marker TTL. Blocking (Redis)."""
    return bool(uid) and marker_db.has_client_seen(uid)


def episode_work_enabled(uid: str) -> bool:
    """Admission and a capable client. Blocking (Redis): call from a worker thread."""
    return episodes_enabled_for(uid) and client_seen(uid)


def reset_for_tests() -> None:
    with _memo_lock:
        _memo.clear()
