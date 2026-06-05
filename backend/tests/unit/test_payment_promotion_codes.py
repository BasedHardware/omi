"""Tests for promotion code support in checkout and upgrade endpoints."""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"
STRIPE_UTILS_SOURCE = Path(__file__).resolve().parents[2] / "utils" / "stripe.py"

# ---------------------------------------------------------------------------
# Source-level structural tests (fast, no import needed)
# ---------------------------------------------------------------------------


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
    source = STRIPE_UTILS_SOURCE.read_text()
    assert "if promotion_code_id:" in source
    assert "session_params['discounts'] = [{'promotion_code': promotion_code_id}]" in source


def test_checkout_helper_allows_promo_codes_when_no_promo():
    source = STRIPE_UTILS_SOURCE.read_text()
    assert "session_params['allow_promotion_codes'] = True" in source


def test_upgrade_catches_stripe_invalid_request_error():
    source = PAYMENT_SOURCE.read_text()
    upgrade_start = source.index("def upgrade_subscription_endpoint")
    upgrade_section = source[upgrade_start:]
    assert "stripe.error.InvalidRequestError" in upgrade_section


def test_upgrade_releases_attached_schedule_before_change():
    """A subscription already attached to a schedule must be released before
    Subscription.modify() / SubscriptionSchedule.create(), otherwise Stripe
    rejects the change ("cannot migrate a subscription already attached to a
    schedule") and the user can never switch plans."""
    source = PAYMENT_SOURCE.read_text()
    assert "def _release_attached_schedules" in source
    upgrade_section = source[source.index("def upgrade_subscription_endpoint") :]
    assert "_release_attached_schedules(stripe_sub)" in upgrade_section
    release_pos = upgrade_section.index("_release_attached_schedules(stripe_sub)")
    assert release_pos < upgrade_section.index("stripe.Subscription.modify"), "release must precede modify"
    assert release_pos < upgrade_section.index("SubscriptionSchedule.create"), "release must precede schedule create"


def test_checkout_catches_stripe_invalid_request_error():
    source = PAYMENT_SOURCE.read_text()
    checkout_start = source.index("def create_checkout_session_endpoint")
    checkout_section = source[checkout_start : source.index("def upgrade_subscription_endpoint")]
    assert "stripe.error.InvalidRequestError" in checkout_section


# ---------------------------------------------------------------------------
# Behavioral tests (import and call endpoints via mocked dependencies)
# ---------------------------------------------------------------------------


def _setup_payment_module():
    """Import payment router with all heavy deps mocked."""
    # Mock heavy modules before importing
    for mod_name in [
        "database._client",
        "database.redis_db",
        "database.users",
        "database.conversations",
        "database.memories",
        "database.action_items",
        "database",
        "utils.fair_use",
        "utils.notifications",
        "utils.subscription",
        "utils.stripe",
        "utils.apps",
        "utils.other.endpoints",
        "utils.other",
        "utils.overage",
        "utils.executors",
        "utils.log_sanitizer",
        "models.users",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    # Provide required names in mocked modules
    db_mod = sys.modules["database"]
    db_mod.users = MagicMock()
    db_mod.conversations = MagicMock()
    db_mod.memories = MagicMock()
    db_mod.action_items = MagicMock()

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.set_credits_invalidation_signal = MagicMock()

    fair_use_mod = sys.modules["utils.fair_use"]
    fair_use_mod.clear_fair_use_on_upgrade = MagicMock()

    notif_mod = sys.modules["utils.notifications"]
    notif_mod.send_notification = MagicMock()
    notif_mod.send_subscription_paid_personalized_notification = MagicMock()

    sub_mod = sys.modules["utils.subscription"]
    sub_mod.can_user_make_payment = MagicMock(return_value=(True, None))
    sub_mod.get_basic_plan_limits = MagicMock()
    sub_mod.get_paid_plan_definitions = MagicMock()
    sub_mod.get_plan_type_from_price_id = MagicMock()
    sub_mod.get_plan_limits = MagicMock()
    sub_mod.is_paid_plan = MagicMock(return_value=True)
    sub_mod.filter_plans_for_user = MagicMock()
    sub_mod.should_show_new_plans = MagicMock()
    sub_mod.adapt_plans_for_legacy_client = MagicMock()
    sub_mod.clear_trial_paywall_cache = MagicMock()
    sub_mod.find_active_paid_subscription_for_user = MagicMock()

    stripe_utils_mod = sys.modules["utils.stripe"]
    stripe_utils_mod.base_url = "http://test/"
    stripe_utils_mod.create_subscription_checkout_session = MagicMock()
    stripe_utils_mod.create_connect_account = MagicMock()
    stripe_utils_mod.refresh_connect_account_link = MagicMock()
    stripe_utils_mod.is_onboarding_complete = MagicMock()

    apps_mod = sys.modules["utils.apps"]
    apps_mod.find_app_subscription = MagicMock()
    apps_mod.get_is_user_paid_app = MagicMock()
    apps_mod.paid_app = MagicMock()
    apps_mod.set_user_app_sub_customer_id = MagicMock()

    endpoints_mod = sys.modules["utils.other.endpoints"]
    endpoints_mod.get_current_user_uid = lambda: "test-uid"
    endpoints_mod.get_current_user_uid_no_byok_validation = lambda: "test-uid"

    overage_mod = sys.modules["utils.overage"]
    overage_mod.OVERAGE_EXPLAINER_TITLE = ""
    overage_mod.PROVIDER_REFERENCE_RATES = {}
    overage_mod.build_explainer_text = MagicMock()
    overage_mod.get_user_overage = MagicMock()
    overage_mod.is_overage_plan = MagicMock()

    exec_mod = sys.modules["utils.executors"]
    exec_mod.db_executor = MagicMock()
    exec_mod.stripe_executor = MagicMock()
    exec_mod.run_blocking = MagicMock()

    sanitizer_mod = sys.modules["utils.log_sanitizer"]
    sanitizer_mod.sanitize = lambda x: x

    models_mod = sys.modules["models.users"]
    models_mod.PlanType = MagicMock()
    models_mod.Subscription = MagicMock()
    models_mod.SubscriptionStatus = MagicMock()
    models_mod.PlanLimits = MagicMock()

    users_db_mod = sys.modules["database.users"]
    users_db_mod.get_stripe_connect_account_id = MagicMock()
    users_db_mod.set_stripe_connect_account_id = MagicMock()
    users_db_mod.set_paypal_payment_details = MagicMock()
    users_db_mod.get_default_payment_method = MagicMock()
    users_db_mod.set_default_payment_method = MagicMock()
    users_db_mod.get_paypal_payment_details = MagicMock()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Force re-import of payment router
    if "routers.payment" in sys.modules:
        del sys.modules["routers.payment"]

    from routers import payment as payment_router

    app = FastAPI()
    app.include_router(payment_router.router)
    app.dependency_overrides[payment_router.auth.get_current_user_uid] = lambda: "test-uid"
    app.dependency_overrides[payment_router.auth.get_current_user_uid_no_byok_validation] = lambda: "test-uid"

    return TestClient(app), payment_router


# --- Checkout endpoint tests ---


def test_checkout_invalid_promo_returns_400():
    """Invalid promo code returns 400 and does not create a session."""
    client, router = _setup_payment_module()

    with patch.object(router.stripe, "PromotionCode") as mock_promo:
        mock_promo.list.return_value = MagicMock(data=[])
        response = client.post("/v1/payments/checkout-session", json={"price_id": "price_123", "promotion_code": "BAD"})

    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]
    router.stripe_utils.create_subscription_checkout_session.assert_not_called()


def test_checkout_valid_promo_passes_id_to_session():
    """Valid promo code resolves ID and passes it to create_subscription_checkout_session."""
    client, router = _setup_payment_module()

    mock_promo_obj = MagicMock()
    mock_promo_obj.id = "promo_abc123"
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_session.id = "cs_test_123"

    with patch.object(router.stripe, "PromotionCode") as mock_promo:
        mock_promo.list.return_value = MagicMock(data=[mock_promo_obj])
        router.stripe_utils.create_subscription_checkout_session.return_value = mock_session
        router.subscription_utils.can_user_make_payment.return_value = (True, None)
        router.users_db.get_stripe_customer_id.return_value = None

        with patch.object(router, "_try_reactivate_subscription", return_value=None):
            response = client.post(
                "/v1/payments/checkout-session", json={"price_id": "price_123", "promotion_code": "WELCOME50"}
            )

    assert response.status_code == 200
    call_kwargs = router.stripe_utils.create_subscription_checkout_session.call_args
    assert call_kwargs[1].get("promotion_code_id") == "promo_abc123" or (
        len(call_kwargs[0]) > 4 and call_kwargs[0][4] == "promo_abc123"
    )


def test_checkout_no_promo_omits_promo_id():
    """No promo code passes None as promotion_code_id."""
    client, router = _setup_payment_module()

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_session.id = "cs_test_456"
    router.stripe_utils.create_subscription_checkout_session.return_value = mock_session
    router.subscription_utils.can_user_make_payment.return_value = (True, None)
    router.users_db.get_stripe_customer_id.return_value = None

    with patch.object(router, "_try_reactivate_subscription", return_value=None):
        response = client.post("/v1/payments/checkout-session", json={"price_id": "price_123"})

    assert response.status_code == 200
    call_kwargs = router.stripe_utils.create_subscription_checkout_session.call_args
    assert call_kwargs[1].get("promotion_code_id") is None


# --- _release_attached_schedules helper ---


def test_release_attached_schedules_releases_only_matching_active():
    """Releases active/not_started schedules attached to THIS subscription;
    skips completed schedules and schedules for other subscriptions."""
    client, router = _setup_payment_module()

    sched_match = MagicMock(id="ss_active", status="active", subscription="sub_1")
    sched_not_started = MagicMock(id="ss_pending", status="not_started", subscription="sub_1")
    sched_other_sub = MagicMock(id="ss_other", status="active", subscription="sub_OTHER")
    sched_completed = MagicMock(id="ss_done", status="completed", subscription="sub_1")

    with patch.object(router.stripe, "SubscriptionSchedule") as mock_ss:
        mock_ss.list.return_value = MagicMock(data=[sched_match, sched_not_started, sched_other_sub, sched_completed])
        router._release_attached_schedules({"id": "sub_1", "customer": "cus_1"})

    mock_ss.list.assert_called_once_with(customer="cus_1", limit=10)
    released = {c.args[0] for c in mock_ss.release.call_args_list}
    assert released == {"ss_active", "ss_pending"}


def test_release_attached_schedules_noop_without_customer():
    """No customer/sub id -> no Stripe calls (defensive)."""
    client, router = _setup_payment_module()
    with patch.object(router.stripe, "SubscriptionSchedule") as mock_ss:
        router._release_attached_schedules({"id": "sub_1"})  # missing customer
        router._release_attached_schedules({"customer": "cus_1"})  # missing id
    mock_ss.list.assert_not_called()


def test_release_attached_schedules_swallows_list_errors():
    """A Stripe failure while listing schedules must not break the upgrade."""
    client, router = _setup_payment_module()
    with patch.object(router.stripe, "SubscriptionSchedule") as mock_ss:
        mock_ss.list.side_effect = Exception("stripe down")
        # Should not raise
        router._release_attached_schedules({"id": "sub_1", "customer": "cus_1"})
    mock_ss.release.assert_not_called()
