"""One flagged funded-compute admission boundary, shared by every producer.

Warm checks read only the open hour/day buckets, never scan a month per LLM
call. A processing scope reuses its admission for already-admitted fanout.
"""

from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import os
import logging
from typing import Any, Mapping

from config.stt_cap_dispatch import execution_admission_enabled as enabled
from config.rate_card import recording_units_per_hour
from config.plan_catalog import allocation_limit
from database.funded_usage_session import budget_session, client_identity
from database import users as users_db
from config import ladder_v1 as ladder_policy
from config.stt_cap_dispatch import enabled as legacy_enabled
from utils.subscription import resolve_transcription_allowance, get_monthly_usage_for_subscription
from utils.transcription_allowance import TranscriptionAllowance
from utils.stt_cap_dispatch import funded_allowance
from utils.llm.usage_tracker import track_usage
from utils import ladder_v1

_scope: ContextVar[dict | None] = ContextVar('funded_processing_scope', default=None)
_UNSET = object()


def allowance(uid: str, *, subscription: Any = _UNSET, usage: Any = _UNSET, firestore_client: Any = None):
    scope = _scope.get()
    key = (uid, client_identity(firestore_client))
    if scope is not None and key in scope:
        return scope[key][1]
    with budget_session(uid, firestore_client=firestore_client) as session:
        try:
            client_kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
            if subscription is _UNSET:
                subscription = users_db.get_user_valid_subscription(uid, provision=False, **client_kwargs)
            entitlement = (
                ladder_policy.entitlements(subscription) if ladder_policy.budget_enforcement_enabled() else None
            )
            if entitlement is not None:
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
                # Retain the existing legacy bypass / explicitly unenforced policy.
                result = funded_allowance(uid, usage_cache=session.units, subscription=subscription)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                'event=funded_processing outcome=unavailable exception_type=%s', type(exc).__name__
            )
            result = TranscriptionAllowance('on_device', 0, 'allowance_unavailable', limit_seconds=0)
    if scope is not None:
        scope[key] = (firestore_client, result)
    return result


def monthly_usage(uid: str) -> dict:
    """Subscription reporting shares closed-hour totals instead of rescanning every poll."""
    if not enabled():
        return get_monthly_usage_for_subscription(uid)
    raw = os.getenv('SUBSCRIPTION_LAUNCH_DATE')
    try:
        launch = datetime.strptime(raw or '', '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        # Preserve the resolver's missing/invalid/future launch-date contract.
        return get_monthly_usage_for_subscription(uid)
    with budget_session(uid) as session:
        return session.legacy.read(uid, launch)


def processing_allowed(uid: str, *, firestore_client: Any = None) -> bool:
    kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
    return not enabled() or allowance(uid, **kwargs).managed


def capacity(value: Any) -> tuple[float | None, float | None]:
    """Units and budget, or None for the catalog's explicit unlimited marker."""
    rate = float(recording_units_per_hour('batch'))
    if getattr(value, 'remaining_units', None) is not None:
        return max(0, value.remaining_units), value.budget_units
    seconds = getattr(value, 'remaining_seconds', None)
    limit = getattr(value, 'limit_seconds', None)
    return (None if seconds is None else max(0, seconds) * rate / 3600, None if limit is None else limit * rate / 3600)


def period_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m')


@contextmanager
def admission_scope():
    if _scope.get() is not None:
        yield
        return
    token = _scope.set({})
    try:
        yield
    finally:
        _scope.reset(token)


def scoped(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not enabled():
            return fn(*args, **kwargs)
        uid = args[0] if args else kwargs['uid']
        with admission_scope(), track_usage(uid, 'conversation_processing'):
            return fn(*args, **kwargs)

    return wrapped
