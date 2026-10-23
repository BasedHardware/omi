"""Unit tests verifying payment proration failure guards in routers.payment and _build_subscription_from_stripe_object.

Regression test for issue #23301:
A declined proration on a plan change switches the plan anyway and drops a paid subscriber to Free.
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

# Ensure clean domain models if previous tests stubbed them with MagicMocks in sys.modules
if 'models.users' in sys.modules and isinstance(getattr(sys.modules['models.users'], 'PlanType', None), MagicMock):
    for mod in list(sys.modules.keys()):
        if mod.startswith(('models.users', 'utils.subscription', 'routers.payment')):
            del sys.modules[mod]

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import stripe
from models.users import PlanType, Subscription, SubscriptionStatus
from utils.subscription import get_plan_limits
from routers.payment import (
    _build_subscription_from_stripe_object,
    upgrade_subscription_endpoint,
    UpgradeSubscriptionRequest,
)


def test_build_subscription_past_due_preserves_paid_until_period_end():
    now = int(time.time())
    future = now + 86400 * 30  # 30 days remaining in paid period

    stripe_sub_future = {
        'id': 'sub_123',
        'status': 'past_due',
        'current_period_start': now - 86400 * 30,
        'current_period_end': future,
        'cancel_at_period_end': False,
        'items': {'data': [{'price': {'id': 'price_plus_annual'}}]},
    }

    with (
        patch('routers.payment.get_plan_type_from_price_id', return_value=PlanType.plus),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
    ):
        sub = _build_subscription_from_stripe_object(stripe_sub_future, now=now)
        assert sub is not None
        assert sub.plan == PlanType.plus
        assert sub.status == SubscriptionStatus.active
        assert sub.current_period_end == future


def test_build_subscription_past_due_drops_to_basic_when_period_ended():
    now = int(time.time())
    past = now - 100

    stripe_sub_past = {
        'id': 'sub_123',
        'status': 'past_due',
        'current_period_start': now - 86400 * 60,
        'current_period_end': past,
        'cancel_at_period_end': False,
        'items': {'data': [{'price': {'id': 'price_plus_annual'}}]},
    }

    with (
        patch('routers.payment.get_plan_type_from_price_id', return_value=PlanType.plus),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
    ):
        sub_expired = _build_subscription_from_stripe_object(stripe_sub_past, now=now)
        assert sub_expired is not None
        assert sub_expired.plan == PlanType.basic


def test_upgrade_subscription_endpoint_card_declined_raises_402():
    uid = 'test_user_123'
    current_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_start=int(time.time()) - 86400 * 10,
        current_period_end=int(time.time()) + 86400 * 350,
        stripe_subscription_id='sub_annual_plus',
    )

    mock_stripe_sub = MagicMock()
    mock_stripe_sub.to_dict.return_value = {
        'id': 'sub_annual_plus',
        'cancel_at_period_end': False,
        'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_plus_annual'}}]},
        'current_period_start': current_sub.current_period_start,
        'current_period_end': current_sub.current_period_end,
    }

    target_price_mock = MagicMock()
    target_price_mock.recurring.interval = 'year'

    card_error = stripe.error.CardError(
        message="Your card was declined. Insufficient funds.",
        param="card",
        code="card_declined",
    )

    with (
        patch('routers.payment._validate_price_id'),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id', side_effect=lambda pid: PlanType.unlimited if pid == 'price_unlimited_annual' else PlanType.plus),
        patch('routers.payment.stripe.Price.retrieve', return_value=target_price_mock),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', side_effect=card_error),
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
    ):
        request = UpgradeSubscriptionRequest(price_id='price_unlimited_annual')
        with pytest.raises(HTTPException) as exc_info:
            upgrade_subscription_endpoint(request, uid=uid)

        assert exc_info.value.status_code == 402
        assert "Upgrade payment failed or was declined" in exc_info.value.detail
        assert "Your current plan remains active" in exc_info.value.detail
        mock_update_db.assert_not_called()


def test_upgrade_subscription_endpoint_declined_invoice_raises_402():
    uid = 'test_user_123'
    current_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_start=int(time.time()) - 86400 * 10,
        current_period_end=int(time.time()) + 86400 * 350,
        stripe_subscription_id='sub_annual_plus',
    )

    mock_stripe_sub = MagicMock()
    mock_stripe_sub.to_dict.return_value = {
        'id': 'sub_annual_plus',
        'cancel_at_period_end': False,
        'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_plus_annual'}}]},
        'current_period_start': current_sub.current_period_start,
        'current_period_end': current_sub.current_period_end,
    }

    target_price_mock = MagicMock()
    target_price_mock.recurring.interval = 'year'

    # Stripe returns modified subscription with pending_if_incomplete invoice requires_payment_method
    updated_sub_dict = {
        'id': 'sub_annual_plus',
        'status': 'past_due',
        'pending_update': {'items': [{'price': 'price_unlimited_annual'}]},
        'latest_invoice': {
            'id': 'in_123',
            'status': 'open',
            'payment_intent': {
                'id': 'pi_123',
                'status': 'requires_payment_method',
                'last_payment_error': {'message': 'The card has insufficient funds.'},
            },
        },
        'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_plus_annual'}}]},
    }
    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = updated_sub_dict

    with (
        patch('routers.payment._validate_price_id'),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id', side_effect=lambda pid: PlanType.unlimited if pid == 'price_unlimited_annual' else PlanType.plus),
        patch('routers.payment.stripe.Price.retrieve', return_value=target_price_mock),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', return_value=mock_updated_sub) as mock_modify,
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
    ):
        request = UpgradeSubscriptionRequest(price_id='price_unlimited_annual')
        with pytest.raises(HTTPException) as exc_info:
            upgrade_subscription_endpoint(request, uid=uid)

        assert exc_info.value.status_code == 402
        assert "The card has insufficient funds" in exc_info.value.detail
        assert "Your current plan remains active" in exc_info.value.detail
        # Verify payment_behavior='pending_if_incomplete' was supplied to Stripe
        modify_kwargs = mock_modify.call_args[1]
        assert modify_kwargs.get('payment_behavior') == 'pending_if_incomplete'
        assert modify_kwargs.get('expand') == ['latest_invoice.payment_intent']
        # User subscription must NOT have been updated
        mock_update_db.assert_not_called()


def test_upgrade_subscription_endpoint_success_updates_plan():
    uid = 'test_user_123'
    current_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_start=int(time.time()) - 86400 * 10,
        current_period_end=int(time.time()) + 86400 * 350,
        stripe_subscription_id='sub_annual_plus',
    )

    mock_stripe_sub = MagicMock()
    mock_stripe_sub.to_dict.return_value = {
        'id': 'sub_annual_plus',
        'cancel_at_period_end': False,
        'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_plus_annual'}}]},
        'current_period_start': current_sub.current_period_start,
        'current_period_end': current_sub.current_period_end,
    }

    target_price_mock = MagicMock()
    target_price_mock.recurring.interval = 'year'

    updated_sub_dict = {
        'id': 'sub_annual_plus',
        'status': 'active',
        'latest_invoice': {
            'id': 'in_123',
            'status': 'paid',
            'payment_intent': {
                'id': 'pi_123',
                'status': 'succeeded',
            },
        },
        'current_period_start': int(time.time()),
        'current_period_end': int(time.time()) + 86400 * 365,
        'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_unlimited_annual'}}]},
    }
    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = updated_sub_dict

    with (
        patch('routers.payment._validate_price_id'),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id', side_effect=lambda pid: PlanType.unlimited if pid == 'price_unlimited_annual' else PlanType.plus),
        patch('routers.payment.stripe.Price.retrieve', return_value=target_price_mock),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', return_value=mock_updated_sub),
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
        patch('routers.payment.conversations_db.unlock_all_conversations'),
        patch('routers.payment.memories_db.unlock_all_memories'),
        patch('routers.payment.action_items_db.unlock_all_action_items'),
        patch('routers.payment.clear_fair_use_on_upgrade'),
        patch('routers.payment.set_credits_invalidation_signal'),
        patch('routers.payment.clear_trial_paywall_cache'),
        patch('routers.payment.funded_processing_enabled', return_value=False),
    ):
        request = UpgradeSubscriptionRequest(price_id='price_unlimited_annual')
        resp = upgrade_subscription_endpoint(request, uid=uid)

        assert resp['status'] == 'success'
        assert "You've been upgraded to Unlimited" in resp['message']
        mock_update_db.assert_called_once()
        saved_sub = mock_update_db.call_args[0][1]
        assert saved_sub['plan'] == 'unlimited'


@pytest.mark.asyncio
async def test_webhook_past_due_stale_shield_preserves_current_paid_sub():
    from routers.payment import _handle_stripe_event

    now = int(time.time())
    current_paid = Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        current_period_start=now - 100,
        current_period_end=now + 10000,
        stripe_subscription_id='sub_new_active',
    )

    stale_past_due_event = {
        'type': 'customer.subscription.updated',
        'data': {
            'object': {
                'id': 'sub_old_superseded',
                'customer': 'cus_123',
                'status': 'past_due',
                'current_period_start': now - 2000,
                'current_period_end': now + 5000,
                'items': {'data': [{'price': {'id': 'price_plus'}}]},
            }
        }
    }

    with (
        patch('routers.payment.users_db.get_user_by_stripe_customer_id', return_value={'uid': 'user_123'}),
        patch('routers.payment.users_db.get_existing_user_subscription', return_value=current_paid),
        patch('routers.payment.preserves_current_paid_subscription', return_value=True),
        patch('routers.payment.users_db.update_user_subscription') as mock_update,
    ):
        res = await _handle_stripe_event(stale_past_due_event)
        assert res == {'status': 'success'}
        mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_past_due_same_sub_grants_grace():
    from routers.payment import _handle_stripe_event

    now = int(time.time())
    current_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_start=now - 100,
        current_period_end=now + 10000,
        stripe_subscription_id='sub_same',
    )

    past_due_event = {
        'type': 'customer.subscription.updated',
        'data': {
            'object': {
                'id': 'sub_same',
                'customer': 'cus_123',
                'status': 'past_due',
                'current_period_start': now - 100,
                'current_period_end': now + 10000,
                'items': {'data': [{'price': {'id': 'price_plus'}}]},
            }
        }
    }

    with (
        patch('routers.payment.users_db.get_user_by_stripe_customer_id', return_value={'uid': 'user_123'}),
        patch('routers.payment.users_db.get_existing_user_subscription', return_value=current_sub),
        patch('routers.payment.preserves_current_paid_subscription', return_value=False),
        patch('routers.payment.find_active_paid_subscription_for_user', return_value=None),
        patch('routers.payment.get_plan_type_from_price_id', return_value=PlanType.plus),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.users_db.update_user_subscription') as mock_update,
        patch('routers.payment.users_db.get_user_profile', return_value={'uid': 'user_123'}),
        patch('routers.payment.users_db.set_stripe_customer_id'),
        patch('routers.payment.conversations_db.unlock_all_conversations'),
        patch('routers.payment.memories_db.unlock_all_memories'),
        patch('routers.payment.action_items_db.unlock_all_action_items'),
        patch('routers.payment.clear_trial_paywall_cache'),
        patch('routers.payment.clear_fair_use_on_upgrade'),
        patch('routers.payment.set_credits_invalidation_signal'),
        patch('routers.payment.funded_processing_enabled', return_value=False),
    ):
        res = await _handle_stripe_event(past_due_event)
        assert res == {'status': 'success'}
        mock_update.assert_called_once()
        saved = mock_update.call_args[0][1]
        assert saved['plan'] == 'plus'
        assert saved['status'] == 'active'

