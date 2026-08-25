"""The checkout/upgrade paths must reject an empty, whitespace-only, oversized, non-purchasable, or
unknown price_id.

Two layers guard price_id:
  1. CreateCheckoutRequest / UpgradeSubscriptionRequest bound it (min_length=1, max_length=255), so
     an empty or oversized value is a clean 422 at the request boundary.
  2. Both payment endpoints call _validate_price_id(request.price_id) as their first step, before any
     Stripe call: it rejects a whitespace-only value and any id that is not currently purchasable
     (is_purchasable_price_id is False) with a 400, so a non-purchasable price_id never reaches Stripe.

_validate_price_id validates against is_purchasable_price_id (the active plan catalog only), NOT
get_plan_type_from_price_id. The difference matters: get_plan_type_from_price_id also accepts
LEGACY_PRICE_MAP prices, which exist for existing subscribers' renewals and webhook/subscription
reconciliation. Those legacy prices must not be selectable as new checkout/upgrade targets, so the
request boundary excludes them while reconciliation still resolves them.

Test isolation: routers.payment imports cleanly, so the test imports the models/handlers normally and
patches is_purchasable_price_id (no Stripe, no network).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import routers.payment as payment  # noqa: E402
import utils.subscription as subscription  # noqa: E402
from routers.payment import CreateCheckoutRequest, UpgradeSubscriptionRequest  # noqa: E402

# --- Layer 1: model bounds (422 at the request boundary) ---


def test_checkout_accepts_valid_price_id():
    assert CreateCheckoutRequest(price_id='price_123').price_id == 'price_123'


def test_upgrade_accepts_valid_price_id():
    assert UpgradeSubscriptionRequest(price_id='price_123').price_id == 'price_123'


@pytest.mark.parametrize('model', [CreateCheckoutRequest, UpgradeSubscriptionRequest])
def test_rejects_empty_price_id(model):
    with pytest.raises(ValidationError):
        model(price_id='')


@pytest.mark.parametrize('model', [CreateCheckoutRequest, UpgradeSubscriptionRequest])
def test_rejects_overlong_price_id(model):
    with pytest.raises(ValidationError):
        model(price_id='x' * 256)


# --- Layer 2: _validate_price_id boundary check (400 before any Stripe call) ---


def test_validate_price_id_accepts_purchasable_plan():
    with patch.object(payment, 'is_purchasable_price_id', return_value=True) as pp:
        payment._validate_price_id('price_configured')  # must not raise
    pp.assert_called_once_with('price_configured')


def test_validate_price_id_rejects_whitespace_only():
    # Whitespace passes the model's min_length=1 but is not a real id: 400 before the plan lookup.
    with patch.object(payment, 'is_purchasable_price_id') as pp:
        with pytest.raises(HTTPException) as ei:
            payment._validate_price_id('   ')
    assert ei.value.status_code == 400
    pp.assert_not_called()


def test_validate_price_id_rejects_non_purchasable():
    with patch.object(payment, 'is_purchasable_price_id', return_value=False):
        with pytest.raises(HTTPException) as ei:
            payment._validate_price_id('price_unknown')
    assert ei.value.status_code == 400


def test_checkout_endpoint_rejects_non_purchasable_price_id_before_stripe():
    # The handler validates first, so a non-purchasable id 400s before reaching Stripe or the DB.
    with patch.object(payment, 'is_purchasable_price_id', return_value=False):
        with pytest.raises(HTTPException) as ei:
            payment.create_checkout_session_endpoint(CreateCheckoutRequest(price_id='price_unknown'), uid='u1')
    assert ei.value.status_code == 400


def test_upgrade_endpoint_rejects_non_purchasable_price_id_before_stripe():
    with patch.object(payment, 'is_purchasable_price_id', return_value=False):
        with pytest.raises(HTTPException) as ei:
            payment.upgrade_subscription_endpoint(UpgradeSubscriptionRequest(price_id='price_unknown'), uid='u1')
    assert ei.value.status_code == 400


# --- Regression: a legacy price is rejected as a new checkout/upgrade target but still resolves for
#     reconciliation. is_purchasable_price_id (checkout boundary) excludes LEGACY_PRICE_MAP;
#     get_plan_type_from_price_id (reconciliation) still recognizes it. ---


def test_legacy_price_rejected_for_checkout_but_recognized_for_reconciliation():
    legacy_id = 'price_legacy_old'
    active_id = 'price_active_new'
    plan = 'unlimited'
    fake_definitions = [{'monthly_price_id': active_id, 'annual_price_id': '', 'plan_type': plan}]
    with patch.object(subscription, 'get_paid_plan_definitions', return_value=fake_definitions), patch.dict(
        subscription.LEGACY_PRICE_MAP, {legacy_id: plan}, clear=False
    ):
        # reconciliation / webhook path still resolves the legacy price to its plan
        assert subscription.get_plan_type_from_price_id(legacy_id) == plan
        # but the checkout/upgrade boundary rejects it because it is not currently purchasable
        assert subscription.is_purchasable_price_id(legacy_id) is False
        # the active catalog price is still purchasable
        assert subscription.is_purchasable_price_id(active_id) is True
