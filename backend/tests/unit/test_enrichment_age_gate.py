"""Historical tasks relinquish queue slots without deleting durable custody."""

import time
from unittest.mock import Mock

import pytest

from tests.unit.test_enrichment_route import client, rows, KEY  # noqa: F401
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import age_gate, outbox
from utils.enrichment import consumer as consumer_module


def test_old_wake_returns_200_without_calling_llm_and_preserves_debt(rows, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    old = rows[0][KEY]
    old.update(first_pending_at=time.time() - 73 * 3600, sync_hold=True, version=4)
    token = old['task_token']
    process = Mock(side_effect=AssertionError('historical work must not call LLM'))
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda _: process)
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 200
    assert response.json()['reason'] == 'age_gate_72h'
    parked = rows[0][KEY]
    assert parked['dormant'] and parked['age_gate_parked'] and parked['due_at'] is None
    assert parked['deferred_reason'] == 'age_gate_72h' and parked['task_token'] != token
    assert parked['version'] == 4 and parked['sync_hold'] and parked['uid'] == 'u'
    assert parked['first_pending_at'] == old['first_pending_at']
    process.assert_not_called()


def test_fresh_wake_keeps_processing(rows, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    rows[0][KEY].update(first_pending_at=time.time() - 3600, due_at=0)
    process = Mock(return_value=None)
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda _: process)
    assert (
        client.post(
            '/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': rows[0][KEY]['task_token']}
        ).status_code
        == 200
    )
    process.assert_called_once()


def test_old_conversation_with_a_new_obligation_is_parked(rows, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = time.time()
    rows[0][KEY]['first_pending_at'] = now - 60
    monkeypatch.setattr(age_gate, 'conversation_created_at', lambda *_: now - 73 * 3600)
    assert age_gate.park_if_expired(KEY, rows[0][KEY]['task_token'], now=now)


def test_sweep_parks_old_work_and_never_rewakes_it(rows, sweep_query, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = time.time()
    rows[0][KEY]['first_pending_at'] = now - 73 * 3600
    rows[1].clear()
    assert outbox.sweep(now=now) == {'repaired': 0, 'error': 0}
    assert outbox.sweep(now=now + 3600) == {'repaired': 0, 'error': 0}
    outbox.mark('u', 'c', 'en', now=now + 3600)
    assert rows[0][KEY]['age_gate_parked'] and not rows[1]


@pytest.mark.parametrize('fence', ['lease', 'token'])
def test_gate_never_steals_a_current_worker_or_newer_wake(rows, monkeypatch, fence):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = time.time()
    rows[0][KEY]['first_pending_at'] = now - 73 * 3600
    token = rows[0][KEY]['task_token']
    if fence == 'lease':
        rows[0][KEY].update(owner='current-worker', lease_until=now + 120)
    else:
        token = 'f' * 32
    assert not age_gate.park_if_expired(KEY, token, now=now)
    assert not rows[0][KEY].get('age_gate_parked')


@pytest.mark.parametrize('setting', ['nan', '-1', 'invalid'])
def test_invalid_age_config_keeps_the_72_hour_default(monkeypatch, setting):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', setting)
    assert age_gate.max_age_seconds() == 72 * 3600


def test_zero_disables_new_parking_without_io(monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    monkeypatch.setattr(outbox, 'get_firestore_client', Mock(side_effect=AssertionError('unexpected IO')))
    assert not age_gate.park_if_expired(KEY, 'a' * 32)


def test_debt_repair_parks_old_conversation_without_rewaking(state, monkeypatch):  # noqa: F811
    from services import summary_debt_repair as repair
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    now = time.time()
    conversation = {
        'status': 'completed',
        'created_at': now - 73 * 3600,
        'summary_first_pending_at': now - 3600,
        'summary_due_at': now - 100,
        'summary_lane': 'batch',
        'sync_content_revision': 3,
    }
    client = StrictFirestore({('users', 'u'): {}, ('users', 'u', 'conversations', 'c'): conversation})
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda *_: False)
    monkeypatch.setattr(repair, 'assert_batch_write_allowed', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(repair.delivery, 'refusal', lambda *_: None)
    assert not repair.redrive(client, 'u', 'c', now=now)
    parked = client.rows[('sync_reprocess_outbox', KEY)]
    token = parked['task_token']
    assert parked['age_gate_parked'] and parked['deferred_reason'] == 'age_gate_72h'
    assert not repair.redrive(client, 'u', 'c', now=now + 300)
    assert client.rows[('sync_reprocess_outbox', KEY)]['task_token'] == token
    assert not state[1]
    assert client.rows[('users', 'u', 'conversations', 'c')] == conversation


def test_historical_debt_cannot_hide_fresh_work_behind_the_admission_cap(monkeypatch):
    from types import SimpleNamespace
    from services import summary_debt_repair as repair
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    now = time.time()
    old = {'created_at': now - 73 * 3600, 'summary_first_pending_at': now - 3600, 'summary_due_at': now - 100}
    fresh = {**old, 'created_at': now - 3600}
    page = [SimpleNamespace(reference=SimpleNamespace(path='users/u/conversations/old'), to_dict=lambda: old)] * 99
    page.append(SimpleNamespace(reference=SimpleNamespace(path='users/u/conversations/fresh'), to_dict=lambda: fresh))
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'repair_enabled', lambda: True)
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda *_: False)
    monkeypatch.setattr(repair.delivery, 'refusal', lambda *_: None)
    monkeypatch.setattr(repair, 'due_conversations', lambda *_, phase, **__: page if phase == 'newest' else [])
    redrive = Mock(return_value=True)
    monkeypatch.setattr(repair, 'redrive', redrive)
    assert repair.tick(now=now, client=StrictFirestore()) == {
        'scanned': 100,
        'admitted': 1,
        'errors': 0,
        'expired_seen': 99,
        'near_expiry_admitted': 0,
    }
    assert redrive.call_args.args[1:] == ('u', 'fresh')
    redrive.assert_called_once()

    assert repair.delivery.EXPIRED_SEEN._value.get() == 99
