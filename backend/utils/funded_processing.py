"""One flagged funded-compute admission boundary, shared by every producer.

Warm checks read only the open hour/day buckets, never scan a month per LLM
call. Each dispatch rechecks admission against current usage.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import os
import logging
from typing import Any, Mapping

from config.stt_cap_dispatch import execution_admission_enabled, any_execution_admission_enabled
from config.stt_cap_dispatch import enabled as legacy_enabled

_UNSET = object()
_backlog_grant: ContextVar[tuple[str, str] | None] = ContextVar('funded_backlog_grant', default=None)


def enabled(uid: str, lane: str | None = None) -> bool:
    """Owner surfaces use any lane; processing dispatches supply batch explicitly."""
    return any_execution_admission_enabled(uid) if lane is None else execution_admission_enabled(uid, lane)


def consent_allows(uid: str) -> bool:
    """A chosen backlog grant cannot authorize later dispatches after reset."""
    if not enabled(uid):
        return True
    grant = _backlog_grant.get()
    return grant is None or grant == (uid, period_id())


@contextmanager
def backlog_consent(uid: str, period: str):
    if not enabled(uid):
        yield
        return
    token = _backlog_grant.set((uid, period))
    try:
        yield
    finally:
        _backlog_grant.reset(token)


def allowance(uid: str, *, subscription: Any = _UNSET, usage: Any = _UNSET, firestore_client: Any = None):
    # Admission callers short-circuit before loading database/provider dependencies.
    from config import ladder_v1 as ladder_policy
    from database.funded_usage_session import budget_session
    from utils.transcription_allowance import TranscriptionAllowance

    with budget_session(uid, firestore_client=firestore_client) as session:
        try:
            client_kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
            if subscription is _UNSET:
                from database import users as users_db

                subscription = users_db.get_user_valid_subscription(uid, provision=False, **client_kwargs)
            entitlement = (
                ladder_policy.entitlements(subscription) if ladder_policy.budget_enforcement_enabled() else None
            )
            if entitlement is not None:
                from utils import ladder_v1

                # Use the actual projection and client, not a placeholder allowance.
                # The same unit session serves direct chat budget_snapshot callers.
                snapshot = ladder_v1.budget_snapshot(uid, subscription, session_cache=session.units, **client_kwargs)
                if snapshot is None:
                    raise ValueError('Missing enforced ladder budget')
                exhausted = snapshot['budget_percent'] >= 100
                result = TranscriptionAllowance(
                    'on_device' if exhausted else 'managed',
                    0 if exhausted else None,
                    'usage_budget_exhausted' if exhausted else 'usage_budget_available',
                    limit_seconds=None,
                    remaining_units=max(0, snapshot['budget_units'] - snapshot['used_units']),
                    budget_units=snapshot['budget_units'],
                )
            elif legacy_enabled():
                from config.plan_catalog import allocation_limit
                from utils.subscription import resolve_transcription_allowance

                if usage is _UNSET:
                    plan = (
                        subscription.get('plan')
                        if isinstance(subscription, Mapping)
                        else getattr(subscription, 'plan', None)
                    )
                    if subscription is None:
                        usage = {}
                    elif not isinstance(plan, str):
                        raise ValueError('Invalid subscription plan')
                    elif allocation_limit(plan, 'transcription') is None:
                        # No finite ledger is needed for explicitly unlimited
                        # legacy accounts; the resolver still owns policy.
                        usage = {}
                    else:
                        launch = datetime.strptime(os.environ['SUBSCRIPTION_LAUNCH_DATE'], '%Y-%m-%d').replace(
                            tzinfo=timezone.utc
                        )
                        usage = session.legacy.read(uid, launch, **client_kwargs)
                used = max(usage.get('transcription_seconds', 0), usage.get('speech_seconds', 0))
                result = resolve_transcription_allowance(
                    uid,
                    subscription=subscription,
                    usage={**usage, 'transcription_seconds': used},
                    byok_active=False,
                    omi_funded=True,
                )
            else:
                from utils.stt_cap_dispatch import funded_allowance

                # Retain the existing legacy bypass / explicitly unenforced policy.
                result = funded_allowance(uid, usage_cache=session.units, subscription=subscription)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                'event=funded_processing outcome=unavailable exception_type=%s', type(exc).__name__
            )
            result = TranscriptionAllowance('on_device', 0, 'allowance_unavailable', limit_seconds=0)
    return result


def monthly_usage(uid: str) -> dict:
    """Subscription reporting shares closed-hour totals instead of rescanning every poll."""
    if not enabled(uid):
        from utils.subscription import get_monthly_usage_for_subscription

        return get_monthly_usage_for_subscription(uid)
    raw = os.getenv('SUBSCRIPTION_LAUNCH_DATE')
    try:
        launch = datetime.strptime(raw or '', '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        from utils.subscription import get_monthly_usage_for_subscription

        # Preserve the resolver's missing/invalid/future launch-date contract.
        return get_monthly_usage_for_subscription(uid)
    from database.funded_usage_session import budget_session

    with budget_session(uid) as session:
        return session.legacy.read(uid, launch)


def processing_allowed(uid: str, *, firestore_client: Any = None) -> bool:
    kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
    return not enabled(uid, 'batch') or consent_allows(uid) and allowance(uid, **kwargs).managed


def capacity(value: Any) -> tuple[float | None, float | None]:
    """Units and budget, or None for the catalog's explicit unlimited marker."""
    from config.rate_card import recording_units_per_hour

    rate = float(recording_units_per_hour('batch'))
    if getattr(value, 'remaining_units', None) is not None:
        return max(0, value.remaining_units), value.budget_units
    seconds = getattr(value, 'remaining_seconds', None)
    limit = getattr(value, 'limit_seconds', None)
    return (None if seconds is None else max(0, seconds) * rate / 3600, None if limit is None else limit * rate / 3600)


def period_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m')


def scoped(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        uid = args[0] if args else kwargs['uid']
        if not enabled(uid, 'batch'):
            return fn(*args, **kwargs)
        from utils.llm.usage_tracker import track_usage

        with track_usage(uid, 'conversation_processing'):
            return fn(*args, **kwargs)

    return wrapped
