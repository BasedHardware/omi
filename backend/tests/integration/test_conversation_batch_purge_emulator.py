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
from datetime import timedelta
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


def test_deleting_parked_jobs_retires_hold_owner_exactly_once(plane):
    from database.batch_pipeline_purge import _delete_job

    holds = plane.client.collection('batch_pipeline_prod_allowance_holds').document(plane.key)
    holds.set({'owner_key': plane.key, 'owner_id': plane.uid, 'held_count': 2, 'active': True, 'revision': 2})
    jobs = plane.client.collection('batch_pipeline_prod_jobs')
    for index in range(2):
        ref = jobs.document(f'held-{index}')
        ref.set(
            {
                'owner_id': plane.uid,
                'owner_key': plane.key,
                'priority': 2,
                'state': 'allowance_held',
                'conversation_id': f'conversation-{index}',
            }
        )
        snapshot = ref.get()
        _delete_job(plane.client, 'batch_pipeline_prod', snapshot, retain_ordering=True)
        assert holds.get().to_dict()['held_count'] == 1 - index
        assert holds.get().to_dict()['active'] is (index == 0)
        # A repeated purge of the same snapshot cannot spend the count twice.
        _delete_job(plane.client, 'batch_pipeline_prod', snapshot, retain_ordering=True)
        assert holds.get().to_dict()['held_count'] == 1 - index


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
    statuses, errors = [], []

    def delete(cid):
        try:
            with TestClient(route.app) as client:
                statuses.append(client.delete(f'/v1/conversations/{cid}?cascade=true').status_code)
        except Exception as error:  # surface, don't drop, a thread's failure
            errors.append(f'{type(error).__name__}: {error}')

    threads = [threading.Thread(target=delete, args=(cid,)) for cid in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert statuses == [204] * 6, errors
    # Hidden at once: erased in the request, or accepted behind a peer (row marked deleted).
    for cid in ids:
        row = plane.client.document(f'users/{plane.uid}/conversations/{cid}').get()
        assert not row.exists or row.to_dict().get('deleted') is True
    _drain_erasures(monkeypatch, route)
    assert not any(_exists(plane, 'users', plane.uid, 'conversations', cid) for cid in ids)


def _drain_erasures(monkeypatch, route, passes=30):
    """Reconciler passes plus the consumer running each dispatched erasure, until none is owed."""
    from database import conversation_batch_purge_jobs as purge_jobs
    from utils.conversations import deletion_batch_purge

    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    outcomes = []
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    for _ in range(passes):
        sent = []
        monkeypatch.setattr(
            deletion_batch_purge,
            'enqueue_conversation_batch_purge',
            lambda job, gen, erasure=False: sent.append((job, gen)) if erasure else None,
        )
        future = purge_jobs._now() + timedelta(hours=2)  # every spread/busy timer has elapsed
        monkeypatch.setattr(purge_jobs, '_now', lambda: future)
        deletion_batch_purge.reconcile_conversation_batch_purges()
        if not sent:
            break
        for job, gen in sent:
            outcomes.append(purge_jobs.run_erasure_job(job, gen, erase=route.routes.erase_accepted_conversation))
    return outcomes


def test_53_same_second_deletes_are_accepted_and_erased_in_order_on_real_transactions(monkeypatch, plane, route):
    """Prod 2026-11-12 shape: one phone sent 53 cascade deletes in the same second."""
    from database import conversation_batch_purge_jobs as purge_jobs

    original = route.routes.delete_conversation_and_frame_evidence
    inside, peak = [0], [0]
    lock = threading.Lock()

    def slower(*args, **kwargs):
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        try:
            time.sleep(0.3)  # in-gate work so the burst genuinely contends
            return original(*args, **kwargs)
        finally:
            with lock:
                inside[0] -= 1

    monkeypatch.setattr(route.routes, 'delete_conversation_and_frame_evidence', slower)
    ids = [f'conv-{index}-{uuid4().hex[:6]}' for index in range(53)]
    for cid in ids:
        _conversation(plane, cid)
    keep = f'keep-{uuid4().hex[:6]}'
    _conversation(plane, keep)
    statuses, elapsed, errors = [], [], []
    start = threading.Barrier(len(ids))

    def delete(cid):
        try:
            with TestClient(route.app) as client:
                start.wait()
                began = time.monotonic()
                statuses.append(client.delete(f'/v1/conversations/{cid}?cascade=true').status_code)
                elapsed.append(time.monotonic() - began)
        except Exception as error:  # surface, don't drop, a thread's failure
            errors.append(f'{type(error).__name__}: {error}')

    threads = [threading.Thread(target=delete, args=(cid,)) for cid in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    assert statuses == [204] * 53, errors
    assert max(elapsed) < 5.0, sorted(elapsed)[-5:]  # serialized: 53 x >=0.3 s, and 409 past 20 s
    accepted = []
    for cid in ids:
        assert _exists(plane, 'users', plane.uid, 'deleted_conversations', cid)
        row = plane.client.document(f'users/{plane.uid}/conversations/{cid}').get()
        assert not row.exists or row.to_dict().get('deleted') is True
        if (
            plane.client.collection(purge_jobs.ERASURE_COLLECTION)
            .document(purge_jobs.erasure_job_id(plane.uid, cid))
            .get()
            .exists
        ):
            accepted.append(cid)
    assert accepted, 'the burst must exercise the accept path'

    outcomes = _drain_erasures(monkeypatch, route)

    assert outcomes.count('erased') == len(accepted), outcomes
    assert not any(_exists(plane, 'users', plane.uid, 'conversations', cid) for cid in ids)
    assert _exists(plane, 'users', plane.uid, 'conversations', keep)
    assert peak[0] == 1, 'two same-account cascades erased inside the account gate at once'
    assert not any(
        plane.client.collection(purge_jobs.ERASURE_COLLECTION)
        .document(purge_jobs.erasure_job_id(plane.uid, cid))
        .get()
        .exists
        for cid in ids
    )
    for cid in ids:  # every erasure armed its batch purge next to the tombstone
        assert plane.client.collection(purge_jobs.COLLECTION).document(purge_jobs.job_id(plane.uid, cid)).get().exists


def test_hold_after_acceptance_keeps_the_conversation_hidden_and_retained(monkeypatch, plane, route):
    from database import conversation_batch_purge_jobs as purge_jobs
    from database import legal_holds

    cid = f'conv-{uuid4().hex[:8]}'
    _conversation(plane, cid)
    legal_holds.acquire_destructive_operation(plane.uid, kind='explicit_memory_deletion', token='peer-delete')
    with TestClient(route.app) as client:
        assert client.delete(f'/v1/conversations/{cid}?cascade=true').status_code == 204
    legal_holds.finish_destructive_operation(
        plane.uid, kind='explicit_memory_deletion', token='peer-delete', outcome='completed'
    )
    legal_holds.place_legal_hold(plane.uid, issuer='legal_hold_service')

    assert _drain_erasures(monkeypatch, route, passes=1) == ['held']
    row = plane.client.document(f'users/{plane.uid}/conversations/{cid}').get()
    assert row.exists and row.to_dict()['deleted'] is True  # hidden, retained under the hold
    owed = plane.client.collection(purge_jobs.ERASURE_COLLECTION).document(purge_jobs.erasure_job_id(plane.uid, cid))
    assert owed.get().to_dict()['last_outcome'] == 'held'


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
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    monkeypatch.setattr(
        deletion_batch_purge,
        'enqueue_conversation_batch_purge',
        lambda job, gen, erasure=False: None if erasure else sent.append((job, gen)),
    )
    deletion_batch_purge.reconcile_conversation_batch_purges()
    return sent


def _delete(plane, route, cid):
    _conversation(plane, cid)
    with TestClient(route.app) as client:
        assert client.delete(f'/v1/conversations/{cid}?cascade=true').status_code == 204


def _quick(job, generation, **kwargs):
    from database import conversation_batch_purge_jobs as purge_jobs

    kwargs.setdefault('sleep', lambda seconds: None)
    return purge_jobs.run_job(job, generation, **kwargs)


def _owed(plane, job):
    from database import conversation_batch_purge_jobs as purge_jobs

    return list(plane.client.collection(purge_jobs.COLLECTION).document(job).collection('segments').stream())


def _redrive(monkeypatch, plane, job):
    from database import conversation_batch_purge_jobs as purge_jobs

    plane.client.collection(purge_jobs.COLLECTION).document(job).update({'due_at': purge_jobs._now()})
    return _reconcile(monkeypatch)


def test_reconciled_purge_erases_only_its_conversation_then_clears(monkeypatch, plane, route):
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=3, others=150)
    [(job, generation)] = _reconcile(monkeypatch)
    assert _quick(job, generation) == 'purged'
    assert _results_left(plane, cid) == 0
    others = list(plane.client.collection('batch_pipeline_prod_results').where('owner_key', '==', plane.key).stream())
    assert sum(1 for row in others if (row.to_dict() or {}).get('conversation_id', '').startswith('other-')) == 150
    assert not plane.client.collection(purge_jobs.COLLECTION).document(job).get().exists
    assert _owed(plane, job) == []
    assert _quick(job, generation) == 'missing'


def test_hold_between_purge_units_stops_erasure_until_release(monkeypatch, plane, route):
    from database import legal_holds

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=150, others=0)
    units = []

    def hold_after_two_units(_seconds):
        units.append(True)
        if len(units) == 2:  # between units: no gate held
            legal_holds.place_legal_hold(plane.uid, issuer='admin', active=True)

    [(job, generation)] = _reconcile(monkeypatch)
    assert _quick(job, generation, sleep=hold_after_two_units) == 'held'
    assert _results_left(plane, cid) == 130, 'erased after the hold committed'
    assert len(_owed(plane, job)) == 130  # remaining segment work is durable

    legal_holds.place_legal_hold(plane.uid, issuer='admin', active=False)
    [(job, generation)] = _redrive(monkeypatch, plane, job)
    assert generation == 2
    assert _quick(job, generation) == 'purged'
    assert _results_left(plane, cid) == 0 and _owed(plane, job) == []


def test_hold_before_artifact_unit_resume_erases_segment_only_artifact(monkeypatch, plane, route):
    """Reviewer round-2 resume probe: the artifact carries only its segment id."""
    from database import batch_pipeline_purge, legal_holds
    from database import conversation_batch_purge_jobs as purge_jobs
    from utils.batch_pipeline import retention

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=1, others=0)
    segment = f'{plane.uid}-r0000'
    artifact = plane.client.collection('batch_pipeline_prod_artifacts').document(f'{segment}-audio')
    uri = f'gs://synthetic/batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/object'
    artifact.set(
        {
            'owner_key': plane.key,
            'owner_id': plane.uid,
            'segment_id': segment,
            'conversation_ids': [],
            'uri': uri,
            'kind': 'audio',
        }
    )
    objects_deleted = []
    monkeypatch.setattr(
        retention,
        'delete_batch_object',
        lambda uid, uri, timeout=None, storage_client=None: objects_deleted.append(uri),
    )
    real_page = batch_pipeline_purge.queries.owner_documents
    held = []

    def page_then_hold(client, namespace, table, key, *, after=None):
        rows = real_page(client, namespace, table, key, after=after)
        if namespace == 'batch_pipeline_prod' and table == 'artifacts' and rows and not held:
            legal_holds.place_legal_hold(plane.uid, issuer='admin', active=True)
            held.append(True)
        return rows

    monkeypatch.setattr(batch_pipeline_purge.queries, 'owner_documents', page_then_hold)
    [(job, generation)] = _reconcile(monkeypatch)
    assert _quick(job, generation) == 'held'
    assert artifact.get().exists and objects_deleted == []
    assert [row.to_dict()['segment_id'] for row in _owed(plane, job)] == [segment]

    monkeypatch.setattr(batch_pipeline_purge.queries, 'owner_documents', real_page)
    legal_holds.place_legal_hold(plane.uid, issuer='admin', active=False)
    [(job, generation)] = _redrive(monkeypatch, plane, job)
    assert _quick(job, generation) == 'purged'
    assert not artifact.get().exists and objects_deleted == [uri]
    assert _results_left(plane, cid) == 0
    assert not plane.client.collection(purge_jobs.COLLECTION).document(job).get().exists


def test_checkpointed_runs_resume_from_real_cursors_until_done(monkeypatch, plane, route):
    from database import batch_pipeline_purge
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=0, others=250)  # a long unmatched prefix ...
    mine = plane.client.collection('batch_pipeline_prod_results').document(f'{plane.uid}-zzzz')
    mine.set({'owner_key': plane.key, 'conversation_id': cid, 'segment_id': f'{plane.uid}-zzzz'})  # ... then ours
    real_page = batch_pipeline_purge.queries.owner_documents
    cursors = []

    def recording_page(client, namespace, table, key, *, after=None):
        if namespace == 'batch_pipeline_prod' and table == 'results':
            cursors.append(after.id if after is not None else None)
        return real_page(client, namespace, table, key, after=after)

    monkeypatch.setattr(batch_pipeline_purge.queries, 'owner_documents', recording_page)
    [(job, generation)] = _reconcile(monkeypatch)
    outcomes = []
    for _ in range(80):  # one checkpoint per run: every page, table and phase boundary
        outcomes.append(_quick(job, generation, budget_seconds=0))  # hand off at every checkpoint
        if outcomes[-1] == 'purged':
            break
        [(job, generation)] = _reconcile(monkeypatch)
    assert outcomes[-1] == 'purged' and 'checkpointed' in outcomes
    assert cursors[:3] == [None, f'{plane.uid}-r0099', f'{plane.uid}-r0199']  # each run resumed after the last
    assert not mine.get().to_dict().get('conversation_id')
    assert not plane.client.collection(purge_jobs.COLLECTION).document(job).get().exists


def test_account_wipe_gate_fails_the_run_retryably_and_keeps_the_obligation(monkeypatch, plane, route):
    from database import legal_holds
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _seed_batch(plane, cid, mine=2, others=5)
    legal_holds.acquire_destructive_operation(plane.uid, kind='account_deletion', token='synthetic-wipe')
    [(job, generation)] = _reconcile(monkeypatch)
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _quick(job, generation)
    assert _results_left(plane, cid) == 2
    row = plane.client.collection(purge_jobs.COLLECTION).document(job).get().to_dict()
    assert row['last_outcome'] == 'failed' and row['progress']['phase'] == 'segments'
    assert len(_owed(plane, job)) == 2


def _scripted_storage(monkeypatch, plane, statuses, *, seconds=4.5):
    """The real google-cloud-storage SDK; only its HTTP responses are scripted."""
    import requests
    from google.cloud import storage
    from utils.other import local_storage

    client = storage.Client(project='demo-storage-sdk', credentials=AnonymousCredentials())
    calls = []

    def http(method, url, headers, data, target_object, timeout):
        calls.append(timeout)
        time.sleep(seconds)
        response = requests.Response()
        response.status_code = statuses[min(len(calls), len(statuses)) - 1]
        response._content = b'{"error": {"message": "scripted transient storage outage"}}'
        if response.status_code == 204:
            response._content = b''
        response.headers['content-type'] = 'application/json'
        response.request = requests.Request(method, url).prepare()
        return response

    monkeypatch.setattr(client._connection, '_do_request', http)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: client)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-bucket')
    return calls


def test_storage_sdk_retries_cannot_hold_the_gate_past_a_foreground_delete(monkeypatch, plane, route):
    """Reviewer round-3 probe: four 503s then 204, 4.5 s each, used to hold the gate 33 s (foreground 409)."""
    from database import conversation_batch_purge_jobs as purge_jobs

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _conversation(plane, 'foreground-conversation')
    calls = _scripted_storage(monkeypatch, plane, [503, 503, 503, 503, 204])
    uri = f'gs://synthetic-bucket/batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/test.enc#123'
    artifact = plane.client.collection('batch_pipeline_prod_artifacts').document('artifact-1')
    artifact.set({'owner_key': plane.key, 'owner_id': plane.uid, 'conversation_ids': [cid], 'uri': uri})
    [(job, generation)] = _reconcile(monkeypatch)
    outcomes, errors = [], []

    def background():
        try:
            outcomes.append(_quick(job, generation))
        except Exception as error:
            errors.append(type(error).__name__)

    worker = threading.Thread(target=background)
    worker.start()
    for _ in range(100):  # wait until the purge is inside its storage call, holding the gate
        if calls:
            break
        time.sleep(0.05)
    with TestClient(route.app) as foreground:
        started = time.monotonic()
        response = foreground.delete('/v1/conversations/foreground-conversation?cascade=true')
        waited = time.monotonic() - started
    worker.join(timeout=60)
    assert response.status_code == 204, waited
    assert waited < 10.0
    # One bounded attempt, no SDK retry; the unit failed retryably and released the gate.
    assert len(calls) == 1 and calls[0] <= 5.0
    assert errors == ['ServiceUnavailable'] and outcomes == []
    assert artifact.get().exists
    row = plane.client.collection(purge_jobs.COLLECTION).document(job).get().to_dict()
    assert row['last_outcome'] == 'failed'  # the debt is kept

    # Storage recovers: the queue's retry of the same generation completes the purge.
    calls_after = _scripted_storage(monkeypatch, plane, [204], seconds=0.0)
    assert _quick(job, generation) == 'purged'
    assert calls_after and not artifact.get().exists


def test_real_unit_gate_expiry_frees_foreground_deletes_when_release_is_lost(monkeypatch, plane, route):
    from database import legal_holds

    _conversation(plane, 'foreground-conversation')
    monkeypatch.setattr(legal_holds, 'UNIT_EXPIRY_SECONDS', 1.0)
    monkeypatch.setattr(legal_holds, 'UNIT_HOLD_SECONDS', 0.8)
    monkeypatch.setattr(legal_holds, 'UNIT_BODY_SECONDS', 0.5)
    monkeypatch.setattr(legal_holds, '_release_bounded_unit', lambda *args, **kwargs: None)  # release never lands
    with legal_holds.bounded_destructive_unit(plane.uid):
        pass
    gate = plane.client.document(f'legal_hold_deletion_gates/{plane.uid}').get().to_dict()
    assert gate['state'] == 'running' and gate['expires_at']
    with TestClient(route.app) as foreground:
        started = time.monotonic()
        response = foreground.delete('/v1/conversations/foreground-conversation?cascade=true')
        waited = time.monotonic() - started
    assert response.status_code == 204
    assert waited < 5.0


def test_real_firestore_rpc_past_the_unit_deadline_is_not_sent(plane):
    from database import rpc_deadline

    rpc_deadline.bind_firestore_client(plane.client)
    ref = plane.client.collection('synthetic_deadline').document('d1')
    with rpc_deadline.rpc_deadline(rpc_deadline.now() - 0.001):
        with pytest.raises(rpc_deadline.RpcDeadlineExceeded):
            ref.set({'erased': True})
    with rpc_deadline.rpc_deadline(rpc_deadline.now() + 5):
        ref.set({'erased': True})  # one bounded attempt on the real client
    assert ref.get().to_dict() == {'erased': True}


def test_slow_remote_erasure_keeps_the_gate_until_it_resolves_real_transport(monkeypatch, plane, route):
    """Reviewer round-4 probe as a regression: a slowly progressing storage response outlives the unit's
    10 s expiry. Real google-cloud-storage SDK and requests transport over a loopback socket, real gate,
    real hold writer, real public route. The gate must not change hands, nor a hold commit, before the
    erasure's outcome is known."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from google.cloud import storage
    from database import legal_holds
    from utils.other import local_storage

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _conversation(plane, 'foreground-conversation')
    entered, erased_at, timeline = threading.Event(), {}, {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_DELETE(self):
            timeline['http_started'] = time.monotonic()
            entered.set()
            self.wfile.write(b'HTTP/1.1 204 No Content\r\nX-Progress: ')
            self.wfile.flush()
            for _ in range(13):  # progress below the socket read timeout, past the unit expiry
                time.sleep(1)
                self.wfile.write(b'x')
                self.wfile.flush()
            erased_at['t'] = time.monotonic()  # the remote side effect lands here
            self.wfile.write(b'\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            self.wfile.flush()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = storage.Client(
        project='demo-slow-http',
        credentials=AnonymousCredentials(),
        client_options={'api_endpoint': f'http://127.0.0.1:{server.server_port}'},
    )
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: client)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-bucket')
    uri = f'gs://synthetic-bucket/batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/a.enc#123'
    artifact = plane.client.collection('batch_pipeline_prod_artifacts').document('artifact-1')
    artifact.set({'owner_key': plane.key, 'owner_id': plane.uid, 'conversation_ids': [cid], 'uri': uri})
    [(job, generation)] = _reconcile(monkeypatch)
    errors = []
    worker = threading.Thread(target=lambda: _run_capturing(job, generation, errors))
    try:
        worker.start()
        assert entered.wait(10)
        time.sleep(10.5)  # past the unit gate's 10 s expiry, request still in flight
        hold_attempt = {}
        try:
            legal_holds.place_legal_hold(plane.uid, issuer='admin')
            hold_attempt['committed_at'] = time.monotonic()
        except legal_holds.DestructiveOperationInProgress:
            hold_attempt['rejected_at'] = time.monotonic()
        with TestClient(route.app) as foreground:
            response = foreground.delete('/v1/conversations/foreground-conversation?cascade=true')
        timeline['foreground_done'] = time.monotonic()
        # The busy gate accepts the foreground delete without erasing anything: hidden, owed, retained.
        row = plane.client.document(f'users/{plane.uid}/conversations/foreground-conversation').get()
        erased_before_resolution = not row.exists
        worker.join(20)
        assert 'rejected_at' in hold_attempt, 'a hold committed while the erasure was unresolved'
        assert response.status_code == 204
        assert not erased_before_resolution, 'the foreground erased while the remote erasure was unresolved'
        assert row.to_dict()['deleted'] is True
        legal_holds.place_legal_hold(plane.uid, issuer='admin')  # now it can, and nothing erases after it
        assert not worker.is_alive()
        assert _drain_erasures(monkeypatch, route, passes=1) == ['held']
        assert _exists(plane, 'users', plane.uid, 'conversations', 'foreground-conversation')
    finally:
        worker.join(20)
        server.shutdown()
        server.server_close()
        client.close()


def _run_capturing(job, generation, errors):
    try:
        _quick(job, generation)
    except BaseException as error:  # the late response overran the unit: retryable failure, debt kept
        errors.append(type(error).__name__)


def test_unanswered_delete_is_not_settled_by_a_retry_503_real_transport(monkeypatch, plane, route):
    """Round-5 item 1 on the real transport: the first DELETE is never answered (client times out) but
    lands later; the retries get 503. The gate must stay held, so no hold commits before that erasure,
    and only a later definitive 404 for the same pinned generation settles it."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from google.cloud import storage
    from database import conversation_batch_purge_jobs as purge_jobs
    from database import legal_holds
    from utils.other import local_storage

    cid = f'conv-{uuid4().hex[:8]}'
    _delete(plane, route, cid)
    _conversation(plane, 'foreground-conversation')
    first_landed, lock, calls = threading.Event(), threading.Lock(), []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_DELETE(self):
            with lock:
                calls.append(time.monotonic())
                number = len(calls)
            if number == 1:
                time.sleep(8)  # the client gives up; the server operation continues
                first_landed.set()
                status, body = 204, b''
            elif first_landed.is_set():
                status, body = 404, b'{"error": {"code": 404, "message": "gone"}}'
            else:
                status, body = 503, b'{"error": {"code": 503, "message": "unavailable"}}'
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = storage.Client(
        project='demo-unanswered',
        credentials=AnonymousCredentials(),
        client_options={'api_endpoint': f'http://127.0.0.1:{server.server_port}'},
    )
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: client)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-bucket')
    uri = f'gs://synthetic-bucket/batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/a.enc#123'
    artifact = plane.client.collection('batch_pipeline_prod_artifacts').document('artifact-1')
    artifact.set({'owner_key': plane.key, 'owner_id': plane.uid, 'conversation_ids': [cid], 'uri': uri})
    gate_ref = plane.client.document(f'legal_hold_deletion_gates/{plane.uid}')
    try:
        [(job, generation)] = _reconcile(monkeypatch)
        with pytest.raises(Exception) as unanswered:
            _quick(job, generation)
        assert type(unanswered.value).__name__ in {'ReadTimeout', 'ConnectionError', 'Timeout'}
        assert len(calls) == 1 + legal_holds.UNIT_REMOTE_RESOLVE_ATTEMPTS  # retries answered 503
        gate = gate_ref.get().to_dict()
        assert gate['state'] == 'running' and gate['remote_inflight'] is True  # not settled by a 503
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            legal_holds.place_legal_hold(plane.uid, issuer='admin')  # no hold before the late erasure
        assert first_landed.wait(10)

        # The next run settles it: the same pinned delete now answers 404, the generation is gone.
        gate_ref.update({'remote_inflight_at': gate['remote_inflight_at'] - timedelta(minutes=5)})
        plane.client.collection(purge_jobs.COLLECTION).document(job).update({'due_at': purge_jobs._now()})
        [(job, generation)] = _reconcile(monkeypatch)
        assert _quick(job, generation) == 'purged'
        assert not artifact.get().exists
        with TestClient(route.app) as foreground:
            assert foreground.delete('/v1/conversations/foreground-conversation?cascade=true').status_code == 204
        legal_holds.place_legal_hold(plane.uid, issuer='admin')  # after the erasure, not before it
    finally:
        server.shutdown()
        server.server_close()
        client.close()
