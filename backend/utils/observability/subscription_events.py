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
from typing import Any

from config.plan_catalog import PlanType, resolve_stripe_price_plan
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
