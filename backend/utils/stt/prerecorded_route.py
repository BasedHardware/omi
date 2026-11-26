"""One recording's pre-recorded provider selection, resolved once and reusable for several pieces."""

import time
from contextvars import ContextVar
from typing import Any, Optional, Tuple

import httpx

from config.prerecorded_language import language_class, language_guard_enabled

# The language probe's own bound when no caller deadline is set: httpx.Timeout(8, connect=2).
PROBE_SECONDS = 10.0
# Set by ``pre_recorded.verification_stt_deadline``: a caller's monotonic budget for its provider
# requests and language probe. Lives here so the probe can read it without importing pre_recorded.
verification_deadline: ContextVar[Optional[float]] = ContextVar('verification_stt_deadline', default=None)


def budget_timeout(remaining: float) -> httpx.Timeout:
    """One request inside ``remaining`` seconds: connect, pool, write and read share it, not each take it."""
    connect, pool, write = min(remaining * 0.1, 3.0), min(remaining * 0.05, 1.0), remaining * 0.25
    return httpx.Timeout(connect=connect, pool=pool, write=write, read=remaining - connect - pool - write)


def probe_timeout(default: httpx.Timeout) -> httpx.Timeout:
    """The language probe's timeout: ``default``, or what is left of a caller's ``verification_stt_deadline``."""
    deadline = verification_deadline.get()
    if deadline is None:
        return default
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('language probe deadline expired')
    return budget_timeout(min(remaining, PROBE_SECONDS))


def prerecorded_bytes_route(
    audio_bytes: bytes,
    language: Optional[str],
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    encoding: Optional[str] = None,
    before_probe=None,
    before_self_probe=None,
) -> Tuple[Any, Optional[str]]:
    """The selected service and the language to construct its provider with, for these bytes.

    ``prerecorded_from_bytes`` resolves this for every call; a caller that sends several pieces of one
    recording (the v3 fast finish's chunks) resolves it once and passes it back as ``route``.
    ``before_probe`` / ``before_self_probe`` are asked right before audio leaves for the vendor or the
    self-hosted language probe; False skips that probe.
    """
    from utils.stt.batch_language import resolve_language, select_decision
    from utils.stt.pre_recorded import get_prerecorded_service

    decision = resolve_language(
        language,
        audio_bytes,
        sample_rate=sample_rate,
        channels=channels,
        encoding=encoding,
        **({'before_probe': before_probe} if before_probe is not None else {}),
        **({'before_self_probe': before_self_probe} if before_self_probe is not None else {}),
    )
    resolved = decision.language if decision.parakeet_safe else language
    if not language_guard_enabled() or language_class(language) != 'unknown':
        resolved = language
    selected = select_decision(language, decision, get_prerecorded_service)
    return selected, resolved
