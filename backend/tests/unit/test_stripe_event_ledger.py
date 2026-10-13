"""Firestore ordering/lease receipts and real async wrapper failure boundaries."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database import stripe_event_ledger as ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import billing_flags, stripe_webhook_ledger as delivery
from routers import payment
from tests.unit.test_subscription_ingestion_characterization import lane, event as lifecycle_event, run as run_lifecycle

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def event(event_id='evt-one', created=100, kind='customer.subscription.updated'):
    return {
        'id': event_id,
        'created': created,
        'type': kind,
        'data': {'object': {'id': 'sub-one', 'subscription': 'sub-one'}},
    }


def receipt(db):
    return next(value for path, value in db.rows.items() if path[0] == ledger.EVENT_COLLECTION)


def test_claim_complete_duplicate_and_minimal_receipt_use_strict_transactions():
    db = StrictFirestore()
    payload = event()
    assert ledger.claim_event(payload, 'owner', now=NOW, client=db).outcome == 'claimed'
    assert ledger.claim_event(payload, 'other', now=NOW, client=db).outcome == 'busy'
    assert ledger.finish_event(payload, 'owner', succeeded=True, now=NOW, client=db) is False
    assert ledger.claim_event(payload, 'other', now=NOW, client=db).outcome == 'duplicate'
    stored = receipt(db)
    assert stored['outcome'] == 'acknowledged'
    assert stored['expires_at'] == NOW + timedelta(days=90)
    assert stored['event_type'] == payload['type']
    assert stored['event_created'] == 100
    assert stored['subscription_id'] == 'sub-one'
    assert not {'payload', 'uid', 'customer', 'signature', 'error'}.intersection(stored)
    assert sum(len(t.sets) + len(t.updates) for t in db.transactions) == 3


def test_failure_releases_lease_and_old_owner_cannot_complete_new_claim():
    db = StrictFirestore()
    payload = event()
    ledger.claim_event(payload, 'owner', now=NOW, client=db)
    ledger.finish_event(payload, 'owner', succeeded=False, now=NOW, client=db)
    assert ledger.claim_event(payload, 'retry', now=NOW, client=db).outcome == 'claimed'
    assert receipt(db)['attempt'] == 2
    with pytest.raises(RuntimeError, match='ownership lost'):
        ledger.finish_event(payload, 'owner', succeeded=True, now=NOW, client=db)
    assert receipt(db)['token'] == 'retry'


def test_crash_lease_expiry_and_retention_expiry_reallow_processing():
    db = StrictFirestore()
    payload = event()
    ledger.claim_event(payload, 'crashed', now=NOW, client=db)
    expired = NOW + timedelta(seconds=ledger.LEASE_SECONDS)
    assert ledger.claim_event(payload, 'retry', now=expired, client=db).outcome == 'claimed'
    ledger.finish_event(payload, 'retry', succeeded=True, now=expired, client=db)
    assert ledger.claim_event(payload, 'later', now=expired + timedelta(days=90), client=db).outcome == 'claimed'


def test_old_event_detected_on_claim_and_on_late_completion_without_suppression():
    db = StrictFirestore()
    old, new = event('evt-old', 100), event('evt-new', 200)
    assert ledger.claim_event(old, 'old', now=NOW, client=db).out_of_order is False
    ledger.claim_event(new, 'new', now=NOW, client=db)
    ledger.finish_event(new, 'new', succeeded=True, now=NOW, client=db)
    assert ledger.finish_event(old, 'old', succeeded=True, now=NOW, client=db) is True
    assert ledger.claim_event(event('evt-even-older', 50), 'older', now=NOW, client=db).out_of_order is True
    order = next(value for path, value in db.rows.items() if path[0] == ledger.ORDER_COLLECTION)
    assert order['latest_created'] == 200


@pytest.mark.parametrize(
    'bad', [{'id': ''}, {'id': 'evt-bad', 'created': 'not-time', 'type': 'fixture', 'data': {'object': {}}}]
)
def test_malformed_receipt_metadata_fails_before_writes(bad):
    db = StrictFirestore()
    with pytest.raises(ValueError):
        ledger.claim_event(bad, 'owner', now=NOW, client=db)
    assert db.rows == {}


@pytest.fixture
def dispatch(monkeypatch):
    state = SimpleNamespace(
        claim='claimed', claim_error=False, finish_error=False, handler_error=False, calls=[], outcomes=[]
    )
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(delivery, 'record_outcome', state.outcomes.append)

    def claim(*args, **kwargs):
        state.calls.append('claim')
        if state.claim_error:
            raise RuntimeError('fixture receipt failure')
        return ledger.Claim(state.claim, 'token')

    def finish(*args, **kwargs):
        state.calls.append(('finish', kwargs['succeeded']))
        if state.finish_error:
            raise RuntimeError('fixture completion failure')
        return True

    monkeypatch.setattr(ledger, 'claim_event', claim)
    monkeypatch.setattr(ledger, 'finish_event', finish)
    monkeypatch.setattr(ledger, 'observe_event', lambda *args: state.calls.append('observe'))

    async def run_db(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def handler():
        state.calls.append('handler')
        if state.handler_error:
            raise RuntimeError('fixture handler failure')
        return {'status': 'success'}

    state.run = lambda payload=None: asyncio.run(delivery.dispatch_with_ledger(payload or event(), handler, run_db))
    return state


@pytest.mark.parametrize('raw', ['', 'false', '0', 'garbage'])
def test_flag_is_off_by_default_and_for_invalid_values(dispatch, monkeypatch, raw):
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', raw)
    assert billing_flags.webhook_ledger_enabled() is False
    assert dispatch.run() == {'status': 'success'}
    assert dispatch.calls == ['handler']


@pytest.mark.parametrize('claim,status', [('duplicate', 200), ('busy', 503)])
def test_duplicate_is_noop_and_inflight_is_retryable(dispatch, claim, status):
    dispatch.claim = claim
    if status == 200:
        assert dispatch.run() == {'status': 'success'}
    else:
        with pytest.raises(HTTPException) as error:
            dispatch.run()
        assert error.value.status_code == 503
    assert dispatch.calls == ['claim']


def test_claim_error_prevents_any_handler_effect(dispatch):
    dispatch.claim_error = True
    with pytest.raises(HTTPException) as error:
        dispatch.run()
    assert error.value.status_code == 503
    assert dispatch.calls == ['claim']


def test_handler_failure_is_not_marked_success(dispatch):
    dispatch.handler_error = True
    with pytest.raises(RuntimeError, match='fixture handler failure'):
        dispatch.run()
    assert dispatch.calls == ['claim', 'handler', ('finish', False)]


def test_completion_failure_requires_retry_after_handler_effects(dispatch):
    dispatch.finish_error = True
    with pytest.raises(HTTPException) as error:
        dispatch.run()
    assert error.value.status_code == 503
    assert dispatch.calls == ['claim', 'handler', ('finish', True)]


def test_success_records_out_of_order_as_observation_not_policy(dispatch):
    assert dispatch.run() == {'status': 'success'}
    assert dispatch.outcomes == ['claimed', 'acknowledged', 'out_of_order']


def test_swallowed_error_handlers_are_observed_but_never_suppressed(dispatch):
    dispatch.run(event(kind='invoice.paid'))
    dispatch.run(event(kind='invoice.paid'))
    assert dispatch.calls == ['handler', 'observe', 'handler', 'observe']


def test_auxiliary_observation_failure_does_not_change_handler_response(dispatch, monkeypatch):
    def fail(*args):
        raise RuntimeError('fixture observation unavailable')

    monkeypatch.setattr(ledger, 'observe_event', fail)
    assert dispatch.run(event(kind='invoice.paid')) == {'status': 'success'}
    assert dispatch.outcomes == ['unprotected', 'observe_error']


def test_creator_app_checkout_keeps_its_separate_legacy_delivery_semantics(dispatch):
    payload = event(kind='checkout.session.completed')
    payload['data']['object']['metadata'] = {'app_id': 'fixture-creator-app'}
    assert dispatch.run(payload) == {'status': 'success'}
    assert dispatch.calls == ['handler', 'observe']


def test_actual_verified_webhook_enters_the_dispatch_boundary(monkeypatch):
    calls = []
    payload = event(kind='ignored.fixture')
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: payload)

    async def dispatcher(event, handler, run_db):
        calls.append(event['id'])
        return await handler()

    monkeypatch.setattr(payment, 'dispatch_with_ledger', dispatcher)

    class Request:
        async def body(self):
            return b'fixture'

    assert asyncio.run(payment.stripe_webhook(Request(), 'fixture')) == {'status': 'success'}
    assert calls == ['evt-one']


def test_absent_flag_does_not_touch_ledger(dispatch, monkeypatch):
    monkeypatch.delenv('BILLING_WEBHOOK_LEDGER_ENABLED', raising=False)
    dispatch.run()
    assert dispatch.calls == ['handler']
    assert dispatch.outcomes == []


def test_slow_claim_returns_retryable_error_without_running_handler(monkeypatch):
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(delivery, 'LEDGER_RPC_WAIT_SECONDS', 0.001)
    effects = []

    async def slow_db(*args, **kwargs):
        await asyncio.sleep(0.1)

    async def handler():
        effects.append('handler')
        return {'status': 'success'}

    with pytest.raises(HTTPException) as error:
        asyncio.run(delivery.dispatch_with_ledger(event(), handler, slow_db))
    assert error.value.status_code == 503
    assert effects == []


def test_ledger_metric_outcomes_are_closed_and_preinitialized():
    from utils.observability import billing_ledger as metrics

    for outcome in metrics.OUTCOMES:
        assert metrics.LEDGER.labels(outcome=outcome)._value.get() >= 0
    with pytest.raises(ValueError):
        metrics.record_outcome('evt-account-sensitive-value')


def test_real_webhook_duplicate_does_not_repeat_any_entitlement_effect(lane, monkeypatch):
    db = StrictFirestore()
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.event = lifecycle_event('customer.subscription.updated', 'active')
    assert run_lifecycle(lane) == {'status': 'success'}
    first_effects = list(lane.calls)
    first_state = lane.current.model_dump_json()
    assert run_lifecycle(lane) == {'status': 'success'}
    assert lane.calls == first_effects
    assert lane.current.model_dump_json() == first_state
    assert receipt(db)['outcome'] == 'acknowledged'


def test_real_webhook_failed_write_remains_retryable(lane, monkeypatch):
    db = StrictFirestore()
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.event = lifecycle_event('customer.subscription.updated', 'active')
    lane.error = RuntimeError('fixture write failure')
    with pytest.raises(RuntimeError, match='fixture write failure'):
        run_lifecycle(lane)
    assert receipt(db)['outcome'] == 'failed'
    lane.error = None
    assert run_lifecycle(lane) == {'status': 'success'}
    assert receipt(db)['outcome'] == 'acknowledged'
    assert receipt(db)['attempt'] == 2


@pytest.mark.parametrize(
    'kind',
    [
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
        'checkout.session.completed',
    ],
)
def test_real_webhook_unknown_price_is_200_and_same_id_reenters(lane, monkeypatch, kind):
    db = StrictFirestore()
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.event = lifecycle_event(kind, 'active')
    obj = lane.event['data']['object']
    obj['items']['data'][0]['price']['id'] = 'price_unknown'
    if kind == 'checkout.session.completed':
        import stripe

        lane.stripe_obj = obj
        lane.event['data']['object'] = stripe.checkout.Session.construct_from(
            {
                'id': 'cs-fixture',
                'client_reference_id': 'fixture-user',
                'customer': 'cus-fixture',
                'subscription': 'sub-current',
                'metadata': {},
            },
            'fixture',
        )
    builds = []
    build = payment._build_subscription_from_stripe_object

    def tracking(obj):
        builds.append(obj['id'])
        return build(obj)

    monkeypatch.setattr(payment, '_build_subscription_from_stripe_object', tracking)
    assert run_lifecycle(lane) == {'status': 'success'}
    assert not any(name == 'write' for name, _ in lane.calls)
    assert receipt(db)['outcome'] == 'failed'
    assert run_lifecycle(lane) == {'status': 'success'}
    assert len(builds) == 2
    assert receipt(db)['attempt'] == 2
    obj['items']['data'][0]['price']['id'] = 'price_plus'
    assert run_lifecycle(lane) == {'status': 'success'}
    assert receipt(db)['outcome'] == 'acknowledged'
    assert sum(name == 'write' for name, _ in lane.calls) == 1
    assert run_lifecycle(lane) == {'status': 'success'}
    assert len(builds) == 3


def test_real_webhook_uncommitted_finish_replays_after_lease(lane, monkeypatch):
    db = StrictFirestore()
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    now = [NOW]
    claim, finish = ledger.claim_event, ledger.finish_event
    monkeypatch.setattr(ledger, 'claim_event', lambda e, t: claim(e, t, now=now[0], client=db))

    def unavailable(*args, **kwargs):
        raise RuntimeError('fixture finish did not commit')

    monkeypatch.setattr(ledger, 'finish_event', unavailable)
    lane.event = lifecycle_event('customer.subscription.updated', 'active')
    with pytest.raises(HTTPException) as error:
        run_lifecycle(lane)
    assert error.value.status_code == 503
    assert receipt(db)['outcome'] == 'processing'
    assert sum(name == 'write' for name, _ in lane.calls) == 1
    with pytest.raises(HTTPException):
        run_lifecycle(lane)
    assert sum(name == 'write' for name, _ in lane.calls) == 1
    now[0] += timedelta(seconds=ledger.LEASE_SECONDS)
    monkeypatch.setattr(ledger, 'finish_event', lambda e, t, **kw: finish(e, t, now=now[0], client=db, **kw))
    assert run_lifecycle(lane) == {'status': 'success'}
    assert sum(name == 'write' for name, _ in lane.calls) == 2
    assert receipt(db)['outcome'] == 'acknowledged'
    assert run_lifecycle(lane) == {'status': 'success'}
    assert sum(name == 'write' for name, _ in lane.calls) == 2


def test_failed_newer_claim_does_not_advance_success_order():
    db = StrictFirestore()
    new = event('evt-new', 200)
    ledger.claim_event(new, 'new', now=NOW, client=db)
    ledger.finish_event(new, 'new', succeeded=False, now=NOW, client=db)
    assert ledger.claim_event(event('evt-old', 100), 'old', now=NOW, client=db).out_of_order is False
