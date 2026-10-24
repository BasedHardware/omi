"""Legacy endpoint remains byte-identical regardless of the new flag."""

from unittest.mock import MagicMock

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import payment
from models.users import PlanType, Subscription, SubscriptionStatus


@pytest.fixture(scope='module')
def client():
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture-user'
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('platform', ['ios', 'android', 'macos', 'windows', 'web'])
@pytest.mark.parametrize('cancel_at_period_end', [False, True])
@pytest.mark.parametrize('plan', ['basic', 'plus', 'operator', 'architect', 'unlimited', 'unlimited_v2'])
def test_v1_response_bytes_do_not_change_with_storefront_flag(
    client, monkeypatch, platform, plan, cancel_at_period_end
):
    monkeypatch.setattr(
        payment.users_db,
        'get_user_subscription',
        lambda uid, **kwargs: Subscription(
            plan=PlanType(plan),
            status=SubscriptionStatus.active,
            stripe_subscription_id='sub_fixture' if plan != 'basic' else None,
            cancel_at_period_end=cancel_at_period_end,
        ),
    )
    # Catalog filtering reads the period-valid projection (like checkout); this
    # fixture's records carry no period end, so paid plans project to basic and
    # the single-plan rule shapes mobile/web the same way in every flag state —
    # what must not change is the v1 bytes across the storefront flag itself.
    monkeypatch.setattr(
        payment.users_db,
        'get_user_valid_subscription',
        lambda uid, **kwargs: Subscription(plan=PlanType(plan), status=SubscriptionStatus.active),
    )
    for name in ['UNLIMITED', 'PLUS', 'OPERATOR', 'ARCHITECT', 'UNLIMITED_V2']:
        monkeypatch.setenv(f'STRIPE_{name}_MONTHLY_PRICE_ID', f'price_{name}_month')
        monkeypatch.setenv(f'STRIPE_{name}_ANNUAL_PRICE_ID', f'price_{name}_year')

    def retrieve(identifier):
        row = MagicMock()
        row.id = identifier
        row.unit_amount = 1900 if identifier.endswith('month') else 19000
        row.recurring.interval = 'month' if identifier.endswith('month') else 'year'
        return row

    monkeypatch.setattr(stripe.Price, 'retrieve', retrieve)
    stripe_sub = MagicMock()
    stripe_sub.to_dict.return_value = {'items': {'data': [{'price': {'id': f'price_{plan.upper()}_month'}}]}}
    monkeypatch.setattr(stripe.Subscription, 'retrieve', lambda identifier: stripe_sub)
    headers = {'X-App-Platform': platform, 'X-App-Version': '99.0.0'}
    monkeypatch.delenv('STOREFRONT_LADDER_V1_ENABLED', raising=False)
    before = client.get('/v1/payments/available-plans', headers=headers)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'false')
    off = client.get('/v1/payments/available-plans', headers=headers)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    on = client.get('/v1/payments/available-plans', headers=headers)
    assert before.status_code == off.status_code == on.status_code == 200
    assert before.content == off.content == on.content
