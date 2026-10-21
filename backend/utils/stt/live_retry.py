"""One fast, jittered same-target retry after a connection-level failure.

A transient transport drop (connect timeout, connection_lost/send_failed
before the first text) on a provider that is not benched is retried once on
the same target before the chain falls through. Without it, a Soniox connect
blip with no permitted successor exhausted the session, or fell to a last
resort failing at 40% (prod 2026-10-20). Typed provider rejections (4xx/5xx,
429, budget, auth, capacity) never retry here; they have their own paths.
"""

from __future__ import annotations

import random

from config.live_stt_resilience import same_target_retry_enabled

SAME_TARGET_RETRY_REASONS = frozenset({'connection_lost', 'timeout', 'send_failed'})
# External vendors over the internet. In-cluster Parakeet has its own
# re-entry paths (no-text rescue, cheap lease failback, window admission).
SAME_TARGET_RETRY_FAMILIES = frozenset({'soniox', 'modulate', 'deepgram'})
RETRY_JITTER_SECONDS = (0.1, 0.5)


def same_target_retry_allowed(
    reason: str | None,
    *,
    text_seen: bool | None,
    stage: int,
    circuit_open: bool,
    already_retried: bool,
    family: str = 'soniox',
) -> bool:
    """Pure policy: one retry, connection-level, before text, not benched."""
    return (
        same_target_retry_enabled()
        and family in SAME_TARGET_RETRY_FAMILIES
        and not already_retried
        and text_seen is False
        and reason in SAME_TARGET_RETRY_REASONS
        and stage > 0
        and not circuit_open
    )


def retry_jitter_seconds(rng: random.Random | None = None) -> float:
    low, high = RETRY_JITTER_SECONDS
    return (rng or random).uniform(low, high)
