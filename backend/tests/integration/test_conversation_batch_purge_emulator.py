"""Conversation delete serialization and durable batch purge on the Firestore emulator.

Real transactions for the account gate, the hold writer, the tombstone+obligation
batch and the obligation lifecycle. Storage/vector side effects are stubbed.
Run: firebase emulators:exec --only firestore --project demo-omi \
  "cd backend && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python -m pytest \
  tests/integration/test_conversation_batch_purge_emulator.py"
"""

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import FailedPrecondition, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from prometheus_client import REGISTRY

from database import batch_privacy_late_intents as late_intents, batch_privacy_late_sweeps as late_sweeps
from database.batch_pipeline_store import FirestoreStore
from config.firestore_read_levers import _parse as parse_levers
from config.policy import BatchUnitPolicy
from utils import funded_processing, stt_cap_dispatch
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from dataclasses import asdict, replace
from utils.stt import batch_language
from utils.other.local_storage import LocalBlob, LocalStorageClient

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures('delayed_execution')]
ERASURE_ON = '{"bpp_late_erasure_execute":100}'


@pytest.fixture
def delayed_execution(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', ERASURE_ON)


@pytest.fixture
def plane(monkeypatch, tmp_path):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    # WAL orphan sweeps use their own imported factory. Keep storage synthetic
    # even when a test separately replaces the artifact-delete transport.
    from utils.batch_pipeline import record_wal_erasure
    from utils.other import local_storage

    objects = local_storage.LocalStorageClient(tmp_path / 'wal-storage')
    monkeypatch.setattr(record_wal_erasure, 'create_storage_client', lambda: objects)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: objects)
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


def test_purge_erases_intake_parked_unit_and_debits_owner_once(plane, monkeypatch):
    from config.policy import BatchUnitPolicy
    from database.batch_pipeline_allowance_hold import IntakeRefusal
    from database.batch_pipeline_intake import admit
    from database import batch_pipeline_purge
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_ALLOWANCE_INTAKE_PARK_ENABLED', raising=False)
    namespace = 'batch_pipeline_test_allowance_purge'
    store = FirestoreStore(namespace, firestore_client=plane.client)
    now = time.time()
    cid = 'intake-capture'
    _conversation(plane, cid)
    item = WorkItem(
        'held',
        plane.uid,
        now - 30,
        'gs://synthetic/held',
        30,
        Priority.FRESH,
        conversation_id=cid,
        privacy_generation=0,
        requires_compute_admission=True,
    )
    binding = ProjectionBinding(plane.uid, 'bp_held', 'intake-content', ('held',))
    assert (
        admit(
            store,
            [item],
            binding,
            now,
            namespace=namespace,
            policy=BatchUnitPolicy(batch_enabled=True),
            intake={'lane': 'fresh', 'owner_id': plane.uid, 'owner_key': plane.key, 'segment_ids': ['held']},
            intake_refusal=IntakeRefusal(now, (None, None)),
        )['outcome']
        == 'batch'
    )
    job = plane.client.collection(f'{namespace}_jobs').document('held')
    held = plane.client.collection(f'{namespace}_allowance_holds').document(plane.key)
    snapshot = job.get()
    assert snapshot.to_dict()['state'] == 'allowance_held'
    assert held.get().to_dict()['held_count'] == 1

    plane.client.document(f'users/{plane.uid}/deleted_conversations/{cid}').set({'deleted': True})
    monkeypatch.setattr(batch_pipeline_purge, 'purge_jobstore_owner', MagicMock())
    delete_uri = MagicMock()
    for _ in range(2):
        batch_pipeline_purge.purge_batch_owner(
            plane.uid,
            firestore_client=plane.client,
            conversation_id=cid,
            namespaces=(namespace,),
            delete_uri=delete_uri,
        )
        owner = held.get().to_dict()
        assert owner['held_count'] == 0 and not owner['active']
        assert not job.get().exists
    delete_uri.assert_called_once_with(plane.uid, item.audio_uri)


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


def test_post_window_sweep_erases_a_late_commit_and_keeps_unrelated_rows(plane, route, monkeypatch):
    from database import conversation_batch_purge_jobs as jobs
    from database import privacy_check_metrics

    cid = 'synthetic-after-first-sweep'
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    _delete(plane, route, cid)
    [(immediate, generation)] = _reconcile(monkeypatch)
    assert _quick(immediate, generation) == 'purged'
    assert not plane.client.collection(jobs.COLLECTION).document(immediate).get().exists

    # A write from an earlier in-flight attempt becomes visible after the
    # first sweep has already removed its job. The delayed job is independent.
    _seed_batch(plane, cid, mine=1, others=1)
    assert _results_left(plane, cid) == 1
    delayed, _ = jobs.post_window_job(plane.client, plane.uid, cid)
    row = delayed.get().to_dict()
    assert row['post_window'] is True
    assert _reconcile(monkeypatch) == []
    assert 'due_at' not in row
    eligible_at = max(row['post_window_due_at'], row['post_window_started_at'] + jobs.POST_WINDOW_DELAY)
    monkeypatch.setattr(jobs, '_now', lambda: eligible_at + timedelta(seconds=1))
    assert _reconcile(monkeypatch) == []
    assert _quick(delayed.id, 0) == 'superseded'
    assert delayed.get().exists and _results_left(plane, cid) == 1
    assert _pending_count('conversation_execution') == 1
    rollback = '{"bpp_tokenless_write_cache":0,"bpp_late_erasure_execute":100}'
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', rollback)
    assert parse_levers(rollback) == {'bpp_tokenless_write_cache': 0, 'bpp_late_erasure_execute': 100}
    [(job, generation)] = _reconcile(monkeypatch)
    assert job == delayed.id
    completed = privacy_check_metrics.POST_WINDOW_SWEEPS.labels('conversation_deleted')
    before = completed._value.get()
    assert _quick(job, generation) == 'purged'
    assert _results_left(plane, cid) == 0
    assert _results_left(plane, 'other-1') == 1
    assert completed._value.get() == before + 1
    assert _quick(job, generation) == 'missing'


@pytest.mark.parametrize(
    'policy',
    [
        'account_deleted',
        'data_protection',
        'recording_policy',
        'conversation_recording',
        'replaced_recording',
        'replaced_recording_without_sync',
    ],
)
def test_late_privacy_sweep_recovers_an_inflight_object(plane, monkeypatch, tmp_path, policy):
    from datetime import datetime, timezone

    from database import batch_privacy_late_intents as intents, batch_privacy_late_sweeps as sweeps
    from database import legal_holds, privacy_check_metrics as metrics
    from utils.other.local_storage import LocalStorageClient

    client, uid = plane.client, plane.uid
    scoped = policy in {'conversation_recording', 'replaced_recording', 'replaced_recording_without_sync'}
    reason = 'recording_policy' if scoped else policy
    storage = LocalStorageClient(tmp_path / 'late-purge')
    name = 'synthetic-late-batch'
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', name)
    monkeypatch.setattr(sweeps, 'create_storage_client', lambda: storage)
    mirrored = []

    def reconcile_postgres(namespace, owner):
        mirrored.append((namespace, owner))
        return 1

    monkeypatch.setattr(sweeps, 'purge_owner', reconcile_postgres)
    artifacts = client.collection('batch_pipeline_prod_artifacts')
    cid = 'synthetic-recording'
    pending = datetime.now(timezone.utc) + timedelta(minutes=30)

    def receipt(key, owner=uid, source=cid, record_origin=True):
        segment = f'synthetic-{key}'
        object_name = f'batch-pipeline/batch_pipeline_prod/owners/{plane.key}/results/{segment}/{uuid4().hex}.enc'
        ref = artifacts.document(key)
        ref.set(
            {
                'owner_key': plane.key,
                'owner_id': owner,
                'segment_id': segment,
                'conversation_ids': [source],
                'kind': 'results',
                'record_origin': record_origin,
                'record_lane_owner': 'batch_live_v1',
                'uri': f'gs://{name}/{object_name}',
                'write_pending_until': pending,
            }
        )
        return ref, storage.bucket(name).blob(object_name)

    old, stale = receipt('late')
    other, unrelated = receipt('unrelated', owner='another-synthetic-owner')
    unrelated.upload_from_string(b'outside the erasure scope')
    if reason == 'recording_policy':
        nonrecord, nonrecord_audio = receipt('nonrecord', record_origin=False)
        nonrecord_audio.upload_from_string(b'known non-recording audio')
    user = client.collection('users').document(uid)
    if scoped:
        conversation = user.collection('conversations').document(cid)
        conversation.set({'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True})
        other_source, other_audio = receipt('another-recording', source='another-synthetic-conversation')
        other_audio.upload_from_string(b'outside the recording scope')
        if policy == 'replaced_recording':
            conversation.set({'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': False})
        elif policy == 'replaced_recording_without_sync':
            conversation.set({'record_lane_owner': 'batch_live_v1'})
        else:
            conversation.update({'private_cloud_sync_enabled': False})
        # Even a re-enable before reconciliation cannot cancel the earlier obligation.
        conversation.update({'private_cloud_sync_enabled': True})
    elif reason == 'account_deleted':
        # Irreversible completion, after the primary wipe has removed the root.
        user.delete()
        client.collection('account_deletions').document(uid).set({'wipe_status': 'completed'})
    elif reason == 'data_protection':
        user.update({'data_protection_level': 'e2ee'})
    else:
        user.update({'private_cloud_sync_enabled': False})

    [intent] = list(client.collection(intents.COLLECTION).stream())
    data = intent.to_dict()
    assert data['reason'] == reason
    assert sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == (
        {} if reason == 'account_deleted' else {'scope_verified': 1}
    )

    # The delayed provider write lands after the privacy mutation, while the
    # original create-only receipt still predates the new policy.
    stale.upload_from_string(b'in-flight object')
    if reason != 'account_deleted':
        new, fresh = receipt('newer')
        fresh.upload_from_string(b'new-policy object')

    clock = [data['changed_at'] + intents.DELAY + timedelta(seconds=1)]
    monkeypatch.setattr(sweeps, '_now', lambda: clock[0])
    assert sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'waiting_for_upload': 1}
    assert stale.exists()

    clock[0] = pending + timedelta(seconds=10)
    legal_holds.place_legal_hold(uid, issuer='legal_hold_service', firestore_client=client)
    assert sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'held': 1}
    assert old.get().exists and stale.exists()
    legal_holds.place_legal_hold(uid, issuer='legal_hold_service', active=False, firestore_client=client)

    clock[0] += sweeps.HOLD_RETRY + timedelta(seconds=5)
    completed = metrics.POST_WINDOW_SWEEPS.labels(reason)
    before = completed._value.get()
    for _ in range(10):
        sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
        if not intent.reference.get().exists:
            break
        clock[0] += timedelta(seconds=10)

    assert not intent.reference.get().exists
    assert not old.get().exists and not stale.exists()
    assert other.get().exists and unrelated.exists()
    if reason != 'account_deleted':
        assert new.get().exists and fresh.exists()
    if scoped:
        assert other_source.get().exists and other_audio.exists()
    if reason == 'recording_policy':
        assert nonrecord.get().exists and nonrecord_audio.exists()
    assert ('batch_pipeline_prod', uid) in mirrored
    assert completed._value.get() == before + 1
    assert sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {}


@pytest.mark.parametrize(
    'origin,legacy',
    [(True, False), (True, True), (False, False)],
    ids=['native-provenance', 'missing-provenance', 'known-non-recording'],
)
def test_recording_revocation_recovers_crashed_pre_admission_upload(plane, monkeypatch, tmp_path, origin, legacy):
    client, uid = plane.client, plane.uid
    namespace, bucket = 'batch_pipeline_dev', 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'crashed-upload')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda namespace, owner: 0)
    user = client.collection('users').document(uid)
    user.update({'private_cloud_sync_enabled': True})
    cid = 'synthetic-recording'
    user.collection('conversations').document(cid).set(
        {'private_cloud_sync_enabled': True, **({'record_lane_owner': 'batch_live_v1'} if origin else {})}
    )
    store = FirestoreStore(namespace, firestore_client=client)
    artifacts = create_artifact_store(store, storage, bucket, b'x' * 32)
    item = WorkItem(
        'synthetic-unit', uid, 100, 'record:pending', 1, Priority.FRESH, conversation_id=cid, privacy_generation=0
    )
    receipt_collection = client.collection(f'{namespace}_artifacts')
    unit_job = client.collection(f'{namespace}_jobs').document(item.segment_id)

    class UploadProcessExited(BaseException):
        pass

    upload = LocalBlob.upload_from_file

    def revoke_during_upload(blob, file_obj, *args, **kwargs):
        assert not unit_job.get().exists
        [receipt] = receipt_collection.stream()
        assert receipt.get('record_origin') is origin
        if legacy:
            receipt.reference.update({'record_origin': firestore.DELETE_FIELD})
        assert not blob.exists()
        user.update({'private_cloud_sync_enabled': False})
        upload(blob, file_obj, *args, **kwargs)
        raise UploadProcessExited()

    monkeypatch.setattr(LocalBlob, 'upload_from_file', revoke_during_upload)
    with pytest.raises(UploadProcessExited):
        artifacts.stage_audio(
            item, b'synthetic audio', record_origin=origin, record_lane_owner='batch_live_v1' if origin else None
        )

    [receipt] = receipt_collection.stream()
    assert ('record_origin' in receipt.to_dict()) is not legacy
    [intent] = client.collection(late_intents.COLLECTION).stream()
    assert intent.get('reason') == 'recording_policy'
    assert not unit_job.get().exists
    blob = storage.bucket(bucket).blob(receipt.get('uri').removeprefix(f'gs://{bucket}/'))
    assert blob.exists()
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'scope_verified': 1}

    clock = [intent.get('changed_at') + late_intents.DELAY + timedelta(seconds=1)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    # The first page visits the empty prod-named namespace of this emulator.
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'progress': 1}
    clock[0] += late_sweeps.PAGE_RETRY
    expected = 'waiting_for_upload' if origin else 'progress'
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {expected: 1}
    assert blob.exists()

    clock[0] = receipt.get('write_pending_until') + timedelta(seconds=10)
    for _ in range(10):
        outcomes = late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
        assert 'retry' not in outcomes
        if outcomes == {'completed': 1}:
            break
        clock[0] += late_sweeps.PAGE_RETRY

    assert not intent.reference.get().exists
    assert receipt.reference.get().exists is (not origin)
    assert blob.exists() is (not origin)


@pytest.mark.parametrize('denied_at_commit', [True, False], ids=['opt-out', 'same-commit-restore'])
def test_audio_admission_preserves_recording_erasure_window(plane, monkeypatch, tmp_path, denied_at_commit):
    from utils.batch_pipeline.live import record_identity, register_recording
    from utils.batch_pipeline.record_provider import admit_record_units

    client, uid = plane.client, plane.uid
    namespace, bucket = 'batch_pipeline_dev', 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'admitted-audio')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda *_: 0)
    user = client.collection('users').document(uid)
    user.update({'private_cloud_sync_enabled': True})
    cid = 'synthetic-recording'
    row = {
        'id': cid,
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_audio_closed': True,
        'private_cloud_sync_enabled': True,
        'finished_at': datetime.now(timezone.utc),
    }
    user.collection('conversations').document(cid).set(row)
    store = FirestoreStore(namespace, firestore_client=client)
    assert register_recording(uid, row, store=store)
    content, segment = record_identity(uid, cid)
    binding = ProjectionBinding(
        uid,
        'bp_' + content,
        content,
        (segment,),
        target_conversation_id=cid,
        record_origin=True,
        native_record=True,
        language='en',
        private_cloud_sync_enabled=True,
    )
    item = WorkItem(
        segment, uid, time.time() - 10, 'record:pending', 1, Priority.FRESH, conversation_id=cid, privacy_generation=0
    )
    artifacts = create_artifact_store(store, storage, bucket, b'x' * 32)
    receipts = client.collection(f'{namespace}_artifacts')
    upload = LocalBlob.upload_from_file
    reserved = []

    def change_policy_before_object_lands(blob, file_obj, *args, **kwargs):
        [receipt] = receipts.stream()
        reserved.append(receipt)
        # Firestore's REQUEST_TIME has millisecond precision; separate it from reservation creation.
        time.sleep(0.005)
        batch = client.batch()
        batch.update(user, {'private_cloud_sync_enabled': False})
        if not denied_at_commit:
            batch.update(user, {'private_cloud_sync_enabled': True})
        batch.commit()
        assert not blob.exists()
        upload(blob, file_obj, *args, **kwargs)
        if denied_at_commit:
            user.update({'private_cloud_sync_enabled': True})

    monkeypatch.setattr(LocalBlob, 'upload_from_file', change_policy_before_object_lands)
    uri = artifacts.stage_audio(item, b'synthetic audio', record_origin=True, record_lane_owner='batch_live_v1')
    [before_admission] = reserved
    [intent] = client.collection(late_intents.COLLECTION).stream()
    changed_at = intent.get('changed_at')
    deadline = before_admission.get('write_pending_until')
    assert before_admission.create_time <= changed_at <= deadline
    assert (
        admit_record_units(
            store,
            [replace(item, audio_uri=uri)],
            binding,
            time.time(),
            namespace=namespace,
            policy=BatchUnitPolicy(batch_enabled=True),
            require_artifacts=True,
        )['outcome']
        == 'batch'
    )
    receipt = before_admission.reference
    assert 'write_pending_until' not in receipt.get().to_dict()
    blob = storage.bucket(bucket).blob(uri.removeprefix(f'gs://{bucket}/').split('#', 1)[0])
    assert blob.exists()

    clock = [changed_at + late_intents.DELAY + timedelta(seconds=1)]
    assert clock[0] < deadline
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    reconcile = late_sweeps.reconcile_batch_privacy_late_sweeps
    if denied_at_commit:
        assert reconcile(firestore_client=client) == {'scope_verified': 1}
        for _ in range(8):
            clock[0] += late_sweeps.PAGE_RETRY
            if reconcile(firestore_client=client) == {'completed': 1}:
                break
    else:
        assert reconcile(firestore_client=client) == {'superseded': 1}

    assert not intent.reference.get().exists
    assert blob.exists() is (not denied_at_commit)
    assert receipt.get().exists is (not denied_at_commit)


def test_existing_record_job_supplies_artifact_provenance_without_projection_binding(plane, monkeypatch, tmp_path):
    namespace = 'batch_pipeline_dev'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = FirestoreStore(namespace, firestore_client=plane.client)
    storage = LocalStorageClient(tmp_path / 'record-job-artifact')
    artifacts = create_artifact_store(store, storage, 'synthetic-late-batch', b'x' * 32)
    item = WorkItem('synthetic-unit', plane.uid, 100, 'record:pending', 1, Priority.FRESH, privacy_generation=0)
    plane.client.collection(f'{namespace}_jobs').document(item.segment_id).set(
        {'owner_id': plane.uid, 'record_origin': True}
    )

    artifacts.stage_audio(item, b'synthetic audio')

    [receipt] = plane.client.collection(f'{namespace}_artifacts').stream()
    assert receipt.get('record_origin') is True


@pytest.mark.parametrize('origin', [False, True])
async def test_sync_intake_persists_provenance_before_admission(plane, monkeypatch, tmp_path, origin):
    namespace = 'batch_pipeline_dev'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    monkeypatch.setattr(funded_processing, 'consent_allows', lambda *_: True)
    monkeypatch.setattr(stt_cap_dispatch, 'sync_allowed', lambda *a, **k: True)
    store = FirestoreStore(namespace, firestore_client=plane.client)
    storage = LocalStorageClient(tmp_path / 'sync-stage')
    artifacts = create_artifact_store(store, storage, 'synthetic-late-batch', b'x' * 32)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: artifacts)
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda *_: intake.LegacySyncMode.ON)
    monkeypatch.setattr(
        batch_language,
        'resolve_language',
        lambda *a, **k: SimpleNamespace(
            language='en', evidence='declared', confidence=1.0, parakeet_safe=True, probe_seconds=0
        ),
    )
    user = plane.client.collection('users').document(plane.uid)
    user.update({'language': 'en', 'private_cloud_sync_enabled': True})
    cid = 'synthetic-sync-capture'
    user.collection('conversations').document(cid).set(
        {'language': 'en', **({'record_lane_owner': 'batch_sync_v1'} if origin else {})}
    )

    class StopBeforeAdmission(BaseException):
        pass

    observed = {}

    def check_receipt(blob, file_obj, *args, **kwargs):
        [receipt] = plane.client.collection(f'{namespace}_artifacts').stream()
        observed['record_origin'] = receipt.get('record_origin')
        observed['job_exists'] = (
            plane.client.collection(f'{namespace}_jobs').document(receipt.get('segment_id')).get().exists
        )
        observed['object_exists'] = blob.exists()
        raise StopBeforeAdmission()

    monkeypatch.setattr(LocalBlob, 'upload_from_file', check_receipt)
    with pytest.raises(StopBeforeAdmission):
        await intake.accept_upload(
            uid=plane.uid,
            job_id='synthetic-sync',
            content_id='synthetic-sync',
            paths=[],
            lane='fresh',
            recording_age_seconds=0,
            source='desktop' if origin else 'omi',
            should_lock=False,
            conversation_id=cid,
            client_device_id=None,
            client_platform='ios',
            decode=lambda _: (unit for unit in (audio_unit(100, b'\x01\x00' * 16000),)),
            policy=BatchUnitPolicy(batch_enabled=True, live_record_enabled=origin),
        )
    assert observed == {'record_origin': origin, 'job_exists': False, 'object_exists': False}


@pytest.mark.parametrize('policy', [{'uses_custom_stt': True}, {'private_cloud_sync_enabled': False}])
@pytest.mark.parametrize('claim_after_edit', [False, True])
def test_ordinary_conversation_policy_edit_preserves_pending_unknown_artifact(
    plane, monkeypatch, tmp_path, policy, claim_after_edit
):
    client, uid = plane.client, plane.uid
    bucket = 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'ordinary-capture')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    mirror = MagicMock(return_value=0)
    monkeypatch.setattr(late_sweeps, 'purge_owner', mirror)
    cid = 'ordinary-sync-conversation'
    conversation = client.collection('users').document(uid).collection('conversations').document(cid)
    conversation.set({'private_cloud_sync_enabled': True})
    path = f'batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/unit/{uuid4().hex}.enc'
    blob = storage.bucket(bucket).blob(path)
    blob.upload_from_string(b'pending ordinary audio')
    receipt = client.collection('batch_pipeline_prod_artifacts').document('ordinary-audio')
    deadline = datetime.now(timezone.utc) + timedelta(minutes=30)
    receipt.set(
        {
            'owner_key': plane.key,
            'owner_id': uid,
            'conversation_ids': [cid],
            'kind': 'audio',
            'segment_id': 'unit',
            'uri': f'gs://{bucket}/{path}',
            'write_pending_until': deadline,
        }
    )
    conversation.update(policy)
    if claim_after_edit:
        conversation.update({'record_lane_owner': 'batch_live_v1'})
    clock = [deadline + timedelta(seconds=10)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    for _ in range(8):
        late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
        clock[0] += timedelta(seconds=10)
    assert receipt.get().exists and blob.exists()
    assert not list(client.collection(late_intents.COLLECTION).stream())
    mirror.assert_not_called()


def test_maskless_account_revocation_arms_recording_erasure(plane):
    user = plane.client.collection('users').document(plane.uid)
    user.set({'private_cloud_sync_enabled': True})
    assert not list(plane.client.collection(late_intents.COLLECTION).stream())
    user.set({'private_cloud_sync_enabled': False})
    [intent] = plane.client.collection(late_intents.COLLECTION).stream()
    assert intent.get('reason') == 'recording_policy'
    assert intent.get('conversation_id') == ''


def _register_pending_result(plane, monkeypatch, tmp_path, variant):
    bucket, namespace, uid = 'synthetic-late-batch', 'batch_pipeline_dev', plane.uid
    storage = LocalStorageClient(tmp_path / 'result-upload')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda *_: 0)
    user = plane.client.collection('users').document(uid)
    user.update({'private_cloud_sync_enabled': True})
    cid, segment = 'synthetic-source', 'synthetic-unit'
    origin = variant != 'legacy-nonrecording'
    lane = {'desktop-sync': 'batch_sync_v1', 'native': 'batch_live_v1'}.get(variant)
    user.collection('conversations').document(cid).set(
        {'private_cloud_sync_enabled': True, **({'record_lane_owner': lane} if lane else {})}
    )
    binding = ProjectionBinding(
        uid,
        'synthetic-job',
        'synthetic-content',
        (segment,),
        source='desktop' if variant == 'desktop-sync' else 'omi',
        target_conversation_id=cid,
        record_origin=origin,
        native_record=variant == 'native',
    )
    job = {'owner_id': uid, 'state': 'leased', 'conversation_id': cid, 'projection_binding': asdict(binding)}
    if variant == 'native':
        job.update(record_lane_owner=lane, record_origin=True)
    plane.client.collection(f'{namespace}_jobs').document(segment).set(job)
    artifacts = create_artifact_store(
        FirestoreStore(namespace, firestore_client=plane.client), storage, bucket, b'x' * 32
    )
    item = WorkItem(segment, uid, 100, 'record:pending', 1, Priority.FRESH, conversation_id=cid, privacy_generation=0)
    uri = artifacts.persist_result(item, {'synthetic_result': True})
    blob = storage.bucket(bucket).blob(uri.removeprefix(f'gs://{bucket}/').split('#', 1)[0])
    [receipt] = plane.client.collection(f'{namespace}_artifacts').stream()
    return user, receipt, blob


@pytest.mark.parametrize('variant', ['desktop-sync', 'legacy-nonrecording', 'native', 'legacy-unstamped'])
def test_account_opt_out_preserves_allowed_admitted_results(plane, monkeypatch, tmp_path, variant):
    user, receipt, blob = _register_pending_result(
        plane, monkeypatch, tmp_path, 'native' if variant == 'legacy-unstamped' else variant
    )
    start = receipt.create_time
    assert receipt.get('record_origin') is (variant != 'legacy-nonrecording')
    if variant == 'desktop-sync':
        assert receipt.get('record_lane_owner') == 'batch_sync_v1'
    if variant == 'legacy-unstamped':
        receipt.reference.update({'record_lane_owner': firestore.DELETE_FIELD})
        monkeypatch.setenv('BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS', '1')
    user.update({'private_cloud_sync_enabled': False})
    [intent] = plane.client.collection(late_intents.COLLECTION).stream()
    # Preserve the emulator's real Commit revision for historical proof and
    # simulate the five-minute offset on the independent reservation clock.
    intent.reference.update({'changed_at': start + timedelta(minutes=5)})
    clock = [start + timedelta(minutes=5)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    reconcile = late_sweeps.reconcile_batch_privacy_late_sweeps
    assert reconcile(firestore_client=plane.client) == {'scope_verified': 1}
    clock[0] = start + timedelta(minutes=30)
    for _ in range(8):
        if reconcile(firestore_client=plane.client) == {'completed': 1}:
            break
        clock[0] += late_sweeps.PAGE_RETRY
    assert not intent.reference.get().exists
    assert receipt.reference.get().exists is (variant != 'native')
    assert blob.exists() is (variant != 'native')
    if variant == 'legacy-unstamped':
        [debt] = plane.client.collection(late_intents.COLLECTION).stream()
        assert debt.get('artifact_id') == receipt.id
        assert debt.get('dead_letter_error') == 'recording_lane_unproven'
        assert 'execute_at' not in debt.to_dict()


def test_default_closed_sweep_keeps_proof_and_resumes_after_history_window(plane, monkeypatch, tmp_path):
    from database.batch_pipeline_staging import ORPHAN_GRACE, reap_one

    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    client = plane.client
    user, receipt, blob = _register_pending_result(plane, monkeypatch, tmp_path, 'native')
    user.update({'private_cloud_sync_enabled': False})
    [intent] = client.collection(late_intents.COLLECTION).stream()
    reconcile = late_sweeps.reconcile_batch_privacy_late_sweeps
    assert reconcile(firestore_client=client) == {'scope_verified': 1}
    proof = intent.reference.get().to_dict()
    assert proof['scope_verified'] is True and 'due_at' not in proof
    assert _pending_count('artifact_execution') == 1
    user.update({'private_cloud_sync_enabled': True})
    deadline = receipt.get('write_pending_until')
    clock = [deadline + ORPHAN_GRACE + timedelta(seconds=1)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    storage = late_sweeps.create_storage_client
    mocked_storage = MagicMock(side_effect=storage)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', mocked_storage)
    assert reconcile(firestore_client=client) == {}
    mocked_storage.assert_not_called()
    assert intent.reference.get().exists and receipt.reference.get().exists and blob.exists()
    client.collection('batch_pipeline_dev_jobs').document(receipt.get('segment_id')).update(
        {'result.result_uri': receipt.get('uri')}
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert reap_one(store, receipt.id, clock[0])
    retired = receipt.reference.get().to_dict()
    assert 'write_pending_until' not in retired and retired['late_erasure_pending_until'] == deadline
    monkeypatch.setattr(
        late_sweeps, '_historical_scope', MagicMock(side_effect=AssertionError('proof must be durable'))
    )
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', ERASURE_ON)
    for _ in range(8):
        if reconcile(firestore_client=client) == {'completed': 1}:
            break
        clock[0] += late_sweeps.PAGE_RETRY
    assert not intent.reference.get().exists and not receipt.reference.get().exists and not blob.exists()
    assert _pending_count('artifact_execution') == 0


def _pending_count(phase):
    return REGISTRY.get_sample_value('omi_batch_pipeline_privacy_post_window_pending', {'phase': phase})


@pytest.mark.parametrize(
    'path', ['same-commit-restore', 'later-restore', 'history-unreadable', 'history-transient', 'unverified-retry']
)
def test_account_recording_erasures_require_a_denial_at_the_policy_commit(plane, monkeypatch, tmp_path, path):
    client, uid = plane.client, plane.uid
    bucket = 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'account-recording-policy')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda *_: 0)
    user = client.collection('users').document(uid)
    user.update({'private_cloud_sync_enabled': True})
    object_name = f'batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/unit/{uuid4().hex}.enc'
    blob = storage.bucket(bucket).blob(object_name)
    pending = datetime.now(timezone.utc) + timedelta(minutes=30)
    receipt = client.collection('batch_pipeline_prod_artifacts').document('pending-recording')
    receipt.set(
        {
            'owner_key': plane.key,
            'owner_id': uid,
            'kind': 'audio',
            'segment_id': 'unit',
            'record_origin': True,
            'record_lane_owner': 'batch_live_v1',
            'uri': f'gs://{bucket}/{object_name}',
            'write_pending_until': pending,
        }
    )
    if path == 'same-commit-restore':
        batch = client.batch()
        batch.update(user, {'private_cloud_sync_enabled': False})
        batch.update(user, {'private_cloud_sync_enabled': True})
        batch.commit()
    else:
        user.update({'private_cloud_sync_enabled': False})
        user.update({'private_cloud_sync_enabled': True})
    assert user.get().get('private_cloud_sync_enabled') is True
    blob.upload_from_string(b'late recording audio')
    [intent] = client.collection(late_intents.COLLECTION).stream()
    assert intent.get('reason') == 'recording_policy' and intent.get('conversation_id') == ''
    assert receipt.get().create_time <= intent.create_time <= pending

    clock = [max(intent.get('due_at'), pending) + timedelta(seconds=1)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    reconcile = late_sweeps.reconcile_batch_privacy_late_sweeps
    if path in {'history-unreadable', 'history-transient', 'unverified-retry'}:
        monkeypatch.setenv('BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS', '2')
        before = _dead_letter_count('scope_history_unavailable')

        def unavailable(_client, reference, field_paths, read_time):
            assert path in {'history-unreadable', 'history-transient'}
            assert reference.path == user.path
            assert tuple(field_paths) == ('private_cloud_sync_enabled',)
            assert read_time == intent.create_time
            if path == 'history-transient':
                raise ServiceUnavailable('historical read unavailable')
            raise FailedPrecondition('historical proof unavailable')

        monkeypatch.setattr(late_sweeps, '_historical_scope', unavailable)
        if path == 'unverified-retry':
            retry = intent.reference.parent.document('legacy-receipt-retry')
            retry.set({**intent.to_dict(), 'artifact_id': receipt.id, 'scope_verified': False})
            intent.reference.delete()
            intent = retry.get()
        assert reconcile(firestore_client=client) == {'retry': 1}
        clock[0] += late_sweeps.RETRY
        assert reconcile(firestore_client=client) == {'dead_lettered': 1}
        assert reconcile(firestore_client=client) == {}
        debt = intent.reference.get().to_dict()
        assert debt['dead_letter_error'] == 'scope_history_unavailable'
        assert 'due_at' not in debt
        assert 'execute_at' not in debt
        assert _dead_letter_count('scope_history_unavailable') == before + 1
    elif path == 'same-commit-restore':
        assert reconcile(firestore_client=client) == {'superseded': 1}
        assert not intent.reference.get().exists
    else:
        assert reconcile(firestore_client=client) == {'scope_verified': 1}
        assert intent.reference.get().get('scope_verified') is True
        assert receipt.get().exists and blob.exists()
        for _ in range(10):
            clock[0] += late_sweeps.PAGE_RETRY
            if reconcile(firestore_client=client) == {'completed': 1}:
                break
        assert not intent.reference.get().exists
    assert receipt.get().exists is (path != 'later-restore')
    assert blob.exists() is (path != 'later-restore')


@pytest.mark.parametrize('change', ['allowed-protection', 'clear-migration', 'same-commit-reenable'])
def test_allowed_protection_edit_preserves_pending_artifact(plane, monkeypatch, tmp_path, change):
    client, uid = plane.client, plane.uid
    bucket = 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'protection-settings')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda *_: 0)
    path = f'batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/unit/{uuid4().hex}.enc'
    blob = storage.bucket(bucket).blob(path)
    blob.upload_from_string(b'pending audio')
    receipt = client.collection('batch_pipeline_prod_artifacts').document('pending-audio')
    pending = datetime.now(timezone.utc) + timedelta(minutes=30)
    receipt.set(
        {
            'owner_key': plane.key,
            'owner_id': uid,
            'kind': 'audio',
            'segment_id': 'unit',
            'uri': f'gs://{bucket}/{path}',
            'write_pending_until': pending,
        }
    )
    user = client.collection('users').document(uid)
    if change == 'same-commit-reenable':
        batch = client.batch()
        batch.update(user, {'data_protection_level': 'e2ee'})
        batch.update(user, {'data_protection_level': 'enhanced'})
        batch.commit()
    else:
        fields = {'data_protection_level': 'standard'} if change == 'allowed-protection' else {'migration_status': None}
        user.update(fields)
    clock = [pending + timedelta(seconds=10)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    for _ in range(8):
        late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
        clock[0] += timedelta(seconds=10)
    assert receipt.get().exists and blob.exists()
    assert not list(client.collection(late_intents.COLLECTION).stream())


def test_late_sweep_settles_receipt_after_normal_retention_cleanup(plane, monkeypatch, tmp_path):
    from database.batch_pipeline_staging import ORPHAN_GRACE, reap_one
    from utils.batch_pipeline.retention import cleanup_completed_artifacts

    client = plane.client
    user, reserved, blob = _register_pending_result(plane, monkeypatch, tmp_path, 'native')
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    receipt = reserved.reference
    deadline = reserved.get('write_pending_until')
    uri = reserved.get('uri')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    time.sleep(0.005)  # Separate receipt creation from the millisecond-precision policy REQUEST_TIME.
    user.update({'private_cloud_sync_enabled': False})
    [intent] = client.collection(late_intents.COLLECTION).stream()
    assert reserved.create_time <= intent.get('changed_at') <= deadline
    reconcile = late_sweeps.reconcile_batch_privacy_late_sweeps
    assert reconcile(firestore_client=client) == {'scope_verified': 1}

    client.collection('batch_pipeline_dev_jobs').document(reserved.get('segment_id')).update({'result.result_uri': uri})
    cleanup_at = deadline + ORPHAN_GRACE + timedelta(seconds=1)
    assert reap_one(store, receipt.id, cleanup_at)
    receipt.update({'cleanup_after': cleanup_at})
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_ENABLED', 'false')

    def delete_uri(uid, target):
        assert (uid, target) == (plane.uid, uri)
        blob.delete()

    assert cleanup_completed_artifacts(store, cleanup_at, delete_uri=delete_uri) == 1
    cleaned = receipt.get()
    assert cleaned.exists and not blob.exists()
    assert 'uri' not in cleaned.to_dict() and cleaned.get('late_erasure_pending_until') == deadline
    assert cleaned.get('expires_at') > cleanup_at

    storage_factory = MagicMock(wraps=late_sweeps.create_storage_client)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', storage_factory)
    mirror = MagicMock(return_value=0)
    monkeypatch.setattr(late_sweeps, 'purge_owner', mirror)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', ERASURE_ON)
    clock = [cleanup_at + timedelta(seconds=1)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    for _ in range(8):
        outcomes = reconcile(firestore_client=client)
        assert 'retry' not in outcomes and 'dead_lettered' not in outcomes
        if outcomes == {'completed': 1}:
            break
        clock[0] += late_sweeps.PAGE_RETRY

    assert not list(intent.reference.parent.stream())
    assert not receipt.get().exists and not blob.exists()
    storage_factory.assert_not_called()
    mirror.assert_called_once_with(store.namespace, plane.uid)


@pytest.mark.parametrize('invalid', ['identity', 'bucket', 'missing-uri', 'pending-cleanup', 'null-uri-with-ttl'])
def test_permanent_receipt_failure_dead_letters_and_valid_rows_recover(plane, monkeypatch, tmp_path, invalid):
    client, uid = plane.client, plane.uid
    bucket = 'synthetic-late-batch'
    storage = LocalStorageClient(tmp_path / 'dead-letter')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', bucket)
    monkeypatch.setattr(late_sweeps, 'create_storage_client', lambda: storage)
    monkeypatch.setattr(late_sweeps, 'purge_owner', lambda *_: 0)
    artifacts = client.collection('batch_pipeline_prod_artifacts')
    user = client.collection('users').document(uid)
    user.update({'private_cloud_sync_enabled': True})
    pending = datetime.now(timezone.utc) + timedelta(minutes=30)
    root = f'batch-pipeline/batch_pipeline_prod/owners/{plane.key}/audio/unit'
    valid_path = f'{root}/{uuid4().hex}.enc'
    bad_bucket = 'synthetic-unconfigured' if invalid == 'bucket' else bucket
    bad_path = f'{root}/mutable.enc' if invalid == 'identity' else f'{root}/{uuid4().hex}.enc'
    common = {
        'owner_key': plane.key,
        'owner_id': uid,
        'kind': 'audio',
        'segment_id': 'unit',
        'record_origin': True,
        'record_lane_owner': 'batch_live_v1',
        'write_pending_until': pending,
    }
    good, bad = artifacts.document('b-valid'), artifacts.document('a-malformed')
    good.set({**common, 'uri': f'gs://{bucket}/{valid_path}'})
    invalid_fields = {
        'missing-uri': {},
        'pending-cleanup': {'cleanup_after': pending, 'expires_at': pending + timedelta(days=45)},
        'null-uri-with-ttl': {'uri': None, 'expires_at': pending + timedelta(days=45)},
    }
    bad.set({**common, **invalid_fields.get(invalid, {'uri': f'gs://{bad_bucket}/{bad_path}'})})
    good_blob = storage.bucket(bucket).blob(valid_path)
    bad_blob = storage.bucket(bad_bucket).blob(bad_path)
    good_blob.upload_from_string(b'valid recording')
    bad_blob.upload_from_string(b'unverified identity')
    user.update({'private_cloud_sync_enabled': False})
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'scope_verified': 1}
    error = 'artifact_identity' if invalid == 'identity' else 'artifact_address'
    before = _dead_letter_count(error)
    clock = [pending + timedelta(seconds=10)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'retry': 1}
    clock[0] += late_sweeps.PAGE_RETRY
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'progress': 1}
    assert not good.get().exists and not good_blob.exists()
    for _ in range(4):
        clock[0] += late_sweeps.PAGE_RETRY
        late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
    for _ in range(3):
        clock[0] += late_sweeps.RETRY + timedelta(seconds=10)
        assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'retry': 1}
    clock[0] += late_sweeps.RETRY + timedelta(seconds=10)
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'dead_lettered': 1}
    for _ in range(8):
        clock[0] += timedelta(seconds=10)
        late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client)
    assert not good.get().exists and not good_blob.exists()
    assert bad.get().exists and bad_blob.exists()
    [debt] = list(client.collection(late_intents.COLLECTION).stream())
    assert debt.get('artifact_id') == bad.id
    assert debt.get('permanent_attempts') == 5
    assert 'due_at' not in debt.to_dict()
    assert _dead_letter_count(error) == before + 1


def test_late_sweep_read_budget_includes_full_artifact_page(plane, monkeypatch):
    from testing.firestore_read_budget import delta_reads, snapshot_reads

    client, uid = plane.client, plane.uid
    artifacts = client.collection('batch_pipeline_prod_artifacts')
    batch = client.batch()
    for i in range(100):
        # The scan still pays to read unrelated-to-the-event receipts.
        batch.set(artifacts.document(f'synthetic-{i:03}'), {'owner_key': plane.key, 'owner_id': uid})
    batch.commit()
    client.collection('users').document(uid).update({'private_cloud_sync_enabled': False})
    [event] = client.collection(late_intents.COLLECTION).stream()
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'scope_verified': 1}
    monkeypatch.setattr(
        late_sweeps, '_now', lambda: event.get('changed_at') + late_intents.DELAY + timedelta(seconds=1)
    )
    before = snapshot_reads()
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'progress': 1}
    reads = delta_reads(before).reads
    manifest = json.loads(
        (Path(__file__).resolve().parents[3] / '.github/firestore-collection-budgets.json').read_text()
    )
    [budget] = [row for row in manifest['budgets'] if row['collection'] == late_intents.COLLECTION]
    assert 100 < reads <= budget['reads_per_unit_budget']
    assert budget['reads_per_day_budget'] >= budget['reads_per_unit_budget'] * 4 * 24 * 60


@pytest.mark.parametrize('malformed', ['missing-owner', 'missing-scope', 'invalid-receipt-id', 'invalid-cursor'])
def test_malformed_intent_is_dead_lettered_at_configured_limit(plane, monkeypatch, malformed):
    client = plane.client
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(late_sweeps, '_now', lambda: clock[0])
    monkeypatch.setenv('BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS', '2')
    event = client.collection(late_intents.COLLECTION).document('synthetic-malformed')
    event.set(
        {
            'uid': plane.uid,
            'reason': 'recording_policy',
            'conversation_id': '',
            'changed_at': clock[0] - late_intents.DELAY,
            'due_at': clock[0],
        }
    )
    change = {
        'missing-owner': {'uid': firestore.DELETE_FIELD},
        'missing-scope': {'conversation_id': firestore.DELETE_FIELD},
        'invalid-receipt-id': {'artifact_id': None},
        'invalid-cursor': {'after': 'x' * 1501},
    }
    event.update(change[malformed])
    before = _dead_letter_count('malformed_intent')
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'retry': 1}
    clock[0] += late_sweeps.RETRY
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'dead_lettered': 1}
    assert late_sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {}
    row = event.get().to_dict()
    assert row['permanent_attempts'] == 2 and row['dead_letter_error'] == 'malformed_intent'
    assert _dead_letter_count('malformed_intent') == before + 1


def _dead_letter_count(error):
    return REGISTRY.get_sample_value('omi_batch_pipeline_privacy_post_window_dead_letters_total', {'error': error}) or 0


@pytest.mark.parametrize('site', ('probe', 'lease'))
def test_warm_write_cache_denies_after_opt_out_before_redis_invalidation(plane, monkeypatch, site):
    import fakeredis

    from database import batch_privacy_write_authority as authority, batch_privacy_write_cache as cache
    from database import batch_privacy_write_fence as fence
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    redis = fakeredis.FakeRedis()
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic-test-only')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-write-proof-key-for-test-only')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":100}')
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(cache, 'available', lambda client: client is plane.client)
    monkeypatch.setattr(authority, 'ttl_disabled', lambda: False)

    user = plane.client.collection('users').document(plane.uid)
    user.update({'private_cloud_sync_enabled': True})
    user.collection('conversations').document('native').set(
        {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True}
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=plane.client)
    ref = plane.client.collection('batch_pipeline_dev_jobs').document('unleased')
    row = {
        'owner_id': plane.uid,
        'owner_key': plane.key,
        'conversation_id': 'native',
        'privacy_generation': 0,
        'state': 'ready',
        'requires_compute_admission': True,
        'segment_id': ref.id,
    }
    ref.set(row)

    def probe(tx):
        return tx._probe_write_privacy(plane.uid, ('native',), 0)

    def lease(tx):
        job = tx.get('jobs', ref.id)
        tx.put('jobs', ref.id, {**job, 'state': 'leased', 'attempt': 1, 'token': 'lease', 'lease_until': 123.0})

    action = probe if site == 'probe' else lease
    assert store.run(probe) == 0
    hits = cache.TOKENLESS.labels(f'{site}_hit')._value
    before_hit = hits.get()
    store.run(action)
    assert hits.get() == before_hit + 1
    ref.set(row)

    committed = threading.Event()
    release_notification = threading.Event()

    def pause_and_drop_notification(paths, commit_time):
        committed.set()
        assert release_notification.wait(timeout=10)

    monkeypatch.setattr(fence, 'invalidate_tokenless', pause_and_drop_notification)
    with ThreadPoolExecutor(max_workers=1) as writer:
        revoke = writer.submit(user.update, {'private_cloud_sync_enabled': False})
        try:
            assert committed.wait(timeout=5)
            assert user.get().get('private_cloud_sync_enabled') is False
            with pytest.raises(BatchPrivacyBlocked, match='recording_privacy_changed'):
                store.run(action)
        finally:
            release_notification.set()
            revoke.result(timeout=5)
    with pytest.raises(BatchPrivacyBlocked, match='recording_privacy_changed'):
        store.run(action)
    assert hits.get() == before_hit + 1
    assert ref.get().get('state') == 'ready'


def test_tokenless_write_cache_is_limited_to_existing_compute_admitted_leases(plane, monkeypatch):
    from dataclasses import replace

    import fakeredis

    from database import batch_privacy_write_authority as authority, batch_privacy_write_cache as cache
    from database import batch_privacy_write_audit as audit, batch_privacy_write_fence
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_store import FirestoreStore
    from testing.firestore_read_budget import delta_reads, reads_for_caller, snapshot_reads

    redis = fakeredis.FakeRedis()
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic-test-only')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-write-proof-key-for-test-only')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(cache, 'available', lambda client: True)
    monkeypatch.setattr(authority, 'ttl_disabled', lambda: False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":100,"bpp_tokenless_write_audit":100}')
    store = FirestoreStore('batch_pipeline_dev', firestore_client=plane.client)
    assert store.run(lambda tx: tx._probe_write_privacy(plane.uid, ('source',), 0)) == 0

    ref = plane.client.collection('batch_pipeline_dev_jobs').document('unleased')
    row = {
        'owner_id': plane.uid,
        'owner_key': plane.key,
        'conversation_id': 'source',
        'privacy_generation': 0,
        'state': 'ready',
        'requires_compute_admission': True,
        'segment_id': 'unleased',
    }
    ref.set(row)

    def lease(tx):
        job = tx.get('jobs', ref.id)
        tx.put(
            'jobs', ref.id, {**job, 'state': 'leased', 'attempt': 1, 'token': 'synthetic-lease', 'lease_until': 123.0}
        )

    def read_count(action):
        before = snapshot_reads()
        store.run(action)
        return reads_for_caller(delta_reads(before), 'database.batch_pipeline_privacy:read')

    assert read_count(lease) == 1
    ref.set(row)

    pending_audits = []
    monkeypatch.setattr(audit.random, 'randrange', lambda _: 0)
    monkeypatch.setattr(
        audit.read_cache_shadow_executor,
        'submit',
        lambda run, *args: pending_audits.append((run, args)) or MagicMock(),
    )
    monkeypatch.setattr(audit, '_ROLE', 'integration')
    agree_by_role = audit.AUDIT_BY_ROLE.labels('integration', 'agree')._value
    before_role = agree_by_role.get()
    assert read_count(lambda tx: tx._probe_write_privacy(plane.uid, ('source',), 0)) == 1
    assert read_count(lease) == 1
    assert [args[1].site for _, args in pending_audits] == ['probe', 'lease']
    assert ref.get().to_dict()['state'] == 'leased'
    assert agree_by_role.get() == before_role
    for run, args in pending_audits:
        agree = audit.AUDIT.labels(args[1].site, 'agree')._value
        before = agree.get()
        run(*args)
        assert agree.get() == before + 1
    assert agree_by_role.get() == before_role + 2
    lease_hit = next(hit for _, (_, hit, _) in pending_audits if hit.site == 'lease')
    pending_audits.clear()

    ref.set(row)
    shadow = cache.TOKENLESS_SHADOW.labels('lease', 'match')
    before = shadow._value.get()
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":100,"bpp_tokenless_write_shadow":100}')
    probe_shadow = cache.TOKENLESS_SHADOW.labels('probe', 'match')._value
    before_probe = probe_shadow.get()
    assert store.run(lambda tx: tx._probe_write_privacy(plane.uid, ('source',), 0)) == 0
    assert probe_shadow.get() == before_probe + 1
    assert read_count(lease) > 1
    assert shadow._value.get() == before + 1
    assert not pending_audits
    ref.set(row)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":0}')
    assert read_count(lease) > 1

    # Keep the pre-change proof in Redis to model retrospective audit outcomes.
    # Content writes still call durable authority.
    monkeypatch.setattr(batch_privacy_write_fence, 'invalidate_tokenless', lambda *args: None)
    plane.client.collection('users').document(plane.uid).update({'migration_status': 'pending'})
    token = plane.client.collection(audit.PRIVACY_COLLECTION).document(plane.key).get()
    current_version = audit.token_version(token)
    assert current_version is not None and current_version != lease_hit.decision.version
    # Model a refusal with and without a token revision explaining the change.
    unexplained_hit = replace(lease_hit, decision=replace(lease_hit.decision, version=current_version))
    for hit, outcome in (
        (lease_hit, 'disagree_within_window'),
        (unexplained_hit, 'disagree_beyond_window'),
    ):
        counter = audit.AUDIT_BY_ROLE.labels('integration', outcome)._value
        before = counter.get()
        audit._run(plane.client, hit, audit._Budget(time.monotonic() + 2))
        assert counter.get() == before + 1

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_write_cache":100}')
    with pytest.raises(BatchPrivacyBlocked, match='data_protection_changed'):
        store.run(lambda tx: tx.put('jobs', ref.id, {**row, 'state': 'result_ready', 'result': {'outcome': 'silence'}}))


def test_completed_account_intent_is_inert_if_account_is_restored(plane, monkeypatch):
    from database import batch_privacy_late_intents as intents, batch_privacy_late_sweeps as sweeps

    client, uid = plane.client, plane.uid
    marker = client.collection('account_deletions').document(uid)
    user = client.collection('users').document(uid)
    user.delete()
    marker.set({'wipe_status': 'completed'})
    [intent] = list(client.collection(intents.COLLECTION).stream())
    marker.update({'wipe_status': 'cancelled'})
    user.set({'data_protection_level': 'standard'})
    clock = intent.to_dict()['changed_at'] + intents.DELAY + timedelta(seconds=5)
    monkeypatch.setattr(sweeps, '_now', lambda: clock)

    def unexpected_erase(*args, **kwargs):
        raise AssertionError('superseded sweep opened storage')

    monkeypatch.setattr(sweeps, 'create_storage_client', unexpected_erase)
    assert sweeps.reconcile_batch_privacy_late_sweeps(firestore_client=client) == {'superseded': 1}
    assert not intent.reference.get().exists and user.get().exists
