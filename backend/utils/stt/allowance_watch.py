"""Watch-only spend-point evidence for the free-allowance reservation rollout.

This deliberately cannot refuse a provider call. The existing admission policy
continues to serve until the one-day reconciliation gate has passed.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import logging
import math
import os
from typing import Any

from prometheus_client import Counter

logger = logging.getLogger(__name__)
PATHS = frozenset(
    {'live_open', 'live_billing', 'prerecorded', 'batch_gpu', 'batch_provider', 'one_shot', 'ptt', 'processing'}
)
PROVIDERS = frozenset({'deepgram', 'soniox', 'modulate', 'parakeet', 'llm'})
DECISIONS = Counter(
    'omi_free_allowance_watch_decisions',
    'Watch-only spend-point decisions; no user identifiers',
    ['path', 'provider', 'decision'],
)
SECONDS = Counter(
    'omi_free_allowance_watch_seconds',
    'Observed seconds by decision; requests are estimates, billing observations are separate',
    ['path', 'provider', 'decision'],
)


@dataclass(frozen=True)
class Snapshot:
    decision: str
    remaining: float | None = None


def _policy():
    # Provider imports must not load subscription clients or perform IO.
    from database import users
    from utils import subscription

    return users, subscription


def _monthly_seconds(uid: str, now: datetime, *, firestore_client: Any = None) -> float:
    """Read the billing ledger directly, without launch-date or cohort fallbacks.

    A projection without a verified baseline is unavailable, not zero. This
    reader never scans account data, rebuilds a projection, or creates a user.
    """
    from database import monthly_usage_totals

    return monthly_usage_totals.read_verified_transcription_seconds(uid, now, firestore_client=firestore_client)


def snapshot(uid: str | None, *, customer_funded: bool = False, now: datetime | None = None) -> Snapshot:
    """One strict answer for all watch points. No flag, source or cohort input.

    Paying plans (including Stripe trials on those plans) are exempt from this
    free-only policy. A request key exempts only the provider actually using it;
    callers decide that at the actual provider boundary.
    """
    if customer_funded:
        return Snapshot('customer_funded')
    if not uid:
        return Snapshot('identity_unavailable')
    try:
        users, policy = _policy()
        if policy.is_marketplace_reviewer(uid) or uid == policy.RELEASE_PROBE_UID:
            return Snapshot('exempt')
        subscription = users.get_user_valid_subscription(uid, provision=False)
        if subscription is None:
            return Snapshot('subscription_unavailable')
        if policy.is_paid_plan(subscription.plan):
            return Snapshot('paid_or_trial')
        if getattr(subscription.plan, 'value', subscription.plan) != 'basic':
            return Snapshot('subscription_unavailable')
        limit = policy.transcription_allowance_seconds(subscription.plan)
        if type(limit) not in (int, float) or not math.isfinite(limit) or limit < 0:
            return Snapshot('subscription_unavailable')
        used = _monthly_seconds(uid, now or datetime.now(timezone.utc))
        return Snapshot('free', max(0, limit - used))
    except Exception:
        return Snapshot('usage_unavailable')


def observe(
    uid: str | None,
    path: str,
    provider: Any,
    seconds: float = 0,
    *,
    customer_funded: bool = False,
) -> None:
    """Emit bounded aggregate evidence; no exception or result can affect serving.

    The kill switch disables instrumentation, not any existing admission check.
    Requested seconds and billed seconds must never be summed together.
    """
    if os.getenv('STT_FREE_ALLOWANCE_WATCH_ENABLED', 'true').strip().lower() in {'false', '0', 'off', 'no'}:
        return
    try:
        if path not in PATHS:
            raise ValueError('unknown watch path')
        provider = getattr(provider, 'value', provider)
        provider = provider if provider in PROVIDERS else 'unknown'
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('invalid observed seconds')
        result = snapshot(uid, customer_funded=customer_funded)
        decision = result.decision
        if decision == 'free':
            if result.remaining is None:
                decision = 'usage_unavailable'
            else:
                decision = 'would_refuse' if result.remaining == 0 or seconds > result.remaining else 'would_allow'
        DECISIONS.labels(path, provider, decision).inc()
        SECONDS.labels(path, provider, decision).inc(seconds)
        logger.info(
            'event=free_allowance_watch path=%s provider=%s decision=%s seconds=%s', path, provider, decision, seconds
        )
    except Exception:
        # Instrumentation must not become an accidental enforcement rollout.
        # This is a missing observation, never an allow decision.
        logger.warning('event=free_allowance_watch decision=observation_failed')


def observe_request(path: str, provider: str, seconds: float = 0) -> None:
    """For synchronous provider clients; authentication context crosses executors."""
    try:
        from utils.byok import get_byok_uid
        from utils.stt_cap_dispatch import customer_funded

        observe(get_byok_uid(), path, provider, seconds, customer_funded=customer_funded(provider))
    except Exception:
        logger.warning('event=free_allowance_watch decision=observation_failed')


async def observe_async(
    uid: str | None,
    path: str,
    provider: Any,
    seconds: float = 0,
    *,
    customer_funded: bool = False,
    timeout: float = 2.5,
) -> None:
    from utils.executors import db_executor, run_blocking

    try:
        await asyncio.wait_for(
            run_blocking(db_executor, observe, uid, path, provider, seconds, customer_funded=customer_funded),
            timeout=timeout,
        )
    except Exception:
        logger.warning('event=free_allowance_watch decision=observation_failed')
