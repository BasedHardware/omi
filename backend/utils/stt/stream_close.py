"""Bounded counters for provider STT stream-close reasons.

Vendor error frames already carry a typed death reason. This module is the
closed label set those frames increment so budget/quota exhaustion is countable
without putting raw vendor messages on a metric label.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from utils.metrics import OMI_STT_PROVIDER_RETIRED, OMI_STT_STREAM_CLOSE_TOTAL

PROVIDER_BUDGET_EXHAUSTED = 'provider_budget_exhausted'
PROVIDER_AUTH_REJECTED = 'provider_auth_rejected'
PROVIDER_RATE_LIMITED = 'provider_rate_limited'
ACCOUNT_REJECTION_REASONS = frozenset({PROVIDER_BUDGET_EXHAUSTED, PROVIDER_AUTH_REJECTED})

# Velma's budget refusals are free text (in-stream error frames, batch error
# bodies, refused-upgrade reason phrases). Both the live paths (streaming.py)
# and the batch path (pre_recorded.py) match these markers and map any hit to
# PROVIDER_BUDGET_EXHAUSTED — the token the budget page alerts on. "insufficient
# credits" is the 429 Velma-2 answers when the account is out of credits
# (2026-10-22: it flowed as an untyped provider error for ~1h because no path
# matched it). Matched, never logged or labeled.
MODULATE_BUDGET_MARKERS = (
    'monthly usage limit',
    'usage limit reached',
    'quota exceeded',
    'insufficient credits',
)

STT_STREAM_CLOSE_PROVIDERS = frozenset({'soniox', 'modulate', 'deepgram', 'parakeet'})
STT_STREAM_CLOSE_REASONS = frozenset(
    {
        *ACCOUNT_REJECTION_REASONS,
        PROVIDER_RATE_LIMITED,
        'soniox_idle_timeout',
        'soniox_request_timeout',
        'soniox_no_audio_teardown',
        'soniox_rotation',
        'soniox_invalid_hint',
        'modulate_serve_error',
        'connection_lost',
        'provider_5xx',
    }
)

# Default per David's 2026-09 ruling: hosted Deepgram is intentionally unfunded
# (too expensive), so its 402s must not page forever. Deployments override with
# STT_RETIRED_PROVIDERS (comma-separated provider tokens; empty disables all).
DEFAULT_RETIRED_PROVIDERS = 'deepgram'


def bounded_stream_close_provider(provider: str) -> str:
    label = (provider or '').strip().lower()
    return label if label in STT_STREAM_CLOSE_PROVIDERS else 'unknown'


def bounded_stream_close_reason(reason: Optional[str]) -> str:
    label = (reason or '').strip().lower()
    return label if label in STT_STREAM_CLOSE_REASONS else 'connection_lost'


def initialize_stt_stream_close_children() -> None:
    """Publish every bounded provider/reason child at zero. Never raises.

    Prometheus needs a scraped zero before the first close to observe its
    increase. Include the provider fallback bucket, but never vendor strings.
    Repeated initialization only touches children; it never resets counts.
    """

    try:
        for provider in sorted(STT_STREAM_CLOSE_PROVIDERS | {'unknown'}):
            for reason in sorted(STT_STREAM_CLOSE_REASONS):
                OMI_STT_STREAM_CLOSE_TOTAL.labels(provider=provider, reason=reason)
    except Exception:
        pass


def record_stt_stream_close(*, provider: str, reason: Optional[str]) -> None:
    """Increment ``omi_stt_stream_close_total``. Never raises."""

    try:
        OMI_STT_STREAM_CLOSE_TOTAL.labels(
            provider=bounded_stream_close_provider(provider),
            reason=bounded_stream_close_reason(reason),
        ).inc()
    except Exception:
        pass


def retired_stt_providers(env: Optional[Mapping[str, str]] = None) -> frozenset[str]:
    """Bounded read of the deployment's retired-provider config.

    Retired means intentionally unfunded or decommissioned: the leg still
    answers 402/serve errors, so per-provider budget and leg-error alerts must
    exclude it or they fire forever. Values are bounded by the closed provider
    vocabulary; unknown tokens are ignored (the metric label set stays closed).
    """

    source = os.environ if env is None else env
    raw = source.get('STT_RETIRED_PROVIDERS', DEFAULT_RETIRED_PROVIDERS)
    return frozenset(token.strip().lower() for token in raw.split(',') if token.strip()) & STT_STREAM_CLOSE_PROVIDERS


def publish_stt_provider_retired(env: Optional[Mapping[str, str]] = None) -> None:
    """Export ``omi_stt_provider_retired`` for every bounded provider. Never raises.

    Sets 0/1 (not just 1) so the alert's ``unless`` join has a series for every
    provider and an absent gauge stays visibly absent rather than silently
    healthy. Re-readable: deploy-time config changes re-publish.
    """

    try:
        retired = retired_stt_providers(env)
        for provider in STT_STREAM_CLOSE_PROVIDERS:
            OMI_STT_PROVIDER_RETIRED.labels(provider=provider).set(1 if provider in retired else 0)
    except Exception:
        pass


# Direct Soniox users also import this module, even without streaming.py.
initialize_stt_stream_close_children()
publish_stt_provider_retired()
