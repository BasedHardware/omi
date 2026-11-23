"""Measure idle finish/projection and HTTP pending-work reads at two backlog sizes."""

from datetime import datetime, timezone
import os
from urllib.parse import urlsplit
from uuid import uuid4

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client, sync_jobs
from database.batch_pipeline_projection_finish_backfill import BACKFILL_VERSION, backfill_ref
from database.batch_pipeline_store import FirestoreStore
from routers import pending_work
from testing.firestore_read_budget import assert_read_budget, delta_reads, snapshot_reads
from utils.batch_pipeline.projection import Projector

pytestmark = pytest.mark.integration
BACKLOG = 200


@pytest.fixture
def client(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('requires a dedicated loopback Firestore emulator')
    assert urlsplit(f'http://{host}').hostname in {'127.0.0.1', 'localhost', '::1'}
    firestore_client = firestore.Client(
        project=f'demo-idle-budget-{uuid4().hex[:8]}', credentials=AnonymousCredentials()
    )
    monkeypatch.setattr(_client, '_firestore_client', firestore_client)
    try:
        yield firestore_client
    finally:
        firestore_client.close()


def _seed(client, collection, backlog, row):
    batch = client.batch()
    for index in range(backlog):
        batch.set(collection.document(f'ineligible-{index:04}'), row)
    batch.commit()


@pytest.mark.parametrize('backlog', [BACKLOG, 2 * BACKLOG])
def test_idle_backlog_projection_sweep(client, monkeypatch, backlog):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    store = FirestoreStore('batch_pipeline_test_idle', firestore_client=client)
    backfill_ref(client, store.namespace).set({'complete': True, 'version': BACKFILL_VERSION})
    _seed(
        client,
        client.collection(f'{store.namespace}_results'),
        backlog,
        {
            'projection_state': 'completed',
            'committed_at': 1_760_000_000.0,
        },
    )

    def unexpected_load(*_):
        pytest.fail('idle sweep attempted to load a result')

    projector = Projector(store, unexpected_load)
    before = snapshot_reads()
    counts = projector.sweep()
    delta = delta_reads(before)
    assert counts == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
    assert not projector.has_async_followups
    print(f'idle_backlog_projection_sweep rows={backlog}: total={delta.reads:g}')
    assert delta.reads > 0, delta
    assert_read_budget('idle_backlog_projection_sweep', delta.reads, delta)


@pytest.mark.parametrize('backlog', [BACKLOG, 2 * BACKLOG])
def test_idle_backlog_pending_work(client, monkeypatch, backlog):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'on')
    monkeypatch.setattr(sync_jobs, 'r', fakeredis.FakeRedis())
    uid = 'synthetic-pending-owner'
    collection = client.collection('users').document(uid).collection('conversations')
    # Rows still match the stored processing query, but completed finalization
    # excludes them after the read. This exercises the route's pagination.
    _seed(
        client,
        collection,
        backlog,
        {
            'status': 'processing',
            'finalization_status': 'completed',
            'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )
    app = FastAPI()
    app.include_router(pending_work.router)
    app.dependency_overrides[pending_work.auth.get_current_user_uid] = lambda: uid

    with TestClient(app) as http:
        before = snapshot_reads()
        response = http.get('/v1/pending-work')
        delta = delta_reads(before)

    assert response.status_code == 200, response.text
    assert response.json() == {'enabled': True, 'home_processing_today': True, 'items': [], 'attention_unseen_count': 0}
    print(f'idle_backlog_pending_work rows={backlog}: total={delta.reads:g}')
    assert delta.reads > 0, delta
    # The 2x case measures the existing growth. The CI ceiling is set on the
    # 200-row run so a regression fails without requiring a custody source fix.
    if backlog == BACKLOG:
        assert_read_budget('idle_backlog_pending_work', delta.reads, delta)
