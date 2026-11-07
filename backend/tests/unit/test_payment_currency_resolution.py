import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from models.users import PlanType, SubscriptionStatus
from tests.unit.test_payment_promotion_codes import _setup_payment_module
from utils.billing_currency import BillingCurrencyUnavailable


@pytest.fixture
def payment_router():
    router = _setup_payment_module(include_client=False)
    router.get_plan_limits.return_value = {}
    return router


def test_upgrade_resolves_currency_matched_price_when_base_usd_requested(payment_router):
    """When a user with an active JPY subscription requests an upgrade using a base
    USD price ID (common on mobile clients that query base definitions), the endpoint
    must resolve the matching currency-specific price via price_for_currency rather than
    crashing with a 409 BillingCurrencyUnavailable / Stripe currency mismatch."""
    router = payment_router
    uid = "test_user_jpy"

    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_jpy_123",
        plan="plus",
        status="active",
        model_dump=lambda: {"stripe_subscription_id": "sub_jpy_123", "plan": "plus", "status": "active"},
    )

    now_ts = int(time.time())
    stripe_sub_dict = {
        "id": "sub_jpy_123",
        "customer": "cus_jpy_123",
        "status": "active",
        "currency": "jpy",
        "current_period_start": now_ts - 86400,
        "current_period_end": now_ts + 20 * 86400,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_jpy_item",
                    "price": {"id": "price_plus_jpy", "currency": "jpy", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    mock_usd_price = MagicMock()
    mock_usd_price.id = "price_unlimited_usd"
    mock_usd_price.currency = "usd"
    mock_usd_price.recurring.interval = "month"

    mock_jpy_resolved_price = MagicMock()
    mock_jpy_resolved_price.id = "price_unlimited_jpy"
    mock_jpy_resolved_price.currency = "jpy"
    mock_jpy_resolved_price.recurring.interval = "month"

    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "items": {
            "data": [
                {
                    "id": "si_jpy_item",
                    "price": {"id": "price_unlimited_jpy", "currency": "jpy", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", side_effect=lambda p: PlanType.plus if "plus" in p else PlanType.unlimited_v2), \
         patch.object(router.stripe.Price, "retrieve", side_effect=lambda p: mock_usd_price if p == "price_unlimited_usd" else mock_jpy_resolved_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.Subscription, "modify", return_value=mock_updated_sub) as mock_sub_modify, \
         patch.object(router.stripe, "SubscriptionSchedule"), \
         patch.object(router, "price_for_currency", return_value=mock_jpy_resolved_price) as mock_pfc, \
         patch.object(router.users_db, "update_user_subscription"):

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_usd")
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        assert response["status"] == "success"
        # Verify price_for_currency was called to map USD -> JPY
        mock_pfc.assert_called()
        # Verify Subscription.modify was called with the JPY price, not the USD price
        call_kwargs = mock_sub_modify.call_args[1]
        assert call_kwargs["items"] == [{"id": "si_jpy_item", "price": "price_unlimited_jpy"}]


def test_upgrade_rejects_cleanly_when_currency_cannot_be_resolved(payment_router):
    """When target price currency does not match subscription currency and no
    currency price exists, upgrade should raise HTTP 409 BillingCurrencyUnavailable."""
    router = payment_router
    uid = "test_user_gbp"

    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_gbp_123",
        plan="plus",
        status="active",
        model_dump=lambda: {"stripe_subscription_id": "sub_gbp_123", "plan": "plus", "status": "active"},
    )

    now_ts = int(time.time())
    stripe_sub_dict = {
        "id": "sub_gbp_123",
        "customer": "cus_gbp_123",
        "status": "active",
        "currency": "gbp",
        "current_period_start": now_ts - 86400,
        "current_period_end": now_ts + 20 * 86400,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_gbp_item",
                    "price": {"id": "price_plus_gbp", "currency": "gbp", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    mock_usd_price = MagicMock()
    mock_usd_price.id = "price_unlimited_usd"
    mock_usd_price.currency = "usd"
    mock_usd_price.recurring.interval = "month"

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", side_effect=lambda p: PlanType.plus if "plus" in p else PlanType.unlimited_v2), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_usd_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router, "price_for_currency", side_effect=BillingCurrencyUnavailable("Not available in gbp")):

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_usd")
        with pytest.raises(HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(request, uid=uid)

        assert exc_info.value.status_code == 409
        assert "Not available in gbp" in exc_info.value.detail


def test_upgrade_handles_unexpected_error_during_currency_resolution(payment_router):
    """When an unexpected exception (e.g. transient failure) occurs during price_for_currency,
    it must be logged and mapped to the generic BillingCurrencyUnavailable 409."""
    router = payment_router
    uid = "test_user_err"

    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_err_123",
        plan="plus",
        status="active",
        model_dump=lambda: {"stripe_subscription_id": "sub_err_123", "plan": "plus", "status": "active"},
    )

    now_ts = int(time.time())
    stripe_sub_dict = {
        "id": "sub_err_123",
        "customer": "cus_err_123",
        "status": "active",
        "currency": "eur",
        "current_period_start": now_ts - 86400,
        "current_period_end": now_ts + 20 * 86400,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_err_item",
                    "price": {"id": "price_plus_eur", "currency": "eur", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    mock_usd_price = MagicMock()
    mock_usd_price.id = "price_unlimited_usd"
    mock_usd_price.currency = "usd"
    mock_usd_price.recurring.interval = "month"

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", side_effect=lambda p: PlanType.plus if "plus" in p else PlanType.unlimited_v2), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_usd_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router, "price_for_currency", side_effect=RuntimeError("Transient network failure")), \
         patch.object(router.logger, "warning") as mock_log_warn:

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_usd")
        with pytest.raises(HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(request, uid=uid)

        assert exc_info.value.status_code == 409
        assert "Please reopen Plans & Billing to select a price in your billing currency" in exc_info.value.detail
        mock_log_warn.assert_called()
        assert "RuntimeError" in mock_log_warn.call_args[0][0]


def test_upgrade_reverifies_currency_binding_for_resolved_price(payment_router):
    """When the resolved price carries a currency_binding, it must flow through
    the verification block (lines 901-919) and successfully complete the upgrade."""
    router = payment_router
    uid = "test_user_binding_jpy"

    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_jpy_456",
        plan="plus",
        status="active",
        model_dump=lambda: {"stripe_subscription_id": "sub_jpy_456", "plan": "plus", "status": "active"},
    )

    now_ts = int(time.time())
    stripe_sub_dict = {
        "id": "sub_jpy_456",
        "customer": "cus_jpy_456",
        "status": "active",
        "currency": "jpy",
        "current_period_start": now_ts - 86400,
        "current_period_end": now_ts + 20 * 86400,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_jpy_item_456",
                    "price": {"id": "price_plus_jpy", "currency": "jpy", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    mock_usd_price = MagicMock()
    mock_usd_price.id = "price_unlimited_usd"
    mock_usd_price.currency = "usd"
    mock_usd_price.recurring.interval = "month"

    mock_jpy_resolved_price = MagicMock()
    mock_jpy_resolved_price.id = "price_unlimited_jpy"
    mock_jpy_resolved_price.currency = "jpy"
    mock_jpy_resolved_price.recurring.interval = "month"

    mock_plan_def = {
        "plan_type": PlanType.unlimited_v2,
        "monthly_price_id": "price_unlimited_usd",
        "annual_price_id": "price_unlimited_annual_usd",
    }

    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "items": {
            "data": [
                {
                    "id": "si_jpy_item_456",
                    "price": {"id": "price_unlimited_jpy", "currency": "jpy", "recurring": {"interval": "month"}},
                }
            ]
        },
    }

    def mock_retrieve_price(pid):
        if pid == "price_unlimited_usd":
            return mock_usd_price
        return mock_jpy_resolved_price

    def mock_pfc(price, curr):
        if price.id == "price_unlimited_usd" and curr == "jpy":
            return mock_jpy_resolved_price
        return price

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", side_effect=lambda p: PlanType.plus if "plus" in p else PlanType.unlimited_v2), \
         patch.object(router.stripe.Price, "retrieve", side_effect=mock_retrieve_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.Subscription, "modify", return_value=mock_updated_sub) as mock_sub_modify, \
         patch.object(router.stripe, "SubscriptionSchedule"), \
         patch.object(router, "management_binding", return_value=(PlanType.unlimited_v2, "month", "jpy")), \
         patch.object(router, "get_paid_plan_definitions", return_value=[mock_plan_def]), \
         patch.object(router, "price_for_currency", side_effect=mock_pfc), \
         patch.object(router.users_db, "update_user_subscription"):

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_usd")
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        assert response["status"] == "success"
        call_kwargs = mock_sub_modify.call_args[1]
        assert call_kwargs["items"] == [{"id": "si_jpy_item_456", "price": "price_unlimited_jpy"}]
