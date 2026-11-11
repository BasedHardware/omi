"""Conversation delete serialization and durable batch purge on the Firestore emulator.

Real transactions for the account gate, the hold writer, the tombstone+obligation
batch and the obligation lifecycle. Storage/vector side effects are stubbed.
Run: firebase emulators:exec --only firestore --project demo-omi \
  "cd backend && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python -m pytest \
  tests/integration/test_conversation_batch_purge_emulator.py"
"""

import hashlib
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

pytestmark = pytest.mark.integration


@pytest.fixture
def plane(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    from database import _client

    client = firestore.Client(project=f'demo-purge-{uuid4().hex[:10]}', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(_client, '_data_plane_firestore_client', client)  # process singleton
    uid = f'synthetic-purge-{uuid4().hex[:10]}'
    client.collection('users').document(uid).set({'data_protection_level': 'standard'})
    return SimpleNamespace(client=client, uid=uid, key=hashlib.sha256(uid.encode()).hexdigest())


@pytest.fixture
def route(monkeypatch, plane):
    from routers import conversations as routes
    from utils.conversations import deletion_batch_purge

    for name in (
        'delete_owner_prompt_embedding_cache',
        'delete_conversation_screen_frames',
        'delete_privacy_conversation_audio',
        'delete_vector',
        'delete_transcript_chunk_vectors',
        'delete_action_item_vectors_batch',
        'record_product_event',
    ):
        monkeypatch.setattr(routes, name, MagicMock())
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: plane.uid
    return SimpleNamespace(app=app, routes=routes)


def _conversation(plane, cid):
    plane.client.collection('users').document(plane.uid).collection('conversations').document(cid).set(
        {'id': cid, 'status': 'completed'}
    )


def _exists(plane, *path):
    return plane.client.document('/'.join(path)).get().exists


def _seed_batch(plane, cid, *, mine, others):
    """Owner rows across scan pages (100/page); ``mine`` belong to ``cid``."""
    plane.client.collection('batch_pipeline_prod_owners').document(plane.key).set(
        {'owner_key': plane.key, 'projection_watermark': 'seg-none'}
    )
    batch, count = plane.client.batch(), 0
    for index in range(mine + others):
        owner = cid if index < mine else f'other-{index}'
        batch.set(
            plane.client.collection('batch_pipeline_prod_results').document(f'{plane.uid}-r{index:04d}'),
            {'owner_key': plane.key, 'conversation_id': owner, 'segment_id': f'{plane.uid}-r{index:04d}'},
        )
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = plane.client.batch()
    batch.commit()


def _results_left(plane, cid):
    rows = plane.client.collection('batch_pipeline_prod_results').where('owner_key', '==', plane.key).stream()
    return sum(
        1
        for row in rows
        if (row.to_dict() or {}).get('conversation_id') == cid and 'projection_state' not in row.to_dict()
    )


def test_six_parallel_same_account_cascade_deletes_all_succeed(monkeypatch, plane, route):
    """Prod 2026-11-11 shape: one phone deletes six at once; old code answered 1x204 + 5x409."""
    original = route.routes.delete_conversation_and_frame_evidence

    def slower(*args, **kwargs):
        time.sleep(0.5)  # in-gate work so the six genuinely contend
        return original(*args, **kwargs)

    monkeypatch.setattr(route.routes, 'delete_conversation_and_frame_evidence', slower)
    ids = [f'conv-{index}-{uuid4().hex[:6]}' for index in range(6)]
    for cid in ids:
        _conversation(plane, cid)
    statuses = []

    def delete(cid):
        with TestClient(route.app) as client:
            statuses.append(client.delete(f'/v1/conversations/{cid}?cascade=true').status_code)

    threads = [threading.Thread(target=delete, args=(cid,)) for cid in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert statuses == [204] * 6
    assert not any(_exists(plane, 'users', plane.uid, 'conversations', cid) for cid in ids)


def test_delete_arms_obligation_atomically_and_retry_keeps_the_tombstone(plane, route):
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _conversation(plane, cid)
    with TestClient(route.app) as client:
        assert client.delete(f'/v1/conversations/{cid}?cascade=true').status_code == 204
    tombstone = plane.client.document(f'users/{plane.uid}/deleted_conversations/{cid}').get().to_dict()
    job = plane.client.collection(purge_jobs.COLLECTION).document(purge_jobs.job_id(plane.uid, cid))
    assert job.get().to_dict()['conversation_id'] == cid
    job.update({'generation': 3})
    with TestClient(route.app) as client:  # retried delete after the doc is gone
        assert client.delete(f'/v1/conversations/{cid}?cascade=true').status_code == 204
    again = plane.client.document(f'users/{plane.uid}/deleted_conversations/{cid}').get().to_dict()
    assert again['deleted_at'] == tombstone['deleted_at']  # original binding preserved
    assert job.get().to_dict()['generation'] == 3  # re-armed, not reset


def _reconcile(monkeypatch):
    from utils.conversations import deletion_batch_purge

    sent = []
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    monkeypatch.setattr(
        deletion_batch_purge, 'enqueue_conversation_batch_purge', lambda job, gen: sent.append((job, gen))
    )
    deletion_batch_purge.reconcile_conversation_batch_purges()
    return sent


def _delete(plane, route, cid):
    _conversation(plane, cid)
    with TestClient(route.app) as client:
        assert client.delete(f'/v1/conversations/{cid}?cascade=true').status_code == 204


def test_reconciled_purge_erases_only_its_conversation_then_clears(monkeypatch, plane, route):
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=3, others=150)
    [(job, generation)] = _reconcile(monkeypatch)
    assert purge_jobs.run_job(job, generation) == 'purged'
    assert _results_left(plane, cid) == 0
    others = list(plane.client.collection('batch_pipeline_prod_results').where('owner_key', '==', plane.key).stream())
    assert sum(1 for row in others if (row.to_dict() or {}).get('conversation_id', '').startswith('other-')) == 150
    assert not plane.client.collection(purge_jobs.COLLECTION).document(job).get().exists
    assert purge_jobs.run_job(job, generation) == 'missing'


def test_hold_between_purge_units_stops_erasure_until_release(monkeypatch, plane, route):
    from database import batch_pipeline_purge, legal_holds
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=150, others=0)  # matches on two scan pages
    real_page = batch_pipeline_purge.queries.owner_documents
    pages = []

    def page_then_hold(client, namespace, table, key, *, after=None):
        rows = real_page(client, namespace, table, key, after=after)
        if namespace == 'batch_pipeline_prod' and table == 'results':
            pages.append(len(rows))
            if len(pages) == 2:  # the scan reads results page two: no gate is held
                legal_holds.place_legal_hold(plane.uid, issuer='admin', active=True)
        return rows

    monkeypatch.setattr(batch_pipeline_purge.queries, 'owner_documents', page_then_hold)
    [(job, generation)] = _reconcile(monkeypatch)
    assert purge_jobs.run_job(job, generation) == 'held'
    assert _results_left(plane, cid) == 50, 'rows erased after the hold committed'
    row = plane.client.collection(purge_jobs.COLLECTION).document(job).get().to_dict()
    assert row['last_outcome'] == 'held'

    monkeypatch.setattr(batch_pipeline_purge.queries, 'owner_documents', real_page)
    legal_holds.place_legal_hold(plane.uid, issuer='admin', active=False)
    plane.client.collection(purge_jobs.COLLECTION).document(job).update({'due_at': purge_jobs._now()})
    [(job, generation)] = _reconcile(monkeypatch)
    assert generation == 2
    assert purge_jobs.run_job(job, generation) == 'purged'
    assert _results_left(plane, cid) == 0


def test_account_wipe_gate_fails_the_run_retryably_and_keeps_the_obligation(monkeypatch, plane, route):
    from database import legal_holds
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=2, others=5)
    legal_holds.acquire_destructive_operation(plane.uid, kind='account_deletion', token='synthetic-wipe')
    [(job, generation)] = _reconcile(monkeypatch)
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        purge_jobs.run_job(job, generation)
    assert _results_left(plane, cid) == 2
    assert plane.client.collection(purge_jobs.COLLECTION).document(job).get().to_dict()['last_outcome'] == 'failed'
