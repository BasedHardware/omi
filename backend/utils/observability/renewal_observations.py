"""Minimal provider billing observations; no entitlement or notification effects.

Immutable attempt/outcome facts avoid last-arrival-wins status regressions.
Only verified webhook payload fields are used: no Stripe reads or user lookups.
"""

# LIFECYCLE: permanent

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import AlreadyExists

from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
COLLECTION = 'billing_renewal_observations'
RETENTION_DAYS = 90
INVOICE_OUTCOMES = {
    'invoice.finalized': 'finalized',
    'invoice.payment_failed': 'failed',
    'invoice.paid': 'paid',
    'invoice.payment_succeeded': 'paid',
    'invoice.voided': 'void',
    'invoice.marked_uncollectible': 'uncollectible',
}
STATUSES = {'draft', 'open', 'paid', 'void', 'uncollectible', 'active', 'trialing', 'past_due', 'unpaid', 'canceled'}


def enabled() -> bool:
    return os.getenv('BILLING_RENEWAL_OBSERVATIONS_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'}


def _reference(value):
    if isinstance(value, Mapping):
        value = value.get('id')
    return value if isinstance(value, str) and 0 < len(value) <= 255 else None


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _period(value):
    return value if type(value) is int and 0 <= value <= 253402300799 else None


def _dimensions(items, *, truncated=False) -> dict[str, str]:
    from config.plan_catalog import resolve_stripe_price_plan

    unknown = {'interval': 'unknown', 'plan': 'unknown'}
    if truncated or not isinstance(items, list) or not items:
        return unknown
    intervals: set[str] = set()
    plans: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            return unknown
        price = item.get('price')
        if not isinstance(price, Mapping) or not isinstance(price.get('id'), str):
            return unknown
        recurring = price.get('recurring')
        if not isinstance(recurring, Mapping) or recurring.get('interval') not in {'month', 'year'}:
            return unknown
        intervals.add(str(recurring['interval']))
        try:
            plans.add(resolve_stripe_price_plan(str(price['id'])).value)
        except ValueError:
            return unknown
    if len(intervals) != 1 or len(plans) != 1:
        return unknown
    return {'interval': next(iter(intervals)), 'plan': next(iter(plans))}


def _record_outcome(outcome: str) -> None:
    from utils.metrics import OMI_BILLING_RENEWAL_OBSERVATIONS

    # Literal labels make the closed vocabulary explicit to the label ratchet.
    if outcome == 'eligible':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='eligible').inc()
    elif outcome == 'created':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='created').inc()
    elif outcome == 'duplicate':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='duplicate').inc()
    elif outcome == 'projection_error':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='projection_error').inc()
    elif outcome == 'write_error':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='write_error').inc()
    elif outcome == 'timeout':
        OMI_BILLING_RENEWAL_OBSERVATIONS.labels(outcome='timeout').inc()


def project_event(event: Mapping, *, now: datetime | None = None):
    """Return (semantic key, allowlisted fields), or None; never retain payloads."""
    kind = event.get('type')
    if kind not in INVOICE_OUTCOMES and kind not in {
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
    }:
        return None
    obj = (event.get('data') or {}).get('object')
    if not isinstance(obj, Mapping) or type(event.get('created')) is not int or not _reference(event.get('id')):
        return None
    now = now or datetime.now(timezone.utc)
    status = obj.get('status')
    details = obj.get('subscription_details') or (obj.get('parent') or {}).get('subscription_details') or {}
    if (details.get('metadata') or {}).get('app_id') or (obj.get('metadata') or {}).get('app_id'):
        return None
    if kind in INVOICE_OUTCOMES:
        invoice = _reference(obj.get('id'))
        subscription = _reference(obj.get('subscription') or details.get('subscription'))
        attempt = obj.get('attempt_count')
        if obj.get('billing_reason') != 'subscription_cycle' or not invoice or not subscription:
            return None
        if type(attempt) is not int or not 0 <= attempt <= 10000:
            return None
        outcome = INVOICE_OUTCOMES[kind]
        key = _hash(f'invoice:{invoice}:{attempt}:{outcome}')
        dimensions = _dimensions(
            (obj.get('lines') or {}).get('data') or [], truncated=bool((obj.get('lines') or {}).get('has_more'))
        )
        fields = {
            'observation_kind': 'invoice',
            'outcome': outcome,
            'attempt_count': attempt,
            'attempted': obj.get('attempted') is True,
            'paid_out_of_band': obj.get('paid_out_of_band') is True,
            'amount_due_positive': type(obj.get('amount_due')) is int and obj['amount_due'] > 0,
            'invoice_period_start': _period(obj.get('period_start')),
            'invoice_period_end': _period(obj.get('period_end')),
            # A truncated line collection cannot prove interval/plan coverage.
            **(
                dimensions
                if not (obj.get('lines') or {}).get('has_more')
                else {'interval': 'unknown', 'plan': 'unknown'}
            ),
        }
    else:
        previous = (event.get('data') or {}).get('previous_attributes') or {}
        if kind == 'customer.subscription.updated' and not {'status', 'cancel_at_period_end', 'cancel_at'}.intersection(
            previous
        ):
            return None
        subscription = _reference(obj.get('id'))
        if not subscription:
            return None
        invoice = _reference(obj.get('latest_invoice'))
        key = _hash(f'subscription:{event["id"]}')
        fields = {
            'observation_kind': 'subscription_snapshot',
            'outcome': 'subscription_snapshot',
            'subscription_created': _period(obj.get('created')),
            'cancel_at_period_end': obj.get('cancel_at_period_end') is True,
            'cancel_at': _period(obj.get('cancel_at')),
            'ended_at': _period(obj.get('ended_at')),
            'current_period_end': _period(obj.get('current_period_end')),
            'cancellation_reason': (
                (obj.get('cancellation_details') or {}).get('reason')
                if (obj.get('cancellation_details') or {}).get('reason')
                in {'cancellation_requested', 'payment_failed', 'payment_disputed'}
                else 'unknown'
            ),
            **_dimensions(
                (obj.get('items') or {}).get('data') or [], truncated=bool((obj.get('items') or {}).get('has_more'))
            ),
        }
    return key, {
        **fields,
        'schema_version': 1,
        'provider_livemode': event.get('livemode') if type(event.get('livemode')) is bool else None,
        'invoice_key': _hash(invoice) if invoice else None,
        'subscription_key': _hash(subscription),
        'provider_status': status if status in STATUSES else 'unknown',
        'provider_event_created': event['created'],
        'observed_at': now,
        'expires_at': now + timedelta(days=RETENTION_DAYS),
        'scope': 'recognized_consumer_price' if fields['plan'] != 'unknown' else 'unknown',
        'renewal_ordinal': 'unknown',
    }


def persist_observation(observation, *, client=None):
    if client is None:
        from database._client import get_firestore_client

        client = get_firestore_client()
    key, fields = observation
    try:
        client.collection(COLLECTION).document(key).create(fields, retry=None, timeout=1.0)
        return 'created'
    except AlreadyExists:
        return 'duplicate'


async def observe_verified_event(event: Mapping) -> None:
    """Best effort after signature validation; failures cannot change webhook result."""
    if not enabled():
        return
    phase = 'projection_error'
    try:
        observation = project_event(event)
        if observation is not None:
            _record_outcome('eligible')
            phase = 'write_error'
            outcome = await asyncio.wait_for(run_blocking(db_executor, persist_observation, observation), timeout=1.25)
            _record_outcome(outcome)
    except Exception as error:
        _record_outcome('timeout' if isinstance(error, asyncio.TimeoutError) else phase)
        logger.warning('renewal observation unavailable error_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='billing_renewal_observation',
            to_mode='none',
            reason='timeout' if isinstance(error, asyncio.TimeoutError) else 'unavailable',
            outcome='degraded',
        )
