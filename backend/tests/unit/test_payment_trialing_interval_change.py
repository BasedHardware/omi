import time
from types import SimpleNamespace
from models.users import PlanType
from unittest.mock import MagicMock, patch
import pytest

from tests.unit.test_payment_promotion_codes import _setup_payment_module


@pytest.fixture
def payment_router():
    router = _setup_payment_module(include_client=False)
    router.get_plan_limits.return_value = {}
    return router


def test_trialing_interval_switch_modifies_subscription_directly_without_schedule(payment_router):
    """When switching interval during an active trial (e.g. annual to monthly),
    the endpoint must update the subscription directly with proration_behavior='none'
    and preserve trial_end, instead of creating a SubscriptionSchedule which terminates
    the trial prematurely and invoices the full annual amount (#23298)."""
    router = payment_router
    uid = "test_user_trialing"
    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_trialing_123",
        plan="unlimited",
        status="trialing",
        model_dump=lambda: {"stripe_subscription_id": "sub_trialing_123", "plan": "unlimited", "status": "trialing"},
    )

    now_ts = int(time.time())
    trial_end_ts = now_ts + 6 * 86400  # 6 days remaining

    stripe_sub_dict = {
        "id": "sub_trialing_123",
        "customer": "cus_123",
        "status": "trialing",
        "trial_start": now_ts - 86400,
        "trial_end": trial_end_ts,
        "current_period_start": now_ts - 86400,
        "current_period_end": trial_end_ts,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_annual",
                    "price": {
                        "id": "price_unlimited_annual",
                        "recurring": {"interval": "year"},
                    },
                }
            ]
        },
    }

    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "items": {
            "data": [
                {
                    "id": "si_annual",
                    "price": {
                        "id": "price_unlimited_monthly",
                        "recurring": {"interval": "month"},
                    },
                }
            ]
        },
    }

    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = "month"

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", return_value=PlanType.unlimited), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_target_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.Subscription, "modify", return_value=mock_updated_sub) as mock_sub_modify, \
         patch.object(router.stripe, "SubscriptionSchedule") as mock_schedule, \
         patch.object(router.users_db, "update_user_subscription") as mock_db_update:

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_monthly")
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        # 1. SubscriptionSchedule must NOT be created
        mock_schedule.create.assert_not_called()
        mock_schedule.modify.assert_not_called()

        # 2. Subscription.modify must be called directly with trial preserved
        mock_sub_modify.assert_called_once()
        call_args, call_kwargs = mock_sub_modify.call_args
        assert call_args[0] == "sub_trialing_123"
        assert call_kwargs["proration_behavior"] == "none"
        assert call_kwargs["trial_end"] == trial_end_ts
        assert call_kwargs["items"] == [{"id": "si_annual", "price": "price_unlimited_monthly"}]
        assert call_kwargs["metadata"] == {"uid": uid, "upgrade_type": "unlimited_month"}

        # 3. Response should reflect preserved trial and no schedule ID
        assert response["status"] == "success"
        assert response["schedule_id"] is None
        assert response["days_remaining"] in (5, 6)
        assert "Your free trial continues" in response["message"]

        # 4. Local database should be updated
        mock_db_update.assert_called_once()


def test_non_trialing_interval_switch_still_uses_subscription_schedule(payment_router):
    """Active (non-trialing) subscribers switching intervals must continue to use
    SubscriptionSchedule so the switch takes effect at current_period_end."""
    router = payment_router
    uid = "test_user_active"
    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_active_123",
        plan="unlimited",
        status="active",
        model_dump=lambda: {"stripe_subscription_id": "sub_active_123", "plan": "unlimited", "status": "active"},
    )

    now_ts = int(time.time())
    period_end_ts = now_ts + 20 * 86400

    stripe_sub_dict = {
        "id": "sub_active_123",
        "customer": "cus_123",
        "status": "active",
        "trial_end": None,
        "current_period_start": now_ts - 10 * 86400,
        "current_period_end": period_end_ts,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_monthly",
                    "price": {
                        "id": "price_unlimited_monthly",
                        "recurring": {"interval": "month"},
                    },
                }
            ]
        },
    }

    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = "year"

    mock_schedule_obj = MagicMock(id="sched_123")

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", return_value=PlanType.unlimited), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_target_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.SubscriptionSchedule, "create", return_value=mock_schedule_obj) as mock_sched_create, \
         patch.object(router.stripe.SubscriptionSchedule, "modify", return_value=mock_schedule_obj) as mock_sched_modify:

        request = router.UpgradeSubscriptionRequest(price_id="price_unlimited_annual")
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        # SubscriptionSchedule MUST be created for non-trialing active interval changes
        mock_sched_create.assert_called_once_with(from_subscription="sub_active_123")
        mock_sched_modify.assert_called_once()
        assert response["status"] == "success"
        assert response["schedule_id"] == "sched_123"


def test_trialing_interval_switch_with_promo_code_passes_discounts(payment_router):
    """When a valid promo code is provided during a trialing interval switch,
    it should be passed in discounts to Subscription.modify."""
    router = payment_router
    uid = "test_user_trial_promo"
    current_sub = SimpleNamespace(
        stripe_subscription_id="sub_trial_promo",
        plan="unlimited",
        status="trialing",
        model_dump=lambda: {"stripe_subscription_id": "sub_trial_promo", "plan": "unlimited", "status": "trialing"},
    )

    now_ts = int(time.time())
    trial_end_ts = now_ts + 5 * 86400

    stripe_sub_dict = {
        "id": "sub_trial_promo",
        "customer": "cus_123",
        "status": "trialing",
        "trial_end": trial_end_ts,
        "current_period_start": now_ts,
        "current_period_end": trial_end_ts,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_item",
                    "price": {"id": "price_annual", "recurring": {"interval": "year"}},
                }
            ]
        },
    }

    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = "month"

    mock_promo = MagicMock(id="promo_trial_abc")

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", return_value=PlanType.unlimited), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_target_price), \
         patch.object(router.stripe.PromotionCode, "list", return_value=MagicMock(data=[mock_promo])), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.Subscription, "modify", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)) as mock_sub_modify:

        request = router.UpgradeSubscriptionRequest(
            price_id="price_monthly",
            promotion_code="PROMO_SAVE",
        )
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        assert response["status"] == "success"
        call_kwargs = mock_sub_modify.call_args[1]
        assert call_kwargs["discounts"] == [{"promotion_code": "promo_trial_abc"}]
        assert call_kwargs["proration_behavior"] == "none"
        assert call_kwargs["trial_end"] == trial_end_ts


@pytest.mark.parametrize(
    "from_interval,to_interval,initial_price_id,target_price_id,remaining_days",
    [
        ("year", "month", "price_unlimited_annual", "price_unlimited_monthly", 7),
        ("month", "year", "price_unlimited_monthly", "price_unlimited_annual", 14),
        ("month", "year", "price_unlimited_monthly", "price_unlimited_annual", 3),
    ],
)
def test_subscription_interval_switch_during_trial_preserves_end_date(
    payment_router,
    from_interval,
    to_interval,
    initial_price_id,
    target_price_id,
    remaining_days,
):
    """Parametrized verification that switching intervals in either direction
    (annual -> monthly or monthly -> annual) during an active trial explicitly checks
    subscription.status == 'trialing', preserves the original trial_end date,
    applies proration_behavior='none', and bypasses SubscriptionSchedule creation."""
    router = payment_router
    uid = f"user_trial_{from_interval}_to_{to_interval}"
    current_sub = SimpleNamespace(
        stripe_subscription_id=f"sub_trial_{from_interval}",
        plan="unlimited",
        status="trialing",
        model_dump=lambda: {
            "stripe_subscription_id": f"sub_trial_{from_interval}",
            "plan": "unlimited",
            "status": "trialing",
        },
    )

    now_ts = int(time.time())
    trial_end_ts = now_ts + remaining_days * 86400

    stripe_sub_dict = {
        "id": f"sub_trial_{from_interval}",
        "customer": "cus_123",
        "status": "trialing",
        "trial_start": now_ts - 86400,
        "trial_end": trial_end_ts,
        "current_period_start": now_ts - 86400,
        "current_period_end": trial_end_ts,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_item_123",
                    "price": {
                        "id": initial_price_id,
                        "recurring": {"interval": from_interval},
                    },
                }
            ]
        },
    }

    mock_updated_sub = MagicMock()
    mock_updated_sub.to_dict.return_value = {
        **stripe_sub_dict,
        "items": {
            "data": [
                {
                    "id": "si_item_123",
                    "price": {
                        "id": target_price_id,
                        "recurring": {"interval": to_interval},
                    },
                }
            ]
        },
    }

    mock_target_price = MagicMock()
    mock_target_price.recurring.interval = to_interval

    with patch.object(router, "_validate_price_id"), \
         patch.object(router.users_db, "get_user_subscription", return_value=current_sub), \
         patch.object(router, "is_paid_plan", return_value=True), \
         patch.object(router, "get_plan_type_from_price_id", return_value=PlanType.unlimited), \
         patch.object(router.stripe.Price, "retrieve", return_value=mock_target_price), \
         patch.object(router.stripe.Subscription, "retrieve", return_value=MagicMock(to_dict=lambda: stripe_sub_dict)), \
         patch.object(router.stripe.Subscription, "modify", return_value=mock_updated_sub) as mock_sub_modify, \
         patch.object(router.stripe, "SubscriptionSchedule") as mock_schedule, \
         patch.object(router.users_db, "update_user_subscription") as mock_db_update:

        request = router.UpgradeSubscriptionRequest(price_id=target_price_id)
        response = router.upgrade_subscription_endpoint(request, uid=uid)

        # 1. SubscriptionSchedule must NOT be touched during trial
        mock_schedule.create.assert_not_called()
        mock_schedule.modify.assert_not_called()

        # 2. Subscription.modify must be invoked directly with preserved trial_end and proration_behavior='none'
        mock_sub_modify.assert_called_once()
        call_args, call_kwargs = mock_sub_modify.call_args
        assert call_args[0] == f"sub_trial_{from_interval}"
        assert call_kwargs["proration_behavior"] == "none"
        assert call_kwargs["trial_end"] == trial_end_ts
        assert call_kwargs["items"] == [{"id": "si_item_123", "price": target_price_id}]
        assert call_kwargs["metadata"] == {"uid": uid, "upgrade_type": f"unlimited_{to_interval}"}

        # 3. Response validation
        assert response["status"] == "success"
        assert response["schedule_id"] is None
        assert response["days_remaining"] in (remaining_days - 1, remaining_days)
        assert "Your free trial continues" in response["message"]
        assert to_interval in response["message"]

        mock_db_update.assert_called_once()

