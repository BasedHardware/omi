"""Request/job-scoped MemorySystem cohort pin (WS-E §4, WS-L follow-up)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from utils.memory.memory_system import MemorySystem, resolve_memory_system

_pinned_memory_system: contextvars.ContextVar[Optional[tuple[str, MemorySystem]]] = contextvars.ContextVar(
    "_pinned_memory_system",
    default=None,
)


def pin_memory_system(uid: str, *, db_client: Any = None) -> MemorySystem:
    """Resolve and pin the memory cohort for one request / tool invocation."""
    system = resolve_memory_system(uid, db_client=db_client)
    _pinned_memory_system.set((uid, system))
    return system


def get_pinned_memory_system(*, uid: str) -> Optional[MemorySystem]:
    """Return the pinned cohort for ``uid`` when this request/job has pinned one."""
    pinned = _pinned_memory_system.get()
    if pinned is None:
        return None
    pinned_uid, system = pinned
    if pinned_uid != uid:
        return None
    return system


def resolve_pinned_memory_system(uid: str, *, db_client: Any = None) -> MemorySystem:
    """Use the request pin when set; otherwise resolve (unpinned call sites)."""
    pinned = get_pinned_memory_system(uid=uid)
    if pinned is not None:
        return pinned
    return resolve_memory_system(uid, db_client=db_client)


def clear_memory_system_pin() -> None:
    """Drop any active pin (test harness / explicit cleanup)."""
    _pinned_memory_system.set(None)


@contextmanager
def memory_system_request_scope(uid: str, *, db_client: Any = None) -> Iterator[MemorySystem]:
    """Pin cohort for a block; reset on exit so thread-pool workers do not leak pins."""
    system = resolve_memory_system(uid, db_client=db_client)
    token = _pinned_memory_system.set((uid, system))
    try:
        yield system
    finally:
        _pinned_memory_system.reset(token)
