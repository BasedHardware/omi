"""Tests for proration decline protection during cross-plan subscription changes (#23301).

When an active subscriber upgrades their plan (cross-plan change with proration),
`stripe.Subscription.modify` must use `payment_behavior='error_if_incomplete'`.
If the prorated payment is declined (e.g. card declined, insufficient funds),
the update must be rejected immediately without modifying the local subscription
in the database or demoting the user to Basic/Free.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
import stripe  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import routers.payment as payment  # noqa: E402

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / 'routers' / 'payment.py'


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding='utf-8')


def test_cross_plan_change_declares_error_if_incomplete():
    """Verify source declares payment_behavior='error_if_incomplete' in modify_params."""
    source = _source()
    assert "'payment_behavior': 'error_if_incomplete'" in source


def test_upgrade_subscription_endpoint_has_card_error_handler():
    """Verify upgrade_subscription_endpoint catches stripe.error.CardError safely."""
    source = _source()
    start = source.index('def upgrade_subscription_endpoint(')
    end = source.index('\n@router.', start + 1) if '\n@router.' in source[start + 1 :] else len(source)
    func_source = source[start:end]

    assert 'except stripe.error.CardError as e:' in func_source
    assert 'Upgrade payment failed:' in func_source
    assert 'Your current plan remains active.' in func_source


def _build_mock_stripe_sub(sub_id: str, price_id: str):
    data = {
        'id': sub_id,
        'status': 'active',
        'items': {'data': [{'id': f'si_{sub_id}', 'price': {'id': price_id}}]},
    }
    m = MagicMock()
    m.to_dict.return_value = data
    m.__getitem__.side_effect = data.__getitem__
    m.get.side_effect = data.get
    return m


def test_cross_plan_upgrade_passes_payment_behavior_to_stripe():
    """When upgrading cross-plan, payment_behavior='error_if_incomplete' is passed to stripe.Subscription.modify."""
    uid = 'test_uid_123'
    current_sub = payment.Subscription(
        plan=payment.PlanType.unlimited,
        status=payment.SubscriptionStatus.active,
        stripe_subscription_id='sub_active_123',
    )
    mock_stripe_sub = _build_mock_stripe_sub('sub_active_123', 'price_unlimited_monthly')
    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = 'month'

    mock_updated_sub = MagicMock()
    updated_dict = {
        'id': 'sub_active_123',
        'status': 'active',
        'items': {'data': [{'id': 'si_sub_active_123', 'price': {'id': 'price_architect_monthly'}}]},
    }
    mock_updated_sub.to_dict.return_value = updated_dict
    mock_updated_sub.get.side_effect = updated_dict.get
    mock_updated_sub.__getitem__.side_effect = updated_dict.__getitem__

    with (
        patch('routers.payment.is_purchasable_price_id', return_value=True),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id') as mock_plan_type,
        patch('routers.payment.stripe.Price.retrieve', return_value=mock_target_price),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', return_value=mock_updated_sub) as mock_modify,
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
        patch('routers.payment.set_credits_invalidation_signal'),
        patch('routers.payment.clear_trial_paywall_cache'),
        patch('routers.payment.conversations_db.unlock_all_conversations'),
        patch('routers.payment.memories_db.unlock_all_memories'),
        patch('routers.payment.action_items_db.unlock_all_action_items'),
        patch('routers.payment.clear_fair_use_on_upgrade'),
        patch('routers.payment.funded_processing_enabled', return_value=False),
    ):
        mock_plan_type.side_effect = lambda price_id: (
            payment.PlanType.architect if 'architect' in price_id else payment.PlanType.unlimited
        )

        req = payment.UpgradeSubscriptionRequest(price_id='price_architect_monthly')
        res = payment.upgrade_subscription_endpoint(req, uid=uid)

        assert res['status'] == 'success'
        mock_modify.assert_called_once()
        _, kwargs = mock_modify.call_args
        assert kwargs.get('payment_behavior') == 'error_if_incomplete'
        assert kwargs.get('proration_behavior') == 'always_invoice'
        mock_update_db.assert_called_once()


def test_cross_plan_upgrade_card_declined_preserves_current_plan():
    """If the card is declined during upgrade proration, CardError is caught and current plan is preserved."""
    uid = 'test_uid_456'
    current_sub = payment.Subscription(
        plan=payment.PlanType.unlimited,
        status=payment.SubscriptionStatus.active,
        stripe_subscription_id='sub_active_456',
    )
    mock_stripe_sub = _build_mock_stripe_sub('sub_active_456', 'price_unlimited_annual')
    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = 'year'

    card_err = stripe.error.CardError(
        message="Your card has insufficient funds.",
        param="card",
        code="card_declined",
    )

    with (
        patch('routers.payment.is_purchasable_price_id', return_value=True),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id') as mock_plan_type,
        patch('routers.payment.stripe.Price.retrieve', return_value=mock_target_price),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', side_effect=card_err),
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
    ):
        mock_plan_type.side_effect = lambda price_id: (
            payment.PlanType.architect if 'architect' in price_id else payment.PlanType.unlimited
        )

        req = payment.UpgradeSubscriptionRequest(price_id='price_architect_annual')
        with pytest.raises(HTTPException) as exc_info:
            payment.upgrade_subscription_endpoint(req, uid=uid)

        assert exc_info.value.status_code == 400
        assert "Upgrade payment failed: Your card has insufficient funds. Your current plan remains active." in exc_info.value.detail
        # Most critical: database MUST NOT be updated to free/basic or new plan!
        mock_update_db.assert_not_called()


def test_cross_plan_upgrade_non_active_result_aborts_without_database_update():
    """If Stripe returns a non-active status (e.g. past_due), the operation aborts to protect user's subscription."""
    uid = 'test_uid_789'
    current_sub = payment.Subscription(
        plan=payment.PlanType.unlimited,
        status=payment.SubscriptionStatus.active,
        stripe_subscription_id='sub_active_789',
    )
    mock_stripe_sub = _build_mock_stripe_sub('sub_active_789', 'price_unlimited_monthly')
    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = 'month'

    # Simulated past_due subscription returned by Stripe
    mock_past_due_sub = MagicMock()
    past_due_dict = {
        'id': 'sub_active_789',
        'status': 'past_due',
        'items': {'data': [{'id': 'si_sub_active_789', 'price': {'id': 'price_architect_monthly'}}]},
    }
    mock_past_due_sub.to_dict.return_value = past_due_dict
    mock_past_due_sub.get.side_effect = past_due_dict.get
    mock_past_due_sub.__getitem__.side_effect = past_due_dict.__getitem__

    with (
        patch('routers.payment.is_purchasable_price_id', return_value=True),
        patch('routers.payment.users_db.get_user_subscription', return_value=current_sub),
        patch('routers.payment.stripe.Subscription.retrieve', return_value=mock_stripe_sub),
        patch('routers.payment.get_plan_type_from_price_id') as mock_plan_type,
        patch('routers.payment.stripe.Price.retrieve', return_value=mock_target_price),
        patch('routers.payment._release_attached_schedules'),
        patch('routers.payment.stripe.Subscription.modify', return_value=mock_past_due_sub),
        patch('routers.payment.users_db.update_user_subscription') as mock_update_db,
    ):
        mock_plan_type.side_effect = lambda price_id: (
            payment.PlanType.architect if 'architect' in price_id else payment.PlanType.unlimited
        )

        req = payment.UpgradeSubscriptionRequest(price_id='price_architect_monthly')
        with pytest.raises(HTTPException) as exc_info:
            payment.upgrade_subscription_endpoint(req, uid=uid)

        assert exc_info.value.status_code == 400
        assert "Upgrade payment could not be completed. Your current plan remains active." in exc_info.value.detail
        # Database was never updated to past_due / Basic!
        mock_update_db.assert_not_called()
