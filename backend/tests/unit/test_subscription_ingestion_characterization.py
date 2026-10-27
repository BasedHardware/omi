"""Golden behavior of payment.py at origin/main e52113704226, before extraction.

These assertions intentionally preserve uncomfortable behavior (trialing grants
paid access, past_due loses it, and old same-subscription events overwrite newer
ones). Changing those is a separate product/bug-fix review, not a refactor.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database.legal_holds import DestructiveOperationInProgress
from models.users import PlanLimits, PlanType, Subscription, SubscriptionStatus
from routers import payment
from utils.observability import billing_webhook

STATUSES = ('active', 'trialing', 'past_due', 'unpaid', 'canceled', 'incomplete', 'incomplete_expired', 'paused')
EVENTS = ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted')
PAID_PLANS = (PlanType.plus, PlanType.unlimited_v2, PlanType.unlimited, PlanType.operator, PlanType.architect)
NOW = 1_900_000_000


class Request:
    async def body(self):
        return b'fixture'


@pytest.fixture
def lane(monkeypatch):
    state = SimpleNamespace(
        event=None, current=None, replacement=None, calls=[], error=None, owner=True, stripe_obj=None
    )

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def effect(name):
        return lambda *args, **kwargs: state.calls.append((name, args))

    def write(uid, payload):
        if state.error:
            raise state.error
        state.calls.append(('write', (uid, payload)))
        state.current = Subscription.model_validate(payload)

    async def telemetry(*args, **kwargs):
        state.calls.append(('telemetry', ()))

    async def notify(uid):
        state.calls.append(('notification', (uid,)))

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment.time, 'time', lambda: NOW)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: state.event)
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kwargs: None)
    monkeypatch.setattr(payment, 'get_plan_type_from_price_id', lambda price: PlanType(price.removeprefix('price_')))
    monkeypatch.setattr(payment, 'get_plan_limits', lambda plan: PlanLimits(transcription_seconds=123))
    monkeypatch.setattr(payment, 'get_basic_plan_limits', lambda: PlanLimits(transcription_seconds=7))
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid} if state.owner else None)
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(payment.users_db, 'set_stripe_customer_id', effect('customer'))
    monkeypatch.setattr(payment, 'find_active_paid_subscription_for_user', lambda uid: state.replacement)
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', effect('credits'))
    monkeypatch.setattr(payment, 'clear_trial_paywall_cache', effect('trial_cache'))
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', effect('fair_use'))
    for module, method, name in (
        (payment.conversations_db, 'unlock_all_conversations', 'conversations'),
        (payment.memories_db, 'unlock_all_memories', 'memories'),
        (payment.action_items_db, 'unlock_all_action_items', 'actions'),
    ):
        monkeypatch.setattr(module, method, effect(name))
    monkeypatch.setattr(billing_webhook, 'schedule_billing_webhook_events', telemetry)
    monkeypatch.setattr(payment, 'send_subscription_paid_personalized_notification', notify)
    monkeypatch.setattr(
        payment.stripe.Subscription,
        'retrieve',
        lambda *args: stripe.Subscription.construct_from(state.stripe_obj, 'fixture'),
    )
    monkeypatch.setattr(payment.stripe.Subscription, 'modify', effect('stripe_metadata'))
    monkeypatch.setattr(payment.stripe.Subscription, 'cancel', effect('stripe_cancel'))
    return state


def event(kind, status, plan=PlanType.plus, sub_id='sub-current', created=NOW):
    return {
        'id': 'evt-fixture',
        'type': kind,
        'created': created,
        'data': {
            'object': {
                'id': sub_id,
                'status': status,
                'customer': 'cus-fixture',
                'metadata': {'uid': 'fixture-user'},
                'items': {'data': [{'price': {'id': f'price_{plan.value}', 'currency': 'jpy', 'unit_amount': 4800}}]},
                'current_period_start': NOW - 100,
                'current_period_end': NOW + 100,
                'cancel_at_period_end': True,
            }
        },
    }


def run(lane):
    return asyncio.run(payment.stripe_webhook(Request(), 'fixture-signature'))


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


@pytest.mark.parametrize('kind', EVENTS)
@pytest.mark.parametrize('status', STATUSES)
@pytest.mark.parametrize('plan', PAID_PLANS)
def test_every_lifecycle_status_and_paid_plan_preserves_bytes_and_effect_order(lane, kind, status, plan):
    lane.event = event(kind, status, plan)
    assert run(lane) == {'status': 'success'}
    paid = status in ('active', 'trialing')
    # Portal "cancel immediately" fires canceled while the period is still live;
    # the paid-through grace (FC-early-terminal-strips-paid-period) keeps the paid
    # plan until period end instead of downgrading to Basic on the spot.
    keeps_paid = paid or status == 'canceled'
    expected = Subscription(
        plan=plan if keeps_paid else PlanType.basic,
        status=SubscriptionStatus.active,
        stripe_subscription_id='sub-current',
        current_period_start=NOW - 100,
        current_period_end=NOW + 100,
        cancel_at_period_end=keeps_paid,
        limits=PlanLimits(transcription_seconds=123 if keeps_paid else 7),
    )
    # Includes every model field and default, especially current_price_id=None.
    assert wire(lane.current.model_dump()) == wire(expected.model_dump())
    assert [name for name, _ in lane.calls] == (
        ['customer', 'conversations', 'memories', 'actions', 'write', 'telemetry', 'credits', 'trial_cache', 'fair_use']
        if keeps_paid
        else ['write', 'telemetry', 'credits', 'trial_cache']
    )


@pytest.mark.parametrize('kind', EVENTS)
@pytest.mark.parametrize('period_end', [None, 0, NOW - 1, NOW, NOW + 1])
def test_stale_different_subscription_only_shielded_by_valid_stored_paid_period(lane, kind, period_end):
    lane.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-new', current_period_end=period_end)
    before = lane.current.model_dump_json()
    lane.event = event(kind, 'canceled', sub_id='sub-old')
    assert run(lane) == {'status': 'success'}
    if period_end and period_end >= NOW:
        assert lane.current.model_dump_json() == before
        assert lane.calls == []
    else:
        assert lane.current.plan == PlanType.basic


def test_adoption_preserves_replacement_bytes_and_does_not_copy_stale_customer(lane):
    lane.replacement = Subscription(
        plan=PlanType.operator, stripe_subscription_id='sub-new', current_price_id='price-old'
    )
    lane.event = event(EVENTS[2], 'canceled', sub_id='sub-old')
    assert run(lane) == {'status': 'success'}
    assert lane.current.model_dump_json() == lane.replacement.model_dump_json()
    assert [name for name, _ in lane.calls] == [
        'conversations',
        'memories',
        'actions',
        'write',
        'credits',
        'trial_cache',
        'fair_use',
    ]


def test_out_of_order_same_subscription_is_currently_last_delivery_wins(lane):
    lane.event = event(EVENTS[1], 'active', created=NOW)
    run(lane)
    assert lane.current.plan == PlanType.plus
    lane.event = event(EVENTS[0], 'incomplete', created=NOW - 50)
    run(lane)
    assert lane.current.plan == PlanType.basic


def test_retry_currently_repeats_writes_and_unlocks(lane):
    lane.event = event(EVENTS[1], 'active')
    run(lane)
    run(lane)
    assert [name for name, _ in lane.calls].count('write') == 2
    assert [name for name, _ in lane.calls].count('conversations') == 2


@pytest.mark.parametrize('status', ['active', 'trialing'])
def test_unknown_price_keeps_current_state(lane, status):
    lane.current = Subscription(plan=PlanType.operator)
    lane.event = event(EVENTS[1], status)
    lane.event['data']['object']['items']['data'][0]['price']['id'] = 'price_unknown'
    assert run(lane) == {'status': 'success'}
    assert lane.current.plan == PlanType.operator
    assert lane.calls == []


def test_write_failure_propagates_after_customer_and_unlock_partial_effects(lane):
    lane.event = event(EVENTS[1], 'active')
    lane.error = RuntimeError('fixture write failure')
    with pytest.raises(RuntimeError, match='fixture write failure'):
        run(lane)
    assert [name for name, _ in lane.calls] == ['customer', 'conversations', 'memories', 'actions']


@pytest.mark.parametrize('kind', ['invoice.payment_failed', 'charge.refunded', 'charge.dispute.created', 'unknown'])
def test_unhandled_event_has_no_entitlement_effect(lane, kind):
    lane.event = event(kind, 'active')
    assert run(lane) == {'status': 'success'}
    assert lane.calls == []


@pytest.mark.parametrize(
    'kind', ['subscription_schedule.completed', 'subscription_schedule.updated', 'subscription_schedule.canceled']
)
@pytest.mark.parametrize('status', STATUSES)
@pytest.mark.parametrize('schedule_status', ['active', 'completed', 'canceled'])
def test_schedule_event_status_matrix(lane, kind, status, schedule_status):
    lane.stripe_obj = event(EVENTS[1], status)['data']['object']
    lane.event = {
        'type': kind,
        'data': {
            'object': {
                'id': 'sched-fixture',
                'metadata': {'uid': 'fixture-user'},
                'status': schedule_status,
                'subscription': 'sub-current',
            }
        },
    }
    assert run(lane) == {'status': 'success'}
    if schedule_status == 'active':
        assert lane.calls == []
        return
    assert lane.current.plan == (PlanType.plus if status in ('active', 'trialing') else PlanType.basic)
    assert (
        lane.current.cancel_at_period_end is True
        if schedule_status == 'canceled'
        else lane.current.cancel_at_period_end == (status in ('active', 'trialing'))
    )
    assert [name for name, _ in lane.calls] == ['write', 'credits', 'trial_cache'] + (
        ['fair_use'] if schedule_status == 'completed' and status in ('active', 'trialing') else []
    )


def test_schedule_write_failure_is_currently_acknowledged(lane):
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'type': 'subscription_schedule.completed',
        'data': {'object': {'metadata': {'uid': 'fixture-user'}, 'status': 'completed', 'subscription': 'sub-current'}},
    }
    lane.error = RuntimeError('fixture write failure')
    assert run(lane) == {'status': 'success'}
    assert lane.calls == []


@pytest.mark.parametrize(
    'stored_plan,same_id,duplicate',
    [(PlanType.basic, True, False), (PlanType.plus, True, True), (PlanType.plus, False, False)],
)
def test_checkout_created_before_completed_and_duplicate_paths(lane, stored_plan, same_id, duplicate):
    lane.current = Subscription(plan=stored_plan, stripe_subscription_id='sub-current' if same_id else 'sub-old')
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'type': 'checkout.session.completed',
        'data': {
            'object': stripe.checkout.Session.construct_from(
                {
                    'id': 'cs-fixture',
                    'client_reference_id': 'fixture-user',
                    'metadata': {},
                    'customer': 'cus-fixture',
                    'subscription': 'sub-current',
                },
                'fixture',
            )
        },
    }
    result = run(lane)
    if duplicate:
        assert result == {'status': 'success', 'message': 'Subscription already processed.'}
        assert [name for name, _ in lane.calls] == ['conversations', 'memories', 'actions', 'fair_use']
    else:
        assert lane.current.plan == PlanType.plus
        assert [name for name, _ in lane.calls] == (['stripe_cancel'] if stored_plan == PlanType.plus else []) + [
            'customer',
            'write',
            'credits',
            'trial_cache',
            'conversations',
            'memories',
            'actions',
            'fair_use',
            'stripe_metadata',
            'notification',
        ]


def _checkout_event():
    return {
        'type': 'checkout.session.completed',
        'data': {
            'object': stripe.checkout.Session.construct_from(
                {
                    'id': 'cs-fixture',
                    'client_reference_id': 'fixture-user',
                    'metadata': {},
                    'customer': 'cus-fixture',
                    'subscription': 'sub-current',
                },
                'fixture',
            )
        },
    }


def _post_webhook():
    app = FastAPI()
    app.include_router(payment.router)
    client = TestClient(app, raise_server_exceptions=False)
    return client.post('/v1/stripe/webhook', content=b'{}', headers={'stripe-signature': 'fixture'})


def _call_names(lane):
    return [name for name, _ in lane.calls]


def test_checkout_session_completed_normal_path_unchanged(lane):
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = _checkout_event()
    response = _post_webhook()
    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    assert lane.current.plan == PlanType.plus
    assert _call_names(lane) == [
        'customer',
        'write',
        'credits',
        'trial_cache',
        'conversations',
        'memories',
        'actions',
        'fair_use',
        'stripe_metadata',
        'notification',
    ]


@pytest.mark.parametrize('fence_type', ['deletion_gate', 'data_plane_read'])
def test_checkout_session_completed_retries_unlock_after_fence_clears(lane, monkeypatch, fence_type):
    blocked = {'on': True}

    def conversations(uid):
        lane.calls.append(('conversations', (uid,)))
        if blocked['on']:
            if fence_type == 'deletion_gate':
                raise DestructiveOperationInProgress('live deletion marker')
            raise RuntimeError('data-plane read failed')

    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', conversations)
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = _checkout_event()

    first = _post_webhook()
    assert first.status_code == 500
    assert 'success' not in first.text
    assert lane.current.plan == PlanType.plus
    assert lane.current.stripe_subscription_id == 'sub-current'
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('conversations') == 1
    assert 'memories' not in _call_names(lane)

    # Stripe retries while the gate is still closed. duplicate_checkout must not ack.
    second = _post_webhook()
    assert second.status_code == 500
    assert 'success' not in second.text
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('conversations') == 2
    assert 'memories' not in _call_names(lane)

    assert 'fair_use' not in _call_names(lane)

    blocked['on'] = False
    third = _post_webhook()
    assert third.status_code == 200
    assert third.json()['status'] == 'success'
    assert third.json().get('message', 'Subscription already processed.') == 'Subscription already processed.'
    assert 'stripe_metadata' not in _call_names(lane)
    assert 'notification' not in _call_names(lane)
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('conversations') == 3
    assert 'memories' in _call_names(lane)
    assert 'actions' in _call_names(lane)
    assert _call_names(lane).count('fair_use') == 1
    assert _call_names(lane).index('fair_use') > _call_names(lane).index('actions')


def _arm_cross_plan_upgrade(lane, monkeypatch, current_price='price_plus'):
    prices = {'current': current_price}

    def stripe_sub(price_id):
        return {
            'id': 'sub-upgrade',
            'status': 'active',
            'cancel_at_period_end': False,
            'current_period_start': NOW - 100,
            'current_period_end': NOW + 100,
            'items': {'data': [{'id': 'si_1', 'price': {'id': price_id, 'currency': 'usd', 'unit_amount': 1000}}]},
        }

    def retrieve(sub_id):
        return stripe.Subscription.construct_from(stripe_sub(prices['current']), 'fixture')

    def modify(sub_id, **params):
        lane.calls.append(('modify', (sub_id,)))
        prices['current'] = params['items'][0]['price']
        return stripe.Subscription.construct_from(stripe_sub(prices['current']), 'fixture')

    lane.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-upgrade')
    monkeypatch.setattr(payment, 'is_purchasable_price_id', lambda price_id: True)
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', retrieve)
    monkeypatch.setattr(payment.stripe.Subscription, 'modify', modify)
    monkeypatch.setattr(
        payment.stripe.Price,
        'retrieve',
        lambda price_id: SimpleNamespace(currency='usd', recurring=SimpleNamespace(interval='month')),
    )
    monkeypatch.setattr(payment, '_release_attached_schedules', lambda stripe_sub: None)


def test_upgrade_subscription_normal_path_unchanged(lane, monkeypatch):
    _arm_cross_plan_upgrade(lane, monkeypatch)
    result = payment.upgrade_subscription_endpoint(
        payment.UpgradeSubscriptionRequest(price_id='price_unlimited_v2'), uid='fixture-user'
    )
    assert result['status'] == 'success'
    assert 'upgraded' in result['message'].lower()
    assert lane.current.plan == PlanType.unlimited_v2
    assert _call_names(lane) == [
        'modify',
        'write',
        'credits',
        'trial_cache',
        'conversations',
        'memories',
        'actions',
        'fair_use',
    ]


@pytest.mark.parametrize('fence_type', ['deletion_gate', 'data_plane_read'])
def test_upgrade_subscription_retries_unlock_after_fence_clears(lane, monkeypatch, fence_type):
    blocked = {'on': True}

    def conversations(uid):
        lane.calls.append(('conversations', (uid,)))
        if blocked['on']:
            if fence_type == 'deletion_gate':
                raise DestructiveOperationInProgress('live deletion marker')
            raise RuntimeError('data-plane read failed')

    _arm_cross_plan_upgrade(lane, monkeypatch)
    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', conversations)
    monkeypatch.setattr(payment, 'has_recoverable_locked_content', lambda uid: True)
    request = payment.UpgradeSubscriptionRequest(price_id='price_unlimited_v2')

    with pytest.raises(HTTPException) as first:
        payment.upgrade_subscription_endpoint(request, uid='fixture-user')
    assert first.value.status_code == 500
    assert lane.current.plan == PlanType.unlimited_v2
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('modify') == 1
    assert 'memories' not in _call_names(lane)

    with pytest.raises(HTTPException) as second:
        payment.upgrade_subscription_endpoint(request, uid='fixture-user')
    assert second.value.status_code == 500
    assert 'already subscribed' not in str(second.value.detail)
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('modify') == 1
    assert _call_names(lane).count('conversations') == 2
    assert 'memories' not in _call_names(lane)
    assert 'fair_use' not in _call_names(lane)

    blocked['on'] = False
    with pytest.raises(HTTPException) as third:
        payment.upgrade_subscription_endpoint(request, uid='fixture-user')
    assert third.value.status_code == 400
    assert 'already subscribed' in third.value.detail
    assert _call_names(lane).count('write') == 1
    assert _call_names(lane).count('modify') == 1
    assert _call_names(lane).count('conversations') == 3
    assert 'memories' in _call_names(lane)
    assert 'actions' in _call_names(lane)
    assert _call_names(lane).count('fair_use') == 1
    assert _call_names(lane).index('fair_use') > _call_names(lane).index('actions')


_ALREADY_SUBSCRIBED = "You are already subscribed to this plan. Please select a different plan to upgrade or downgrade."


def test_already_subscribed_replays_unlock_only_when_locked_content_remains(lane, monkeypatch):
    _arm_cross_plan_upgrade(lane, monkeypatch, current_price='price_unlimited_v2')
    locked = {'on': False}
    monkeypatch.setattr(payment, 'has_recoverable_locked_content', lambda uid: locked['on'])
    request = payment.UpgradeSubscriptionRequest(price_id='price_unlimited_v2')

    with pytest.raises(HTTPException) as first:
        payment.upgrade_subscription_endpoint(request, uid='fixture-user')
    assert first.value.status_code == 400
    assert first.value.detail == _ALREADY_SUBSCRIBED
    assert _call_names(lane) == ['fair_use']

    locked['on'] = True
    lane.calls.clear()
    with pytest.raises(HTTPException) as second:
        payment.upgrade_subscription_endpoint(request, uid='fixture-user')
    assert second.value.status_code == 400
    assert second.value.detail == _ALREADY_SUBSCRIBED
    assert _call_names(lane) == ['conversations', 'memories', 'actions', 'fair_use']


def test_checkout_duplicate_retry_does_not_ack_until_fair_use_clears(lane, monkeypatch):
    blocked = {'unlock': True, 'fair_use': True}

    def conversations(uid):
        lane.calls.append(('conversations', (uid,)))
        if blocked['unlock']:
            raise DestructiveOperationInProgress('live deletion marker')

    def fair_use(uid):
        lane.calls.append(('fair_use', (uid,)))
        if blocked['fair_use']:
            raise RuntimeError('fair-use clear failed')

    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', conversations)
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', fair_use)
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = _checkout_event()

    first = _post_webhook()
    assert first.status_code == 500
    assert 'success' not in first.text
    assert 'fair_use' not in _call_names(lane)

    blocked['unlock'] = False
    second = _post_webhook()
    assert second.status_code == 500
    assert 'success' not in second.text
    assert _call_names(lane).count('fair_use') == 1
    assert 'memories' in _call_names(lane)
    assert 'actions' in _call_names(lane)

    blocked['fair_use'] = False
    third = _post_webhook()
    assert third.status_code == 200
    assert third.json()['status'] == 'success'
    assert third.json().get('message', 'Subscription already processed.') == 'Subscription already processed.'
    assert 'stripe_metadata' not in _call_names(lane)
    assert _call_names(lane).count('fair_use') == 2
    assert _call_names(lane).count('write') == 1


def test_stale_guard_decision_is_not_rechecked_after_stripe_lookup(lane, monkeypatch):
    # origin/main checks preservation once, before IO. A clock rollback during
    # lookup must not turn a previously failed preservation check into success.
    lane.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-new', current_period_end=NOW)
    lane.event = event(EVENTS[2], 'canceled', sub_id='sub-old')
    clock = iter((NOW + 1, NOW - 1))
    monkeypatch.setattr(payment.time, 'time', lambda: next(clock, NOW - 1))
    assert run(lane) == {'status': 'success'}
    assert lane.current.plan == PlanType.basic


@pytest.mark.parametrize('status', ['active', 'trialing'])
def test_active_snapshot_preserves_false_cancel_flag(lane, status):
    lane.event = event(EVENTS[1], status)
    lane.event['data']['object']['cancel_at_period_end'] = False
    run(lane)
    assert lane.current.cancel_at_period_end is False


@pytest.mark.parametrize('schedule_status', ['completed', 'canceled'])
def test_schedule_currently_overwrites_different_valid_paid_subscription(lane, schedule_status):
    lane.current = Subscription(plan=PlanType.operator, stripe_subscription_id='sub-new', current_period_end=NOW + 100)
    lane.stripe_obj = event(EVENTS[1], 'canceled', sub_id='sub-old')['data']['object']
    lane.event = {
        'type': 'subscription_schedule.' + schedule_status,
        'data': {
            'object': {
                'metadata': {'uid': 'fixture-user'},
                'status': schedule_status,
                'subscription': 'sub-old',
            }
        },
    }
    run(lane)
    assert lane.current.plan == PlanType.basic
    assert lane.current.stripe_subscription_id == 'sub-old'


def test_checkout_cancel_failure_currently_still_activates(lane, monkeypatch):
    lane.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-old')
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'type': 'checkout.session.completed',
        'data': {
            'object': stripe.checkout.Session.construct_from(
                {
                    'id': 'cs-fixture',
                    'client_reference_id': 'fixture-user',
                    'metadata': {},
                    'customer': 'cus-fixture',
                    'subscription': 'sub-current',
                },
                'fixture',
            )
        },
    }

    def fail(*args):
        raise RuntimeError('fixture cancellation failed')

    monkeypatch.setattr(payment.stripe.Subscription, 'cancel', fail)
    run(lane)
    assert lane.current.plan == PlanType.plus
    assert lane.current.stripe_subscription_id == 'sub-current'


def test_missing_profile_currently_does_not_block_subscription_mutation(lane):
    lane.owner = False
    lane.event = event(EVENTS[1], 'active')
    run(lane)
    assert lane.current.plan == PlanType.plus
    assert 'telemetry' not in [name for name, _ in lane.calls]


@pytest.mark.parametrize('kind', ['invoice.paid', 'invoice.payment_succeeded'])
def test_invoice_only_renews_creator_app(lane, monkeypatch, kind):
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.stripe_obj['metadata']['app_id'] = 'creator-fixture'
    lane.event = {'type': kind, 'data': {'object': {'subscription': 'sub-current'}}}
    monkeypatch.setattr(payment, 'paid_app', lambda *args: lane.calls.append(('paid_app', args)))
    run(lane)
    assert [name for name, _ in lane.calls] == ['paid_app']
    assert lane.current is None


def test_invalid_signature_is_400_before_any_effect(lane, monkeypatch):
    from fastapi import HTTPException

    def invalid(*args):
        raise stripe.error.SignatureVerificationError('fixture invalid signature', 'fixture')

    monkeypatch.setattr(payment.stripe_utils, 'parse_event', invalid)
    with pytest.raises(HTTPException) as error:
        run(lane)
    assert error.value.status_code == 400
    assert lane.calls == []


def test_lifecycle_observation_precedes_entitlement_effects(lane, monkeypatch):
    lane.event = event(EVENTS[1], 'active')
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kw: lane.calls.append(('observation', ())))
    run(lane)
    assert [name for name, _ in lane.calls][:2] == ['observation', 'customer']


@pytest.mark.parametrize('ledger_enabled', [False, True])
@pytest.mark.parametrize('stored_plan', [PlanType.basic, PlanType.plus])
def test_unresolved_checkout_preserves_cache_and_valid_stored_plan_effects(
    lane, monkeypatch, ledger_enabled, stored_plan
):
    """#21372: retry admission must follow cache invalidation and valid-paid unlocks."""
    lane.current = Subscription(plan=stored_plan, current_period_end=NOW + 100)
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = _checkout_event()
    monkeypatch.setattr(payment, '_update_subscription_from_session', lambda uid, session: False)
    monkeypatch.setattr(payment, 'webhook_ledger_enabled', lambda: ledger_enabled)
    result = asyncio.run(payment._handle_stripe_event(lane.event))
    expected = ['credits', 'trial_cache']
    if stored_plan == PlanType.plus:
        expected += ['conversations', 'memories', 'actions', 'fair_use']
    assert _call_names(lane)[: len(expected)] == expected
    assert 'write' not in _call_names(lane)
    assert lane.current.plan == stored_plan
    assert isinstance(result, payment.RetryableBillingSkip) == ledger_enabled
    if ledger_enabled:
        assert _call_names(lane) == expected
