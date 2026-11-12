"""A wall-clock deadline for every RPC made inside a bounded destructive unit or run.

Per-request ``timeout`` arguments do not bound SDK-internal retries (the GCS
generation-match policy retries for 120 s) or calls the caller never sees
(transaction begin/commit/rollback). Inside ``rpc_deadline`` each call on a
bound Firestore or storage client runs once, with no SDK retry, and with a
timeout no longer than the time left; past the deadline it raises before
sending. This bounds latency only: a request already sent can still take
effect remotely after its client-side timeout, which is why remote erasures
are tracked as in flight on the account gate (``legal_holds``).
Outside the scope a bound client behaves exactly as before.
"""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

_DEADLINE: ContextVar[float | None] = ContextVar('rpc_deadline', default=None)
_MARK = '_omi_rpc_deadline_bound'
# GAPIC methods of google.cloud.firestore_v1's FirestoreClient used by reads, queries and transactions.
_FIRESTORE_METHODS = (
    'batch_get_documents',
    'batch_write',
    'begin_transaction',
    'commit',
    'create_document',
    'delete_document',
    'get_document',
    'list_documents',
    'rollback',
    'run_aggregation_query',
    'run_query',
    'update_document',
)
# A rollback only releases server-side locks; let it out briefly even past the deadline.
ROLLBACK_GRACE_SECONDS = 1.0


class RpcDeadlineExceeded(TimeoutError):
    """The unit's deadline passed; the call was not sent."""


def now() -> float:
    return time.monotonic()


def remaining() -> float | None:
    deadline = _DEADLINE.get()
    return None if deadline is None else deadline - now()


@contextmanager
def rpc_deadline(at: float) -> Iterator[None]:
    """Bound every RPC on bound clients in this context by monotonic time ``at`` (nested scopes only tighten)."""
    outer = _DEADLINE.get()
    token = _DEADLINE.set(at if outer is None else min(at, outer))
    try:
        yield
    finally:
        _DEADLINE.reset(token)


@contextmanager
def override(at: float) -> Iterator[None]:
    """Replace the current deadline with ``at``; callers cap ``at`` by any deadline they must still honour."""
    token = _DEADLINE.set(at)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def current() -> float | None:
    return _DEADLINE.get()


def _left_or_raise(name: str) -> float | None:
    left = remaining()
    if left is None:
        return None
    if name == 'rollback':
        return max(left, ROLLBACK_GRACE_SECONDS)
    if left <= 0:
        raise RpcDeadlineExceeded(f'{name} not sent: unit deadline passed')
    return left


def _bounded_gapic(name: str, call: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(call)
    def bounded(*args: Any, **kwargs: Any) -> Any:
        left = _left_or_raise(name)
        if left is None:
            return call(*args, **kwargs)
        kwargs['retry'] = None
        kwargs['timeout'] = left
        return call(*args, **kwargs)

    return bounded


def bind_firestore_client(client: Any) -> Any:
    """Make ``client``'s RPCs honour ``rpc_deadline``; idempotent, a no-op for non-SDK clients."""
    api = getattr(client, '_firestore_api', None)  # the SDK's GAPIC client: the one path every RPC takes
    if api is None or getattr(api, _MARK, False) is True:
        return client
    for name in _FIRESTORE_METHODS:
        call = getattr(api, name, None)
        if callable(call):
            setattr(api, name, _bounded_gapic(name, call))
    setattr(api, _MARK, True)
    return client


def bind_storage_client(client: Any) -> Any:
    """Cap ``client``'s HTTP timeouts by ``rpc_deadline`` and refuse to send past it; idempotent."""
    session = getattr(client, '_http', None)  # google-auth AuthorizedSession shared by every storage call
    request = getattr(session, 'request', None)
    if session is None or not callable(request) or getattr(session, _MARK, False) is True:
        return client

    @functools.wraps(request)
    def bounded(*args: Any, **kwargs: Any) -> Any:
        left = _left_or_raise('storage')
        if left is not None:
            # No max_allowed_time: it raises only after a response already arrived,
            # which would disguise a definitive outcome as an unknown one.
            timeout = kwargs.get('timeout')
            if isinstance(timeout, tuple):
                kwargs['timeout'] = tuple(min(float(part), left) for part in timeout)
            else:
                kwargs['timeout'] = left if timeout is None else min(float(timeout), left)
        return request(*args, **kwargs)

    setattr(session, 'request', bounded)
    setattr(session, _MARK, True)
    return client


__all__ = [
    'RpcDeadlineExceeded',
    'bind_firestore_client',
    'bind_storage_client',
    'current',
    'now',
    'override',
    'remaining',
    'rpc_deadline',
]
