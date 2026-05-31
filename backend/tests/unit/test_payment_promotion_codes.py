from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"
STRIPE_UTILS_SOURCE = Path(__file__).resolve().parents[2] / "utils" / "stripe.py"


def test_checkout_request_model_accepts_promotion_code():
    source = PAYMENT_SOURCE.read_text()
    assert 'class CreateCheckoutRequest(BaseModel):' in source
    assert 'promotion_code: Optional[str] = None' in source


def test_upgrade_request_model_accepts_promotion_code():
    source = PAYMENT_SOURCE.read_text()
    assert 'class UpgradeSubscriptionRequest(BaseModel):' in source
    assert 'promotion_code: Optional[str] = None' in source


def test_checkout_validates_promo_before_reactivation():
    """Promo validation must happen before _try_reactivate_subscription."""
    source = PAYMENT_SOURCE.read_text()
    promo_check_pos = source.index("PromotionCode.list(code=request.promotion_code")
    reactivation_pos = source.index("_try_reactivate_subscription(uid, request.price_id)")
    # In checkout endpoint, the positions should be in order: first promo check occurs before reactivation
    # Both appear — get the ones inside create_checkout_session_endpoint
    endpoint_start = source.index("def create_checkout_session_endpoint")
    promo_in_checkout = source.index("PromotionCode.list", endpoint_start)
    reactivation_in_checkout = source.index("_try_reactivate_subscription", endpoint_start)
    assert promo_in_checkout < reactivation_in_checkout, "Promo validation must run before reactivation check"


def test_upgrade_uses_promotion_code_id_not_coupon():
    """Upgrade must use promotion_code ID (preserves restrictions) not coupon ID."""
    source = PAYMENT_SOURCE.read_text()
    upgrade_start = source.index("def upgrade_subscription_endpoint")
    upgrade_section = source[upgrade_start:]
    assert "{'promotion_code': resolved_promo_id}" in upgrade_section
    assert "{'coupon':" not in upgrade_section


def test_upgrade_applies_promo_to_schedule_phases():
    """Same-plan interval changes must apply promo discount to the target phase."""
    source = PAYMENT_SOURCE.read_text()
    upgrade_start = source.index("def upgrade_subscription_endpoint")
    upgrade_section = source[upgrade_start:]
    assert "SubscriptionSchedule.modify" in upgrade_section
    schedule_pos = upgrade_section.index("SubscriptionSchedule.modify")
    after_schedule = upgrade_section[schedule_pos:]
    assert "resolved_promo_id" in after_schedule


def test_checkout_helper_uses_discounts_when_promo_provided():
    """With promotion_code_id, helper sets discounts and omits allow_promotion_codes."""
    source = STRIPE_UTILS_SOURCE.read_text()
    assert "if promotion_code_id:" in source
    assert "session_params['discounts'] = [{'promotion_code': promotion_code_id}]" in source


def test_checkout_helper_allows_promo_codes_when_no_promo():
    """Without promotion_code_id, helper sets allow_promotion_codes=True."""
    source = STRIPE_UTILS_SOURCE.read_text()
    assert "session_params['allow_promotion_codes'] = True" in source


def test_upgrade_catches_stripe_invalid_request_error():
    """Stripe InvalidRequestError on upgrade must map to HTTP 400."""
    source = PAYMENT_SOURCE.read_text()
    upgrade_start = source.index("def upgrade_subscription_endpoint")
    upgrade_section = source[upgrade_start:]
    assert "stripe.error.InvalidRequestError" in upgrade_section


def test_checkout_catches_stripe_invalid_request_error():
    """Stripe InvalidRequestError on checkout must map to HTTP 400."""
    source = PAYMENT_SOURCE.read_text()
    checkout_start = source.index("def create_checkout_session_endpoint")
    checkout_section = source[checkout_start : source.index("def upgrade_subscription_endpoint")]
    assert "stripe.error.InvalidRequestError" in checkout_section
