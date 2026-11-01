"""Bounded, invocation-local discovery snapshots; never mutation authority."""

from contextvars import ContextVar
from functools import wraps
import threading
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from config.firestore_read_levers import lever_enabled

P = ParamSpec('P')
R = TypeVar('R')
MAX_ENTRIES = 128


class _Memo:
    def __init__(self):
        self.entries: dict = {}
        self.lock = threading.Lock()
        self.closed = False

    def entry(self, key, client):
        with self.lock:
            if self.closed:
                return None
            if key not in self.entries:
                if len(self.entries) >= MAX_ENTRIES:
                    return None
                # Retain the client so its id cannot be reused during this job.
                self.entries[key] = (client, threading.Lock(), {})
            return self.entries[key]

    def close(self):
        with self.lock:
            self.closed = True
            self.entries.clear()


_memo: ContextVar[_Memo | None] = ContextVar('sync_snapshot_resolve_memo', default=None)


def sync_snapshot_resolve_job(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Fresh scope per delivery/pipeline invocation, including retries and nesting.

    run_blocking propagates this context to executor leaves. Closing also
    disables it in copied contexts retained by a later task or callback.
    """

    @wraps(fn)
    async def scoped(*args: P.args, **kwargs: P.kwargs) -> R:
        memo = _Memo()
        token = _memo.set(memo)
        try:
            return await fn(*args, **kwargs)
        finally:
            memo.close()
            _memo.reset(token)

    return scoped


def memoize_resolve(fn):
    """Coalesce only discovery reads; keep the original resolver/metric caller."""

    @wraps(fn)
    def resolve(uid: str, conversation_id: str, *, client_factory: Callable[[], Any], max_hops: int = 16):
        memo = _memo.get()
        if (
            memo is None
            or memo.closed
            or not lever_enabled('sync_snapshot_resolve_cache', uid)
            or max_hops <= 0
            or not conversation_id
            or '/' in conversation_id
            or len(conversation_id.encode()) > 256
        ):
            return fn(uid, conversation_id, client_factory=client_factory, max_hops=max_hops)
        client = client_factory()
        entry = memo.entry((uid, id(client), conversation_id, max_hops), client)
        if entry is None:
            return fn(uid, conversation_id, client_factory=lambda: client, max_hops=max_hops)
        _, lock, result = entry
        # Single-flight per key; unrelated conversations never serialize their IO.
        with lock:
            if memo.closed:
                return fn(uid, conversation_id, client_factory=lambda: client, max_hops=max_hops)
            if 'snapshot' not in result:
                snapshot = fn(uid, conversation_id, client_factory=lambda: client, max_hops=max_hops)
                if not memo.closed:
                    result['snapshot'] = snapshot
                return snapshot
            return result['snapshot']

    return resolve
