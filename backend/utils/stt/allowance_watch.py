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
    {'live_open', 'live_billing', 'prerecorded', 'batch_gpu', 'batch_provider', 'one_shot', 'ptt', 'processing', 'sync'}
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

LEASE_DECISIONS = Counter(
    'omi_free_allowance_lease_decisions', 'Shared shadow reservation decisions; no serving effect', ['path', 'reason']
)
SETTLED_SECONDS = Counter(
    'omi_free_allowance_settled_seconds', 'Confirmed billing seconds joined to a shadow operation', ['path']
)


def enabled() -> bool:
    return os.getenv('STT_FREE_ALLOWANCE_WATCH_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


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
    from database import free_allowance_leases

    return free_allowance_leases.chargeable_seconds(uid, now, firestore_client=firestore_client)


def entitlement(uid: str | None, *, customer_funded: bool = False) -> tuple[str, float | None]:
    """Free-only billing entitlement, with no launch-date/cohort/rollout gate."""
    if customer_funded:
        return 'customer_funded', None
    if not uid:
        return 'identity_unavailable', None
    try:
        users, policy = _policy()
        if policy.is_marketplace_reviewer(uid) or uid == policy.RELEASE_PROBE_UID:
            return 'exempt', None
        subscription = users.get_user_valid_subscription(uid, provision=False)
        if subscription is None:
            return 'subscription_unavailable', None
        if policy.is_paid_plan(subscription.plan):
            return 'paid_or_trial', None
        if getattr(subscription.plan, 'value', subscription.plan) != 'basic':
            return 'subscription_unavailable', None
        limit = policy.transcription_allowance_seconds(subscription.plan)
        if type(limit) not in (int, float) or not math.isfinite(limit) or limit < 0:
            return 'subscription_unavailable', None
        return 'free', float(limit)
    except Exception:
        return 'subscription_unavailable', None


def snapshot(uid: str | None, *, customer_funded: bool = False, now: datetime | None = None) -> Snapshot:
    """Speech and processing observe identical billed seconds plus in-flight holds."""
    decision, limit = entitlement(uid, customer_funded=customer_funded)
    if limit is None:
        return Snapshot(decision)
    try:
        if uid is None:
            return Snapshot('identity_unavailable')
        used = _monthly_seconds(uid, now or datetime.now(timezone.utc))
        return Snapshot('free', max(0, limit - used))
    except Exception:
        return Snapshot('usage_unavailable')


def emit(path: str, provider: Any, decision: str, seconds: float) -> None:
    if path not in PATHS:
        return
    provider = getattr(provider, 'value', provider)
    provider = provider if provider in PROVIDERS else 'unknown'
    DECISIONS.labels(path, provider, decision).inc()
    SECONDS.labels(path, provider, decision).inc(seconds)
    logger.info(
        'event=free_allowance_watch path=%s provider=%s decision=%s seconds=%s', path, provider, decision, seconds
    )


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
    if not enabled():
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
        emit(path, provider, decision, seconds)
    except Exception:
        # Instrumentation must not become an accidental enforcement rollout.
        # This is a missing observation, never an allow decision.
        logger.warning('event=free_allowance_watch decision=observation_failed')


def observe_unbound(uid: str | None, path: str, provider: Any, seconds: float = 0, *, customer_funded=False) -> None:
    """A new/unwired spend path cannot turn a snapshot into reservation permission."""
    if not enabled() or path not in PATHS:
        return
    decision, limit = entitlement(uid, customer_funded=customer_funded)
    if decision in {'customer_funded', 'paid_or_trial', 'exempt'}:
        emit(path, provider, decision, 0)
        return
    reason = 'billing_scope_unavailable' if limit is not None else decision
    LEASE_DECISIONS.labels(path, reason).inc()
    emit(
        path,
        provider,
        'would_refuse',
        seconds if type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0 else 0,
    )


def observe_request(path: str, provider: str, seconds: float = 0) -> None:
    """For synchronous provider clients; authentication context crosses executors."""
    try:
        from utils.byok import get_byok_uid
        from utils.stt_cap_dispatch import customer_funded

        from utils.stt.allowance_session import current

        scope = current.get()
        if scope is not None:
            if scope.seconds is None and seconds > 0:
                scope.seconds = seconds
            scope.reserve(provider, customer_funded=customer_funded(provider))
        else:
            observe_unbound(get_byok_uid(), path, provider, seconds, customer_funded=customer_funded(provider))
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
    if not enabled():
        return
    from utils.stt.allowance_session import current
    from utils.stt_cap_dispatch import customer_funded as actual_customer_funded

    scope = current.get()
    if scope is not None and path in {'prerecorded', 'batch_provider', 'one_shot', 'live_open'}:
        if uid is not None and uid != scope.uid:
            emit(path, provider, 'identity_mismatch', 0)
            return
        if scope.seconds is None and seconds > 0:
            scope.seconds = seconds
        await scope.reserve_async(provider, customer_funded=actual_customer_funded(provider), timeout=timeout)
        return
    from utils.executors import db_executor, free_allowance_executor, run_blocking

    spend_point = path in {'prerecorded', 'batch_provider', 'batch_gpu', 'one_shot', 'live_open'}
    observer = observe_unbound if spend_point else observe
    executor = free_allowance_executor if spend_point else db_executor
    try:
        await asyncio.wait_for(
            run_blocking(executor, observer, uid, path, provider, seconds, customer_funded=customer_funded),
            timeout=timeout,
        )
    except Exception:
        logger.warning('event=free_allowance_watch decision=observation_failed')
