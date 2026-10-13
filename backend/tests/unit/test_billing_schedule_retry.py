"""Named bug: failed schedule entitlement writes were acknowledged with HTTP 200."""

import pytest
from fastapi import HTTPException

from database import stripe_event_ledger as ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_subscription_ingestion_characterization import lane, event, run, EVENTS


@pytest.mark.parametrize('status', ['completed', 'canceled'])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('failure', ['write', 'retrieve'])
def test_failed_schedule_is_retryable_only_when_the_new_gate_is_on(lane, monkeypatch, status, enabled, failure):
    from routers import payment

    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true' if enabled else 'false')
    db = StrictFirestore()
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'id': 'evt-schedule-fixture',
        'created': 100,
        'type': f'subscription_schedule.{status}',
        'data': {
            'object': {
                'id': 'sched-fixture',
                'metadata': {'uid': 'fixture-user'},
                'status': status,
                'subscription': 'sub-current',
            }
        },
    }
    if failure == 'write':
        lane.error = RuntimeError('fixture durable write unavailable')
    else:

        def fail(*args):
            raise RuntimeError('fixture Stripe read unavailable')

        monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', fail)
    if enabled:
        with pytest.raises(HTTPException) as error:
            run(lane)
        assert error.value.status_code == 503
        receipts = [value for path, value in db.rows.items() if path[0] == ledger.EVENT_COLLECTION]
        assert receipts[0]['outcome'] == 'failed'
    else:
        assert run(lane) == {'status': 'success'}
        assert db.rows == {}
    assert lane.calls == []


@pytest.mark.parametrize('status', ['completed', 'canceled'])
def test_schedule_recovery_is_processed_once(lane, monkeypatch, status):
    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    db = StrictFirestore()
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'id': 'evt-schedule-recovered',
        'created': 100,
        'type': f'subscription_schedule.{status}',
        'data': {
            'object': {
                'id': 'sched-fixture',
                'metadata': {'uid': 'fixture-user'},
                'status': status,
                'subscription': 'sub-current',
            }
        },
    }
    assert run(lane) == {'status': 'success'}
    first = list(lane.calls)
    assert run(lane) == {'status': 'success'}
    assert lane.calls == first
    assert [name for name, _ in first].count('write') == 1


def test_deleted_owner_does_not_become_a_retry_storm(lane, monkeypatch):
    from routers import payment

    monkeypatch.setenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'true')
    db = StrictFirestore()
    monkeypatch.setattr(ledger, '_client', lambda client: db)
    lane.error = payment.FirestoreNotFound('fixture owner deleted')
    lane.stripe_obj = event(EVENTS[1], 'active')['data']['object']
    lane.event = {
        'id': 'evt-deleted-owner',
        'created': 100,
        'type': 'subscription_schedule.completed',
        'data': {'object': {'metadata': {'uid': 'fixture-user'}, 'status': 'completed', 'subscription': 'sub-current'}},
    }
    assert run(lane) == {'status': 'success'}
    assert lane.calls == []
