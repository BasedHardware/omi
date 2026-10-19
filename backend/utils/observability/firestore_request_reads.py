"""Pure request-scoped read accounting shared by ASGI and the SDK read probe."""

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestReadTrace:
    reads: float = 0
    closed: bool = False
    lock: Any = field(default_factory=threading.Lock)


_request_read_trace: ContextVar[RequestReadTrace | None] = ContextVar('firestore_request_read_trace', default=None)


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
    except Exception:
        pass
