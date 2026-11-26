"""Carry one scheduling claim through the canonical projector and its executors."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

from database.batch_pipeline_projection_outbox import Obligation, holds_claim
from database.batch_pipeline_projection_protocol import ProjectionBlocked

_delivery_claim: ContextVar[tuple[Obligation, str, Callable[[], float]] | None] = ContextVar(
    'projection_delivery_claim', default=None
)


@contextmanager
def fenced_delivery(key: Obligation, token: str, clock: Callable[[], float]):
    previous = _delivery_claim.set((key, token, clock))
    try:
        yield
    finally:
        _delivery_claim.reset(previous)


def assert_delivery_claim(segment_id: str, row: dict | Callable[[], dict]) -> None:
    delivery = _delivery_claim.get()
    if delivery is not None:
        key, token, clock = delivery
        if key.segment_id == segment_id:
            entry = row() if callable(row) else row
            if not holds_claim(entry, key, token, clock()):
                raise ProjectionBlocked('projection delivery claim lost')
