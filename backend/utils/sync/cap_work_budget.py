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
    deadline = None if seconds is None else time.monotonic() + max(0, seconds)
    inherited = _DEADLINE.get()
    if inherited is not None:
        deadline = inherited if deadline is None else min(inherited, deadline)
    token = _DEADLINE.set(deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)
