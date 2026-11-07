"""Aged barrier rows settle in the existing defer CAS; retained custody is immutable."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from config.batch_pipeline import RECORD_DEAD_LETTER_SECONDS
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_record_dead_letter import requeue_record
from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import live
from utils.batch_pipeline.intake import _terminally_held

# Imported at collection: the router's cold import (~2.5 s) must not count against the
# first parametrized case's 1 s unit budget.
from routers import batch_pipeline as _requeue_router  # noqa: E402

NOW = 2_000_000.0
BARRIER = 'capture upload/finalization barrier not closed'


@pytest.fixture
def drain(monkeypatch):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'off')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)

    async def refuse(*args, **kwargs):
        raise ValueError(BARRIER)

    monkeypatch.setattr(live, 'admit_recording', refuse)
    store = MemoryStore()
    store.rows['jobs', 'record'] = {
        'segment_id': 'record',
        'owner_id': 'owner',
        'conversation_id': 'capture',
        'privacy_generation': 3,
        'state': 'record_pending',
        'available_at': 0,
        'enqueued_at': 1,
        'merge_pending': False,
        'record_snapshot': {'record_audio_closed': False, 'record_upload_sessions': {'custody': True}},
        'audio_uri': 'gs://synthetic/immutable',
    }
    return store


@pytest.mark.asyncio
async def test_first_barrier_failure_gives_even_old_rows_full_window(drain):
    before = deepcopy(drain.rows['jobs', 'record'])
    await live.drain_recordings(drain)
    row = drain.rows['jobs', 'record']
    assert row['record_dead_letter_deadline_at'] == NOW + RECORD_DEAD_LETTER_SECONDS
    assert row['state'] == 'record_pending'
    assert row['available_at'] == NOW + 60
    for key in before.keys() - {'available_at'}:
        assert row[key] == before[key]
    assert set(drain.rows) == {('jobs', 'record')}


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline,expires', [(NOW + 1, False), (NOW, True), (NOW - 1, True)])
async def test_window_flip_and_requeue_preserve_every_custody_field(drain, deadline, expires):
    row = drain.rows['jobs', 'record']
    row['record_dead_letter_deadline_at'] = deadline
    before = deepcopy(row)
    counter = Mock()
    await live.drain_recordings(drain, metrics=Mock(record_dead_letter=counter))
    row = drain.rows['jobs', 'record']
    assert row['state'] == ('dead' if expires else 'record_pending')
    assert counter.inc.call_count == int(expires)
    for key in before.keys() - {'available_at', 'state'}:
        assert row[key] == before[key]
    if expires:
        assert row['dead_letter_reason'] == 'record_barrier_aged'
        assert row['record_dead_letter_at'] == NOW
        assert row['merge_pending'] is False
        assert not _terminally_held(row)
        assert not drain.due('record_pending', NOW + 10000, 100)
        assert requeue_record(drain, 'record', NOW + 2)
        assert not requeue_record(drain, 'record', NOW + 3)
        row = drain.rows['jobs', 'record']
        assert row['state'] == 'record_pending' and row['available_at'] == NOW + 2
        assert all(
            row[key] is None
            for key in (
                'dead_letter_reason',
                'record_dead_letter_at',
                'record_dead_letter_deadline_at',
            )
        )
        assert row['record_snapshot'] == before['record_snapshot']
        assert row['audio_uri'] == before['audio_uri']


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline', [True, False, 'yesterday', float('nan'), float('inf'), {}, []])
async def test_malformed_deadlines_never_authorize_expiry(drain, deadline):
    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = deadline
    await live.drain_recordings(drain)
    assert drain.rows['jobs', 'record']['state'] == 'record_pending'
    assert 'record_dead_letter_at' not in drain.rows['jobs', 'record']


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline', [None, NOW - 1])
async def test_flag_off_preserves_ordinary_defer_without_stamps_or_flips(drain, monkeypatch, deadline):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    row = drain.rows['jobs', 'record']
    if deadline is not None:
        row['record_dead_letter_deadline_at'] = deadline
    before = deepcopy(row)
    await live.drain_recordings(drain)
    assert drain.rows['jobs', 'record'] == {**before, 'available_at': NOW + 60}


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [ValueError('another refusal'), RuntimeError(BARRIER), BatchPrivacyBlocked('fenced')])
async def test_only_the_literal_barrier_failure_expires(drain, monkeypatch, error):
    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = NOW - 1

    async def refuse(*args, **kwargs):
        raise error

    monkeypatch.setattr(live, 'admit_recording', refuse)
    await live.drain_recordings(drain)
    assert drain.rows['jobs', 'record']['state'] == 'record_pending'
    assert 'record_dead_letter_at' not in drain.rows['jobs', 'record']


@pytest.mark.asyncio
async def test_newer_claim_cannot_be_expired_by_stale_admission(drain, monkeypatch):
    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = NOW - 1

    async def refuse(store, row):
        store.rows['jobs', 'record']['available_at'] = NOW + 1000
        raise ValueError(BARRIER)

    monkeypatch.setattr(live, 'admit_recording', refuse)
    await live.drain_recordings(drain)
    assert drain.rows['jobs', 'record']['state'] == 'record_pending'
    assert drain.rows['jobs', 'record']['available_at'] == NOW + 1000


@pytest.mark.parametrize(
    'state,reason', [('dead', 'held_expired'), ('cancelled', 'record_barrier_aged'), ('dead', None)]
)
def test_requeue_is_reason_and_state_cas(state, reason):
    store = MemoryStore()
    store.rows['jobs', 'record'] = {'state': state, 'dead_letter_reason': reason}
    before = deepcopy(store.rows)
    assert requeue_record(store, 'record', NOW) is False
    assert store.rows == before
    assert requeue_record(store, 'missing', NOW) is False


@pytest.mark.parametrize('blocked', [False, True])
def test_requeue_uses_real_store_commit_privacy_fence(monkeypatch, blocked):
    from database import batch_pipeline_store

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    job = {
        'state': 'dead',
        'dead_letter_reason': 'record_barrier_aged',
        'owner_id': 'owner',
        'conversation_id': 'capture',
        'privacy_generation': 3,
        'audio_uri': 'gs://synthetic/immutable',
    }
    client = StrictFirestore({('batch_pipeline_dev_jobs', 'record'): job})
    fence = Mock(side_effect=BatchPrivacyBlocked('fenced')) if blocked else Mock(return_value=3)
    monkeypatch.setattr(batch_pipeline_store, 'assert_batch_write_allowed', fence)
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    if blocked:
        with pytest.raises(BatchPrivacyBlocked):
            requeue_record(store, 'record', NOW)
        assert client.rows[('batch_pipeline_dev_jobs', 'record')] == job
    else:
        assert requeue_record(store, 'record', NOW)
        assert client.rows[('batch_pipeline_dev_jobs', 'record')]['state'] == 'record_pending'
    assert fence.call_args.args[2] == 'owner'
    assert fence.call_args.kwargs['conversation_ids'] == ('capture',)
    assert fence.call_args.kwargs['expected_generation'] == 3
    assert set(client.rows) == {('batch_pipeline_dev_jobs', 'record')}


def test_metrics_and_alert_declare_record_inflow_and_fresh_stock():
    import json
    from pathlib import Path
    from utils.batch_pipeline.metrics import QueueMetrics

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry=registry)
    metrics.record_dead_letter.inc()
    metrics.record_dead_letter_stock.set(42)
    metrics.record_dead_letter_observed_at.set(NOW)
    assert registry.get_sample_value('omi_batch_record_dead_letter_total') == 1
    assert registry.get_sample_value('omi_batch_record_dead_letter_units') == 42
    alert = json.loads(
        (Path(__file__).parents[2] / 'charts/monitoring/alerts/batch-record-dead-letter.json').read_text()
    )[0]
    expressions = {item['refId']: item['model'].get('expr', '') for item in alert['data']}
    assert 'increase(omi_batch_record_dead_letter_total[30m])' in expressions['B']
    assert 'omi_batch_record_dead_letter_observed_at_seconds < 900' in expressions['A']
    assert alert['labels']['tier'] == 'agent'


@pytest.mark.parametrize('enabled', [True, False])
def test_stock_samples_on_existing_leader_tick_and_flag_off_is_zero_io(monkeypatch, enabled):
    from utils.batch_pipeline import held_dead_letter

    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', str(enabled).lower())
    store = MemoryStore()
    store.client, store.namespace = Mock(), 'batch_pipeline_dev'
    monkeypatch.setattr(held_dead_letter, 'expired_page_ids', lambda *args: [])
    monkeypatch.setattr(held_dead_letter, 'held_expired_stock', lambda *args: 0)
    sample = Mock(return_value=42)
    monkeypatch.setattr(held_dead_letter, 'record_dead_letter_stock', sample)
    metrics = Mock()
    runner = held_dead_letter.ProjectionHeldDeadLetter(store, metrics=metrics)
    assert runner.tick(NOW) == 0
    assert sample.call_count == int(enabled)
    if enabled:
        metrics.record_dead_letter_stock.set.assert_called_once_with(42)
        metrics.record_dead_letter_observed_at.set.assert_called_once_with(NOW)
    else:
        metrics.record_dead_letter_stock.set.assert_not_called()
        metrics.record_dead_letter_observed_at.set.assert_not_called()
    runner.tick(NOW + 1)
    assert sample.call_count == int(enabled)


def test_stock_sample_failure_does_not_refresh_freshness(monkeypatch):
    from utils.batch_pipeline import held_dead_letter

    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    store = MemoryStore()
    store.client, store.namespace = Mock(), 'batch_pipeline_dev'
    monkeypatch.setattr(held_dead_letter, 'expired_page_ids', lambda *args: [])
    monkeypatch.setattr(held_dead_letter, 'held_expired_stock', lambda *args: 0)
    monkeypatch.setattr(held_dead_letter, 'record_dead_letter_stock', Mock(side_effect=RuntimeError('unavailable')))
    metrics = Mock()
    with pytest.raises(RuntimeError):
        held_dead_letter.ProjectionHeldDeadLetter(store, metrics=metrics).tick(NOW)
    metrics.record_dead_letter_observed_at.set.assert_not_called()
    metrics.record_dead_letter_stock.set.assert_not_called()


@pytest.mark.asyncio
async def test_defer_expiry_cannot_bypass_commit_privacy_fence(monkeypatch):
    from database import batch_pipeline_store

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)
    job = {
        'state': 'record_pending',
        'available_at': 0,
        'merge_pending': False,
        'record_dead_letter_deadline_at': NOW - 1,
        'owner_id': 'owner',
        'conversation_id': 'capture',
        'privacy_generation': 3,
    }
    client = StrictFirestore({('batch_pipeline_dev_jobs', 'record'): job})
    fence = Mock(side_effect=[3, BatchPrivacyBlocked('fenced')])
    monkeypatch.setattr(batch_pipeline_store, 'assert_batch_write_allowed', fence)
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    monkeypatch.setattr(store, 'due', lambda *args: ['record'])

    async def refuse(*args, **kwargs):
        raise ValueError(BARRIER)

    monkeypatch.setattr(live, 'admit_recording', refuse)
    counter = Mock()
    with pytest.raises(BatchPrivacyBlocked):
        await live.drain_recordings(store, metrics=Mock(record_dead_letter=counter))
    # The lease claim committed; the expiry update did not.
    assert client.rows[('batch_pipeline_dev_jobs', 'record')] == {
        **job,
        'available_at': NOW + live.record_drain_lease_seconds(),
    }
    counter.inc.assert_not_called()
    assert fence.call_count == 2


@pytest.mark.parametrize('outcome', ['accepted', 'privacy', 'wrong-reason', 'stage-mismatch', 'unauthorized'])
def test_private_requeue_http_boundary(monkeypatch, outcome):
    from types import SimpleNamespace
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    router = _requeue_router

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    store = MemoryStore()
    job = {'state': 'dead', 'dead_letter_reason': 'record_barrier_aged', 'audio_uri': 'gs://retained'}
    if outcome == 'wrong-reason':
        job['dead_letter_reason'] = 'held_expired'
    store.rows['jobs', 'record'] = job
    if outcome == 'privacy':
        monkeypatch.setattr(store, 'run', Mock(side_effect=BatchPrivacyBlocked('fenced')))
    service = Mock(return_value=SimpleNamespace(store=store))
    monkeypatch.setattr(router, 'serving_for_stage', service)
    app = FastAPI()
    app.include_router(router.router)
    auth = Mock()

    def verify():
        auth()
        if outcome == 'unauthorized':
            raise HTTPException(status_code=403)
        return 0

    app.dependency_overrides[router.verify_worker] = verify
    app.dependency_overrides[router.require_http_stage] = lambda: 'dev'
    with TestClient(app) as client:
        response = client.post(
            '/v2/batch-pipeline/requeue-record',
            json={
                'stage': 'prod' if outcome == 'stage-mismatch' else 'dev',
                'segment_id': 'record',
            },
        )
    auth.assert_called_once()
    if outcome in {'stage-mismatch', 'unauthorized'}:
        assert response.status_code == (409 if outcome == 'stage-mismatch' else 403)
        assert store.rows['jobs', 'record'] == job
    else:
        assert response.status_code == 200
        assert response.json() == {'accepted': outcome == 'accepted'}


@pytest.mark.asyncio
async def test_retryable_defer_counts_only_the_committed_flip(drain, monkeypatch):
    from tests.unit.test_batch_pipeline_scheduler import MemoryTransaction

    drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = NOW - 1
    original = drain.run
    calls = 0

    def replay_defer(body):
        nonlocal calls
        calls += 1
        # pending read, claim, then defer. Discard the first callback attempt.
        if calls == 3:
            body(MemoryTransaction(deepcopy(drain.rows)))
        return original(body)

    monkeypatch.setattr(drain, 'run', replay_defer)
    counter = Mock()
    await live.drain_recordings(drain, metrics=Mock(record_dead_letter=counter))
    counter.inc.assert_called_once_with()
    assert drain.rows['jobs', 'record']['state'] == 'dead'


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,deadline', [(False, None), (True, None), (True, NOW - 1)])
async def test_settlement_composes_with_24863_age_backoff(drain, monkeypatch, enabled, deadline):
    from config.record_drain import BARRIER_RETRY_MAX_SECONDS

    monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', 'on')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', str(enabled).lower())
    if deadline is not None:
        drain.rows['jobs', 'record']['record_dead_letter_deadline_at'] = deadline
    await live.drain_recordings(drain)
    row = drain.rows['jobs', 'record']
    assert row['available_at'] == NOW + BARRIER_RETRY_MAX_SECONDS
    assert row['state'] == ('dead' if deadline is not None else 'record_pending')
    if not enabled:
        assert 'record_dead_letter_deadline_at' not in row
    elif deadline is None:
        assert row['record_dead_letter_deadline_at'] == NOW + RECORD_DEAD_LETTER_SECONDS
