"""Pure legacy Stripe entitlement decisions; IO belongs to payment.py.

The adapter resolves prices, fetches replacement subscriptions and supplies the
clock. No delivery-order policy is introduced here: legacy last-delivery-wins,
trialing access and past_due→Basic are deliberately preserved.
"""

from dataclasses import dataclass
from typing import Mapping, Any

from config.plan_catalog import PAID_PLAN_TYPES
from models.users import PlanType, PlanLimits, Subscription, SubscriptionStatus

SUBSCRIPTION_EVENTS = frozenset(
    {
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
    }
)


def project_subscription(
    obj: Mapping[str, Any], plan: PlanType | None, limits: PlanLimits | dict[str, Any]
) -> Subscription | None:
    """Project a snapshot using a price binding resolved by the IO adapter.

    Inactive snapshots never require a price binding. current_price_id remains
    unset, matching the original webhook (read-path adoption may set it).
    """
    paid_status = obj['status'] in ('active', 'trialing')
    effective_plan = plan if paid_status else PlanType.basic
    if effective_plan is None:
        return None
    return Subscription(
        plan=effective_plan,
        status=SubscriptionStatus.active,
        current_period_end=obj.get('current_period_end'),
        current_period_start=obj.get('current_period_start'),
        stripe_subscription_id=obj['id'],
        cancel_at_period_end=obj.get('cancel_at_period_end', False) if paid_status else False,
        limits=PlanLimits.model_validate(limits),
    )


def preserves_current_paid_subscription(
    current: Subscription | None, event_subscription_id: str | None, now: int
) -> bool:
    """The original stale different-id downgrade guard, with an explicit clock."""
    return bool(
        current
        and event_subscription_id
        and current.stripe_subscription_id != event_subscription_id
        and current.status == SubscriptionStatus.active
        and current.plan in PAID_PLAN_TYPES
        and current.current_period_end
        and current.current_period_end >= now
    )


@dataclass(frozen=True)
class ResolvedStripeEvent:
    """Stripe event plus IO-resolved projection and optional adoption candidate."""

    event_type: str
    subscription_id: str | None
    candidate: Subscription | None
    now: int
    active_paid: Subscription | None = None
    billing_owner_confirmed: bool = False
    schedule_status: str | None = None


@dataclass(frozen=True)
class Transition:
    next_state: Subscription | None
    effects: tuple[str, ...] = ()
    outcome: str = 'ignored'
    adopted_active_paid: bool = False


def transition(current: Subscription | None, event: ResolvedStripeEvent) -> Transition:
    """(current entitlement, resolved Stripe event) → (next entitlement, effects).

    Effects preserve the lifecycle handler's exact ordering. The adapter
    supplies a replacement candidate only after the stored-row preservation
    check fails. No IO, mutation or telemetry happens here.
    """
    if event.event_type == 'checkout.session.completed':
        if current and current.stripe_subscription_id and current.plan in PAID_PLAN_TYPES:
            if current.stripe_subscription_id == event.subscription_id:
                return Transition(current, outcome='duplicate_checkout')
            return Transition(current, ('cancel_old_subscription',), 'replacement_checkout')
        return Transition(current, outcome='new_checkout')
    if event.event_type in {
        'subscription_schedule.completed',
        'subscription_schedule.updated',
        'subscription_schedule.canceled',
    }:
        if event.candidate is None or event.schedule_status not in {'completed', 'canceled'}:
            return Transition(current)
        candidate = event.candidate
        if event.schedule_status == 'canceled':
            candidate = candidate.model_copy(update={'cancel_at_period_end': True})
        effects = ('persist_subscription', 'invalidate_credits', 'clear_trial_cache')
        if event.schedule_status == 'completed' and candidate.plan in PAID_PLAN_TYPES:
            effects += ('clear_fair_use',)
        return Transition(candidate, effects, 'projected')
    if event.event_type not in SUBSCRIPTION_EVENTS or event.candidate is None:
        return Transition(current)
    candidate = event.candidate
    adopted = False
    if candidate.plan not in PAID_PLAN_TYPES:
        if preserves_current_paid_subscription(current, event.subscription_id, event.now):
            return Transition(current, outcome='preserved_current')
        if event.active_paid and event.active_paid.stripe_subscription_id != event.subscription_id:
            candidate = event.active_paid
            adopted = True
    paid = candidate.status == SubscriptionStatus.active and candidate.plan in PAID_PLAN_TYPES
    effects = ()
    if paid:
        if not adopted:
            effects += ('set_customer',)
        effects += ('unlock_conversations', 'unlock_memories', 'unlock_actions')
    effects += ('persist_subscription',)
    if not adopted and event.billing_owner_confirmed:
        effects += ('billing_telemetry',)
    effects += ('invalidate_credits', 'clear_trial_cache')
    if paid:
        effects += ('clear_fair_use',)
    return Transition(candidate, effects, 'adopted' if adopted else 'projected', adopted)
