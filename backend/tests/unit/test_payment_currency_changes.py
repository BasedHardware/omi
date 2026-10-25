"""Installed-client catalog → consented JPY target → Stripe mutation boundary."""

import time
from unittest.mock import Mock

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.plan_catalog import get_plan_definition
from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment
from utils import billing_currency
from utils.subscription import is_purchasable_price_id

PLUS_MONTH = 'price_1ULq6b1F8wnoWYvwtchjjNqq'
PLUS_YEAR = 'price_1ULq7H1F8wnoWYvwC1poOtd5'
PRO_MONTH = 'price_1ULq501F8wnoWYvwwN56CHzO'
PRO_YEAR = 'price_1ULq5e1F8wnoWYvwQT8XQ4Uw'


def price(pid, amount, interval, currency):
    return stripe.Price.construct_from(
        dict(
            id=pid,
            currency=currency,
            unit_amount=amount,
            active=True,
            livemode=True,
            recurring=dict(interval=interval, interval_count=1),
        ),
        'sk_test_fake',
    )


@pytest.fixture
def case(monkeypatch):
    prices = {}
    for plan, month, year, amount in [
        ('PLUS', PLUS_MONTH, PLUS_YEAR, 1800),
        ('UNLIMITED_V2', PRO_MONTH, PRO_YEAR, 4800),
    ]:
        for interval, jpy, factor in [('month', month, 1), ('year', year, 9)]:
            usd = f'price_{plan.lower()}_{interval}_fixture'
            monkeypatch.setenv(f'STRIPE_{plan}_{"MONTHLY" if interval == "month" else "ANNUAL"}_PRICE_ID', usd)
            prices[usd] = price(usd, 1999 * factor, interval, 'usd')
            prices[jpy] = price(jpy, amount * factor, interval, 'jpy')
    now = int(time.time())
    obj = dict(
        id='sub_jpy_fixture',
        customer='cus_fixture',
        status='active',
        currency='jpy',
        items=dict(data=[dict(id='si_fixture', price=prices[PLUS_MONTH].to_dict_recursive())]),
        current_period_start=now - 86400,
        current_period_end=now + 86400 * 29,
        cancel_at_period_end=False,
        metadata=dict(uid='fixture'),
    )
    sub = Subscription(
        plan=PlanType.plus,
        status=SubscriptionStatus.active,
        stripe_subscription_id=obj['id'],
        current_period_start=obj['current_period_start'],
        current_period_end=obj['current_period_end'],
    )
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: sub)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: sub)
    write = Mock()
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(stripe.Subscription, 'retrieve', lambda sid: stripe.Subscription.construct_from(obj, 'fake'))
    monkeypatch.setattr(stripe.Price, 'retrieve', lambda pid: prices[pid])
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'list', lambda **kw: type('Rows', (), {'data': []})())
    release = Mock()
    monkeypatch.setattr(payment, '_release_attached_schedules', release)
    modified = {**obj, 'items': dict(data=[dict(id='si_fixture', price=prices[PRO_MONTH].to_dict_recursive())])}
    modify = Mock(return_value=stripe.Subscription.construct_from(modified, 'fake'))
    monkeypatch.setattr(stripe.Subscription, 'modify', modify)
    schedule_create = Mock(return_value=type('Schedule', (), {'id': 'sched_fixture'})())
    schedule_modify = Mock()
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'create', schedule_create)
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'modify', schedule_modify)
    for owner, name in [
        (payment, 'set_credits_invalidation_signal'),
        (payment, 'clear_trial_paywall_cache'),
        (payment, 'clear_fair_use_on_upgrade'),
        (payment.conversations_db, 'unlock_all_conversations'),
        (payment.memories_db, 'unlock_all_memories'),
        (payment.action_items_db, 'unlock_all_action_items'),
    ]:
        monkeypatch.setattr(owner, name, Mock())
    monkeypatch.setattr(payment, 'funded_processing_enabled', lambda uid: False)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: 'fixture'
    app.dependency_overrides[payment.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture'
    client = TestClient(app)
    client.headers['X-Omi-Billing-Currency'] = '1'
    return dict(
        client=client,
        prices=prices,
        obj=obj,
        sub=sub,
        write=write,
        release=release,
        modify=modify,
        schedule_create=schedule_create,
        schedule_modify=schedule_modify,
    )


def test_catalog_selects_jpy_and_zero_decimal_totals(case):
    response = case['client'].get('/v1/payments/available-plans', headers={'X-App-Platform': 'ios'})
    assert response.status_code == 200, response.text
    rows = {row['id']: row for row in response.json()['plans']}
    assert set(rows) == {PLUS_MONTH, PLUS_YEAR, PRO_MONTH, PRO_YEAR}
    assert rows[PRO_MONTH]['price_string'] == '4,800 JPY/mo'
    assert rows[PRO_YEAR]['billing_total'] == '43,200 JPY'
    assert rows[PRO_YEAR]['unit_amount'] == 43200
    assert rows[PLUS_MONTH]['is_active'] is True
    assert all(row['currency'] == 'jpy' for row in rows.values())


def test_catalog_then_change_keeps_existing_subscription_and_jpy(case):
    rows = case['client'].get('/v1/payments/available-plans').json()['plans']
    selected = next(row for row in rows if row['id'] == PRO_MONTH)
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': selected['id']})
    assert response.status_code == 200, response.text
    assert case['modify'].call_args.kwargs['items'] == [{'id': 'si_fixture', 'price': PRO_MONTH}]
    assert case['modify'].call_args.kwargs['payment_behavior'] == 'error_if_incomplete'
    assert case['write'].call_args.args[1]['plan'] == PlanType.unlimited_v2


def test_same_tier_annual_schedule_uses_jpy_for_both_phases(case):
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PLUS_YEAR})
    assert response.status_code == 200, response.text
    phases = case['schedule_modify'].call_args.kwargs['phases']
    assert phases[0]['items'][0]['price'] == PLUS_MONTH
    assert phases[1]['items'][0]['price'] == PLUS_YEAR
    case['write'].assert_not_called()


@pytest.mark.parametrize('target', ['price_unlimited_v2_month_fixture', 'price_unknown'])
def test_stale_usd_or_unlisted_price_has_no_billing_writes(case, target):
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': target})
    assert response.status_code in (400, 409), response.text
    for key in ('release', 'modify', 'schedule_create', 'schedule_modify', 'write'):
        case[key].assert_not_called()


def test_jpy_variant_is_not_new_checkout_target(case):
    assert not is_purchasable_price_id(PRO_MONTH)
    response = case['client'].post('/v1/payments/checkout-session', json={'price_id': PRO_MONTH})
    assert response.status_code == 400


@pytest.mark.parametrize(
    'attribute,value',
    [('active', False), ('currency', 'usd'), ('livemode', False), ('unit_amount', None), ('recurring', None)],
)
def test_invalid_jpy_target_hidden_and_rejected_before_schedule_release(case, attribute, value):
    case['prices'][PRO_MONTH][attribute] = value
    rows = case['client'].get('/v1/payments/available-plans').json()['plans']
    assert PRO_MONTH not in [row['id'] for row in rows]
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PRO_MONTH})
    assert response.status_code == 409
    case['release'].assert_not_called()
    case['write'].assert_not_called()


def test_usd_subscriber_cannot_post_retained_jpy_target(case):
    case['obj']['currency'] = 'usd'
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PRO_MONTH})
    assert response.status_code == 409
    case['release'].assert_not_called()


def test_failed_payment_preserves_entitlements(case):
    case['modify'].side_effect = stripe.error.CardError('declined', param=None, code='card_declined')
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PRO_MONTH})
    assert response.status_code == 402
    case['write'].assert_not_called()
    payment.conversations_db.unlock_all_conversations.assert_not_called()


def test_currency_lookup_failure_does_not_offer_usd(case, monkeypatch):
    monkeypatch.setattr(stripe.Subscription, 'retrieve', Mock(side_effect=RuntimeError('unavailable')))
    response = case['client'].get('/v1/payments/available-plans')
    assert response.status_code == 503


def test_catalog_management_bindings_do_not_change_entitlements():
    assert get_plan_definition(PlanType.unlimited_v2)['allocations']['transcription']['limit']['kind'] == 'unlimited'
    assert billing_currency.management_binding(PRO_YEAR) == (PlanType.unlimited_v2, 'year', 'jpy')


def test_older_sheet_cannot_display_unsafe_annual_amounts(case):
    case['client'].headers.pop('X-Omi-Billing-Currency')
    response = case['client'].get('/v1/payments/available-plans')
    assert response.status_code == 409
    assert 'update Omi' in response.json()['detail']


def test_exact_current_jpy_price_can_reactivate_without_new_checkout(case):
    case['obj']['cancel_at_period_end'] = True
    case['sub'].cancel_at_period_end = True
    response = case['client'].post('/v1/payments/checkout-session', json={'price_id': PLUS_MONTH})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'reactivated'
    case['modify'].assert_called_once_with('sub_jpy_fixture', cancel_at_period_end=False)


def test_cancel_pending_jpy_plan_cannot_switch_to_another_tier(case):
    case['obj']['cancel_at_period_end'] = True
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PRO_MONTH})
    assert response.status_code == 409
    case['release'].assert_not_called()
    case['modify'].assert_not_called()


def test_unbound_retained_usd_price_stays_rejected(case):
    response = case['client'].post(
        '/v1/payments/upgrade-subscription', json={'price_id': 'price_1TuIa81F8wnoWYvw0iX0j5M8'}
    )
    assert response.status_code == 400
    case['modify'].assert_not_called()


def test_malformed_subscription_currency_refuses_change(case):
    case['obj']['currency'] = None
    case['obj']['items']['data'][0]['price'].pop('currency')
    response = case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': PRO_MONTH})
    assert response.status_code == 409
    case['release'].assert_not_called()


def test_cancelled_plan_offers_keep_jpy_without_an_active_badge(case):
    case['obj']['cancel_at_period_end'] = True
    case['sub'].cancel_at_period_end = True
    response = case['client'].get('/v1/payments/available-plans')
    assert response.status_code == 200, response.text
    rows = response.json()['plans']
    assert len(rows) == 4
    assert all(row['currency'] == 'jpy' and not row['is_active'] for row in rows)


def test_invalid_promotion_does_not_reactivate_current_jpy_subscription(case, monkeypatch):
    case['obj']['cancel_at_period_end'] = True
    case['sub'].cancel_at_period_end = True
    monkeypatch.setattr(stripe.PromotionCode, 'list', Mock(return_value=Mock(data=[])))
    response = case['client'].post(
        '/v1/payments/checkout-session', json={'price_id': PLUS_MONTH, 'promotion_code': 'INVALID_FIXTURE_CODE'}
    )
    assert response.status_code == 400
    case['modify'].assert_not_called()
    case['write'].assert_not_called()
    assert case['sub'].cancel_at_period_end is True
