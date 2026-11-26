"""A caller's deadline over pre-recorded provider requests and the language probes they may trigger.

Owns ``verification_stt_deadline`` and the timeouts it implies. Constraint it upholds: no wait of a
request sent under one deadline is longer than what is left of it. A provider request's connect,
pool, write and read timeouts share what is left, so the request as a whole ends inside it. A
language probe (vendor or self-hosted gate) keeps each of its own short default timeouts, each capped
to what is left, so near the deadline its phases together can run past it by at most those defaults.

A leaf: it imports no other ``utils.stt`` module, so ``pre_recorded``, ``batch_language`` and
``language_gate`` can all import it at top level.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

import httpx

# A caller's monotonic budget for its provider requests and language probes.
verification_deadline: ContextVar[Optional[float]] = ContextVar('verification_stt_deadline', default=None)


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


def probe_timeout(default: httpx.Timeout) -> httpx.Timeout:
    """A language probe's timeout: ``default``, each part capped to what is left of the caller's deadline.

    The vendor probe (connect 2 s, 8 s otherwise) and the self-hosted gate (connect 2 s, 6 s otherwise)
    keep their own short parts whenever more than that is left.
    """
    deadline = verification_deadline.get()
    if deadline is None:
        return default
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('language probe deadline expired')

    def part(value: Optional[float]) -> float:
        return remaining if value is None else min(value, remaining)

    return httpx.Timeout(
        connect=part(default.connect), read=part(default.read), write=part(default.write), pool=part(default.pool)
    )
