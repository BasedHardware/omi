"""Exercise the actual HTTP worker boundary with local Redis/Firestore doubles."""

from unittest.mock import AsyncMock, Mock

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import sync_jobs, sync_redrive
import routers.sync as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'legacy')
    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    monkeypatch.setenv('SYNC_LEGACY_COMPLETION_CONVERGENCE', 'true')
    redis = fakeredis.FakeRedis()
    database = StrictFirestore()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(sync_redrive, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(sync_redrive.firestore, 'transactional', lambda fn: lambda tx: fn(tx))
    monkeypatch.setattr(router, '_delete_staged_blobs_async', AsyncMock())
    monkeypatch.setattr(router, '_download_staged_files', Mock(side_effect=AssertionError('must not download')))
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_cloud_tasks_oidc] = lambda: 0
    payload = {
        'schema_version': 1,
        'uid': 'owner',
        'job_id': 'job',
        'content_id': 'content',
        'lane': 'fresh',
        'ledger_fence_mode': 'legacy',
        'raw_blob_paths': ['syncing/owner/job/test_pcm16.bin'],
    }
    with TestClient(app) as client:
        yield client, database, payload


def test_missing_job_http_ack_follows_durable_custody(worker):
    client, database, payload = worker
    response = client.post('/v2/sync-jobs/run', json=payload)
    assert response.status_code == 200
    assert response.json() == {'status': 'redrive_required'}
    row = database.collection(sync_redrive.COLLECTION).document('job').get().to_dict()
    assert row['payload'] == payload
    router._download_staged_files.assert_not_called()
    router._delete_staged_blobs_async.assert_not_awaited()


def test_legacy_retry_http_converges_real_redis_cas_without_provider(worker):
    client, database, payload = worker
    result = {'total_segments': 0, 'failed_segments': 0, 'errors': [], 'outcome': 'expected_silence'}
    sync_redrive.sync_content_reference(database, 'owner', 'content').create({'status': 'completed', 'result': result})
    sync_jobs.create_sync_job('owner', 1, 0, 'job', content_id='content', ledger_fence_mode='legacy')
    response = client.post('/v2/sync-jobs/run', json=payload)
    assert response.status_code == 200
    assert response.json() == {'status': 'done', 'reconciled': True}
    assert sync_jobs.get_sync_job('job')['status'] == 'completed'
    router._download_staged_files.assert_not_called()
