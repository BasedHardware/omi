"""Drive fencing and authenticated HTTP contract without cloud credentials."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import sync_backfill_worker as policy
from database import sync_backfill_sequencer as registry, sync_jobs
from routers import sync_worker as rpc
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync import worker_control

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
TOKEN = 'w' * 40
PATH = (registry.COLLECTION, 'synthetic')


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    db = StrictFirestore(
        {
            PATH: {
                'active_job_id': 'job',
                'active_epoch': 7,
                'epoch': 7,
                'active_state': 'dispatching',
                'worker_available': True,
                'lease_expires_at': NOW + timedelta(seconds=1800),
                'active_payload': {
                    'uid': 'synthetic',
                    'job_id': 'job',
                    'lane': 'backfill',
                    'ledger_fence_mode': 'active',
                    'worker_eligible': True,
                },
            }
        }
    )
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(registry, '_now', lambda: NOW)
    return db


def test_worker_wins_and_tasks_cannot_begin_renew_or_finish(store):
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN)
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN) is None
    assert registry.begin_job('synthetic', 'job', 7) is None
    assert not registry.renew_job('synthetic', 'job', 7)
    assert not registry.finish_job('synthetic', 'job', 7, 'completed')
    assert registry.renew_job('synthetic', 'job', 7, worker_token=TOKEN)
    assert store.rows[PATH]['lease_expires_at'] == NOW + timedelta(seconds=1800)
    assert all(tx.has_written or not tx.updates for tx in store.transactions)


def test_task_wins_worker_cannot_take_running_owner(store, monkeypatch):
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _: {'status': 'queued'})
    assert registry.begin_job('synthetic', 'job', 7)
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN) is None


@pytest.mark.parametrize(
    'field,value',
    [
        ('worker_eligible', False),
        ('lane', 'fresh'),
        ('ledger_fence_mode', 'legacy'),
        ('uid', 'different'),
        ('job_id', 'different'),
    ],
)
def test_worker_refuses_unsafe_payload(store, field, value):
    store.rows[PATH]['active_payload'][field] = value
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN) is None
    assert store.rows[PATH]['active_state'] == 'dispatching'


def test_worker_expiry_cannot_be_revived_or_completed(store):
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN)
    expired = NOW + timedelta(seconds=1800)
    assert not registry.renew_job('synthetic', 'job', 7, worker_token=TOKEN, now=expired)
    assert not registry.finish_job('synthetic', 'job', 7, 'completed', worker_token=TOKEN, now=expired)
    assert not registry.fail_worker('synthetic', 'job', 7, TOKEN, now=expired)


def test_rollback_closes_intake_without_reading_state(monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_WORKER_PERCENT', raising=False)
    monkeypatch.setattr(registry, 'enabled', MagicMock(side_effect=AssertionError('persistence read')))
    assert worker_control.claim() is None


def test_global_legacy_dark_closes_intake_before_firestore(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_PERCENT', '100')
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'active')
    monkeypatch.setattr(
        worker_control.legacy_dark, 'current_mode', lambda uid=None: worker_control.legacy_dark.LegacySyncMode.DARK
    )
    monkeypatch.setattr(registry, 'get_firestore_client', MagicMock(side_effect=AssertionError('Firestore read')))
    assert worker_control.claim() is None


@pytest.mark.parametrize('value', ['nan', 'inf', '-1', 'invalid', '0'])
def test_bad_or_zero_percent_closes_intake(monkeypatch, value):
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_PERCENT', value)
    assert policy.percent() == 0


def test_failure_requires_run_lock_absence_and_completion_requires_terminal(store, monkeypatch):
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN)
    monkeypatch.setattr(sync_jobs, 'sync_job_run_lock_present', lambda _: True)
    assert not worker_control.fail('synthetic', 'job', 7, TOKEN)
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _: {'uid': 'synthetic', 'status': 'processing'})
    assert not worker_control.complete('synthetic', 'job', 7, TOKEN)
    monkeypatch.setattr(sync_jobs, 'sync_job_run_lock_present', lambda _: False)
    assert worker_control.fail('synthetic', 'job', 7, TOKEN)
    assert store.rows[PATH]['active_epoch'] == 8
    assert not registry.renew_job('synthetic', 'job', 7, worker_token=TOKEN)


def test_terminal_completion_drains_after_percent_rollback(store, monkeypatch):
    assert registry.claim_worker('synthetic', 'job', 7, TOKEN)
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_PERCENT', '0')
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _: {'uid': 'synthetic', 'status': 'completed'})
    monkeypatch.setattr(registry, '_has_pending', lambda *args, **kwargs: False)
    monkeypatch.setattr(worker_control.uid_sequencer, 'kick', lambda _: False)
    assert worker_control.heartbeat('synthetic', 'job', 7, TOKEN)
    assert not worker_control.complete('synthetic', 'job', 7, 'wrong' * 10)
    assert worker_control.complete('synthetic', 'job', 7, TOKEN)
    assert not worker_control.complete('synthetic', 'job', 7, TOKEN)
    assert store.rows[PATH]['epoch'] == 7
    assert 'active_job_id' not in store.rows[PATH]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    app = FastAPI()
    app.include_router(rpc.router)
    with TestClient(app) as client:
        yield client, app


def test_oidc_is_required_even_when_dark(client, monkeypatch):
    from utils import cloud_tasks

    calls = []

    def verify(request, **kwargs):
        from fastapi import HTTPException

        calls.append(kwargs)
        raise HTTPException(status_code=403)

    monkeypatch.setenv('SYNC_BACKFILL_WORKER_AUDIENCE', 'https://synthetic.run.app')
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_SERVICE_ACCOUNT', 'worker@synthetic.invalid')
    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verify)
    http, _ = client
    for path in ('claim', 'heartbeat', 'complete', 'fail'):
        assert http.post(f'/v2/sync-jobs/{path}', json={'stage': 'prod'}).status_code == 403
    assert len(calls) == 4
    assert calls[0]['audience'] == 'https://synthetic.run.app'
    assert calls[0]['invoker_sa'] == 'worker@synthetic.invalid'


def test_real_http_dark_claim_stage_and_validation(client, monkeypatch):
    http, app = client
    app.dependency_overrides[rpc.verify_worker] = lambda: 0
    monkeypatch.delenv('SYNC_BACKFILL_WORKER_PERCENT', raising=False)
    assert http.post('/v2/sync-jobs/claim', json={'stage': 'prod'}).json() == {'lease': None}
    assert http.post('/v2/sync-jobs/claim', json={'stage': 'dev'}).status_code == 422
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert http.post('/v2/sync-jobs/claim', json={'stage': 'prod'}).status_code == 409
    assert (
        http.post(
            '/v2/sync-jobs/heartbeat',
            json={
                'stage': 'prod',
                'uid': 'synthetic',
                'job_id': 'job',
                'epoch': True,
                'token': TOKEN,
            },
        ).status_code
        == 422
    )
