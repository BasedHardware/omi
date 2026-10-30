"""Hermetic unit tests for Issue #24123:
[community-signal] app-update: "Upgrade button does nothing" — processing paused on paid plans.

Verifies:
1. allowance_increased correctly detects allowance increases for Unlimited plan upgrades,
   migrations (unlimited -> unlimited_v2), price/interval changes, and reactivations
   from inactive/lapsed states, while correctly filtering out calendar renewals.
2. upgrade_subscription_endpoint triggers backlog drain (upgrade) when a user already on the
   paid plan requests an upgrade for their current price ID, unblocking held audio before
   returning the client-compatible HTTP 400.
3. reconcile_basic_plan_with_stripe triggers backlog drain upon discovering an active paid plan.
4. choose(..., automatic=True) on an unlimited plan properly authorizes backlog processing (begin=True).
"""

import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from models.users import PlanType, Subscription, SubscriptionStatus
from routers.payment import UpgradeSubscriptionRequest
from utils import processing_backlog as backlog
from utils.processing_backlog import allowance_increased


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', '12345678901234567890123456789012')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')


def test_unlimited_plan_upgrade_and_reactivation_increases_allowance():
    # 1. Finite to Unlimited is an increase
    basic = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    plus = Subscription(plan=PlanType.plus, current_price_id='price_plus', status=SubscriptionStatus.active)
    unlimited = Subscription(plan=PlanType.unlimited, current_price_id='price_unlim_m', status=SubscriptionStatus.active)
    unlimited_v2 = Subscription(plan=PlanType.unlimited_v2, current_price_id='price_unlim_v2_m', status=SubscriptionStatus.active)

    assert allowance_increased(basic, unlimited) is True
    assert allowance_increased(plus, unlimited) is True
    assert allowance_increased(basic, unlimited_v2) is True
    assert allowance_increased(plus, unlimited_v2) is True

    # 2. Inactive Unlimited -> Active Unlimited is a reactivation increase
    inactive_unlimited = Subscription(plan=PlanType.unlimited, current_price_id='price_unlim_m', status=SubscriptionStatus.inactive)
    assert allowance_increased(inactive_unlimited, unlimited) is True

    # 3. Plan migration: Legacy Neo (unlimited) -> Omi Pro (unlimited_v2) is an upgrade
    assert allowance_increased(unlimited, unlimited_v2) is True

    # 4. Price/interval migration: Monthly Unlimited -> Annual Unlimited is an upgrade intent
    unlimited_annual = Subscription(plan=PlanType.unlimited, current_price_id='price_unlim_annual', status=SubscriptionStatus.active)
    assert allowance_increased(unlimited, unlimited_annual) is True

    # 5. Routine calendar renewal of same plan & price must NOT trigger upgrade intent
    renewed_unlimited = unlimited.model_copy(update={'current_period_end': int(time.time()) + 86400 * 30})
    assert allowance_increased(unlimited, renewed_unlimited) is False

    # 6. Downgrades from Unlimited must NOT trigger upgrade intent
    assert allowance_increased(unlimited, basic) is False
    assert allowance_increased(unlimited, plus) is False


def test_same_price_upgrade_endpoint_triggers_backlog_drain(monkeypatch):
    from routers import payment

    uid = 'user-same-price-24123'
    current_sub = Subscription(
        plan=PlanType.unlimited_v2,
        current_price_id='price_pro_month',
        stripe_subscription_id='sub_pro_123',
        status=SubscriptionStatus.active,
    )

    monkeypatch.setattr(payment, '_validate_price_id', lambda _p: None)
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda _uid: current_sub)
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', lambda _sub_id: SimpleNamespace(
        to_dict=lambda: {
            'items': {'data': [{'id': 'si_123', 'price': {'id': 'price_pro_month'}}]},
            'cancel_at_period_end': False,
        }
    ))
    monkeypatch.setattr(payment, 'has_recoverable_locked_content', lambda _uid: False)
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', Mock())
    monkeypatch.setattr(payment, 'funded_processing_enabled', lambda _uid: True)

    upgrade_mock = Mock()
    monkeypatch.setattr('utils.processing_backlog_worker.upgrade', upgrade_mock)

    req = UpgradeSubscriptionRequest(price_id='price_pro_month')
    with pytest.raises(HTTPException) as exc_info:
        payment.upgrade_subscription_endpoint(req, uid=uid)

    assert exc_info.value.status_code == 400
    assert 'You are already subscribed to this plan' in exc_info.value.detail
    upgrade_mock.assert_called_once()
    assert upgrade_mock.call_args[0][0] == uid
    assert 'same-plan-replay:price_pro_month' in upgrade_mock.call_args[0][1]


def test_reconcile_basic_plan_with_stripe_triggers_backlog_drain(monkeypatch):
    from utils import subscription as sub_utils

    uid = 'user-reconcile-24123'
    basic_sub = Subscription(
        plan=PlanType.basic,
        stripe_subscription_id='sub_active_in_stripe',
        status=SubscriptionStatus.active,
    )

    now = int(time.time())
    stripe_dict = {
        'status': 'active',
        'current_period_start': now - 86400,
        'current_period_end': now + 86400 * 30,
        'cancel_at_period_end': False,
        'customer': 'cus_123',
        'items': {'data': [{'price': {'id': 'price_pro_month'}}]},
    }

    monkeypatch.setattr(sub_utils.stripe.Subscription, 'retrieve', lambda _sub_id: SimpleNamespace(
        to_dict=lambda: stripe_dict
    ))
    monkeypatch.setattr(sub_utils, 'get_plan_type_from_price_id', lambda _p: PlanType.unlimited_v2)
    monkeypatch.setattr(sub_utils.users_db, 'set_stripe_customer_id', Mock())
    monkeypatch.setattr(sub_utils.users_db, 'update_user_subscription', Mock())

    upgrade_mock = Mock()
    monkeypatch.setattr('utils.processing_backlog_worker.upgrade', upgrade_mock)

    reconciled = sub_utils.reconcile_basic_plan_with_stripe(uid, basic_sub)
    assert reconciled.plan == PlanType.unlimited_v2
    upgrade_mock.assert_called_once()
    assert upgrade_mock.call_args[0][0] == uid
    assert 'reconcile-upgrade:sub_active_in_stripe:price_pro_month' in upgrade_mock.call_args[0][1]


def test_choose_automatic_on_unlimited_starts_processing(monkeypatch):
    from utils import funded_processing as funded

    uid = 'user-auto-choose-24123'
    monkeypatch.setattr(backlog, 'recovery_cohort_admits', lambda _uid: True)
    monkeypatch.setattr(funded, 'enabled', lambda _uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-10')

    # Unlimited allowance has remaining_seconds=None, managed=True
    unlim_allowance = SimpleNamespace(
        managed=True,
        remaining_units=None,
        budget_units=None,
        remaining_seconds=None,
        limit_seconds=None,
    )
    monkeypatch.setattr(funded, 'allowance', lambda _uid: unlim_allowance)

    # User has 500 held recordings
    audio = {'count': 500, 'seconds': 6000}
    summary = {'count': 0, 'units': 0, 'state': 'waiting_choice', 'period': '2026-10'}
    monkeypatch.setattr('utils.sync.cap_hold.ensure_summary', lambda _uid: audio)
    monkeypatch.setattr('database.processing_backlog.read', lambda _uid: summary)

    start_mock = Mock(return_value={'state': 'processing', 'period': '2026-10'})
    monkeypatch.setattr('database.processing_backlog.start', start_mock)

    intent_at = time.time()
    result = backlog.choose(uid, request_key='auto-key-1', automatic=True, intent_at=intent_at)

    assert result is not None
    assert result['state'] == 'processing'
    start_mock.assert_called_once()
    assert start_mock.call_args.kwargs['begin'] is True
    assert start_mock.call_args.kwargs['remaining'] is None
