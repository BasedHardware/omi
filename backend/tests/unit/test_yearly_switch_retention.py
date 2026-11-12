from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils import experiments, yearly_switch_retention as retention


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('YEARLY_SWITCH_RETENTION_APPROVAL_REF', 'synthetic-approval')
    monkeypatch.setenv('YEARLY_SWITCH_RETENTION_ROLLOUT_AUTHORIZED', 'true')
    monkeypatch.delenv('YEARLY_SWITCH_RETENTION_ENABLED', raising=False)
    monkeypatch.setenv('POSTHOG_PRODUCT_CAPTURE_TOKEN', 'disabled')


def uid_for(arm):
    return next(
        f'synthetic-{n}'
        for n in range(100)
        if experiments.assigned_variant(retention.EXPERIMENT_ID, f'synthetic-{n}') == arm
    )


def admit(db, uid, placement='cancel', count=8, blocked=lambda: False):
    return retention.admit(uid, placement, count_captures=lambda *_: count, blocked=blocked, client=db)


@pytest.mark.parametrize('first,second', [('cancel', 'engaged'), ('engaged', 'cancel')])
def test_once_only_and_cross_placement_exclusion(first, second):
    db = FakeFirestore()
    uid = uid_for('treatment')
    assert admit(db, uid, first)
    assert not admit(db, uid, first)
    assert not admit(db, uid, second)
    assert len(db.docs) == 1
    assert list(db.docs.values())[0]['eligibility']['placement'] == first


def test_control_enrolled_without_either_offer_and_survives_toggles(monkeypatch):
    db = FakeFirestore()
    uid = uid_for('control')
    assert not admit(db, uid)
    record = list(db.docs.values())[0].copy()
    monkeypatch.setenv('YEARLY_SWITCH_RETENTION_ENABLED', 'false')
    assert not admit(db, uid, 'engaged')
    monkeypatch.setenv('YEARLY_SWITCH_RETENTION_ENABLED', 'true')
    assert not admit(db, uid, 'engaged')
    assert list(db.docs.values())[0] == record


@pytest.mark.parametrize('key', ['YEARLY_SWITCH_RETENTION_APPROVAL_REF', 'YEARLY_SWITCH_RETENTION_ROLLOUT_AUTHORIZED'])
def test_missing_approval_or_rollout_has_no_roster_write(monkeypatch, key):
    monkeypatch.delenv(key)
    db = FakeFirestore()
    assert not admit(db, uid_for('treatment'))
    assert db.docs == {}


def test_engagement_threshold_and_frozen_window():
    db = FakeFirestore()
    uid = uid_for('treatment')
    assert not admit(db, uid, 'engaged', count=7)
    assert db.docs == {}
    count = Mock(return_value=8)
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert retention.admit(uid, 'engaged', count_captures=count, blocked=lambda: False, client=db, now=now)
    start, end = count.call_args.args
    assert (end - start).days == 14 and end == now
    assert list(db.docs.values())[0]['eligibility']['completed_saved_captures'] == 8


def test_cancel_does_not_require_engagement():
    assert admit(FakeFirestore(), uid_for('treatment'), count=0)


def test_failed_enrollment_cannot_deliver(monkeypatch):
    monkeypatch.setattr(experiments, 'enroll', lambda **_: None)
    assert not admit(FakeFirestore(), uid_for('treatment'))


def test_deletion_during_enrollment_erases_and_excludes():
    db = FakeFirestore()
    calls = iter([False, True])
    assert not admit(db, uid_for('treatment'), blocked=lambda: next(calls))
    assert db.docs == {}


def test_erase_is_retryable_uid_scoped_and_failure_propagates():
    db = FakeFirestore()
    for uid in ('synthetic-a', 'synthetic-b'):
        experiments.enroll(experiment_id=retention.EXPERIMENT_ID, uid=uid, firestore_client=db)
    retention.erase_assignment('synthetic-a', db)
    retention.erase_assignment('synthetic-a', db)
    assert len(db.docs) == 1 and next(iter(db.docs)).endswith('/synthetic-b')
    bad = Mock()
    bad.collection.return_value.document.return_value.collection.return_value.document.return_value.delete.side_effect = RuntimeError(
        'erase failed'
    )
    with pytest.raises(RuntimeError, match='erase failed'):
        retention.erase_assignment('synthetic-b', bad)


def test_concurrent_eligible_hosts_only_one_delivery(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from tests.unit.fixtures.generic_firestore_fake import FakeDocumentReference

    lock = Lock()
    create = FakeDocumentReference.create

    def atomic_create(ref, value):
        with lock:
            return create(ref, value)

    monkeypatch.setattr(FakeDocumentReference, 'create', atomic_create)
    db = FakeFirestore()
    uid = uid_for('treatment')
    with ThreadPoolExecutor(max_workers=8) as pool:
        delivered = list(pool.map(lambda i: admit(db, uid, 'cancel' if i % 2 else 'engaged'), range(32)))
    assert sum(delivered) == 1 and len(db.docs) == 1


def test_http_admission_and_config_execute_real_routes_with_local_fixtures(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import database.conversations as conversations
    import routers.yearly_switch as routes
    from utils.yearly_switch import YearlySwitch

    db = FakeFirestore()
    original_admit = retention.admit
    monkeypatch.setattr(retention, 'admit', lambda *a, **kw: original_admit(*a, **kw, client=db))
    monkeypatch.setattr(routes.users_db, 'get_user_deletion_wipe_status', lambda _: None)
    monkeypatch.setattr(routes.users_db, 'get_user_subscription', lambda _: Mock(stripe_subscription_id='synthetic'))
    monkeypatch.setattr(
        routes.yearly_switch, 'get_offer', lambda _: YearlySwitch(True, 'eligible', yearly_amount=26991)
    )
    count = Mock(return_value=8)
    monkeypatch.setattr(conversations, 'get_conversations_count', count)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: uid_for('treatment')
    with TestClient(app) as http:
        assert http.get('/v1/payments/yearly-switch-retention').json()['eligible'] is True
        assert not db.docs  # Config reads never consume an opportunity.
        assert http.post('/v1/payments/yearly-switch-retention?placement=engaged').json()['eligible'] is True
        assert http.post('/v1/payments/yearly-switch-retention?placement=engaged').json()['eligible'] is False
        assert http.post('/v1/payments/yearly-switch-retention?placement=cancel').json()['eligible'] is False
        assert http.post('/v1/payments/yearly-switch-retention?placement=other').status_code == 422
    assert count.call_args.kwargs['statuses'] == ['completed']
