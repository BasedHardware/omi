"""Pure runtime contract for the Jev decision model (TypeSafe "System One", #14835).

Jev answers typed questions about one shared state (a probability for a yes/no
question, a distribution for a choice) instead of generating text. The backend
reaches it only through the LLM gateway's ``openrouter.systemone`` lane; the
gateway owns the OpenRouter credential. Both the lane definition
(``llm_gateway/gateway/config_loader.py``) and the backend client
(``utils/llm/jev_client.py``) read the pinned model and route from here.

Each decision that consults Jev has its own deployment flag. Every flag
defaults off, and flags are read at the call boundary, never at import.
"""

from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime, timezone
from typing import Literal

JEV_AUTO_LANE_ID = 'omi:auto:jev-decisions'
# Pinned: a new Jev version changes calibration, and every threshold below was
# measured on 1.13. Bump only with a re-measured threshold.
JEV_MODEL = 'typesafe/jev-1.13'
JEV_PROVIDER = 'openrouter'
# The upstream route's context window is 32k tokens. Characters are a
# conservative proxy (CJK text can approach one token per character), and the
# instructions/criteria share that window, so states are cut well below it.
JEV_MAX_STATE_CHARS = 24_000
# Gateway provider deadline; the backend client's own deadline sits just above
# it so a slow provider surfaces as a gateway timeout rather than a hung hop.
JEV_GATEWAY_REQUEST_MS = 2_500
JEV_CLIENT_TIMEOUT_SECONDS = 3.0
# One retry, only for transport failures and 5xx — never for a malformed answer.
JEV_CLIENT_MAX_ATTEMPTS = 2

CONVERSATION_RELEVANCE_JEV_ENABLED_ENV = 'CONVERSATION_RELEVANCE_JEV_ENABLED'
MEMORY_OWNER_JEV_FLIP_ENABLED_ENV = 'MEMORY_OWNER_JEV_FLIP_ENABLED'
CAPTURE_JEV_SHADOW_ENABLED_ENV = 'CAPTURE_JEV_SHADOW_ENABLED'
CAPTURE_JEV_SHADOW_EXPIRY_ENV = 'CAPTURE_JEV_SHADOW_EXPIRY'
CAPTURE_JEV_SHADOW_DEFAULT_EXPIRY = '2026-10-18T00:00:00Z'

_TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def _flag(name: str) -> bool:
    return os.getenv(name, '').strip().lower() in _TRUE_VALUES


def conversation_relevance_jev_enabled() -> bool:
    """The model tier of conversation relevance asks Jev instead of ``conv_discard``."""
    return _flag(CONVERSATION_RELEVANCE_JEV_ENABLED_ENV)


def memory_owner_jev_flip_enabled() -> bool:
    """Capture may re-attribute a third-party memory candidate to the user on a confident Jev answer.

    Universal when on: INV-MEM-5 (product/invariants/universal-memory-task-authority.md)
    forbids UID cohorts selecting live owner-attribution logic, so there is no
    owner-flip percentage or allowlist. Owner measurement stays sampled via the
    shadow lane.
    """
    return _flag(MEMORY_OWNER_JEV_FLIP_ENABLED_ENV)


RelevanceArm = Literal['keep_all', 'jev', 'nano']


def uid_bucket(uid: str, salt: str) -> float:
    """Stable salted cohort, using the capture shadow's first eight SHA256 bytes."""
    digest = hashlib.sha256(f'{salt}\0{uid}'.encode()).digest()
    # Floating-point rounding of the largest uint64 must not produce 100.
    return min(int.from_bytes(digest[:8], 'big') / 2**64 * 100, math.nextafter(100.0, 0.0))


def percentage(name: str, *, default: float = 0.0) -> float:
    """Invalid, non-finite and out-of-range configuration admits nobody."""
    try:
        value = float(os.getenv(name, str(default)))
        return value if math.isfinite(value) and 0 <= value <= 100 else 0.0
    except ValueError:
        return 0.0


def _percentage_or_none(name: str, *, default: float) -> float | None:
    """Like ``percentage`` but distinguishes a valid zero from invalid config.

    Rollout allowlists must never bypass a malformed percentage, so callers
    that consult an allowlist need ``None`` (invalid) rather than ``0.0``.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) and 0 <= value <= 100 else None


def _allowlisted(uid: str, name: str) -> bool:
    return uid in {value.strip() for value in os.getenv(name, '').split(',') if value.strip()}


def relevance_arm(uid: str) -> RelevanceArm:
    """Consecutive disjoint cohorts. Set K first: changing K moves the Jev window.

    With K fixed, increasing J only extends the Jev range. K+J is capped at
    100; increasing K can absorb existing Jev users into keep_all and shift
    the range's upper edge. Allowlisting never overrides keep_all or flag off,
    and an invalid percentage admits nobody — allowlists included.
    """
    bucket = uid_bucket(uid, 'relevance-arm-v1')
    keep_all = _percentage_or_none('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT', default=0.0)
    if keep_all is not None and bucket < keep_all:
        return 'keep_all'
    if conversation_relevance_jev_enabled():
        jev = _percentage_or_none('CONVERSATION_RELEVANCE_JEV_PERCENT', default=100.0)
        if jev is not None and (
            bucket < min(100.0, (keep_all if keep_all is not None else 0.0) + jev)
            or _allowlisted(uid, 'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST')
        ):
            return 'jev'
    return 'nano'


def relevance_experiment_active() -> bool:
    """Preserve the legacy nano record while every experiment control is off."""
    return (
        conversation_relevance_jev_enabled()
        or percentage('CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT') > 0
        or percentage('CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT') > 0
    )


def capture_jev_shadow_enabled(now: datetime | None = None) -> tuple[bool, str]:
    """A malformed deadline disables the experiment; its default is a hard UTC stop."""
    if not _flag(CAPTURE_JEV_SHADOW_ENABLED_ENV):
        return False, 'flag_off'
    try:
        configured = datetime.fromisoformat(
            os.getenv(CAPTURE_JEV_SHADOW_EXPIRY_ENV, CAPTURE_JEV_SHADOW_DEFAULT_EXPIRY).replace('Z', '+00:00')
        )
        hard_stop = datetime.fromisoformat(CAPTURE_JEV_SHADOW_DEFAULT_EXPIRY.replace('Z', '+00:00'))
        expiry = min(configured, hard_stop)
        if expiry.tzinfo is None or (now or datetime.now(timezone.utc)) >= expiry:
            return False, 'expired'
    except ValueError:
        return False, 'expired'
    return True, 'enabled'
