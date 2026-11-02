"""Pure request-scoped read accounting shared by ASGI and the SDK read probe."""

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass
class RequestReadTrace:
    reads: float = 0
    closed: bool = False
    lock: Any = field(default_factory=threading.Lock)
    components: dict[str, float] = field(default_factory=dict)


class ReadComponent(StrEnum):
    AUTH = 'auth'
    INCOMPLETE = 'incomplete'
    COMPLETED = 'completed'
    LEGACY = 'legacy'
    COUNT = 'count'
    OTHER = 'other'


_request_read_trace: ContextVar[RequestReadTrace | None] = ContextVar('firestore_request_read_trace', default=None)
_read_component: ContextVar[ReadComponent] = ContextVar('firestore_read_component', default=ReadComponent.OTHER)


@contextmanager
def read_component(component: ReadComponent):
    token = _read_component.set(component)
    try:
        yield
    finally:
        _read_component.reset(token)


def bind_request_read_trace(trace: RequestReadTrace):
    return _request_read_trace.set(trace)


def reset_request_read_trace(token: Any) -> None:
    _request_read_trace.reset(token)


def trace_request_reads(amount: float) -> None:
    # The same holder reaches sync dependencies/executors through copied context.
    # Closing the holder revokes detached workers and response background tasks.
    try:
        trace = _request_read_trace.get()
        if trace is not None:
            with trace.lock:
                if not trace.closed:
                    trace.reads += amount
                    component = _read_component.get().value
                    trace.components[component] = trace.components.get(component, 0) + amount
    except Exception:
        pass
