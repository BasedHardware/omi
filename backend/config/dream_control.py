"""Dynamic operator kill switch with a ten-second, last-known-state cache."""

import asyncio
import threading
import time

_lock = threading.Lock()
_until = 0.0
_allowed = False
_refreshing = False


def load_flag():
    from database._client import get_firestore_client

    row = get_firestore_client().collection('dream_control').document('global').get(timeout=0.5).to_dict() or {}
    return row.get('enabled', True) is True


def refresh():
    global _until, _allowed, _refreshing
    with _lock:
        try:
            _allowed = load_flag()
        except Exception:
            # Deny until the first successful read; thereafter retain the last
            # observed state, including an operator stop, during an outage.
            pass
        finally:
            _until = time.monotonic() + 10
            _refreshing = False
    return _allowed


def allowed():
    global _refreshing
    if time.monotonic() < _until or _refreshing:
        return _allowed
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return refresh()
    # Async tool/model checks never perform Firestore IO on the event loop.
    # Transactional write fences run in the DB executor and also consult this
    # cache, so an observed disable applies to late effects within the TTL.
    from utils.executors import db_executor, submit_with_context

    _refreshing = True
    submit_with_context(db_executor, refresh)
    return _allowed
