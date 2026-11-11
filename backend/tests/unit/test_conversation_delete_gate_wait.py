"""Same-account conversation deletes queue behind the account gate and return fast.

Prod 2026-11-11: one cascade delete held ``legal_hold_deletion_gates/{uid}`` for
30-55 s (scaling with the owner's batch-pipeline rows) and every other delete
from that phone got an immediate 409. Deletes now wait (bounded) for a running
same-kind gate, and the per-conversation batch purge leaves the request path.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversation_tombstones, legal_holds
from routers import conversations
from utils.conversations import deletion_batch_purge
from routers import users as users_router
from utils import cloud_tasks

UID = 'uid1'


# --- in-memory Firestore just deep enough for the gate and tombstone documents ---


class _Snapshot:
    def __init__(self, payload):
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return dict(self._payload or {})


class _Ref:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def get(self, transaction=None):
        with self.client.lock:
            return _Snapshot(self.client.docs.get(self.path))

    def create(self, payload):
        from google.api_core.exceptions import AlreadyExists

        with self.client.lock:
            if self.path in self.client.docs:
                raise AlreadyExists('exists')
            self.client.docs[self.path] = dict(payload)

    def set(self, payload, merge=False):
        with self.client.lock:
            current = dict(self.client.docs.get(self.path, {})) if merge else {}
            self.client.docs[self.path] = {**current, **payload}

    def update(self, payload):
        with self.client.lock:
            self.client.docs[self.path] = {**self.client.docs[self.path], **payload}

    def collection(self, name):
        return _Collection(self.client, f'{self.path}/{name}')


class _Collection:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def document(self, document_id):
        return _Ref(self.client, f'{self.path}/{document_id}')


class _Transaction:
    def __init__(self, client):
        self.client = client

    def set(self, reference, payload, merge=False):
        reference.set(payload, merge=merge)


class _Client:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.lock = threading.RLock()

    def collection(self, name):
        return _Collection(self, name)

    def transaction(self):
        return _Transaction(self)


def _gate_doc(*, kind='explicit_memory_deletion', token='peer'):
    return {
        'schema_version': legal_holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': kind,
        'token': token,
        'state': 'running',
        'started_at': legal_holds.datetime.now(legal_holds.timezone.utc),
        'finished_at': None,
    }


GATE_PATH = f'{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{UID}'
HOLD_PATH = f'{legal_holds.LEGAL_HOLDS_COLLECTION}/{UID}'


@pytest.fixture
def gate_client(monkeypatch):
    """The real acquire/finish transactions over one serialized in-memory client."""
    client = _Client()
    lock = threading.Lock()

    def acquire(uid, *, kind, token, firestore_client=None, now=None):
        with lock:
            legal_holds._acquire_destructive_operation_transaction.to_wrap(
                client.transaction(),
                client,
                uid,
                kind,
                token,
                now or legal_holds.datetime.now(legal_holds.timezone.utc),
            )

    def finish(uid, *, kind, token, outcome, firestore_client=None, now=None):
        with lock:
            legal_holds._finish_destructive_operation_transaction.to_wrap(
                client.transaction(),
                client,
                uid,
                kind,
                token,
                outcome,
                now or legal_holds.datetime.now(legal_holds.timezone.utc),
            )

    monkeypatch.setattr(legal_holds, 'acquire_destructive_operation', acquire)
    monkeypatch.setattr(legal_holds, 'finish_destructive_operation', finish)
    monkeypatch.setattr(legal_holds, 'account_deletion_firestore_client', lambda **_kwargs: client)
    return client


@pytest.fixture
def fast_clock(monkeypatch):
    """Virtual time: sleeps advance the clock instantly; ``on_sleep`` hooks peer progress."""
    state = SimpleNamespace(now=0.0, sleeps=[], on_sleep=None)

    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds
        if state.on_sleep:
            state.on_sleep(state)

    monkeypatch.setattr(legal_holds, '_gate_wait_sleep', sleep)
    monkeypatch.setattr(legal_holds, '_gate_wait_clock', lambda: state.now)
    return state


# --- gate wait ---


def test_same_kind_peer_is_waited_for_then_acquired(gate_client, fast_clock):
    gate_client.docs[GATE_PATH] = _gate_doc()

    def release_after_two_polls(state):
        if len(state.sleeps) == 2:
            gate_client.docs[GATE_PATH] = {**gate_client.docs[GATE_PATH], 'state': 'completed'}

    fast_clock.on_sleep = release_after_two_polls
    with legal_holds.destructive_operation_gate(UID, wait_seconds=20) as token:
        assert gate_client.docs[GATE_PATH]['token'] == token
    assert len(fast_clock.sleeps) == 2
    assert gate_client.docs[GATE_PATH]['state'] == 'completed'


def test_same_kind_peer_past_the_wait_budget_still_raises(gate_client, fast_clock):
    gate_client.docs[GATE_PATH] = _gate_doc()
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.destructive_operation_gate(UID, wait_seconds=3):
            pytest.fail('acquired a gate a live peer still owns')
    assert sum(fast_clock.sleeps) == pytest.approx(3)
    assert gate_client.docs[GATE_PATH]['token'] == 'peer'


@pytest.mark.parametrize('kind', ['account_deletion', 'retention_cleanup', 'audio_conversation_deletion'])
def test_other_kind_gate_fails_fast_without_waiting(gate_client, fast_clock, kind):
    gate_client.docs[GATE_PATH] = _gate_doc(kind=kind)
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.destructive_operation_gate(UID, wait_seconds=20):
            pytest.fail('overtook another destructive operation')
    assert fast_clock.sleeps == []


def test_legal_hold_fails_fast_without_waiting(gate_client, fast_clock):
    gate_client.docs[HOLD_PATH] = {
        'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION,
        'issuer': 'admin',
        'active': True,
    }
    with pytest.raises(legal_holds.LegalHoldActive):
        with legal_holds.destructive_operation_gate(UID, wait_seconds=20):
            pytest.fail('deleted under an active legal hold')
    assert fast_clock.sleeps == []
    assert GATE_PATH not in gate_client.docs


def test_default_gate_keeps_fail_fast_contract(gate_client, fast_clock):
    gate_client.docs[GATE_PATH] = _gate_doc()
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.destructive_operation_gate(UID):
            pass
    assert fast_clock.sleeps == []


# --- the HTTP route ---


def _route_app(monkeypatch, body):
    for name in (
        'delete_owner_prompt_embedding_cache',
        'delete_conversation_screen_frames',
        'delete_conversation_and_frame_evidence',
        'delete_privacy_conversation_audio',
        'delete_vector',
        'delete_transcript_chunk_vectors',
        'delete_action_item_vectors_batch',
        'record_product_event',
        'MemoryService',
    ):
        monkeypatch.setattr(conversations, name, MagicMock())
    monkeypatch.setattr(conversations, '_delete_conversation_under_gate', body)
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: False)
    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: UID
    return app


def test_concurrent_same_account_cascade_deletes_all_return_204_serialized(monkeypatch, gate_client):
    monkeypatch.setattr(legal_holds, '_gate_wait_sleep', lambda seconds: time.sleep(min(seconds, 0.02)))
    inside, peak, deleted = [0], [0], []
    counter = threading.Lock()

    def body(conversation_id, *args):
        with counter:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        time.sleep(0.15)
        with counter:
            inside[0] -= 1
            deleted.append(conversation_id)

    app = _route_app(monkeypatch, body)
    statuses = []

    def delete(conversation_id):
        with TestClient(app) as client:
            statuses.append(client.delete(f'/v1/conversations/{conversation_id}?cascade=true').status_code)

    threads = [threading.Thread(target=delete, args=(f'c{i}',)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert statuses == [204] * 5
    assert sorted(deleted) == [f'c{i}' for i in range(5)]
    assert peak[0] == 1, 'two same-account cascades ran inside the account gate at once'
    assert gate_client.docs[GATE_PATH]['state'] == 'completed'


def test_busy_gate_past_the_wait_budget_still_answers_409_with_retry_after(monkeypatch, gate_client, fast_clock):
    gate_client.docs[GATE_PATH] = _gate_doc()
    body = MagicMock()
    app = _route_app(monkeypatch, body)
    with TestClient(app) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 409
    assert response.json() == {'detail': 'account_gate_busy'}
    assert response.headers['Retry-After'] == '2'
    assert sum(fast_clock.sleeps) == pytest.approx(conversations.CONVERSATION_DELETE_GATE_WAIT_SECONDS)
    body.assert_not_called()


def test_account_deletion_gate_blocks_delete_immediately(monkeypatch, gate_client, fast_clock):
    gate_client.docs[GATE_PATH] = _gate_doc(kind='account_deletion')
    body = MagicMock()
    app = _route_app(monkeypatch, body)
    with TestClient(app) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 409
    assert fast_clock.sleeps == []
    body.assert_not_called()


def test_legal_hold_still_blocks_cascade_delete(monkeypatch, gate_client, fast_clock):
    gate_client.docs[HOLD_PATH] = {
        'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION,
        'issuer': 'legal_hold_service',
        'active': True,
    }
    body = MagicMock()
    app = _route_app(monkeypatch, body)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code != 204
    assert fast_clock.sleeps == []
    body.assert_not_called()


# --- the batch purge leaves the request path ---


@pytest.fixture
def tombstone_db(monkeypatch):
    client = _Client()
    monkeypatch.setattr(conversation_tombstones, 'db', client)
    from database import from_segments_chunks

    monkeypatch.setattr(from_segments_chunks, 'purge_chunks', lambda *args, **kwargs: None)
    return client


def _tombstone(client, conversation_id):
    return client.docs.get(f'users/{UID}/{conversation_tombstones.COLLECTION}/{conversation_id}')


def test_deferred_scope_marks_intent_and_skips_the_inline_batch_scan(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    purge = MagicMock()
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    with conversation_tombstones.defer_batch_purges(UID) as deferred:
        conversation_tombstones.record_deletion(UID, 'survivor')
        conversation_tombstones.record_deletion(UID, 'donor')
        conversation_tombstones.record_deletion(UID, 'survivor')
    assert deferred == ['survivor', 'donor']
    purge.assert_not_called()
    assert _tombstone(tombstone_db, 'survivor')['batch_purge_pending'] is True
    assert _tombstone(tombstone_db, 'donor')['batch_purge_pending'] is True
    # Outside the scope, and for another owner inside it, the purge stays inline.
    conversation_tombstones.record_deletion(UID, 'other')
    purge.assert_called_once_with(UID, conversation_id='other')


def _real_route_app(monkeypatch):
    """Real route + tombstone writer; only storage side effects are stubbed."""
    for name in (
        'delete_owner_prompt_embedding_cache',
        'delete_conversation_screen_frames',
        'delete_conversation_and_frame_evidence',
        'delete_privacy_conversation_audio',
        'delete_vector',
        'delete_transcript_chunk_vectors',
        'delete_action_item_vectors_batch',
        'record_product_event',
        'MemoryService',
    ):
        monkeypatch.setattr(conversations, name, MagicMock())
    monkeypatch.setattr(conversations, 'destructive_operation_gate', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(conversations.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **k: {})
    monkeypatch.setattr(conversations, 'retraction_can_be_skipped', lambda *args, **kwargs: True)
    monkeypatch.setattr(conversations.action_items_db, 'get_action_items_by_conversation', lambda *a, **k: [])
    monkeypatch.setattr(conversations.action_items_db, 'delete_action_items_for_conversation', MagicMock())
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: UID
    return app


def test_heavy_owner_delete_returns_without_running_the_batch_scan(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    def heavy_owner_scan(*args, **kwargs):
        time.sleep(3)  # stands in for a 6k-row owner's 53 s scan

    purge = MagicMock(side_effect=heavy_owner_scan)
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    enqueue = MagicMock()
    monkeypatch.setattr(deletion_batch_purge, 'enqueue_conversation_batch_purge', enqueue)
    app = _real_route_app(monkeypatch)
    with TestClient(app) as client:
        started = time.monotonic()
        response = client.delete('/v1/conversations/c1?cascade=true')
        elapsed = time.monotonic() - started
    assert response.status_code == 204
    assert elapsed < 1.5
    purge.assert_not_called()
    enqueue.assert_called_once_with(UID, 'c1')
    assert _tombstone(tombstone_db, 'c1')['batch_purge_pending'] is True


def test_enqueue_failure_falls_back_to_the_inline_purge(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    purge = MagicMock()
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    monkeypatch.setattr(legal_holds, 'assert_account_deletion_permitted', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deletion_batch_purge, 'enqueue_conversation_batch_purge', MagicMock(side_effect=RuntimeError('tasks down'))
    )
    app = _real_route_app(monkeypatch)
    with TestClient(app) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 204
    purge.assert_called_once_with(UID, conversation_id='c1')
    assert _tombstone(tombstone_db, 'c1')['batch_purge_pending'] is False


def test_failed_cascade_still_dispatches_the_recorded_purge(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', MagicMock())
    enqueue = MagicMock()
    monkeypatch.setattr(deletion_batch_purge, 'enqueue_conversation_batch_purge', enqueue)
    app = _real_route_app(monkeypatch)
    conversations.delete_conversation_and_frame_evidence.side_effect = RuntimeError('lake down')
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 500
    enqueue.assert_called_once_with(UID, 'c1')


# --- the durable purge runner and its task handler ---


def test_run_batch_purge_clears_the_marker_only_after_purging(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    purge = MagicMock()
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    monkeypatch.setattr(legal_holds, 'assert_account_deletion_permitted', lambda *args, **kwargs: None)
    assert conversation_tombstones.run_batch_purge(UID, 'missing') == 'no_tombstone'
    with conversation_tombstones.defer_batch_purges(UID):
        conversation_tombstones.record_deletion(UID, 'c1')
    assert conversation_tombstones.run_batch_purge(UID, 'c1') == 'purged'
    assert conversation_tombstones.run_batch_purge(UID, 'c1') == 'already_completed'
    purge.assert_called_once_with(UID, conversation_id='c1')
    assert _tombstone(tombstone_db, 'c1')['batch_purge_pending'] is False


def test_run_batch_purge_refuses_under_legal_hold_and_keeps_the_marker(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    purge = MagicMock()
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)

    def held(*args, **kwargs):
        raise legal_holds.LegalHoldActive('held')

    monkeypatch.setattr(legal_holds, 'assert_account_deletion_permitted', held)
    with conversation_tombstones.defer_batch_purges(UID):
        conversation_tombstones.record_deletion(UID, 'c1')
    with pytest.raises(legal_holds.LegalHoldActive):
        conversation_tombstones.run_batch_purge(UID, 'c1')
    purge.assert_not_called()
    assert _tombstone(tombstone_db, 'c1')['batch_purge_pending'] is True


class _Request:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.mark.parametrize(
    'effect,status,body_status',
    [
        (lambda *a: 'purged', 200, 'done'),
        (MagicMock(side_effect=legal_holds.LegalHoldActive('held')), 200, 'held'),
        (MagicMock(side_effect=RuntimeError('firestore down')), 500, 'retry'),
    ],
)
def test_task_handler_maps_purge_outcomes_to_queue_retry(monkeypatch, effect, status, body_status):
    monkeypatch.setattr(conversation_tombstones, 'run_batch_purge', effect)
    response = asyncio.run(
        users_router.run_conversation_batch_purge(_Request({'uid': UID, 'conversation_id': 'c1'}), 0)
    )
    assert response.status_code == status
    assert body_status.encode() in response.body


def test_task_handler_drops_invalid_payloads(monkeypatch):
    runner = MagicMock()
    monkeypatch.setattr(conversation_tombstones, 'run_batch_purge', runner)
    response = asyncio.run(users_router.run_conversation_batch_purge(_Request({'uid': UID}), 0))
    assert response.status_code == 200
    runner.assert_not_called()


def test_handler_route_verifies_its_own_task_audience():
    routes = [route for route in users_router.router.routes if route.path == cloud_tasks.CONVERSATION_BATCH_PURGE_PATH]
    assert routes and 'POST' in routes[0].methods
    dependencies = [dep.call for dep in routes[0].dependant.dependencies]
    assert cloud_tasks.verify_conversation_batch_purge_cloud_tasks_oidc in dependencies


def test_enqueue_targets_backend_sync_on_the_account_deletion_queue(monkeypatch):
    monkeypatch.setenv('ACCOUNT_DELETION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setenv('ACCOUNT_DELETION_TASKS_QUEUE', 'account-deletion')
    monkeypatch.setenv(
        'ACCOUNT_DELETION_HANDLER_URL', 'https://backend-sync.example.invalid/v1/users/account-deletion-wipes/run'
    )
    monkeypatch.delenv('ACCOUNT_DELETION_TASKS_OIDC_AUDIENCE', raising=False)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    enqueue = MagicMock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    assert cloud_tasks.is_conversation_batch_purge_dispatch_configured()
    cloud_tasks.enqueue_conversation_batch_purge(UID, 'c1')
    queue, url, task_id, payload = enqueue.call_args.args
    assert queue == 'account-deletion'
    assert url == 'https://backend-sync.example.invalid/v1/conversations/deletion-batch-purges/run'
    assert task_id == cloud_tasks.conversation_batch_purge_task_id(UID, 'c1')
    assert payload == {'uid': UID, 'conversation_id': 'c1'}
    # FC-oidc-audience-borrowed-from-sibling-handler: mint and verify for this handler's own URL.
    assert enqueue.call_args.kwargs['audience'] == url
    verified = MagicMock(return_value=3)
    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verified)
    assert cloud_tasks.verify_conversation_batch_purge_cloud_tasks_oidc(MagicMock()) == 3
    assert verified.call_args.kwargs == {'audience': url, 'invoker_sa': 'invoker@example.invalid'}
    monkeypatch.setenv('ACCOUNT_DELETION_DISPATCH_MODE', 'inline')
    assert not cloud_tasks.is_conversation_batch_purge_dispatch_configured()


def test_staged_chunk_purge_is_one_commit_not_128_round_trips():
    from database import from_segments_chunks

    client = MagicMock()
    from_segments_chunks.purge_chunks(UID, 'c1', firestore_client=client)
    batch = client.batch.return_value
    slots = client.collection.return_value.document.return_value.collection.return_value
    assert batch.delete.call_count == 128
    assert [call.args[0] for call in slots.document.call_args_list] == [f'c1-{index:03d}' for index in range(128)]
    batch.commit.assert_called_once()
    slots.document.return_value.delete.assert_not_called()
