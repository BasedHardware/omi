"""Actual checkout route with promo access and independent commercial authority."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment
from tests.unit.test_checkout_first_subscription import checkout, request_checkout, OTHER_PRICE  # noqa: F401
from utils.referral_campaign import CAMPAIGN_ID, GRANT_FIELD


@pytest.fixture
def promotional_checkout(checkout, monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    now = int(datetime.now(timezone.utc).timestamp())
    grant = {'campaign_id': CAMPAIGN_ID, 'status': 'active', 'starts_at': now - 30, 'ends_at': now + 60 * 86400}
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid, **kw: checkout.stored)
    monkeypatch.setattr(
        payment.users_db, 'user_snapshot', lambda *a, **kw: SimpleNamespace(to_dict=lambda: {GRANT_FIELD: grant})
    )
    return checkout


def test_pro_grant_owner_can_start_real_omi_pro_checkout(promotional_checkout):
    state = promotional_checkout
    state.stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    assert payment.users_db.get_user_valid_subscription('owner', provision=False).plan == PlanType.unlimited_v2
    response = request_checkout(state)
    assert response.status_code == 200
    assert response.json()['session_id'] == 'cs_test'
    state.create.assert_called_once()


def test_active_commercial_subscription_still_blocks_duplicate_checkout(promotional_checkout):
    response = request_checkout(promotional_checkout)
    assert response.status_code == 409
    promotional_checkout.create.assert_not_called()


def test_actual_pending_commercial_cancellation_keeps_plan_change_guard(promotional_checkout):
    state = promotional_checkout
    state.stored.cancel_at_period_end = True
    state.stored.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 86400
    response = request_checkout(state, OTHER_PRICE)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Plan changes are available after the current subscription ends'
    state.create.assert_not_called()
