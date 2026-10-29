"""Regression tests for promotion code checkout with requested trial period (#23982, #23300).

Validates:
- Suppressing trial_period_days when a promotion code is provided in CreateCheckoutRequest
- Retaining trial_period_days when no promotion code is provided
- Preventing former subscriber trial_unavailable rejection when promo is provided (trial suppressed)
- Preserving former subscriber trial_unavailable rejection when no promo is provided
- Stripe checkout session helper omits trial_period_days from subscription_data when promotion_code_id is present
- Stripe checkout session helper keeps trial_period_days when promotion_code_id is absent
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import routers.payment as payment  # noqa: E402
from routers.payment import CreateCheckoutRequest  # noqa: E402
import utils.stripe as stripe_utils  # noqa: E402


def _run_checkout_endpoint(price_id='price_1', trial_days=None, promo_code=None, existing_customer_id=None):
    captured = {}

    def mock_create_session(
        uid, price_id, idempotency_key, customer_id=None, promotion_code_id=None, trial_period_days=None
    ):
        captured['uid'] = uid
        captured['price_id'] = price_id
        captured['customer_id'] = customer_id
        captured['promotion_code_id'] = promotion_code_id
        captured['trial_period_days'] = trial_period_days
        return SimpleNamespace(url='https://checkout.stripe.com/pay/cs_test', id='cs_test')

    promo_mock = MagicMock()
    promo_mock.id = 'promo_resolved_123'
    promo_list_data = [promo_mock] if promo_code else []

    with (
        patch.object(payment, 'is_purchasable_price_id', return_value=True),
        patch.object(payment.subscription_utils, 'can_user_make_payment', return_value=(True, '')),
        patch.object(payment.subscription_utils, 'new_buyer_single_plan_violation', return_value=None),
        patch.object(payment, '_try_reactivate_subscription', return_value=None),
        patch.object(payment.users_db, 'get_stripe_customer_id', return_value=existing_customer_id),
        patch.object(payment.stripe.PromotionCode, 'list', return_value=SimpleNamespace(data=promo_list_data)),
        patch.object(payment.stripe_utils, 'create_subscription_checkout_session', side_effect=mock_create_session),
    ):
        req = CreateCheckoutRequest(price_id=price_id, trial_days=trial_days, promotion_code=promo_code)
        resp = payment.create_checkout_session_endpoint(req, uid='uid_test_1')

    return resp, captured


def test_checkout_suppresses_trial_when_promo_provided():
    """When a promo code is provided in checkout, trial_days is omitted to prevent $0 minimum_amount conflict (#23982)."""
    resp, captured = _run_checkout_endpoint(
        price_id='price_unlimited_annual',
        trial_days=7,
        promo_code='PROMO-100-YEAR',
        existing_customer_id=None,
    )
    assert resp['session_id'] == 'cs_test'
    assert captured['promotion_code_id'] == 'promo_resolved_123'
    assert captured['trial_period_days'] is None


def test_checkout_preserves_trial_when_no_promo_provided():
    """When no promo code is provided, trial_days is passed through to Stripe."""
    resp, captured = _run_checkout_endpoint(
        price_id='price_unlimited_annual',
        trial_days=7,
        promo_code=None,
        existing_customer_id=None,
    )
    assert resp['session_id'] == 'cs_test'
    assert captured['promotion_code_id'] is None
    assert captured['trial_period_days'] == 7


def test_existing_customer_with_promo_is_not_refused_trial_unavailable():
    """A returning customer who redeems a promo code is not rejected with trial_unavailable even if trial_days was requested."""
    resp, captured = _run_checkout_endpoint(
        price_id='price_unlimited_annual',
        trial_days=7,
        promo_code='PROMO-RENEW-100',
        existing_customer_id='cus_existing_123',
    )
    assert resp['session_id'] == 'cs_test'
    assert captured['promotion_code_id'] == 'promo_resolved_123'
    assert captured['trial_period_days'] is None


def test_existing_customer_without_promo_is_refused_trial_unavailable():
    """A returning customer requesting trial_days without promo code is rejected with trial_unavailable."""
    with pytest.raises(HTTPException) as excinfo:
        _run_checkout_endpoint(
            price_id='price_unlimited_annual',
            trial_days=7,
            promo_code=None,
            existing_customer_id='cus_existing_123',
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == 'trial_unavailable'


def test_stripe_utils_omits_trial_when_promo_present():
    """utils.stripe omits trial_period_days from subscription_data when promotion_code_id is present."""
    captured = {}

    def fake_create(**params):
        captured.update(params)
        return SimpleNamespace(url='https://checkout.stripe.com/pay/cs_test', id='cs_test')

    with (
        patch.object(stripe_utils.stripe.checkout.Session, 'create', side_effect=fake_create),
        patch.object(stripe_utils.stripe.Price, 'retrieve', return_value=SimpleNamespace(currency='usd')),
    ):
        stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited',
            idempotency_key='k_1',
            promotion_code_id='promo_123',
            trial_period_days=7,
        )

    assert 'trial_period_days' not in captured.get('subscription_data', {})
    assert captured.get('discounts') == [{'promotion_code': 'promo_123'}]


def test_stripe_utils_keeps_trial_when_no_promo_present():
    """utils.stripe retains trial_period_days in subscription_data when promotion_code_id is None."""
    captured = {}

    def fake_create(**params):
        captured.update(params)
        return SimpleNamespace(url='https://checkout.stripe.com/pay/cs_test', id='cs_test')

    with (
        patch.object(stripe_utils.stripe.checkout.Session, 'create', side_effect=fake_create),
        patch.object(stripe_utils.stripe.Price, 'retrieve', return_value=SimpleNamespace(currency='usd')),
    ):
        stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited',
            idempotency_key='k_1',
            promotion_code_id=None,
            trial_period_days=7,
        )

    assert captured.get('subscription_data', {}).get('trial_period_days') == 7
    assert captured.get('allow_promotion_codes') is True
