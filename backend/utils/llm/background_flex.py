"""Declare Flex budget only at a durable background caller, before model dispatch."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from time import monotonic

from config.llm_spend import background_flex_retry_enabled

BUDGET_HEADER = 'X-Omi-Background-Flex-Budget-Ms'
SCOPED_FEATURES = frozenset({'conv_structure', 'memory_l1', 'conversation_v3_summary'})

# These sync call sites borrow a shared worker. Stay inside its existing 60s
# limit, leave 3s for gateway transport, and share one deadline across calls.
_MAX_WORKER_SECONDS = 57
_PUBLICATION_RESERVE_SECONDS = 15
_deadline: ContextVar[tuple[float, frozenset[str]] | None] = ContextVar('background_flex_deadline', default=None)


@contextmanager
def background_flex(closed_at: datetime | None, *, features: frozenset[str]):
    deadline = None
    if background_flex_retry_enabled() and isinstance(closed_at, datetime) and closed_at.tzinfo is not None:
        remaining = (closed_at + timedelta(hours=2) - datetime.now(timezone.utc)).total_seconds()
        deadline = (monotonic() + min(remaining - _PUBLICATION_RESERVE_SECONDS, _MAX_WORKER_SECONDS), features)
    token = _deadline.set(deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def budget_ms(feature: str) -> int:
    scope = _deadline.get()
    if scope is None or feature not in scope[1]:
        return 0
    return max(0, int((scope[0] - monotonic()) * 1000))
