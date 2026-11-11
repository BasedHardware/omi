"""Pure decisions have no clock, storage, Stripe or telemetry dependencies."""

from itertools import permutations

import pytest

from models.users import PlanType, Subscription, SubscriptionStatus, PlanLimits
from utils.subscription_state_machine import ResolvedStripeEvent, project_subscription, transition


@pytest.mark.parametrize(
    'status', ['active', 'trialing', 'past_due', 'unpaid', 'canceled', 'incomplete', 'incomplete_expired', 'paused']
)
def test_projection_is_deterministic_and_does_not_mutate_input(status):
    obj = {'id': 'sub-one', 'status': status, 'current_period_end': 200, 'cancel_at_period_end': True}
    before = dict(obj)
    result = project_subscription(obj, PlanType.plus, PlanLimits(transcription_seconds=5))
    assert (
        result.model_dump_json()
        == project_subscription(obj, PlanType.plus, PlanLimits(transcription_seconds=5)).model_dump_json()
    )
    assert result.plan == (PlanType.plus if status in ('active', 'trialing') else PlanType.basic)
    assert result.current_price_id is None
    assert obj == before


@pytest.mark.parametrize('order', list(permutations(['created', 'updated', 'deleted'])))
def test_all_lifecycle_delivery_permutations_preserve_last_delivery_wins(order):
    current = None
    candidates = {
        'created': Subscription(plan=PlanType.basic, stripe_subscription_id='sub-one'),
        'updated': Subscription(plan=PlanType.plus, stripe_subscription_id='sub-one'),
        'deleted': Subscription(plan=PlanType.basic, stripe_subscription_id='sub-one'),
    }
    for kind in order:
        event = ResolvedStripeEvent(f'customer.subscription.{kind}', 'sub-one', candidates[kind], 100)
        before = current.model_dump_json() if current else None
        decision = transition(current, event)
        assert (current.model_dump_json() if current else None) == before
        assert decision.next_state.model_dump_json() == candidates[kind].model_dump_json()
        current = decision.next_state


@pytest.mark.parametrize('status', list(SubscriptionStatus))
@pytest.mark.parametrize('plan', list(PlanType))
@pytest.mark.parametrize('same_id', [True, False])
def test_current_state_cross_product_preservation(status, plan, same_id):
    current = Subscription(
        plan=plan, status=status, stripe_subscription_id='sub-event' if same_id else 'sub-new', current_period_end=200
    )
    candidate = Subscription(plan=PlanType.basic, stripe_subscription_id='sub-event')
    decision = transition(current, ResolvedStripeEvent('customer.subscription.deleted', 'sub-event', candidate, 100))
    preserved = plan != PlanType.basic and status == SubscriptionStatus.active and not same_id
    assert decision.outcome == ('preserved_current' if preserved else 'projected')
    assert decision.next_state.model_dump_json() == (current if preserved else candidate).model_dump_json()


def test_schedule_cancel_is_copy_and_checkout_duplicate_has_no_effects():
    candidate = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-one')
    event = ResolvedStripeEvent('subscription_schedule.canceled', 'sub-one', candidate, 100, schedule_status='canceled')
    decision = transition(None, event)
    assert decision.next_state.cancel_at_period_end is True
    assert candidate.cancel_at_period_end is False
    decision = transition(candidate, ResolvedStripeEvent('checkout.session.completed', 'sub-one', None, 100))
    assert decision.outcome == 'duplicate_checkout'
    assert decision.effects == ()
