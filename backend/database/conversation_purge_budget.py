"""Per-delivery limits for the conversation batch-purge worker."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from google.api_core.retry import Retry

WORK_SECONDS = 90.0
SETTLEMENT_SECONDS = 15.0
WORK_READS = 4096
SETTLEMENT_READS = 512
MAX_UNITS = 40
NO_STREAM_RETRY = Retry(predicate=lambda _: False)


class WorkLimit(Exception):
    """Stop and hand off the last durable position."""


@dataclass
class Dispatch:
    started: float = field(default_factory=time.monotonic)
    reads: int = WORK_READS
    reserve: int = SETTLEMENT_READS
    units: int = MAX_UNITS

    @property
    def work_left(self) -> float:
        return self.started + WORK_SECONDS - time.monotonic()

    @property
    def settlement_left(self) -> float:
        return self.work_left + SETTLEMENT_SECONDS

    def charge(self, reads: int) -> None:
        if _SETTLING.get():
            if self.settlement_left <= 0 or reads > self.reserve:
                raise TimeoutError('batch purge settlement budget exhausted')
            self.reserve -= reads
        else:
            if self.work_left <= 0 or reads > self.reads:
                raise WorkLimit()
            self.reads -= reads


_ACTIVE: ContextVar[Dispatch | None] = ContextVar('conversation_purge_dispatch', default=None)
_SETTLING: ContextVar[bool] = ContextVar('conversation_purge_settlement', default=False)


def current() -> Dispatch | None:
    return _ACTIVE.get()


@contextmanager
def activate(budget: Dispatch):
    token = _ACTIVE.set(budget)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


@contextmanager
def settling():
    token = _SETTLING.set(True)
    try:
        yield
    finally:
        _SETTLING.reset(token)


def timeout() -> float | None:
    budget = current()
    if budget is None:
        return None
    budget.charge(0)
    return min(5.0, budget.settlement_left if _SETTLING.get() else budget.work_left)


def start_unit(default_wait: float) -> float:
    budget = current()
    if budget is None:
        return default_wait
    if not budget.units or budget.work_left <= 0 or budget.reads < 128:
        raise WorkLimit()
    budget.units -= 1
    return min(default_wait, max(0.0, budget.work_left - 5.0), 3.0)


def stream_options() -> dict[str, Any]:
    return {'retry': NO_STREAM_RETRY} if current() is not None else {}


def charge_rpc(name: str, request: Any) -> None:
    budget = current()
    if budget is None:
        return
    if name in ('get_document', 'update_document', 'delete_document', 'create_document'):
        reads = int(name == 'get_document')
    elif name == 'batch_get_documents':
        docs = request.get('documents') if isinstance(request, dict) else request.documents
        reads = len(docs)
    elif name == 'run_query':
        query = request.get('structured_query') if isinstance(request, dict) else request.structured_query
        if not query.limit or query.offset:
            raise RuntimeError('batch purge query requires an explicit limit and no offset')
        reads = query.limit
    elif name in ('list_documents', 'run_aggregation_query', 'partition_query', 'list_collection_ids'):
        raise RuntimeError('unmetered read in conversation batch purge')
    else:
        reads = 0
    budget.charge(reads)
