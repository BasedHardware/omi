"""Per-dispatch prerecorded vendor-failure notes for the empty-success guard.

The language-detection probe is the one seam that swallows a vendor failure
without raising (``utils.stt.batch_language.detect`` catches every exception),
so a note is the only per-segment trace that the selection was degraded. The
note is a ContextVar: it is visible only to the segment's own dispatch context
(one executor leaf), never to unrelated segments, tasks, or instances.
Raising vendor failures need no note — they fail their segment and are
recorded durably per job by the pipeline.

No payloads, statuses, or exception text — only ``provider`` and ``kind``.
"""

from __future__ import annotations

from contextvars import ContextVar

PROVIDER_ERROR = 'provider_error'
CREDIT_AUTH = 'credit_auth'
KINDS = frozenset({PROVIDER_ERROR, CREDIT_AUTH})
PROVIDERS = frozenset({'parakeet', 'modulate'})

_dispatch_failure: ContextVar[str | None] = ContextVar('prerecorded_dispatch_failure', default=None)


def note_provider_failure(provider: str, kind: str = PROVIDER_ERROR) -> None:
    """Record that this dispatch context saw a prerecorded vendor fail."""
    if provider in PROVIDERS and kind in KINDS:
        _dispatch_failure.set(kind)


def recent_dispatch_failure() -> str | None:
    """The kind of vendor failure noted in this dispatch context, or None."""
    return _dispatch_failure.get()


def reset_prerecorded_health_for_tests() -> None:
    _dispatch_failure.set(None)
