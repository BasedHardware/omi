"""Recent prerecorded vendor failures, in-process, for the empty-success guard.

The vendor adapters raise on connection failures and credit/auth refusals, and
the sync pipeline records those as segment failures. But two seams swallow them
without any per-unit marker: the language-detection probe
(``utils.stt.batch_language`` catches every exception) and Cloud Tasks retries
(a failed attempt's provider error never reaches the attempt that ends with a
valid-empty response). The empty-success guard reads this module to know the
chain that produced a zero-word result was degraded.

Bounded: one timestamped event per provider and kind, kept for a fixed window.
No payloads, statuses, or exception text — only ``provider`` and ``kind``.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Final

PROVIDER_ERROR = 'provider_error'
CREDIT_AUTH = 'credit_auth'
KINDS: Final[frozenset[str]] = frozenset({PROVIDER_ERROR, CREDIT_AUTH})
PROVIDERS: Final[frozenset[str]] = frozenset({'parakeet', 'modulate'})

# Long enough to cover a Cloud Tasks retry cycle after a provider outage;
# short enough that a stale failure cannot hold empties from a healthy chain.
FAILURE_WINDOW_SECONDS = 15 * 60

_events: dict[tuple[str, str], deque[float]] = {}
_lock = threading.Lock()


def note_provider_failure(provider: str, kind: str = PROVIDER_ERROR) -> None:
    """Record that this process saw a prerecorded vendor fail just now."""
    if provider not in PROVIDERS or kind not in KINDS:
        return
    now = time.monotonic()
    with _lock:
        bucket = _events.setdefault((provider, kind), deque())
        bucket.append(now)
        cutoff = now - FAILURE_WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.popleft()


def recent_provider_failure(*, providers: frozenset[str] = PROVIDERS, kinds: frozenset[str] = KINDS) -> str | None:
    """The kind of the most recent in-window vendor failure, or None when healthy.

    Returns ``CREDIT_AUTH`` when both kinds are present: a credit/auth refusal
    is the stronger, more deterministic degradation signal.
    """
    now = time.monotonic()
    cutoff = now - FAILURE_WINDOW_SECONDS
    credit_auth = False
    latest_kind = None
    latest_at = 0.0
    with _lock:
        for (provider, kind), bucket in _events.items():
            if provider not in providers or kind not in kinds:
                continue
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if not bucket:
                continue
            if kind == CREDIT_AUTH:
                credit_auth = True
            if bucket[-1] > latest_at:
                latest_kind, latest_at = kind, bucket[-1]
    if credit_auth:
        return CREDIT_AUTH
    return latest_kind


def reset_prerecorded_health_for_tests() -> None:
    with _lock:
        _events.clear()
