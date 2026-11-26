"""A caller's deadline over pre-recorded provider requests and the language probes they may trigger.

Owns ``verification_stt_deadline`` and the timeouts it implies. Constraint it upholds: every
request sent under one deadline (provider, vendor language probe, self-hosted language gate) has
its connect, pool, write and read timeouts share what is left, so none outlives the caller's budget.
A leaf: it imports no other ``utils.stt`` module, so ``pre_recorded``, ``batch_language`` and
``language_gate`` can all import it at top level.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional, TypeVar

import httpx

# A language probe's own bound: the vendor probe is httpx.Timeout(8, connect=2), the gate (6, connect=2).
PROBE_SECONDS = 10.0
# A caller's monotonic budget for its provider requests and language probes.
verification_deadline: ContextVar[Optional[float]] = ContextVar('verification_stt_deadline', default=None)

_Default = TypeVar('_Default')


@contextmanager
def verification_stt_deadline(deadline: float):
    """Limit every provider request and language probe sent inside to the caller's budget."""
    token = verification_deadline.set(deadline)
    try:
        yield
    finally:
        verification_deadline.reset(token)


def budget_timeout(remaining: float) -> httpx.Timeout:
    """One request inside ``remaining`` seconds: connect, pool, write and read share it, not each take it."""
    connect, pool, write = min(remaining * 0.1, 3.0), min(remaining * 0.05, 1.0), remaining * 0.25
    return httpx.Timeout(connect=connect, pool=pool, write=write, read=remaining - connect - pool - write)


def probe_timeout(default: _Default, seconds: float = PROBE_SECONDS) -> _Default | httpx.Timeout:
    """A language probe's timeout: ``default``, or at most ``seconds`` of what is left of the caller's deadline."""
    deadline = verification_deadline.get()
    if deadline is None:
        return default
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('language probe deadline expired')
    return budget_timeout(min(remaining, seconds))
