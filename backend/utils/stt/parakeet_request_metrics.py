"""Parakeet GPU request time by caller.

The Parakeet pool serves live app uploads, sync (fresh and backfill), batch
recovery, shadow scoring and voice messages through the same `/v1` and `/v2`
transcribe routes, so server-side latency cannot say how much pool time each
caller buys. Each backend caller times its own outbound request here; the sum
of `omi_parakeet_request_seconds` per caller is the request time that caller
holds on the pool. Metrics only: nothing here changes a request.

The caller is explicit (`parakeet_caller(...)`) or, inside a sync attempt,
derived from that attempt's lane. Anything else is `other`.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from prometheus_client import Histogram

CALLERS = (
    'app_proxy',
    'sync_fresh',
    'sync_backfill',
    'sync_unknown',
    'batch_recovery',
    'shadow',
    'voice_message',
    'other',
)
ROUTES = ('v1', 'v2')

PARAKEET_REQUEST_SECONDS = Histogram(
    'omi_parakeet_request_seconds',
    'Wall time of one backend HTTP request to Parakeet transcribe, by caller and route; includes failures',
    ['caller', 'route'],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 120, 180),
)

_SYNC_LANE_CALLERS = {'fresh': 'sync_fresh', 'backfill': 'sync_backfill'}
_caller: ContextVar[str | None] = ContextVar('parakeet_request_caller', default=None)


@contextmanager
def parakeet_caller(name: str) -> Iterator[None]:
    """Attribute Parakeet requests made in this context to `name`."""
    token = _caller.set(name if name in CALLERS else 'other')
    try:
        yield
    finally:
        _caller.reset(token)


def current_parakeet_caller() -> str:
    explicit = _caller.get()
    if explicit is not None:
        return explicit
    # Deferred: utils.chat imports this module, and router suites stub the
    # utils.observability package without its sync_phases submodule.
    from utils.observability.sync_phases import current_sync_lane

    lane = current_sync_lane()
    if lane is not None:
        return _SYNC_LANE_CALLERS.get(lane, 'sync_unknown')
    return 'other'


@contextmanager
def observe_parakeet_request(route: str, caller: str | None = None) -> Iterator[None]:
    """Time one outbound Parakeet request, success or failure."""
    resolved_caller = caller if caller in CALLERS else current_parakeet_caller()
    resolved_route = route if route in ROUTES else 'other'
    started = time.monotonic()
    try:
        yield
    finally:
        PARAKEET_REQUEST_SECONDS.labels(resolved_caller, resolved_route).observe(time.monotonic() - started)
