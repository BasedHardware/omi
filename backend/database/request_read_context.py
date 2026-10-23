"""Request holders shared with lightweight runtimes; no Redis or serving imports."""

import copy
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
from typing import Any

from config.firestore_quick_reads import cohort_request_cache_enabled


@dataclass
class RequestReads:
    values: dict = field(default_factory=dict)
    lock: Any = field(default_factory=threading.RLock)
    closed: bool = False
    cohort_values: dict = field(default_factory=dict)


request_reads: ContextVar[RequestReads | None] = ContextVar('s4_request_reads', default=None)
bypass: ContextVar[bool] = ContextVar('s4_fresh_reads', default=False)


def cohort_memberships(uid, fetch):
    """Bounded request-only membership snapshot; errors/unknowns are never cached."""
    holder = request_reads.get()
    if holder is None or holder.closed or bypass.get() or not cohort_request_cache_enabled():
        return fetch()
    with holder.lock:
        if holder.closed:
            return fetch()
        if uid in holder.cohort_values:
            return copy.deepcopy(holder.cohort_values[uid])
        value = fetch()
        if value is not None and len(holder.cohort_values) < 64:
            holder.cohort_values[uid] = copy.deepcopy(value)
        return value
