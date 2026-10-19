"""Monotonic owner visit budget propagated into held-piece coordinators."""

from contextlib import contextmanager
from contextvars import ContextVar
import time

_DEADLINE: ContextVar[float | None] = ContextVar('cap_hold_work_deadline', default=None)


def exhausted() -> bool:
    deadline = _DEADLINE.get()
    return deadline is not None and time.monotonic() >= deadline


@contextmanager
def visit(seconds: float | None):
    token = _DEADLINE.set(None if seconds is None else time.monotonic() + max(0, seconds))
    try:
        yield
    finally:
        _DEADLINE.reset(token)
