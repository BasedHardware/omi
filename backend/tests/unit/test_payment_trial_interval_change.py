"""Same-plan interval change during a Stripe trial keeps the trial (#23298, #23317)."""

import time
from unittest.mock import Mock

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.users import PlanType, Subscription, SubscriptionStatus
from routers import payment

MONTH = 'price_unlimited_month_fixture'
YEAR = 'price_unlimited_year_fixture'


def price(pid, amount, interval):
    return stripe.Price.construct_from(
        dict(
            id=pid,
            currency='usd',
            unit_amount=amount,
            active=True,
            livemode=True,
            recurring=dict(interval=interval, interval_count=1),
        ),
        'sk_test_fake',
    )


@pytest.fixture
def case(monkeypatch):
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', MONTH)
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID', YEAR)
    prices = {MONTH: price(MONTH, 2999, 'month'), YEAR: price(YEAR, 26991, 'year')}
    now = int(time.time())
    state = {}
    calls = []

    def set_sub(price_id, status='trialing', trial_end=now + 6 * 86400 + 60, latest_invoice='in_create'):
        state['obj'] = dict(
            id='sub_trial_fixture',
            customer='cus_fixture',
            status=status,
            currency='usd',
            trial_end=trial_end,
            latest_invoice=latest_invoice,
            items=dict(data=[dict(id='si_fixture', price=prices[price_id].to_dict_recursive())]),
            current_period_start=now - 86400,
            current_period_end=trial_end if status == 'trialing' else now + 86400 * 29,
            cancel_at_period_end=False,
            metadata=dict(uid='fixture'),
        )

    # The stored subscription never says trialing: SubscriptionStatus has no such value.
    sub = Subscription(
        plan=PlanType.unlimited_v2,
        status=SubscriptionStatus.active,
        stripe_subscription_id='sub_trial_fixture',
    )
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: sub)
    write = Mock(side_effect=lambda *a: calls.append('write'))
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(
        stripe.Subscription, 'retrieve', lambda sid: stripe.Subscription.construct_from(state['obj'], 'fake')
    )
    monkeypatch.setattr(stripe.Price, 'retrieve', lambda pid: prices[pid])
    schedule = type('Schedule', (), {'id': 'sched_old', 'status': 'active', 'subscription': 'sub_trial_fixture'})()
    monkeypatch.setattr(
        stripe.SubscriptionSchedule,
        'list',
        lambda **kw: calls.append('schedule_list') or type('Rows', (), {'data': [schedule]})(),
    )
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'release', lambda sid: calls.append(f'release:{sid}'))
    updated = {}

    def modify(sid, **kw):
        calls.append('modify')
        new_price = kw['items'][0]['price']
        obj = {**state['obj'], 'items': dict(data=[dict(id='si_fixture', price=prices[new_price].to_dict_recursive())])}
        obj.update(updated)
        return stripe.Subscription.construct_from(obj, 'fake')

    sub_modify = Mock(side_effect=modify)
    monkeypatch.setattr(stripe.Subscription, 'modify', sub_modify)
    schedule_create = Mock(return_value=type('Schedule', (), {'id': 'sched_new'})())
    schedule_modify = Mock()
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'create', schedule_create)
    monkeypatch.setattr(stripe.SubscriptionSchedule, 'modify', schedule_modify)
    promo_list = Mock(return_value=type('Rows', (), {'data': [type('Promo', (), {'id': 'promo_fixture'})()]})())
    monkeypatch.setattr(stripe.PromotionCode, 'list', promo_list)
    for owner, name in [
        (payment, 'set_credits_invalidation_signal'),
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
    return dict(
        client=TestClient(app),
        set_sub=set_sub,
        updated=updated,
        calls=calls,
        write=write,
        modify=sub_modify,
        schedule_create=schedule_create,
        schedule_modify=schedule_modify,
        now=now,
    )


def change(case, price_id, **body):
    return case['client'].post('/v1/payments/upgrade-subscription', json={'price_id': price_id, **body})


@pytest.mark.parametrize('current, target', [(YEAR, MONTH), (MONTH, YEAR)])
def test_trial_interval_change_keeps_trial_and_bills_nothing_now(case, current, target):
    trial_end = case['now'] + 6 * 86400 + 60
    case['set_sub'](current, trial_end=trial_end)

    response = change(case, target)

    assert response.status_code == 200, response.text
    case['schedule_create'].assert_not_called()
    case['schedule_modify'].assert_not_called()
    args, kwargs = case['modify'].call_args
    assert args == ('sub_trial_fixture',)
    assert kwargs['items'] == [{'id': 'si_fixture', 'price': target}]
    assert kwargs['proration_behavior'] == 'none'
    assert kwargs['payment_behavior'] == 'error_if_incomplete'
    assert kwargs['trial_end'] == trial_end
    assert kwargs['idempotency_key'] == f'omi-trial-interval-sub_trial_fixture-in_create-{target}-{trial_end}'
    assert 'discounts' not in kwargs
    # An attached schedule from an earlier change is released before the swap, and Firestore is
    # written only after Stripe accepted it.
    assert case['calls'] == ['schedule_list', 'release:sched_old', 'modify', 'write']
    stored = case['write'].call_args.args[1]
    assert stored['plan'] == PlanType.unlimited_v2
    assert stored['current_period_end'] == trial_end
    body = response.json()
    assert body['schedule_id'] is None
    assert body['days_remaining'] == 6


def test_trial_interval_change_with_promotion_code_passes_discount(case):
    case['set_sub'](YEAR)

    response = change(case, MONTH, promotion_code='SAVE')

    assert response.status_code == 200, response.text
    assert case['modify'].call_args.kwargs['discounts'] == [{'promotion_code': 'promo_fixture'}]
    case['schedule_create'].assert_not_called()


@pytest.mark.parametrize('outcome', [{'status': 'incomplete'}, {'pending_update': {'expires_at': 1}}])
def test_trial_interval_change_left_incomplete_is_refused_and_not_stored(case, outcome):
    case['set_sub'](YEAR)
    case['updated'].update(outcome)

    response = change(case, MONTH)

    assert response.status_code == 402, response.text
    case['write'].assert_not_called()
    case['schedule_create'].assert_not_called()


def test_switching_back_within_a_day_never_replays_the_first_change(case):
    # Stripe replays a reused idempotency key for 24h. annual -> monthly -> annual -> monthly
    # must not reuse the first key, or Stripe returns the old monthly result and leaves the sub
    # on annual while Firestore says monthly. Each swap issues a new latest_invoice.
    keys = []
    for current, target, invoice in [(YEAR, MONTH, 'in_1'), (MONTH, YEAR, 'in_2'), (YEAR, MONTH, 'in_3')]:
        case['set_sub'](current, latest_invoice=invoice)
        assert change(case, target).status_code == 200
        keys.append(case['modify'].call_args.kwargs['idempotency_key'])

    assert len(set(keys)) == 3


@pytest.mark.parametrize('trial_end', [None, 'past'])
def test_paid_interval_change_still_schedules_for_period_end(case, trial_end):
    # Only Stripe's trialing status takes the in-place swap; an ended trial keeps the schedule.
    case['set_sub'](MONTH, status='active', trial_end=case['now'] - 86400 if trial_end else None)

    response = change(case, YEAR)

    assert response.status_code == 200, response.text
    case['modify'].assert_not_called()
    case['schedule_create'].assert_called_once_with(from_subscription='sub_trial_fixture')
    phases = case['schedule_modify'].call_args.kwargs['phases']
    assert [phase['items'][0]['price'] for phase in phases] == [MONTH, YEAR]
    assert response.json()['schedule_id'] == 'sched_new'
    case['write'].assert_not_called()
