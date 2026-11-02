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
import time
import types
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models.users import PlanType as PlanTypeForDefinitions

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"
_MISSING = object()

# MagicMocks installed on the shared stub modules. The module-scoped ``router``
# fixture builds them once; ``_uncalled_shared_mocks`` resets their call state per
# test so every test starts from uncalled mocks, exactly as the previous per-test
# re-import provided.
_SHARED_MOCKS: list[MagicMock] = []


def _shared_mock(*args: Any, **kwargs: Any) -> MagicMock:
    mock = MagicMock(*args, **kwargs)
    _SHARED_MOCKS.append(mock)
    return mock


def _install_stub_modules() -> None:
    """Install the stub module environment routers.payment is imported against.

    The stub modules replace any same-named entry unconditionally (no
    ``if mod_name not in sys.modules`` guard): in a batched pytest session the
    real ``database``/``utils`` graphs may already be imported, and writing mock
    attributes onto those real modules would leak into later files after
    teardown. Fresh stubs leave the real module objects untouched; the fixture
    teardown restores the original ``sys.modules`` entries.
    """
    from models.users import PlanLimits, PlanType

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
        sys.modules[mod_name] = types.ModuleType(mod_name)

    from contextlib import contextmanager

    @contextmanager
    def _noop_fresh_reads():
        yield

    fsr_mod = sys.modules["database.fsr_read_cache"]
    fsr_mod.fresh_reader = lambda fn: fn
    fsr_mod.fresh_reads = _noop_fresh_reads

    db_mod = sys.modules["database"]
    db_mod.__path__ = [str(PAYMENT_SOURCE.parents[1] / "database")]
    db_mod.users = _shared_mock()
    db_mod.conversations = _shared_mock()
    db_mod.memories = _shared_mock()
    db_mod.action_items = _shared_mock()

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.set_credits_invalidation_signal = _shared_mock()

    locked_content_mod = sys.modules["database.locked_content"]
    locked_content_mod.has_recoverable_locked_content = _shared_mock(return_value=False)

    fair_use_mod = sys.modules["utils.fair_use"]
    fair_use_mod.clear_fair_use_on_upgrade = _shared_mock()

    notif_mod = sys.modules["utils.notifications"]
    notif_mod.send_notification = _shared_mock()
    notif_mod.send_subscription_paid_personalized_notification = _shared_mock()

    sub_mod = sys.modules["utils.subscription"]
    sub_mod.can_user_make_payment = _shared_mock(return_value=(True, None))
    sub_mod.get_basic_plan_limits = _shared_mock(return_value=PlanLimits())
    sub_mod.get_paid_plan_definitions = _shared_mock()
    sub_mod.get_plan_type_from_price_id = _shared_mock(
        side_effect=lambda pid: PlanType.plus if pid == "price_plus" else PlanType.unlimited
    )
    sub_mod.is_purchasable_price_id = _shared_mock(return_value=True)
    sub_mod.get_plan_limits = _shared_mock(return_value=PlanLimits(transcription_seconds=36000))
    sub_mod.is_paid_plan = _shared_mock(side_effect=lambda plan: plan != PlanType.basic)
    sub_mod.filter_plans_for_user = _shared_mock()
    sub_mod.should_show_new_plans = _shared_mock()
    sub_mod.adapt_plans_for_legacy_client = _shared_mock()
    sub_mod.clear_trial_paywall_cache = _shared_mock()
    sub_mod.find_active_paid_subscription_for_user = _shared_mock()
    sub_mod.price_ids_match_plan_and_interval = _shared_mock(return_value=False)
    sub_mod.desktop_to_consumer_plan_change_error = _shared_mock(return_value=None)
    sub_mod.retired_plan_change_error = _shared_mock(return_value=None)

    fallback_mod = types.ModuleType("utils.observability.fallback")
    fallback_mod.record_fallback = _shared_mock()
    sys.modules["utils.observability.fallback"] = fallback_mod

    billing_ledger_mod = types.ModuleType("utils.observability.billing_ledger")
    billing_ledger_mod.record_outcome = _shared_mock()
    sys.modules["utils.observability.billing_ledger"] = billing_ledger_mod

    subscription_events_mod = types.ModuleType("utils.observability.subscription_events")
    subscription_events_mod.record_subscription_event = _shared_mock()
    sys.modules["utils.observability.subscription_events"] = subscription_events_mod

    stripe_utils_mod = sys.modules["utils.stripe"]
    stripe_utils_mod.base_url = "http://test/"
    stripe_utils_mod.create_subscription_checkout_session = _shared_mock()
    stripe_utils_mod.create_connect_account = _shared_mock()
    stripe_utils_mod.refresh_connect_account_link = _shared_mock()
    stripe_utils_mod.is_onboarding_complete = _shared_mock()

    apps_mod = sys.modules["utils.apps"]
    apps_mod.find_app_subscription = _shared_mock()
    apps_mod.get_is_user_paid_app = _shared_mock()
    apps_mod.paid_app = _shared_mock()
    apps_mod.set_user_app_sub_customer_id = _shared_mock()

    endpoints_mod = sys.modules["utils.other.endpoints"]
    endpoints_mod.get_current_user_uid = lambda: "test-uid"
    endpoints_mod.get_current_user_uid_no_byok_validation = lambda: "test-uid"

    overage_mod = sys.modules["utils.overage"]
    overage_mod.OVERAGE_EXPLAINER_TITLE = ""
    overage_mod.PROVIDER_REFERENCE_RATES = {}
    overage_mod.build_explainer_text = _shared_mock()
    overage_mod.get_user_overage = _shared_mock()
    overage_mod.is_overage_plan = _shared_mock()

    exec_mod = sys.modules["utils.executors"]
    exec_mod.db_executor = _shared_mock()
    exec_mod.stripe_executor = _shared_mock()
    exec_mod.run_blocking = _shared_mock()

    sanitizer_mod = sys.modules["utils.log_sanitizer"]
    sanitizer_mod.sanitize = lambda x: x

    users_db_mod = sys.modules["database.users"]
    users_db_mod.get_stripe_connect_account_id = _shared_mock()
    users_db_mod.get_user_profile = _shared_mock(return_value={})
    users_db_mod.set_stripe_connect_account_id = _shared_mock()
    users_db_mod.set_paypal_payment_details = _shared_mock()
    users_db_mod.get_default_payment_method = _shared_mock()
    users_db_mod.set_default_payment_method = _shared_mock()
    users_db_mod.get_paypal_payment_details = _shared_mock()


@pytest.fixture(scope="module")
def payment_router():
    """Import routers.payment once per file with external IO modules mocked
    while keeping real models.users. The real import graph (stripe SDK, FastAPI,
    models.users) costs ~2s CPU; re-importing it inside every test's call phase
    is what tripped the fast-unit duration guard at 2.15-2.48s against the
    1.00s budget (CI run 40118719182). Module scope pays the import once, in
    fixture setup, which the guard intentionally excludes from per-test CPU.
    """
    modules = dict(sys.modules)
    routers_module = modules.get("routers")
    router_payment = getattr(routers_module, "payment", _MISSING) if routers_module else _MISSING
    # ``from utils import stripe`` / ``from utils import subscription`` resolve through
    # the parent package attribute before the ``sys.modules`` submodule fallback, so a
    # batched session that already imported the real submodules would bind the real
    # modules into the router. Pin the parent attributes to the stubs for the fixture
    # window and restore them at teardown (Luna round 1, PR #23537).
    utils_module = modules.get("utils")
    utils_attrs = {
        attr: getattr(utils_module, attr, _MISSING) if utils_module else _MISSING for attr in ("stripe", "subscription")
    }
    try:
        _install_stub_modules()
        if utils_module is not None:
            utils_module.stripe = sys.modules["utils.stripe"]
            utils_module.subscription = sys.modules["utils.subscription"]
        if "routers.payment" in sys.modules:
            del sys.modules["routers.payment"]
        live_routers_module = sys.modules.get("routers")
        if live_routers_module:
            live_routers_module.__dict__.pop("payment", None)

        from routers import payment as payment_router

        from models.users import PlanType, Subscription, SubscriptionStatus

        payment_router.PlanType = PlanType
        payment_router.Subscription = Subscription
        payment_router.SubscriptionStatus = SubscriptionStatus
        yield payment_router
    finally:
        for module_name in tuple(sys.modules):
            if module_name not in modules:
                del sys.modules[module_name]
        sys.modules.update(modules)
        if utils_module is not None:
            for attr, saved in utils_attrs.items():
                if saved is _MISSING:
                    utils_module.__dict__.pop(attr, None)
                else:
                    setattr(utils_module, attr, saved)
        if routers_module:
            if router_payment is _MISSING:
                routers_module.__dict__.pop("payment", None)
            else:
                routers_module.payment = router_payment


@pytest.fixture(autouse=True)
def _uncalled_shared_mocks(payment_router):
    """Start every test against uncalled shared mocks.

    ``return_value=False, side_effect=False`` keeps the stub configuration
    installed once (e.g. ``can_user_make_payment`` -> ``(True, None)``) while
    clearing call records, matching the per-test fresh-import isolation the
    previous per-test reload provided. Tests override the return values they
    care about (``get_user_subscription``) explicitly.
    """
    for mock in _SHARED_MOCKS:
        mock.reset_mock(return_value=False, side_effect=False)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def test_cross_plan_upgrade_passes_error_if_incomplete_to_stripe_modify(payment_router):
    router = payment_router
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "currency": "usd",
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
            return_value=SimpleNamespace(currency="usd", recurring=SimpleNamespace(interval="month")),
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


def test_declined_proration_card_error_returns_402_and_preserves_paid_plan(payment_router):
    router = payment_router
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "currency": "usd",
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
            return_value=SimpleNamespace(currency="usd", recurring=SimpleNamespace(interval="month")),
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


def test_declined_proration_past_due_snapshot_returns_402_and_never_projects_basic(payment_router):
    """If Stripe ever returns a past_due or pending_update subscription from modify,
    the endpoint must reject with 402 rather than projecting past_due -> Basic (Free)
    and overwriting the subscriber's paid plan in Firestore."""
    router = payment_router
    current_sub = router.Subscription(
        plan=router.PlanType.plus,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_active_plus",
        current_period_start=1_700_000_000,
        current_period_end=1_702_592_000,
    )
    router.users_db.get_user_subscription.return_value = current_sub

    stripe_sub_dict = {
        "currency": "usd",
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
            return_value=SimpleNamespace(currency="usd", recurring=SimpleNamespace(interval="month")),
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


# Yearly switch (switch_now): Omi Pro monthly -> yearly takes the same immediate, declined-safe path,
# charges only the previewed amount, and is refused for every state the in-app offer hides (#23298
# trials, past_due, scheduled cancel or change, discounts, promotion codes, other currencies).
_YS_NOW = int(time.time())
_YS_PRORATION = _YS_NOW - 30
_YS_DUE = 24492
_YS_DEFINITIONS = [
    {
        "plan_type": PlanTypeForDefinitions.unlimited_v2,
        "monthly_price_id": "price_um",
        "annual_price_id": "price_uy",
        "legacy": False,
    },
    {
        "plan_type": PlanTypeForDefinitions.plus,
        "monthly_price_id": "price_pm",
        "annual_price_id": "price_py",
        "legacy": False,
    },
]


def _ys_invoice(amount_due=_YS_DUE, **over):
    invoice = {
        "currency": "usd",
        "amount_due": amount_due,
        "discounts": [],
        "total_discount_amounts": [],
        "lines": {"data": [{"proration": False, "period": {"start": _YS_NOW, "end": _YS_NOW + 365 * 86400}}]},
    }
    invoice.update(over)
    return invoice


def _ys_request(router, **over):
    params = {
        "price_id": "price_uy",
        "switch_now": True,
        "proration_date": _YS_PRORATION,
        "expected_amount_due": _YS_DUE,
        **over,
    }
    return router.UpgradeSubscriptionRequest(**params)


def _ys_stripe_sub(**over):
    sub = {
        "currency": "usd",
        "id": "sub_monthly",
        "customer": "cus_123",
        "status": "active",
        "cancel_at_period_end": False,
        "schedule": None,
        "discount": None,
        "discounts": [],
        "trial_end": None,
        "start_date": _YS_NOW - 40 * 86400,
        "current_period_start": _YS_NOW - 5 * 86400,
        "current_period_end": _YS_NOW + 25 * 86400,
        "items": {
            "data": [
                {
                    "id": "si_monthly",
                    "quantity": 1,
                    "price": {
                        "id": "price_um",
                        "currency": "usd",
                        "unit_amount": 2999,
                        "recurring": {"interval": "month", "interval_count": 1},
                    },
                }
            ]
        },
    }
    sub.update(over)
    return sub


@contextmanager
def _ys_patches(router, stripe_sub_dict, modify, invoice=None):
    """Stripe and catalog for a monthly Unlimited subscriber; yields the mocks tests assert on."""
    retrieved_sub = MagicMock()
    retrieved_sub.to_dict.return_value = stripe_sub_dict
    plans = {"price_um": router.PlanType.unlimited_v2, "price_uy": router.PlanType.unlimited_v2}
    with ExitStack() as stack:
        mocks = SimpleNamespace(
            modify=stack.enter_context(patch.object(router.stripe.Subscription, "modify", **modify)),
            schedule_create=stack.enter_context(patch.object(router.stripe.SubscriptionSchedule, "create")),
            schedule_modify=stack.enter_context(patch.object(router.stripe.SubscriptionSchedule, "modify")),
            promo=stack.enter_context(patch.object(router.stripe.PromotionCode, "list")),
            preview=stack.enter_context(
                patch.object(
                    router.yearly_switch.stripe.Invoice, "create_preview", return_value=invoice or _ys_invoice()
                )
            ),
        )
        stack.enter_context(patch.object(router.stripe.Subscription, "retrieve", return_value=retrieved_sub))
        stack.enter_context(
            patch.object(
                router.stripe.Price,
                "retrieve",
                return_value=SimpleNamespace(currency="usd", recurring=SimpleNamespace(interval="year")),
            )
        )
        stack.enter_context(patch.object(router, "_release_attached_schedules"))
        stack.enter_context(patch.object(router, "funded_processing_enabled", return_value=False))
        stack.enter_context(
            patch.object(
                router, "get_plan_type_from_price_id", side_effect=lambda pid: plans.get(pid, router.PlanType.plus)
            )
        )
        stack.enter_context(patch.object(router.yearly_switch, "_plan_definitions", return_value=_YS_DEFINITIONS))
        yield mocks


def _ys_stored(router):
    router.users_db.get_user_subscription.return_value = router.Subscription(
        plan=router.PlanType.unlimited_v2,
        status=router.SubscriptionStatus.active,
        stripe_subscription_id="sub_monthly",
        current_period_start=_YS_NOW - 5 * 86400,
        current_period_end=_YS_NOW + 25 * 86400,
    )


def test_yearly_switch_charges_now_with_error_if_incomplete_and_the_previewed_proration_date(payment_router):
    router = payment_router
    _ys_stored(router)
    switched = MagicMock()
    switched.to_dict.return_value = _ys_stripe_sub(
        current_period_start=_YS_NOW,
        current_period_end=_YS_NOW + 365 * 86400,
        items={"data": [{"id": "si_monthly", "price": {"id": "price_uy", "recurring": {"interval": "year"}}}]},
    )
    with _ys_patches(router, _ys_stripe_sub(), {"return_value": switched}) as mocks:
        result = router.upgrade_subscription_endpoint(_ys_request(router), uid="u1")

    assert result["status"] == "success"
    # The charge is re-previewed at the reader's proration date before Stripe is written.
    assert mocks.preview.call_args.kwargs["subscription_details"] == {
        "items": [{"id": "si_monthly", "price": "price_uy"}],
        "proration_behavior": "always_invoice",
        "proration_date": _YS_PRORATION,
    }
    mocks.modify.assert_called_once_with(
        "sub_monthly",
        items=[{"id": "si_monthly", "price": "price_uy"}],
        proration_behavior="always_invoice",
        payment_behavior="error_if_incomplete",
        metadata={"uid": "u1", "sub_type": "unlimited_v2", "omi_yearly_switch": "in_app"},
        proration_date=_YS_PRORATION,
        idempotency_key=f"omi-yearly-switch-sub_monthly-{_YS_PRORATION}",
    )
    mocks.schedule_create.assert_not_called()
    written_sub = router.users_db.update_user_subscription.call_args.args[1]
    assert written_sub["plan"] == router.PlanType.unlimited_v2
    assert written_sub["current_period_end"] == _YS_NOW + 365 * 86400


def test_declined_yearly_switch_returns_402_and_keeps_the_monthly_plan(payment_router):
    router = payment_router
    _ys_stored(router)
    card_error = router.stripe.error.CardError(
        message="Your card was declined.",
        param=None,
        code="card_declined",
        json_body={"error": {"message": "Your card was declined."}},
    )
    with _ys_patches(router, _ys_stripe_sub(), {"side_effect": card_error}) as mocks:
        with pytest.raises(router.HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(_ys_request(router), uid="u1")

    assert exc_info.value.status_code == 402
    mocks.modify.assert_called_once()
    mocks.schedule_create.assert_not_called()
    router.users_db.update_user_subscription.assert_not_called()
    router.set_credits_invalidation_signal.assert_not_called()


@pytest.mark.parametrize(
    "over,request_over,invoice",
    [
        ({"status": "trialing", "trial_end": _YS_NOW + 3 * 86400}, {}, None),  # #23298
        ({"trial_end": _YS_NOW + 3 * 86400}, {}, None),
        ({"status": "past_due"}, {}, None),
        ({"status": "unpaid"}, {}, None),
        ({"schedule": "sub_sched_1"}, {}, None),
        ({"pending_update": {"expires_at": _YS_NOW + 86400}}, {}, None),
        ({"discounts": ["di_retention"]}, {}, None),
        ({"discount": {"coupon": {"id": "omi-retention-50off-3mo"}}}, {}, None),
        ({"currency": "jpy"}, {}, None),
        ({"pause_collection": {"behavior": "void"}}, {}, None),
        ({"collection_method": "send_invoice"}, {}, None),
        ({}, {"promotion_code": "SAVE20"}, None),
        ({}, {"proration_date": _YS_NOW - 2 * 3600}, None),  # a stale preview
        ({}, {"proration_date": None}, None),  # no preview, no charge
        ({}, {"expected_amount_due": None}, None),
        ({}, {"expected_amount_due": _YS_DUE + 1}, None),  # not the amount Stripe would charge now
        ({}, {}, _ys_invoice(total_discount_amounts=[{"amount": 500}])),  # a customer-level coupon
        ({}, {"price_id": "price_py"}, None),  # another plan's yearly price
    ],
)
def test_yearly_switch_is_refused_for_every_state_the_offer_hides(payment_router, over, request_over, invoice):
    router = payment_router
    _ys_stored(router)
    with _ys_patches(router, _ys_stripe_sub(**over), {"return_value": MagicMock()}, invoice) as mocks:
        with pytest.raises(router.HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(_ys_request(router, **request_over), uid="u1")

    assert exc_info.value.status_code == 409
    mocks.modify.assert_not_called()
    mocks.schedule_create.assert_not_called()
    mocks.promo.assert_not_called()
    router.users_db.update_user_subscription.assert_not_called()


def test_a_repeated_yearly_switch_after_it_landed_never_charges_again(payment_router):
    """A retry or second tap after the switch succeeded finds the yearly price and stops before Stripe."""
    router = payment_router
    _ys_stored(router)
    yearly = _ys_stripe_sub(
        items={
            "data": [
                {
                    "id": "si_monthly",
                    "quantity": 1,
                    "price": {"id": "price_uy", "currency": "usd", "recurring": {"interval": "year"}},
                }
            ]
        }
    )
    with _ys_patches(router, yearly, {"return_value": MagicMock()}) as mocks:
        with pytest.raises(router.HTTPException) as exc_info:
            router.upgrade_subscription_endpoint(_ys_request(router), uid="u1")

    assert exc_info.value.status_code == 400
    mocks.preview.assert_not_called()
    mocks.modify.assert_not_called()
    mocks.schedule_create.assert_not_called()


def test_same_plan_yearly_without_switch_now_is_still_scheduled_for_the_period_end(payment_router):
    router = payment_router
    _ys_stored(router)
    with _ys_patches(router, _ys_stripe_sub(), {"return_value": MagicMock()}) as mocks:
        mocks.schedule_create.return_value = SimpleNamespace(id="sub_sched_new")
        result = router.upgrade_subscription_endpoint(router.UpgradeSubscriptionRequest(price_id="price_uy"), uid="u1")

    assert result["schedule_id"] == "sub_sched_new"
    mocks.schedule_create.assert_called_once_with(from_subscription="sub_monthly")
    mocks.schedule_modify.assert_called_once()
    mocks.modify.assert_not_called()
