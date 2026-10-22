"""Unit tests for promo code minimum_amount and multi-currency / trial resilience.

Regression tests for:
- Issue #23300: Unlimited first-year promo code rejected with 'minimum amount' in GBP / trial checkout
- Issue #23299: Unlimited membership promo codes carry a USD $269 minimum, rejected for customers paying in other currencies
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

import stripe
from models.users import PlanType, Subscription, SubscriptionStatus
from utils.subscription import get_plan_limits
import utils.stripe as stripe_utils
from routers.payment import (
    create_checkout_session_endpoint,
    upgrade_subscription_endpoint,
    CreateCheckoutRequest,
    UpgradeSubscriptionRequest,
)


def test_checkout_suppresses_trial_when_promo_provided():
    """When a promo code is provided in checkout, trial_days is omitted to prevent $0 minimum_amount conflict."""
    captured = {}

    def mock_create_session(uid, price_id, idempotency_key, customer_id=None, promotion_code_id=None, trial_period_days=None):
        captured['promotion_code_id'] = promotion_code_id
        captured['trial_period_days'] = trial_period_days
        return SimpleNamespace(url='https://checkout.stripe.com/pay/cs_test', id='cs_test')

    promo_mock = MagicMock()
    promo_mock.id = 'promo_unlimited_year'
    promo_list_mock = MagicMock(data=[promo_mock])

    with (
        patch('routers.payment._validate_price_id'),
        patch('routers.payment.subscription_utils.can_user_make_payment', return_value=(True, '')),
        patch('routers.payment.stripe.PromotionCode.list', return_value=promo_list_mock),
        patch('routers.payment._try_reactivate_subscription', return_value=None),
        patch('routers.payment.users_db.get_stripe_customer_id', return_value=None),
        patch('routers.payment.stripe_utils.create_subscription_checkout_session', side_effect=mock_create_session),
    ):
        req = CreateCheckoutRequest(price_id='price_unlimited_annual', promotion_code='OMI-4FHY-W6SR', trial_days=7)
        resp = create_checkout_session_endpoint(req, uid='uid_test')

        assert resp['session_id'] == 'cs_test'
        assert captured['promotion_code_id'] == 'promo_unlimited_year'
        assert captured['trial_period_days'] is None


def test_create_subscription_checkout_session_disables_adaptive_pricing_and_trial():
    """Verify create_subscription_checkout_session omits trial and disables adaptive pricing when promo provided."""
    with patch('utils.stripe.stripe.checkout.Session.create') as mock_session_create:
        mock_session_create.return_value = SimpleNamespace(url='https://checkout.stripe.com/test', id='cs_123')

        stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited',
            idempotency_key='idem_1',
            promotion_code_id='promo_123',
            trial_period_days=7,
        )

        mock_session_create.assert_called_once()
        params = mock_session_create.call_args[1]
        assert 'trial_period_days' not in params.get('subscription_data', {})
        assert params.get('discounts') == [{'promotion_code': 'promo_123'}]
        assert params.get('adaptive_pricing') == {'enabled': False}


def test_create_subscription_checkout_session_minimum_amount_fallback_to_coupon():
    """If Stripe rejects Session.create with minimum amount error, fallback to coupon discount."""
    min_amount_error = stripe.error.InvalidRequestError(
        message="This code is valid, but your order doesn't meet the minimum amount.",
        param="discounts",
    )

    promo_obj = MagicMock()
    promo_obj.coupon.id = 'coup_100_percent'

    with (
        patch('utils.stripe.stripe.checkout.Session.create', side_effect=[min_amount_error, SimpleNamespace(url='https://checkout', id='cs_ok')]) as mock_session_create,
        patch('utils.stripe.stripe.PromotionCode.retrieve', return_value=promo_obj) as mock_retrieve,
    ):
        session = stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited',
            idempotency_key='idem_1',
            promotion_code_id='promo_min_error',
        )

        assert session is not None
        assert session.id == 'cs_ok'
        assert mock_session_create.call_count == 2
        retry_params = mock_session_create.call_args[1]
        assert retry_params['discounts'] == [{'coupon': 'coup_100_percent'}]
        assert 'adaptive_pricing' not in retry_params


def test_upgrade_subscription_endpoint_minimum_amount_fallback_to_coupon():
    """If Stripe Subscription.modify fails with minimum_amount in EUR/GBP, fallback to coupon and deactivate single-use code."""
    uid = 'test_user_eur'
    current_sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_start=1000,
        current_period_end=2000,
        stripe_subscription_id='sub_eur_1',
    )

    mock_stripe_sub = MagicMock()
    mock_stripe_sub.to_dict.return_value = {
        'id': 'sub_eur_1',
        'cancel_at_period_end': False,
        'items': {'data': [{'id': 'si_1', 'price': {'id': 'price_plus_monthly'}}]},
        'current_period_start': 1000,
        'current_period_end': 2000,
    }

    target_price_mock = MagicMock()
    target_price_mock.recurring.interval = 'year'

    min_amount_error = stripe.error.InvalidRequestError(
        message="The promotion code's minimum amount (269.00 USD) was not met. The invoice total was 249.00 EUR.",
        param="discounts",
    )

    promo_obj = MagicMock()
    promo_obj.id = 'promo_skypilot_1'
    promo_obj.max_redemptions = 1
    promo_obj.coupon.id = 'coup_unlimited_year'

    updated_sub_dict = {
        'id': 'sub_eur_1',
        'status': 'active',
        'current_period_start': 2000,
        'current_period_end': 2000 + 86400 * 365,
        'items': {'data': [{'id': 'si_1', 'price': {'id': 'price_unlimited_annual'}}]},
    }
    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = updated_sub_dict

    with (
        patch('routers.payment._validate_price_id'),
        patch('routers.payment.get_basic_plan_limits', side_effect=lambda: get_plan_limits(PlanType.basic)),
        patch('routers.payment.get_plan_limits', side_effect=get_plan_limits),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id', side_effect=lambda pid: PlanType.unlimited if 'unlimited' in pid else PlanType.plus),
        patch('routers.payment.stripe.Price.retrieve', return_value=target_price_mock),
        patch('routers.payment.stripe.PromotionCode.list', return_value=MagicMock(data=[promo_obj])),
        patch('routers.payment.stripe.PromotionCode.retrieve', return_value=promo_obj),
        patch('routers.payment.stripe.PromotionCode.modify') as mock_promo_modify,
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', side_effect=[min_amount_error, mock_updated_sub]) as mock_sub_modify,
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
        patch('routers.payment.conversations_db.unlock_all_conversations'),
        patch('routers.payment.memories_db.unlock_all_memories'),
        patch('routers.payment.action_items_db.unlock_all_action_items'),
        patch('routers.payment.clear_fair_use_on_upgrade'),
        patch('routers.payment.set_credits_invalidation_signal'),
        patch('routers.payment.clear_trial_paywall_cache'),
        patch('routers.payment.funded_processing_enabled', return_value=False),
    ):
        req = UpgradeSubscriptionRequest(price_id='price_unlimited_annual', promotion_code='OMI-EUR-PROMO')
        resp = upgrade_subscription_endpoint(req, uid=uid)

        assert resp['status'] == 'success'
        assert mock_sub_modify.call_count == 2
        # Verify second call used coupon fallback
        retry_modify_call = mock_sub_modify.call_args_list[1][1]
        assert retry_modify_call['discounts'] == [{'coupon': 'coup_unlimited_year'}]
        # Verify single use promo code was deactivated
        mock_promo_modify.assert_called_once_with('promo_skypilot_1', active=False)
        mock_update_db.assert_called_once()
