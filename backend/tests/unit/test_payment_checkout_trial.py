"""The checkout trial is only for a first-time subscriber.

`trial_days` on `POST /v1/payments/checkout-session` becomes Stripe's `subscription_data.trial_period_days`
for a reader with no Stripe customer yet. A reader who already has one (a former subscriber back on the
free plan) must be refused with 400 `trial_unavailable`: the client promised a $0 trial, and silently
charging at once would break that promise. `/v1/users/me/subscription` reports the same rule as
`trial_eligible`, so clients never show the trial copy to a reader who cannot get it.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import routers.payment as payment  # noqa: E402
from routers.payment import CreateCheckoutRequest  # noqa: E402


def test_trial_days_is_bounded():
    assert CreateCheckoutRequest(price_id='price_1').trial_days is None
    assert CreateCheckoutRequest(price_id='price_1', trial_days=7).trial_days == 7
    with pytest.raises(Exception):
        CreateCheckoutRequest(price_id='price_1', trial_days=0)
    with pytest.raises(Exception):
        CreateCheckoutRequest(price_id='price_1', trial_days=31)


def _checkout(trial_days, existing_customer_id):
    captured = {}

    def create_session(
        uid, price_id, idempotency_key, customer_id=None, promotion_code_id=None, trial_period_days=None
    ):
        captured['trial_period_days'] = trial_period_days
        captured['customer_id'] = customer_id
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with (
        patch.object(payment, 'is_purchasable_price_id', return_value=True),
        patch.object(payment.subscription_utils, 'can_user_make_payment', return_value=(True, '')),
        # Trial semantics are orthogonal to the new-buyer single-plan rule, and
        # `price_1` is not a resolvable plan price.
        patch.object(payment.subscription_utils, 'new_buyer_single_plan_violation', return_value=None),
        patch.object(payment, '_try_reactivate_subscription', return_value=None),
        patch.object(payment.users_db, 'get_stripe_customer_id', return_value=existing_customer_id),
        patch.object(payment.stripe_utils, 'create_subscription_checkout_session', side_effect=create_session),
    ):
        result = payment.create_checkout_session_endpoint(
            CreateCheckoutRequest(price_id='price_1', trial_days=trial_days), uid='uid_1'
        )
    return result, captured


def test_first_time_subscriber_gets_the_trial():
    result, captured = _checkout(trial_days=7, existing_customer_id=None)
    assert result['session_id'] == 'cs_test'
    assert captured['trial_period_days'] == 7


def test_first_time_buyer_omi_pro_trial_through_the_single_plan_guard(monkeypatch):
    """The 7-day trial on a configured Omi Pro monthly price must pass the real
    new-buyer single-plan guard (not a stub) and still reach Stripe with the
    trial period — the guard exempts exactly this price for a web new buyer."""
    pro_monthly = 'price_unlimited_v2_monthly_configured'
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', pro_monthly)
    monkeypatch.delenv('NEW_BUYER_SINGLE_PLAN_ENABLED', raising=False)
    captured = {}

    def create_session(
        uid, price_id, idempotency_key, customer_id=None, promotion_code_id=None, trial_period_days=None
    ):
        captured['trial_period_days'] = trial_period_days
        captured['customer_id'] = customer_id
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with (
        patch.object(payment, 'is_purchasable_price_id', return_value=True),
        patch.object(payment.subscription_utils, 'can_user_make_payment', return_value=(True, '')),
        # The guard itself runs for real; only its Firestore read is isolated.
        patch.object(payment.subscription_utils.users_db, 'get_user_valid_subscription', return_value=None),
        patch.object(payment, '_try_reactivate_subscription', return_value=None),
        patch.object(payment.users_db, 'get_stripe_customer_id', return_value=None),
        patch.object(payment.stripe_utils, 'create_subscription_checkout_session', side_effect=create_session),
    ):
        result = payment.create_checkout_session_endpoint(
            CreateCheckoutRequest(price_id=pro_monthly, trial_days=7), uid='uid_1', x_app_platform='web'
        )
    assert result['session_id'] == 'cs_test'
    assert captured['trial_period_days'] == 7


def test_former_subscriber_is_refused_a_trial_instead_of_being_charged():
    with pytest.raises(HTTPException) as excinfo:
        _checkout(trial_days=7, existing_customer_id='cus_existing')
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == 'trial_unavailable'


def test_no_trial_requested_keeps_the_old_checkout():
    result, captured = _checkout(trial_days=None, existing_customer_id='cus_existing')
    assert result['session_id'] == 'cs_test'
    assert captured['trial_period_days'] is None
    assert captured['customer_id'] == 'cus_existing'
