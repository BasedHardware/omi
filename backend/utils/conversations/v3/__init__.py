"""Recording-derived conversations; independent of the episode engine."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Iterator, Mapping

from omi_logging import trace_context

_REQUEST_TRACE_ID: ContextVar[str] = ContextVar('v3_reconcile_trace_id', default='-')


@contextmanager
def bind_request_log_trace(headers: Mapping[bytes, bytes]) -> Iterator[None]:
    """Carry the validated request trace into the projection worker."""
    trace = trace_context(headers)
    token = _REQUEST_TRACE_ID.set(trace[0] if trace else '-')
    try:
        yield
    finally:
        _REQUEST_TRACE_ID.reset(token)


def request_log_trace_id() -> str:
    return _REQUEST_TRACE_ID.get()


class Conflict(RuntimeError):
    """Retryable v3 ownership and source-revision conflicts."""


def preview_wakes(rows, recordings) -> dict[str, datetime]:
    """Keep one recording pending per preview so the existing sweep can recover its deadline."""
    wakes: dict[str, datetime] = {}
    for row in rows:
        due = row.get('_v3_preview_due_at')
        if not isinstance(due, datetime):
            continue
        rid = next(
            (
                rid
                for rid in row.get('v3_recording_ids', ())
                if rid in recordings and not recordings[rid].get('deleted')
            ),
            None,
        )
        if rid is not None:
            wakes[rid] = min(due, wakes.get(rid, due))
    return wakes
