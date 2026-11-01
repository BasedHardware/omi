"""Opt-in synthetic Stripe sandbox verification of the actual payment router.

STRIPE_API_KEY must be a standard sk_test_ key. Creates disposable sandbox
products, prices, customers and subscriptions; no production credentials/data.
Only identity bindings and persistence/cache seams are substituted. All Stripe
reads, payments, schedules and errors use the real sandbox API.

Run from backend: python -m pytest --confcutdir=tests/integration/billing
    tests/integration/billing/test_jpy_plan_changes_stripe.py -v

The dedicated confcutdir isolates this explicit provider test from the unit
network guard and unrelated legacy Firebase integration-session fixture.
"""

import os
import uuid

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import plan_catalog
from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment
from utils import billing_currency


@pytest.fixture(scope='module')
def sandbox_prices():
    key = os.environ.get('STRIPE_API_KEY', '')
    if not key.startswith('sk_test_'):
        pytest.skip('Requires an explicitly supplied standard Stripe sandbox key')
    stripe.api_key = key
    products, prices = [], {}
    try:
        for plan, amount in [(PlanType.plus, 1800), (PlanType.unlimited_v2, 4800)]:
            product = stripe.Product.create(
                name=f'Omi JPY plan-change QA {plan.value}', metadata={'purpose': 'jpy-plan-change-qa'}
            )
            products.append(product.id)
            for currency in ('usd', 'jpy'):
                for interval, factor in [('month', 1), ('year', 9)]:
                    prices[(plan, interval, currency)] = stripe.Price.create(
                        product=product.id,
                        currency=currency,
                        unit_amount=amount * factor,
                        recurring={'interval': interval},
                        metadata={'purpose': 'jpy-plan-change-qa'},
                    )
        yield prices
    finally:
        for row in prices.values():
            stripe.Price.modify(row.id, active=False)
        for pid in products:
            stripe.Product.modify(pid, active=False)


@pytest.fixture
def flow(monkeypatch, sandbox_prices):
    prices = sandbox_prices
    for pid in list(plan_catalog.MANAGEMENT_CURRENCY_PRICES):
        monkeypatch.delitem(plan_catalog.MANAGEMENT_CURRENCY_PRICES, pid)
    for (plan, interval, currency), price in prices.items():
        if currency == 'usd':
            suffix = 'MONTHLY' if interval == 'month' else 'ANNUAL'
            monkeypatch.setenv(f'STRIPE_{plan.value.upper()}_{suffix}_PRICE_ID', price.id)
        else:
            monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES, price.id, plan)
            monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_PRICE_INTERVALS, price.id, interval)
            monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS, price.id, 'legacy')
            monkeypatch.setitem(
                plan_catalog.MANAGEMENT_CURRENCY_PRICES,
                price.id,
                dict(plan_id=plan.value, interval=interval, currency='jpy', price_id=price.id),
            )
    customer = stripe.Customer.create(
        payment_method='pm_card_visa',
        invoice_settings={'default_payment_method': 'pm_card_visa'},
        metadata={'purpose': 'jpy-plan-change-qa'},
    )
    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[{'price': prices[(PlanType.plus, 'month', 'jpy')].id}],
        metadata={'uid': 'synthetic-jpy-qa', 'sub_type': 'plus'},
    )
    stored = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        stripe_subscription_id=subscription.id,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )
    writes = []
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: stored)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: stored)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', lambda uid, data: writes.append(data))
    for owner, name in [
        (payment, 'set_credits_invalidation_signal'),
        (payment, 'clear_trial_paywall_cache'),
        (payment, 'clear_fair_use_on_upgrade'),
        (payment.conversations_db, 'unlock_all_conversations'),
        (payment.memories_db, 'unlock_all_memories'),
        (payment.action_items_db, 'unlock_all_action_items'),
    ]:
        monkeypatch.setattr(owner, name, lambda uid: None)
    monkeypatch.setattr(payment, 'funded_processing_enabled', lambda uid: False)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: 'synthetic-jpy-qa'
    app.dependency_overrides[payment.auth.get_current_user_uid_no_byok_validation] = lambda: 'synthetic-jpy-qa'
    client = TestClient(app)
    client.headers['X-Omi-Billing-Currency'] = '1'
    try:
        yield client, subscription, prices, writes
    finally:
        current = stripe.Subscription.retrieve(subscription.id)
        if current.get('schedule'):
            stripe.SubscriptionSchedule.release(current.schedule)
        stripe.Subscription.delete(subscription.id)
        stripe.Customer.delete(customer.id)


def test_jpy_catalog_to_immediate_plan_change(flow):
    client, sub, prices, writes = flow
    response = client.get('/v1/payments/available-plans', headers={'X-App-Platform': 'ios'})
    assert response.status_code == 200, response.text
    target = prices[(PlanType.unlimited_v2, 'month', 'jpy')].id
    offered = next(row for row in response.json()['plans'] if row['id'] == target)
    assert offered['billing_total'] == '4,800 JPY'
    response = client.post('/v1/payments/upgrade-subscription', json={'price_id': target})
    assert response.status_code == 200, response.text
    current = stripe.Subscription.retrieve(sub.id)
    assert current.currency == 'jpy'
    assert current['items'].data[0].price.id == target
    assert current.latest_invoice and stripe.Invoice.retrieve(current.latest_invoice).status == 'paid'
    assert writes[-1]['plan'] == PlanType.unlimited_v2


def test_jpy_annual_schedule_and_stale_usd_preserve_it(flow):
    client, sub, prices, writes = flow
    target = prices[(PlanType.plus, 'year', 'jpy')].id
    response = client.post('/v1/payments/upgrade-subscription', json={'price_id': target})
    assert response.status_code == 200, response.text
    schedule = stripe.SubscriptionSchedule.retrieve(response.json()['schedule_id'])
    assert schedule.phases[0]['items'][0].price == prices[(PlanType.plus, 'month', 'jpy')].id
    assert schedule.phases[1]['items'][0].price == target
    stale = prices[(PlanType.unlimited_v2, 'month', 'usd')].id
    response = client.post('/v1/payments/upgrade-subscription', json={'price_id': stale})
    assert response.status_code == 409, response.text
    assert stripe.Subscription.retrieve(sub.id).schedule == schedule.id
    assert writes == []


def test_declined_jpy_change_keeps_paid_plan(flow):
    client, sub, prices, writes = flow
    method = stripe.PaymentMethod.attach('pm_card_chargeCustomerFail', customer=sub.customer)
    stripe.Subscription.modify(sub.id, default_payment_method=method.id)
    target = prices[(PlanType.unlimited_v2, 'month', 'jpy')].id
    response = client.post('/v1/payments/upgrade-subscription', json={'price_id': target})
    assert response.status_code == 402, response.text
    current = stripe.Subscription.retrieve(sub.id)
    assert current.status == 'active'
    assert current['items'].data[0].price.id == prices[(PlanType.plus, 'month', 'jpy')].id
    assert writes == []


def test_current_jpy_subscription_reactivates_without_another_subscription(flow):
    client, sub, prices, writes = flow
    stripe.Subscription.modify(sub.id, cancel_at_period_end=True)
    response = client.post(
        '/v1/payments/checkout-session', json={'price_id': prices[(PlanType.plus, 'month', 'jpy')].id}
    )
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'reactivated'
    current = stripe.Subscription.retrieve(sub.id)
    assert current.cancel_at_period_end is False
    assert current['items'].data[0].price.id == prices[(PlanType.plus, 'month', 'jpy')].id
    assert len(stripe.Subscription.list(customer=sub.customer, status='active').data) == 1


def test_one_time_jpy_price_is_not_a_subscription_offer(flow, monkeypatch):
    client, sub, prices, writes = flow
    original = prices[(PlanType.unlimited_v2, 'month', 'jpy')]
    invalid = stripe.Price.create(product=original.product, currency='jpy', unit_amount=4800)
    try:
        monkeypatch.delitem(plan_catalog.MANAGEMENT_CURRENCY_PRICES, original.id)
        monkeypatch.setitem(
            plan_catalog.MANAGEMENT_CURRENCY_PRICES,
            invalid.id,
            dict(price_id=invalid.id, plan_id='unlimited_v2', interval='month', currency='jpy'),
        )
        monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES, invalid.id, PlanType.unlimited_v2)
        monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_PRICE_INTERVALS, invalid.id, 'month')
        monkeypatch.setitem(plan_catalog.RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS, invalid.id, 'legacy')
        catalog = client.get('/v1/payments/available-plans')
        assert catalog.status_code == 200, catalog.text
        assert invalid.id not in [row['id'] for row in catalog.json()['plans']]
        response = client.post('/v1/payments/upgrade-subscription', json={'price_id': invalid.id})
        assert response.status_code == 409, response.text
        assert (
            stripe.Subscription.retrieve(sub.id)['items'].data[0].price.id == prices[(PlanType.plus, 'month', 'jpy')].id
        )
        assert writes == []
    finally:
        stripe.Price.modify(invalid.id, active=False)


def test_invalid_promotion_does_not_reactivate_current_jpy_subscription(flow):
    client, sub, prices, writes = flow
    stripe.Subscription.modify(sub.id, cancel_at_period_end=True)
    response = client.post(
        '/v1/payments/checkout-session',
        json={
            'price_id': prices[(PlanType.plus, 'month', 'jpy')].id,
            'promotion_code': f'OMI-QA-MISSING-{uuid.uuid4().hex}',
        },
    )
    assert response.status_code == 400, response.text
    assert stripe.Subscription.retrieve(sub.id).cancel_at_period_end is True
    assert writes == []
