"""Bounded authorization decisions owned by one task attempt, never a process."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
from threading import RLock
from datetime import datetime
import re

TOKEN_FIELD = 'memo_token'
SCHEMA_FIELD = 'memo_schema'
TOKEN_SCHEMA = 1
# Shared with the sync writer: unchanged authority fields must not become writes.
CONVERSATION_AUTHORITY_FIELDS = frozenset(
    {'deleted', 'sync_merged_into', 'record_lane_owner', 'uses_custom_stt', 'private_cloud_sync_enabled'}
)


def token_version(snapshot):
    """Missing schema, malformed tokens or unknown server revisions never certify reuse."""
    privacy = snapshot.to_dict() or {}
    token = privacy.get(TOKEN_FIELD)
    revision = getattr(snapshot, 'update_time', None)
    if not (
        snapshot.exists
        and isinstance(revision, datetime)
        and revision.tzinfo is not None
        and revision.utcoffset() is not None
        and type(privacy.get(SCHEMA_FIELD)) is int
        and privacy[SCHEMA_FIELD] == TOKEN_SCHEMA
        and isinstance(token, str)
        and re.fullmatch('[0-9a-f]{32}', token) is not None
        and not any(privacy.get(field) for field in ('blocked', 'purging', 'memo_blocked'))
    ):
        return None
    return (token, revision.isoformat(), getattr(revision, 'nanosecond', 0))


class PrivacyAttempt:
    def __init__(self):
        self._entries = OrderedDict()
        self._lock = RLock()
        self._closed = False

    def get(self, key, token):
        with self._lock:
            entry = self._entries.get(key)
            return entry[1] if not self._closed and entry is not None and entry[0] == token else None

    def forget(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def put(self, key, token, generation):
        with self._lock:
            if self._closed:
                return
            self._entries[key] = (token, generation)
            self._entries.move_to_end(key)
            while len(self._entries) > 1024:
                self._entries.popitem(last=False)

    def reset(self):
        with self._lock:
            self._entries.clear()

    def close(self):
        with self._lock:
            self._closed = True
            self._entries.clear()


_ATTEMPT: ContextVar[PrivacyAttempt | None] = ContextVar('batch_privacy_attempt', default=None)


def current_attempt():
    return _ATTEMPT.get()


@contextmanager
def batch_privacy_attempt():
    """Always start fresh, including nested job retries and reused executor threads.

    run_blocking propagates contextvars. Closing also disables late executor
    leaves that outlive cancellation of their owning async attempt.
    """
    attempt = PrivacyAttempt()
    token = _ATTEMPT.set(attempt)
    try:
        yield attempt
    finally:
        attempt.close()
        _ATTEMPT.reset(token)


@contextmanager
def scoped_privacy_attempt(lever_key: str):
    """Open a fresh attempt for one store call when none is current (lever bpp_attempt_scope).

    The attempt memo only certifies reuse with the memo token read inside the
    authorizing transaction, so an authority write (revoke/delete/purge) between two
    decisions in this scope rotates the token and the next decision walks live. An
    outer attempt, when present, is reused unchanged. Lever off: no-op.
    """
    if current_attempt() is not None:
        yield
        return
    from config.firestore_read_levers import lever_enabled

    if not lever_enabled('bpp_attempt_scope', lever_key):
        yield
        return
    with batch_privacy_attempt():
        yield


def with_batch_privacy_attempt(function):
    if inspect.iscoroutinefunction(function):

        @wraps(function)
        async def async_wrapped(*args, **kwargs):
            with batch_privacy_attempt():
                return await function(*args, **kwargs)

        return async_wrapped

    else:

        @wraps(function)
        def wrapped(*args, **kwargs):
            with batch_privacy_attempt():
                return function(*args, **kwargs)

    return wrapped
