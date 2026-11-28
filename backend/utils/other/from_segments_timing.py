"""Bounded timing for the from-segments HTTP waiter and its existing worker."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from time import monotonic
from typing import Callable, Iterator, Literal, TypeVar

from utils.journey_metrics_contract import CLIENT_KINDS

logger = logging.getLogger(__name__)

_Stage = Literal['intake_finished_ms', 'notes_started_ms', 'persisted_ms']
_T = TypeVar('_T')


class FromSegmentsTiming:
    """Share only elapsed times and bounded labels across executor handoffs."""

    def __init__(self, started: float, client_kind: str, keyed: bool):
        self._started = started
        self._lock = Lock()
        self._client_kind = client_kind if client_kind in CLIENT_KINDS else 'unknown'
        self._keyed = keyed
        self._http_status: int | None = None
        self._offsets: dict[str, float | bool] = {}

    def intake(self, prepare: Callable[[], _T]) -> _T:
        try:
            return prepare()
        finally:
            self.mark('intake_finished_ms')

    def _elapsed_ms(self) -> float:
        return round((monotonic() - self._started) * 1000, 2)

    def mark(self, stage: _Stage) -> None:
        with self._lock:
            self._offsets.setdefault(stage, self._elapsed_ms())

    def finish_notes(self, succeeded: bool) -> None:
        with self._lock:
            self._offsets['notes_finished_ms'] = self._elapsed_ms()
            self._offsets['notes_succeeded'] = succeeded

    def _snapshot(self, phase: Literal['http', 'worker']) -> dict[str, object]:
        return {
            'event': 'from_segments_timing',
            'phase': phase,
            'client_kind': self._client_kind,
            'keyed': self._keyed,
            'http_status': self._http_status,
            **self._offsets,
        }

    def finish_http(self, status: int | None) -> None:
        with self._lock:
            self._http_status = status
            self._offsets['http_finished_ms'] = self._elapsed_ms()
            fields = self._snapshot('http')
        _emit(fields)

    @contextmanager
    def worker(self) -> Iterator[None]:
        token = _worker_timing.set(self)
        try:
            yield
        finally:
            _worker_timing.reset(token)
            with self._lock:
                self._offsets['worker_finished_ms'] = self._elapsed_ms()
                fields = self._snapshot('worker') if 'http_finished_ms' in self._offsets else None
            if fields is not None:
                _emit(fields)


def _emit(fields: dict[str, object]) -> None:
    try:
        logger.info(
            'from_segments_timing %s', json.dumps(fields, separators=(',', ':')), extra={**fields, 'omit_trace': True}
        )
    except Exception:
        # A logging sink must not change the request or worker outcome.
        pass


_worker_timing: ContextVar[FromSegmentsTiming | None] = ContextVar('from_segments_worker_timing', default=None)


def from_segments_worker_timing() -> FromSegmentsTiming | None:
    return _worker_timing.get()


def mark_from_segments_persisted(persisted: bool) -> None:
    timing = from_segments_worker_timing()
    if persisted and timing is not None:
        timing.mark('persisted_ms')
