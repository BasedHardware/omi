"""Bounded authorization decisions owned by one task attempt, never a process."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
from threading import RLock

TOKEN_FIELD = 'memo_token'
SCHEMA_FIELD = 'memo_schema'
TOKEN_SCHEMA = 1


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


def with_batch_privacy_attempt(function):
    if inspect.iscoroutinefunction(function):

        @wraps(function)
        async def wrapped(*args, **kwargs):
            with batch_privacy_attempt():
                return await function(*args, **kwargs)

    else:

        @wraps(function)
        def wrapped(*args, **kwargs):
            with batch_privacy_attempt():
                return function(*args, **kwargs)

    return wrapped
