"""Regression tests for issue #23301: declined proration on a plan change.

When an active paid subscriber changes plans via POST /v1/payments/upgrade-subscription:
1. stripe.Subscription.modify must be called with payment_behavior='error_if_incomplete'
   alongside proration_behavior='always_invoice' so Stripe rolls back the price change
   instead of moving the subscription item to the new price and transitioning the
   subscription to past_due when the proration invoice charge is declined.
2. A stripe.error.CardError from stripe.Subscription.modify must return HTTP 402 with a
   user-safe message and leave the stored paid subscription untouched.
3. If stripe.Subscription.modify returns a non-active/trialing snapshot (e.g. past_due or
   incomplete) or an unsettled pending_update, upgrade_subscription_endpoint must reject
   with HTTP 402 before _build_subscription_from_stripe_object projects the non-active
   status to PlanType.basic (Free) and overwrites the user's paid subscription.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"
_MISSING = object()


@pytest.fixture(autouse=True)
def restore_module_stubs():
    modules = dict(sys.modules)
    routers_module = modules.get("routers")
    router_payment = getattr(routers_module, "payment", _MISSING) if routers_module else _MISSING
    yield
    for module_name in tuple(sys.modules):
        if module_name not in modules:
            del sys.modules[module_name]
    sys.modules.update(modules)
    if routers_module:
        if router_payment is _MISSING:
            routers_module.__dict__.pop("payment", None)
        else:
            routers_module.payment = router_payment


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_payment_router() -> Any:
    """Import routers.payment with external IO modules mocked while keeping real models.users."""
    from contextlib import contextmanager
    from models.users import PlanLimits, PlanType, Subscription, SubscriptionStatus

    for mod_name in [
        "database._client",
        "database.fsr_read_cache",
        "database.redis_db",
        "database.locked_content",
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
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    @contextmanager
    def _noop_fresh_reads():
        yield

    fsr_mod = sys.modules["database.fsr_read_cache"]
    fsr_mod.fresh_reader = lambda fn: fn
    fsr_mod.fresh_reads = _noop_fresh_reads

    db_mod = sys.modules["database"]
    db_mod.__path__ = [str(PAYMENT_SOURCE.parents[1] / "database")]
    db_mod.users = MagicMock()
    db_mod.conversations = MagicMock()
    db_mod.memories = MagicMock()
    db_mod.action_items = MagicMock()

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.set_credits_invalidation_signal = MagicMock()

    locked_content_mod = sys.modules["database.locked_content"]
    locked_content_mod.has_recoverable_locked_content = MagicMock(return_value=False)

    fair_use_mod = sys.modules["utils.fair_use"]
    fair_use_mod.clear_fair_use_on_upgrade = MagicMock()

    notif_mod = sys.modules["utils.notifications"]
    notif_mod.send_notification = MagicMock()
    notif_mod.send_subscription_paid_personalized_notification = MagicMock()

    sub_mod = sys.modules["utils.subscription"]
    sub_mod.can_user_make_payment = MagicMock(return_value=(True, None))
    sub_mod.get_basic_plan_limits = MagicMock(return_value=PlanLimits())
    sub_mod.get_paid_plan_definitions = MagicMock()
    sub_mod.get_plan_type_from_price_id = MagicMock(
        side_effect=lambda pid: PlanType.plus if pid == "price_plus" else PlanType.unlimited
    )
    sub_mod.is_purchasable_price_id = MagicMock(return_value=True)
    sub_mod.get_plan_limits = MagicMock(return_value=PlanLimits(transcription_seconds=36000))
    sub_mod.is_paid_plan = MagicMock(side_effect=lambda plan: plan != PlanType.basic)
    sub_mod.filter_plans_for_user = MagicMock()
    sub_mod.should_show_new_plans = MagicMock()
    sub_mod.adapt_plans_for_legacy_client = MagicMock()
    sub_mod.clear_trial_paywall_cache = MagicMock()
    sub_mod.find_active_paid_subscription_for_user = MagicMock()
    sub_mod.price_ids_match_plan_and_interval = MagicMock(return_value=False)
    sub_mod.desktop_to_consumer_plan_change_error = MagicMock(return_value=None)

    fallback_mod = types.ModuleType("utils.observability.fallback")
    fallback_mod.record_fallback = MagicMock()
    sys.modules["utils.observability.fallback"] = fallback_mod

    billing_ledger_mod = types.ModuleType("utils.observability.billing_ledger")
    billing_ledger_mod.record_outcome = MagicMock()
    sys.modules["utils.observability.billing_ledger"] = billing_ledger_mod

    subscription_events_mod = types.ModuleType("utils.observability.subscription_events")
    subscription_events_mod.record_subscription_event = MagicMock()
    sys.modules["utils.observability.subscription_events"] = subscription_events_mod

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

    users_db_mod = sys.modules["database.users"]
    users_db_mod.get_stripe_connect_account_id = MagicMock()
    users_db_mod.get_user_profile = MagicMock(return_value={})
    users_db_mod.set_stripe_connect_account_id = MagicMock()
    users_db_mod.set_paypal_payment_details = MagicMock()
    users_db_mod.get_default_payment_method = MagicMock()
    users_db_mod.set_default_payment_method = MagicMock()
    users_db_mod.get_paypal_payment_details = MagicMock()

    if "routers.payment" in sys.modules:
        del sys.modules["routers.payment"]
    routers_module = sys.modules.get("routers")
    if routers_module:
        routers_module.__dict__.pop("payment", None)

    from routers import payment as payment_router

    payment_router.PlanType = PlanType
    payment_router.Subscription = Subscription
    payment_router.SubscriptionStatus = SubscriptionStatus
    return payment_router


def test_upgrade_sets_error_if_incomplete_payment_behavior_in_source():
    source = _read_source(PAYMENT_SOURCE)
    upgrade_start = source.index("def upgrade_subscription_endpoint")
    cancel_start = source.index("class CancelSubscriptionRequest", upgrade_start)
    upgrade_section = source[upgrade_start:cancel_start]

    assert "'proration_behavior': 'always_invoice'" in upgrade_section
    assert "'payment_behavior': 'error_if_incomplete'" in upgrade_section
    assert "except stripe.error.CardError as e:" in upgrade_section
    card_pos = upgrade_section.index("except stripe.error.CardError as e:")
    generic_pos = upgrade_section.index("except Exception as e:")
    assert card_pos < generic_pos


def test_cross_plan_upgrade_passes_error_if_incomplete_to_stripe_modify():
    router = _load_payment_router()
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "id": "sub_active_plus",
        "customer": "cus_123",
        "status": "active",
        "cancel_at_period_end": False,
        "current_period_start": 1_700_000_000,
        "current_period_end": 1_702_592_000,
        "items": {"data": [{"id": "si_plus", "price": {"id": "price_plus"}}]},
    }
    retrieved_sub = MagicMock()
    retrieved_sub.to_dict.return_value = stripe_sub_dict

    updated_sub = MagicMock()
    updated_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "items": {"data": [{"id": "si_plus", "price": {"id": "price_unlimited"}}]},
    }

    with (
        patch.object(router.stripe.Subscription, "retrieve", return_value=retrieved_sub),
        patch.object(router.stripe.Subscription, "modify", return_value=updated_sub) as mock_modify,
        patch.object(
            router.stripe.Price,
            "retrieve",
            return_value=SimpleNamespace(recurring=SimpleNamespace(interval="month")),
        ),
        patch.object(router, "_release_attached_schedules"),
        patch.object(router, "funded_processing_enabled", return_value=False),
    ):
        result = router.upgrade_subscription_endpoint(
            router.UpgradeSubscriptionRequest(price_id="price_unlimited"), uid="u1"
        )

    assert result["status"] == "success"
    mock_modify.assert_called_once_with(
        "sub_active_plus",
        items=[{"id": "si_plus", "price": "price_unlimited"}],
        proration_behavior="always_invoice",
        payment_behavior="error_if_incomplete",
        metadata={"uid": "u1", "sub_type": "unlimited"},
    )
    router.users_db.update_user_subscription.assert_called_once()
    written_sub = router.users_db.update_user_subscription.call_args.args[1]
    assert written_sub["plan"] == router.PlanType.unlimited


def test_declined_proration_card_error_returns_402_and_preserves_paid_plan():
    router = _load_payment_router()
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "id": "sub_active_plus",
        "customer": "cus_123",
        "status": "active",
        "cancel_at_period_end": False,
        "current_period_start": 1_700_000_000,
        "current_period_end": 1_702_592_000,
        "items": {"data": [{"id": "si_plus", "price": {"id": "price_plus"}}]},
    }
    retrieved_sub = MagicMock()
    retrieved_sub.to_dict.return_value = stripe_sub_dict

    card_error = router.stripe.error.CardError(
        message="Your card has insufficient funds.",
        param=None,
        code="card_declined",
        json_body={"error": {"message": "Your card has insufficient funds."}},
    )

    with (
        patch.object(router.stripe.Subscription, "retrieve", return_value=retrieved_sub),
        patch.object(router.stripe.Subscription, "modify", side_effect=card_error),
        patch.object(
            router.stripe.Price,
            "retrieve",
            return_value=SimpleNamespace(recurring=SimpleNamespace(interval="month")),
        ),
        patch.object(router, "_release_attached_schedules"),
    ):
        with pytest.raises(router.HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(
                router.UpgradeSubscriptionRequest(price_id="price_unlimited"), uid="u1"
            )

    assert exc_info.value.status_code == 402
    assert "insufficient funds" in exc_info.value.detail
    router.users_db.update_user_subscription.assert_not_called()
    router.set_credits_invalidation_signal.assert_not_called()
    router.clear_fair_use_on_upgrade.assert_not_called()


def test_declined_proration_past_due_snapshot_returns_402_and_never_projects_basic():
    """If Stripe ever returns a past_due or pending_update subscription from modify,
    the endpoint must reject with 402 rather than projecting past_due -> Basic (Free)
    and overwriting the subscriber's paid plan in Firestore."""
    router = _load_payment_router()
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "id": "sub_active_plus",
        "customer": "cus_123",
        "status": "active",
        "cancel_at_period_end": False,
        "current_period_start": 1_700_000_000,
        "current_period_end": 1_702_592_000,
        "items": {"data": [{"id": "si_plus", "price": {"id": "price_plus"}}]},
    }
    retrieved_sub = MagicMock()
    retrieved_sub.to_dict.return_value = stripe_sub_dict

    past_due_sub = MagicMock()
    past_due_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "status": "past_due",
        "items": {"data": [{"id": "si_plus", "price": {"id": "price_unlimited"}}]},
    }

    with (
        patch.object(router.stripe.Subscription, "retrieve", return_value=retrieved_sub),
        patch.object(router.stripe.Subscription, "modify", return_value=past_due_sub),
        patch.object(
            router.stripe.Price,
            "retrieve",
            return_value=SimpleNamespace(recurring=SimpleNamespace(interval="month")),
        ),
        patch.object(router, "_release_attached_schedules"),
    ):
        with pytest.raises(router.HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(
                router.UpgradeSubscriptionRequest(price_id="price_unlimited"), uid="u1"
            )

    assert exc_info.value.status_code == 402
    assert "current subscription remains active" in exc_info.value.detail
    router.users_db.update_user_subscription.assert_not_called()
    router.set_credits_invalidation_signal.assert_not_called()
