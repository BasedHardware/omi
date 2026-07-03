"""The checkout/upgrade request models must reject an empty or oversized price_id.

CreateCheckoutRequest and UpgradeSubscriptionRequest took an unvalidated price_id: str, so an
empty value passed request validation and only failed later as an opaque Stripe error. Bounding
it (min_length=1, max_length=255) makes a bad price_id a clean 422 at the request boundary,
consistent with the other request models in the backend.

Test isolation: routers.payment imports cleanly, so the test imports the models normally and
exercises their pydantic validation directly (no Stripe, no monkeypatch).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from routers.payment import CreateCheckoutRequest, UpgradeSubscriptionRequest  # noqa: E402


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
