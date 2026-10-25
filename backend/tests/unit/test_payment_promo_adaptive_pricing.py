"""Promotion-code checkouts pin presentment currency (issue #23299).

Stripe evaluates a promotion code's ``minimum_amount`` restriction against the
checkout session's presentment currency. With Adaptive Pricing enabled, the
converted total for a foreign-currency customer (e.g. EUR 249 for the $269
Unlimited yearly price) falls below the USD-authored minimum and a valid
activation code is rejected with "order total is below the minimum amount".

Sessions created with a resolved promotion code must disable Adaptive Pricing
so the minimum is evaluated against the price's native USD amount. Sessions
without a promotion code keep Stripe's Adaptive Pricing default.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("BASE_API_URL", "http://localhost:8080")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import utils.stripe as stripe_utils  # noqa: E402

STRIPE_UTILS_SOURCE = Path(__file__).resolve().parents[2] / "utils" / "stripe.py"


def _captured_session_params(promotion_code_id):
    captured = {}

    def fake_session_create(**params):
        captured.update(params)
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with patch('utils.stripe.stripe.checkout.Session.create', side_effect=fake_session_create):
        stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited_yearly',
            idempotency_key='idem_1',
            promotion_code_id=promotion_code_id,
        )
    return captured


def test_promo_checkout_disables_adaptive_pricing():
    """A promo-code session pins presentment to the price's USD currency."""
    params = _captured_session_params(promotion_code_id='promo_123')

    assert params['discounts'] == [{'promotion_code': 'promo_123'}]
    assert params['adaptive_pricing'] == {'enabled': False}


def test_promo_free_checkout_keeps_adaptive_pricing_default():
    """Without a promo code the session must not set adaptive_pricing, so
    Stripe's default (Adaptive Pricing where enabled) still applies."""
    params = _captured_session_params(promotion_code_id=None)

    assert params['allow_promotion_codes'] is True
    assert 'adaptive_pricing' not in params
    assert 'discounts' not in params


def test_adaptive_pricing_pin_is_scoped_to_promo_sessions():
    """Static contract: the pin lives inside the promotion_code_id branch, so a
    refactor can never silently widen it to promo-free checkouts."""
    source = STRIPE_UTILS_SOURCE.read_text(encoding="utf-8")

    branch_start = source.index("if promotion_code_id:")
    branch_end = source.index("session_params['allow_promotion_codes'] = True", branch_start)
    promo_branch = source[branch_start:branch_end]

    assert "session_params['adaptive_pricing'] = {'enabled': False}" in promo_branch
