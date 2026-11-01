"""Bounded, privacy-safe counters for Stripe subscription lifecycle events.

Cancellations are otherwise invisible in real time: subscription and MRR state
lives only on a separate Grafana that queries Stripe live, and cancellations
are not tracked anywhere. This module turns the ``customer.subscription.*``
webhook deliveries already handled in ``routers.payment`` into one bounded
counter so a cancellation trend is visible next to feature health.

Recording must never break the webhook it observes: every public entry point
here swallows unexpected errors and logs at warning instead of raising.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from config.plan_catalog import (
    LADDER_V1_STRIPE_PRICES,
    PlanType,
    RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
    resolve_stripe_price_plan,
)
from utils.metrics import OMI_SUBSCRIPTION_EVENTS

logger = logging.getLogger(__name__)

# Closed label surfaces. Never widen these with a uid, customer id,
# subscription id, price id, or email — those are unbounded and would turn
# this counter into an unbounded cardinality leak.
_EVENTS = frozenset(
    {
        'created',
        'cancellation_requested',
        'cancellation_reverted',
        'ended',
        'payment_failed',
    }
)
_PLANS = frozenset({plan.value for plan in PlanType}) | {'unknown'}
_INTERVALS = frozenset({'month', 'year', 'unknown'})
_REASONS = frozenset({'cancellation_requested', 'payment_failure', 'payment_disputed', 'none'})

_PAYMENT_FAILED_STATUSES = frozenset({'past_due', 'unpaid'})

# `reason` describes why a subscription ended, so only this event can ever carry
# one; every other event pins 'none'. Both the recording path and the zero
# initialization below read this, so the reachable label space cannot drift from
# what is actually emitted.
_REASON_BEARING_EVENT = 'ended'


def price_catalog_generation(price_id: str | None) -> str:
    """Return ``legacy``, ``ladder_v1``, or ``unknown`` from the Stripe price id."""

    if not isinstance(price_id, str) or not price_id:
        return 'unknown'
    if price_id in LADDER_V1_STRIPE_PRICES:
        return 'ladder_v1'
    if price_id in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES:
        return 'legacy'
    return 'unknown'


def _currency_wire(price: Mapping[str, Any]) -> str:
    raw = price.get('currency')
    if not isinstance(raw, str) or not raw.strip():
        return 'unknown'
    return raw.strip().lower()[:16]


def _monthly_mrr_cents(price: Mapping[str, Any], interval: str, status: object) -> int | None:
    """USD catalog list price in monthly cents, or None when it is not that.

    Emitted only for ``currency == "usd"`` and a subscription that is not
    ``trialing``. A trial has not been invoiced, and a non-USD ``unit_amount``
    is not cents (JPY 4800 is ¥4800, not $48). Yearly prices use round-half-up
    of ``unit_amount / 12`` (``19990`` becomes ``1666``, not ``1665``).
    Discounts and promotion codes are not applied: this is list price, not
    the amount Stripe will charge.
    """

    if status == 'trialing' or _currency_wire(price) != 'usd':
        return None
    amount = price.get('unit_amount')
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        return None
    if interval == 'month':
        return amount
    if interval == 'year':
        return int((Decimal(amount) / Decimal(12)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return None


def _cancellation_just_scheduled(
    subscription_obj: Mapping[str, Any],
    previous_attributes: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(previous_attributes, Mapping) or 'cancel_at_period_end' not in previous_attributes:
        return False
    previous = previous_attributes.get('cancel_at_period_end')
    current = subscription_obj.get('cancel_at_period_end')
    return (not previous) and bool(current)


def emit_billing_product_event(
    *,
    uid: str,
    stripe_event_id: str | None,
    stripe_event_created: int | float | None,
    stripe_event_type: str,
    subscription_obj: Mapping[str, Any] | None,
    previous_paid_subscription_id: str | None,
    resulting_paid_subscription_id: str | None,
    previous_attributes: Mapping[str, Any] | None = None,
) -> None:
    """Emit an owner-bound billing lifecycle event after webhook resolution.

    Stripe remains authoritative. This is a bounded PostHog projection used by
    product scorecards. Scheduled cancellation is not churn. The event carries
    the catalog price id, currency, a USD list-price ``mrr_cents`` when that
    amount is defined, and a legacy-versus-ladder-v1 marker derived from that
    price id. It does not carry a customer, card, email, or subscription
    identifier. ``mrr_cents`` is not the ARPMAU numerator: that is the Stripe
    book snapshot. These events measure movement.
    """
    if not uid or not stripe_event_id or not isinstance(subscription_obj, Mapping):
        return
    obj = subscription_obj
    plan = _resolve_plan(obj)
    interval = _resolve_interval(obj)
    event_name: str | None = None
    reason = 'none'
    # The caller supplies the durable entitlement after reconciliation. Raw
    # webhook status cannot prove churn: another subscription may retain access.
    # Trialing counts as paid-plan entitlement, matching the product authority;
    # this signal is not a cash/revenue measurement.
    if resulting_paid_subscription_id and (
        not previous_paid_subscription_id
        or (
            obj.get('id') == resulting_paid_subscription_id
            and (
                stripe_event_type == 'customer.subscription.created'
                or (
                    stripe_event_type == 'customer.subscription.updated'
                    and (previous_attributes or {}).get('status') == 'incomplete'
                )
            )
        )
    ):
        event_name = 'Billing Subscription Started'
    elif previous_paid_subscription_id and not resulting_paid_subscription_id:
        if previous_paid_subscription_id != obj.get('id'):
            return
        event_name = 'Billing Subscription Churned'
        reason = (
            'payment_failure' if obj.get('status') in _PAYMENT_FAILED_STATUSES else _resolve_cancellation_reason(obj)
        )
    if event_name is None and _cancellation_just_scheduled(obj, previous_attributes):
        event_name = 'Billing Subscription Cancellation Scheduled'
    if event_name is None:
        return
    price = _first_item_price(obj)
    raw_price_id = price.get('id')
    price_id = raw_price_id[:128] if isinstance(raw_price_id, str) and raw_price_id else 'unknown'
    mrr_cents = _monthly_mrr_cents(price, interval, obj.get('status'))
    try:
        occurred_at = None
        # Initial activation deduplicates checkout/created/updated delivery
        # order. Recovery is a later movement, keyed and dated by its own event.
        initial_activation = event_name == 'Billing Subscription Started' and (
            stripe_event_type == 'customer.subscription.created'
            or (previous_attributes or {}).get('status') == 'incomplete'
        )
        event_time = obj.get('created', stripe_event_created) if initial_activation else stripe_event_created
        if isinstance(event_time, (int, float)):
            from datetime import datetime, timezone

            occurred_at = datetime.fromtimestamp(float(event_time), tz=timezone.utc).isoformat().replace('+00:00', 'Z')
        from utils.product_telemetry import emit_product_event

        emit_product_event(
            uid=uid,
            event=event_name,
            properties={
                '$insert_id': _billing_insert_id(
                    event_name, obj.get('id'), stripe_event_id, initial_activation=initial_activation
                ),
                'billing_event_id': stripe_event_id[:128],
                'occurred_at': occurred_at,
                'billing_source': 'stripe_webhook_authoritative_owner',
                'billing_measurement': (
                    'trial_plan_entitlement' if obj.get('status') == 'trialing' else 'paid_plan_entitlement'
                ),
                'is_trial': obj.get('status') == 'trialing',
                'plan': plan,
                'interval': interval,
                'reason': reason,
                'price_id': price_id,
                'currency': _currency_wire(price),
                'price_generation': price_catalog_generation(price_id if price_id != 'unknown' else None),
                **({'mrr_cents': mrr_cents} if mrr_cents is not None else {}),
            },
        )
    except Exception:
        logger.warning('billing_product_event_emit_failed event=%s', event_name, exc_info=True)


def _billing_insert_id(
    event: str, subscription_id: Any, stripe_event_id: str, *, initial_activation: bool = False
) -> str:
    from uuid import NAMESPACE_URL, uuid5

    # Only initial activation is subscription-scoped. Recovery and other
    # movements are event-scoped so replay is safe without erasing later starts.
    key = subscription_id if initial_activation and subscription_id else stripe_event_id
    return str(uuid5(NAMESPACE_URL, f'omi:billing:{event}:{key}'))


def _reachable_reasons(event: str) -> tuple[str, ...]:
    return tuple(sorted(_REASONS)) if event == _REASON_BEARING_EVENT else ('none',)


def _zero_initialize_label_children() -> None:
    """Create every reachable label child so each series is born at 0, not at 1.

    A prometheus_client Counter child does not exist until its first ``.inc()``,
    so a labelled series is first scraped already holding 1 and is never observed
    at 0. ``increase()`` and ``rate()`` measure movement inside the query window,
    and a series that appears at 1 and stays there has not moved — so the first
    event for a label combination contributes exactly nothing to every panel and
    rule built on them. Subscription events are rare and the labels are wide
    enough (``plan`` x ``interval``, one process per Cloud Run instance) that
    almost every event is the first for its combination, which is how a real
    cancellation renders as a confident 0.

    The reachable space is 4 non-``ended`` events x plans x intervals, plus
    ``ended`` x plans x intervals x reasons — bounded and closed by construction,
    which is the property the label sets above exist to guarantee.
    """

    for event in sorted(_EVENTS):
        for plan in sorted(_PLANS):
            for interval in sorted(_INTERVALS):
                for reason in _reachable_reasons(event):
                    OMI_SUBSCRIPTION_EVENTS.labels(event=event, plan=plan, interval=interval, reason=reason)


_zero_initialize_label_children()


def _determine_event(
    stripe_event_type: str,
    subscription_obj: Mapping[str, Any],
    previous_attributes: Mapping[str, Any],
) -> str | None:
    """Map one Stripe subscription event to a bounded lifecycle event, or None.

    ``previous_attributes`` is populated by Stripe with the *prior* value of
    only the fields that changed on ``customer.subscription.updated``. A plain
    update whose changed fields are not one of the tracked transitions below
    records nothing — that is deliberate noise suppression, not a bug.
    """

    if stripe_event_type == 'customer.subscription.created':
        return 'created'
    if stripe_event_type == 'customer.subscription.deleted':
        return 'ended'
    if stripe_event_type != 'customer.subscription.updated':
        return None

    if 'cancel_at_period_end' in previous_attributes:
        previous_value = previous_attributes.get('cancel_at_period_end')
        current_value = subscription_obj.get('cancel_at_period_end')
        if not previous_value and current_value:
            return 'cancellation_requested'
        if previous_value and not current_value:
            return 'cancellation_reverted'

    if 'status' in previous_attributes:
        current_status = subscription_obj.get('status')
        if current_status in _PAYMENT_FAILED_STATUSES:
            return 'payment_failed'

    return None


def _first_item_price(subscription_obj: Mapping[str, Any]) -> Mapping[str, Any]:
    items = subscription_obj.get('items')
    if not isinstance(items, Mapping):
        return {}
    data = items.get('data')
    if not isinstance(data, list) or not data:
        return {}
    first = data[0]
    if not isinstance(first, Mapping):
        return {}
    price = first.get('price')
    return price if isinstance(price, Mapping) else {}


def _resolve_plan(subscription_obj: Mapping[str, Any]) -> str:
    price_id = _first_item_price(subscription_obj).get('id')
    if not price_id:
        return 'unknown'
    try:
        plan = resolve_stripe_price_plan(price_id)
    except Exception:
        return 'unknown'
    # resolve_stripe_price_plan is typed to always return PlanType; still bound
    # the result against the closed label set rather than trusting the type
    # contract, in case the catalog ever adds a member this metric doesn't know.
    return plan.value if plan.value in _PLANS else 'unknown'


def _resolve_interval(subscription_obj: Mapping[str, Any]) -> str:
    recurring = _first_item_price(subscription_obj).get('recurring')
    interval = recurring.get('interval') if isinstance(recurring, Mapping) else None
    return interval if interval in _INTERVALS else 'unknown'


def _resolve_cancellation_reason(subscription_obj: Mapping[str, Any]) -> str:
    details = subscription_obj.get('cancellation_details')
    reason = details.get('reason') if isinstance(details, Mapping) else None
    return reason if reason in _REASONS else 'none'


def record_subscription_event(
    *,
    stripe_event_type: str,
    subscription_obj: Mapping[str, Any] | None,
    previous_attributes: Mapping[str, Any] | None = None,
) -> None:
    """Record one bounded subscription lifecycle event from a webhook delivery.

    Never raises. A payload this cannot make sense of is recorded as nothing
    rather than guessed at, and any unexpected failure is logged at warning
    and swallowed so instrumentation can never break the webhook path.
    """

    try:
        _record(stripe_event_type, subscription_obj or {}, previous_attributes or {})
    except Exception:
        logger.warning(
            'subscription_event_record_failed stripe_event_type=%s',
            stripe_event_type,
            exc_info=True,
        )


def _record(
    stripe_event_type: str,
    subscription_obj: Mapping[str, Any],
    previous_attributes: Mapping[str, Any],
) -> None:
    event = _determine_event(stripe_event_type, subscription_obj, previous_attributes)
    if event is None or event not in _EVENTS:
        return

    plan = _resolve_plan(subscription_obj)
    interval = _resolve_interval(subscription_obj)
    reason = _resolve_cancellation_reason(subscription_obj) if event == _REASON_BEARING_EVENT else 'none'

    OMI_SUBSCRIPTION_EVENTS.labels(event=event, plan=plan, interval=interval, reason=reason).inc()


def emit_billing_plan_changed(
    *,
    uid: str,
    stripe_event_id: str | None,
    stripe_event_created: int | float | None,
    stripe_event_type: str,
    subscription_obj: Mapping[str, Any] | None,
    previous_paid_subscription_id: str | None,
    resulting_paid_subscription_id: str | None,
    previous_attributes: Mapping[str, Any] | None = None,
) -> None:
    """Project a confirmed same-subscription paid price change; no writes."""
    from datetime import datetime, timezone
    from utils.product_telemetry import emit_product_event

    if (
        not uid
        or not stripe_event_id
        or stripe_event_type != 'customer.subscription.updated'
        or not isinstance(subscription_obj, Mapping)
        or not resulting_paid_subscription_id
        or previous_paid_subscription_id != resulting_paid_subscription_id
        or subscription_obj.get('id') != resulting_paid_subscription_id
        or not isinstance(previous_attributes, Mapping)
    ):
        return
    before = _first_item_price(previous_attributes)
    after = _first_item_price(subscription_obj)
    if not before.get('id') or not after.get('id') or before['id'] == after['id']:
        return
    previous_plan = _resolve_plan(previous_attributes)
    new_plan = _resolve_plan(subscription_obj)
    # Unknown historical prices cannot prove a paid-to-paid price transition.
    if previous_plan in {'basic', 'unknown'} or new_plan in {'basic', 'unknown'}:
        return
    interval = _resolve_interval(subscription_obj)
    is_trial = subscription_obj.get('status') == 'trialing'
    currency = _currency_wire(after)
    # Stripe previous_attributes is partial: absent status means unchanged.
    previous_status = previous_attributes.get('status', subscription_obj.get('status'))
    before_mrr = _monthly_mrr_cents(before, _resolve_interval(previous_attributes), previous_status)
    after_mrr = _monthly_mrr_cents(after, interval, subscription_obj.get('status'))
    occurred_at = None
    if isinstance(stripe_event_created, (int, float)):
        occurred_at = datetime.fromtimestamp(stripe_event_created, timezone.utc).isoformat().replace('+00:00', 'Z')
    event = 'Billing Subscription Plan Changed'
    emit_product_event(
        uid=uid,
        event=event,
        properties={
            '$insert_id': _billing_insert_id(event, subscription_obj.get('id'), stripe_event_id),
            'billing_event_id': stripe_event_id[:128],
            'occurred_at': occurred_at,
            'billing_source': 'stripe_webhook_authoritative_owner',
            'billing_measurement': 'trial_plan_entitlement' if is_trial else 'paid_plan_entitlement',
            'currency': currency,
            'is_trial': is_trial,
            'plan': new_plan,
            'previous_plan': previous_plan,
            'new_plan': new_plan,
            'interval': interval,
            'reason': 'none',
            'price_id': after['id'][:128],
            'price_generation': price_catalog_generation(after['id']),
            **({'mrr_cents': after_mrr, 'mrr_after_cents': after_mrr} if after_mrr is not None else {}),
            **({'mrr_before_cents': before_mrr} if before_mrr is not None else {}),
        },
    )
