"""Real Firestore transactions: crash replay, contention, and stale hash fencing.

Run via test.sh under a dedicated demo-project Firestore emulator. No cloud
credentials, accounts, or production documents are used.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from utils.sync import reprocess
from utils.conversations import llm_input_dedupe as dedupe

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def loopback_only_network():
    from testing.hermetic_network import block_outbound_network

    with block_outbound_network():
        yield


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    import google.auth

    monkeypatch.setattr(google.auth, 'default', lambda **_: (AnonymousCredentials(), 'demo-omi-reprocess'))
    monkeypatch.setenv('PROVIDER_MODE', 'offline')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = firestore.Client(project='demo-omi-reprocess', credentials=AnonymousCredentials())
    client.collection('sync_reprocess_scan').document('cursor').delete()
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: client)
    from database import _client

    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '600')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.delenv('SYNC_TASKS_OIDC_AUDIENCE', raising=False)
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'true')
    tasks = []
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: tasks.append(deepcopy(row)))
    uid = 'test-' + uuid.uuid4().hex
    client.collection('users').document(uid).set({'data_protection_level': 'enhanced'})
    yield client, uid, tasks
    for row in client.collection(reprocess.COLLECTION).where('uid', '==', uid).stream():
        row.reference.delete()
    client.collection('sync_reprocess_scan').document('cursor').delete()
    client.collection('users').document(uid).delete()
    client.close()


def test_concurrent_appends_claim_once_and_run_once(store):
    client, uid, tasks = store
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: reprocess.mark(uid, 'c', 'en', now=0), range(8)))
    assert len(tasks) == 1
    row = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'c')).get().to_dict()
    assert row['version'] == 8
    process = Mock()
    reprocess.run(reprocess.key(uid, 'c'), tasks[-1]['task_token'], process, now=600)
    process.assert_called_once_with(uid, 'c', 'en')
    assert not client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'c')).get().exists


def test_crash_between_dirty_commit_and_enqueue_repaired_by_sweep(store, monkeypatch):
    client, uid, tasks = store
    enqueue = reprocess._enqueue
    monkeypatch.setattr(reprocess, '_enqueue', Mock(side_effect=RuntimeError('crash')))
    with pytest.raises(RuntimeError):
        reprocess.mark(uid, 'c', 'en', now=0)
    assert not tasks
    monkeypatch.setattr(reprocess, '_enqueue', enqueue)
    result = reprocess.sweep(now=600)
    assert result['repaired'] >= 1 and result['error'] == 0
    process = Mock()
    task = next(row for row in tasks if row['uid'] == uid)
    reprocess.run(reprocess.key(uid, 'c'), task['task_token'], process, now=600)
    process.assert_called_once()


def test_crashed_worker_and_append_during_processing_remain_owed(store):
    client, uid, tasks = store
    reprocess.mark(uid, 'c', 'en', now=0)
    key, token = reprocess.key(uid, 'c'), tasks[-1]['task_token']
    with pytest.raises(RuntimeError):
        reprocess.run(key, token, Mock(side_effect=RuntimeError('worker dies')), now=600)
    assert reprocess.run(key, token, Mock(), now=601) == 'busy'
    reprocess.sweep(now=600 + reprocess.LEASE_SECONDS)
    token = next(row['task_token'] for row in reversed(tasks) if row['uid'] == uid)
    reprocess.run(key, token, lambda *args: reprocess.mark(*args, now=2401), now=2400)
    assert client.collection(reprocess.COLLECTION).document(key).get().exists
    process = Mock()
    reprocess.run(key, tasks[-1]['task_token'], process, now=3001)
    process.assert_called_once()
    assert not client.collection(reprocess.COLLECTION).document(key).get().exists


def test_l1_success_hash_never_marks_a_newer_transcript(store):
    client, uid, tasks = store
    conversation = SimpleNamespace(id='c', sync_content_revision=1)
    ref = client.collection('users').document(uid).collection('conversations').document('c')
    try:
        ref.set({'sync_content_revision': 1})
        assert dedupe.l1_succeeded(uid, conversation, 'old-success')
        assert ref.get().to_dict()[dedupe.L1_HASH] == 'old-success'
        ref.update({'sync_content_revision': 2})
        assert not dedupe.l1_succeeded(uid, conversation, 'stale-result')
        assert ref.get().to_dict()[dedupe.L1_HASH] == 'old-success'
        ref.delete()
        assert not dedupe.l1_succeeded(uid, conversation, 'deleted-result')
        assert not ref.get().exists
    finally:
        ref.delete()


def test_loopback_worker_http_runs_current_transcript_once(store, monkeypatch):
    """Serve the production router; replace OIDC/provider leaves, retain real outbox IO."""
    import socket
    import threading
    import time

    from fastapi import FastAPI, Header, HTTPException
    import httpx
    import uvicorn
    from routers import sync as sync_router
    from utils.enrichment import callback

    client, uid, tasks = store
    processed = []
    transcript = client.collection('users').document(uid).collection('conversations').document('http')
    transcript.set({'transcript': 'first'})

    def provider_leaf(user_id, conversation_id, language):
        processed.append(transcript.get().to_dict()['transcript'])

    async def authenticate(authorization: str = Header('')):
        if authorization != 'Bearer local-emulator-task':
            raise HTTPException(status_code=403)
        return 0

    monkeypatch.setattr(callback, 'enrich_conversation', provider_leaf)
    monkeypatch.setattr(sync_router.uid_sequencer, 'production_fence_mode', lambda: None)
    app = FastAPI()
    app.include_router(sync_router.router)
    app.dependency_overrides[sync_router.verify_cloud_tasks_oidc] = authenticate
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        for part in ('first', 'first second', 'first second third'):
            transcript.update({'transcript': part})
            reprocess.mark(uid, 'http', 'en', now=time.time() - 601)
        assert len(tasks) == 1
        payload = {'kind': 'sync_reprocess', 'key': reprocess.key(uid, 'http'), 'task_token': tasks[-1]['task_token']}
        with httpx.Client(base_url=f'http://127.0.0.1:{port}') as http:
            denied = http.post('/v2/sync-jobs/run', json=payload)
            assert denied.status_code == 403
            headers = {'Authorization': 'Bearer local-emulator-task'}
            invalid = http.post('/v2/sync-jobs/run', json={'kind': 'sync_reprocess'}, headers=headers)
            assert invalid.status_code == 400
            result = http.post('/v2/sync-jobs/run', json=payload, headers=headers)
            assert result.status_code == 200 and result.json() == {'status': 'processed'}
            replay = http.post('/v2/sync-jobs/run', json=payload, headers=headers)
            assert replay.status_code == 200 and replay.json() == {'status': 'stale'}
            assert processed == ['first second third']
            transcript.update({'transcript': 'first second third fourth'})
            reprocess.mark(uid, 'http', 'en', now=time.time() - 601)
            payload['task_token'] = tasks[-1]['task_token']
            result = http.post('/v2/sync-jobs/run', json=payload, headers=headers)
            assert result.status_code == 200 and result.json() == {'status': 'processed'}
            assert processed == ['first second third', 'first second third fourth']
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        transcript.delete()


def test_flag_off_success_invalidates_an_older_l1_checkpoint(store, monkeypatch):
    client, uid, _ = store
    conversation = SimpleNamespace(id='l1-rollback', sync_content_revision=1)
    ref = client.collection('users').document(uid).collection('conversations').document(conversation.id)
    try:
        ref.set({'sync_content_revision': 1, dedupe.L1_HASH: 'input-a'})
        monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false')
        assert dedupe.l1_succeeded(uid, conversation, None)
        assert not ref.get().to_dict().get(dedupe.L1_HASH)
    finally:
        ref.delete()
