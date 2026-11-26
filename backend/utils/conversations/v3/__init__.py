"""Recording-derived conversations; independent of the episode engine."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
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


@dataclass
class UnlockedPage:
    remaining: frozenset[str] = frozenset()
    cursor: str | None = None
    seeds: tuple[int, int] = (0, 0)  # (pending, unlocked) seeds this load read
    pending_ids: tuple[str, ...] = ()  # the pending recordings this load seeded
    quarantined: frozenset[str] = frozenset()  # pending recordings set aside for size (v3_size_quarantine)


def preview_wakes(rows, recordings) -> dict[str, datetime]:
    """Keep one recording pending per preview, and each source a held Finish waits on, until its deadline."""
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
    # A held Finish keeps its own recording, and every source whose speech after the cut waits, pending
    # until the hold ends (outline.HOLD_UNTIL): the next load still finds the cut and that speech.
    for rid, recording in recordings.items():
        due = recording.get('_v3_hold_until')
        if isinstance(due, datetime) and not recording.get('deleted'):
            wakes[rid] = min(due, wakes.get(rid, due))
    return wakes
