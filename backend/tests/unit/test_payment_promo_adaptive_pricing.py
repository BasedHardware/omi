"""Every subscription checkout charges in the price's own currency.

Stripe Adaptive Pricing is on at the account level. Left on for a session, it
converts the USD price into the buyer's local currency, so a buyer who saw a
USD price card in the app was charged a different, converted amount. Google
Play rejected Android release 1504 for that mismatch between the displayed and
charged price.

It also broke promotion codes (issue #23299): Stripe evaluates a code's
``minimum_amount`` against the presentment currency, and the converted total
(e.g. EUR 249 for the $269 Unlimited yearly price) fell below the USD-authored
minimum.

So every session, with or without a promotion code, disables Adaptive Pricing.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("BASE_API_URL", "http://localhost:8080")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import utils.stripe as stripe_utils  # noqa: E402

STRIPE_UTILS_SOURCE = Path(__file__).resolve().parents[2] / "utils" / "stripe.py"


def _captured_session_params(promotion_code_id, trial_period_days=None, customer_id=None):
    captured = {}

    def fake_session_create(**params):
        captured.update(params)
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_test', id='cs_test')

    with patch('utils.stripe.stripe.checkout.Session.create', side_effect=fake_session_create):
        stripe_utils.create_subscription_checkout_session(
            uid='uid_1',
            price_id='price_unlimited_yearly',
            idempotency_key='idem_1',
            customer_id=customer_id,
            promotion_code_id=promotion_code_id,
            trial_period_days=trial_period_days,
        )
    return captured


def test_promo_checkout_disables_adaptive_pricing():
    """A promo-code session pins presentment to the price's USD currency."""
    params = _captured_session_params(promotion_code_id='promo_123')

    assert params['discounts'] == [{'promotion_code': 'promo_123'}]
    assert params['adaptive_pricing'] == {'enabled': False}


@pytest.mark.parametrize(
    'trial_period_days, customer_id',
    [(None, None), (7, None), (None, 'cus_existing')],
    ids=['plain', 'trial', 'returning-customer'],
)
def test_promo_free_checkout_disables_adaptive_pricing(trial_period_days, customer_id):
    """A session without a promo code charges the displayed price's currency too."""
    params = _captured_session_params(
        promotion_code_id=None, trial_period_days=trial_period_days, customer_id=customer_id
    )

    assert params['allow_promotion_codes'] is True
    assert 'discounts' not in params
    assert params['adaptive_pricing'] == {'enabled': False}


def test_adaptive_pricing_pin_is_unconditional():
    """Static contract: the pin is in the base session params, not inside a branch,
    so a refactor cannot scope it back to promo sessions."""
    source = STRIPE_UTILS_SOURCE.read_text(encoding="utf-8")

    base_start = source.index("session_params: Dict[str, Any] = {")
    base_end = source.index("if trial_period_days:", base_start)

    assert "'adaptive_pricing': {'enabled': False}" in source[base_start:base_end]
