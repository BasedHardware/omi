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

from database import conversation_batch_purge_jobs as purge_jobs
from database import conversation_tombstones, legal_holds
from routers import conversations
from utils.conversations import deletion_batch_purge
from routers import users as users_router
from utils import cloud_tasks

UID = 'uid1'


# --- in-memory Firestore just deep enough for the gate and tombstone documents ---


class _Snapshot:
    def __init__(self, payload, reference=None):
        self._payload = payload
        self.exists = payload is not None
        self.reference = reference
        self.id = reference.id if reference is not None else None

    def to_dict(self):
        return dict(self._payload or {})


class _Ref:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def get(self, transaction=None, field_paths=None):
        with self.client.lock:
            payload = self.client.docs.get(self.path)
            if payload is not None and field_paths is not None:
                payload = {key: value for key, value in payload.items() if key in field_paths}
            return _Snapshot(payload, self)

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

    def delete(self):
        with self.client.lock:
            self.client.docs.pop(self.path, None)

    @property
    def id(self):
        return self.path.rsplit('/', 1)[-1]

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

    def create(self, reference, payload):
        reference.create(payload)

    def set(self, reference, payload, merge=False):
        reference.set(payload, merge=merge)

    def update(self, reference, payload):
        reference.update(payload)

    def delete(self, reference):
        reference.delete()


class _Batch:
    """Atomic like Firestore: a failed create precondition writes nothing."""

    def __init__(self, client):
        self.client, self.ops = client, []

    def create(self, reference, payload):
        self.ops.append(('create', reference, payload))

    def set(self, reference, payload, merge=False):
        self.ops.append(('set', reference, (payload, merge)))

    def delete(self, reference):
        self.ops.append(('delete', reference, None))

    def commit(self):
        from google.api_core.exceptions import AlreadyExists

        with self.client.lock:
            if any(op == 'create' and ref.path in self.client.docs for op, ref, _ in self.ops):
                raise AlreadyExists('exists')
            for op, ref, payload in self.ops:
                if op == 'create':
                    ref.create(payload)
                elif op == 'set':
                    ref.set(*payload)
                else:
                    ref.delete()


class _Client:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.lock = threading.RLock()

    def collection(self, name):
        return _Collection(self, name)

    def transaction(self):
        return _Transaction(self)

    def batch(self):
        return _Batch(self)


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

    def acquire(uid, *, kind, token, firestore_client=None, now=None, expires_at=None, max_attempts=None):
        with lock:
            legal_holds._acquire_destructive_operation_transaction.to_wrap(
                client.transaction(),
                client,
                uid,
                kind,
                token,
                now or legal_holds.datetime.now(legal_holds.timezone.utc),
                expires_at,
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

    def mark_remote(uid, *, kind, token, inflight, firestore_client=None, target=None):
        with lock:
            legal_holds._mark_remote_erasure_transaction.to_wrap(
                client.transaction(),
                client,
                uid,
                kind,
                token,
                inflight,
                legal_holds.datetime.now(legal_holds.timezone.utc),
                target,
            )

    def settle(uid, *, kind, token, firestore_client=None):
        with lock:
            return legal_holds._settle_remote_erasure_transaction.to_wrap(
                client.transaction(), client, uid, kind, token, legal_holds.datetime.now(legal_holds.timezone.utc)
            )

    monkeypatch.setattr(legal_holds, 'acquire_destructive_operation', acquire)
    monkeypatch.setattr(legal_holds, 'finish_destructive_operation', finish)
    monkeypatch.setattr(legal_holds, 'mark_remote_erasure', mark_remote)
    monkeypatch.setattr(legal_holds, 'settle_stuck_remote_erasure', settle)
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
    monkeypatch.setattr(legal_holds, '_gate_wait_jitter', lambda: 0.0)
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


def test_transaction_contention_on_the_gate_shares_the_wait(monkeypatch, gate_client, fast_clock):
    real_acquire = legal_holds.acquire_destructive_operation
    attempts = []

    def contended(*args, **kwargs):
        attempts.append(True)
        if len(attempts) <= 2:
            raise ValueError('Failed to commit transaction in 5 attempts.')
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(legal_holds, 'acquire_destructive_operation', contended)
    with legal_holds.destructive_operation_gate(UID, wait_seconds=20):
        pass
    assert len(attempts) == 3 and len(fast_clock.sleeps) == 2

    attempts.clear()
    with pytest.raises(ValueError, match='Failed to commit'):
        with legal_holds.destructive_operation_gate(UID):  # no wait budget: unchanged behaviour
            pass

    def invalid(*args, **kwargs):
        raise ValueError('destructive operation identity is invalid')

    monkeypatch.setattr(legal_holds, 'acquire_destructive_operation', invalid)
    fast_clock.sleeps.clear()
    with pytest.raises(ValueError, match='identity'):
        with legal_holds.destructive_operation_gate(UID, wait_seconds=20):
            pass
    assert fast_clock.sleeps == []


def test_route_gate_release_survives_waiter_contention(monkeypatch, gate_client, fast_clock):
    real_finish = legal_holds.finish_destructive_operation
    attempts = []

    def contended(*args, **kwargs):
        attempts.append(True)
        if len(attempts) <= 2:
            raise ValueError('Failed to commit transaction in 5 attempts.')
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(legal_holds, 'finish_destructive_operation', contended)
    with legal_holds.destructive_operation_gate(UID, wait_seconds=20):
        pass
    assert len(attempts) == 3
    assert gate_client.docs[GATE_PATH]['state'] == 'completed'  # not pinned until stale


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


# --- the request only arms a durable obligation ---


@pytest.fixture
def tombstone_db(monkeypatch):
    """One fake plane for tombstones, obligations and the gate; transactions run inline."""
    client = _Client()
    monkeypatch.setattr(conversation_tombstones, 'db', client)
    monkeypatch.setattr(purge_jobs, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(purge_jobs, '_in_transaction', lambda _client, body: body(_Transaction(client)))
    monkeypatch.setattr(
        purge_jobs, 'segment_records', lambda job, ns, limit=None, **k: _segments(client, job, ns, limit)
    )
    from database import from_segments_chunks

    monkeypatch.setattr(from_segments_chunks, 'purge_chunks', lambda *args, **kwargs: None)
    return client


def _segments(client, job, namespace, limit=None):
    prefix = f'{purge_jobs.COLLECTION}/{job}/{purge_jobs.SEGMENTS}/'
    rows = [row for path, row in sorted(client.docs.items()) if path.startswith(prefix)]
    rows = [row for row in rows if row.get('namespace') == namespace]
    return rows[:limit] if limit else rows


def _tombstone(client, conversation_id):
    return client.docs.get(f'users/{UID}/{conversation_tombstones.COLLECTION}/{conversation_id}')


def _obligation(client, conversation_id):
    return client.docs.get(f'{purge_jobs.COLLECTION}/{purge_jobs.job_id(UID, conversation_id)}')


def test_deferred_scope_arms_the_obligation_with_the_tombstone_and_skips_the_scan(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    purge = MagicMock()
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    with conversation_tombstones.defer_batch_purges(UID) as deferred:
        conversation_tombstones.record_deletion(UID, 'survivor')
        conversation_tombstones.record_deletion(UID, 'donor')
        conversation_tombstones.record_deletion(UID, 'survivor')  # retried delete re-arms, keeps tombstone
    assert deferred == ['survivor', 'donor']
    purge.assert_not_called()
    for conversation_id in ('survivor', 'donor'):
        assert _tombstone(tombstone_db, conversation_id)['conversation_id'] == conversation_id
        armed = _obligation(tombstone_db, conversation_id)
        assert armed['uid'] == UID and armed['conversation_id'] == conversation_id and armed['due_at']
    # Outside the scope the purge stays inline (dev/local, and every non-route caller).
    conversation_tombstones.record_deletion(UID, 'other')
    purge.assert_called_once_with(UID, conversation_id='other')
    assert _obligation(tombstone_db, 'other') is None


def test_obligation_is_written_before_fallible_cleanup(monkeypatch, tombstone_db):
    from database import from_segments_chunks

    monkeypatch.setattr(from_segments_chunks, 'purge_chunks', MagicMock(side_effect=RuntimeError('firestore down')))
    with conversation_tombstones.defer_batch_purges(UID):
        with pytest.raises(RuntimeError):
            conversation_tombstones.record_deletion(UID, 'c1')
    assert _tombstone(tombstone_db, 'c1') and _obligation(tombstone_db, 'c1')


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


def test_heavy_owner_delete_returns_without_scanning_or_enqueueing(monkeypatch, tombstone_db):
    from database import batch_pipeline_purge

    def heavy_owner_scan(*args, **kwargs):
        time.sleep(3)  # stands in for a 6k-row owner's 53 s scan

    purge = MagicMock(side_effect=heavy_owner_scan)
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', purge)
    enqueue = MagicMock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    app = _real_route_app(monkeypatch)
    with TestClient(app) as client:
        started = time.monotonic()
        response = client.delete('/v1/conversations/c1?cascade=true')
        elapsed = time.monotonic() - started
    assert response.status_code == 204
    assert elapsed < 1.5
    purge.assert_not_called()
    enqueue.assert_not_called()  # producers never dispatch; the consumer-side reconciler does
    assert _obligation(tombstone_db, 'c1')['due_at']


def test_failed_cascade_keeps_its_armed_obligation(monkeypatch, tombstone_db):
    app = _real_route_app(monkeypatch)
    conversations.delete_conversation_and_frame_evidence.side_effect = RuntimeError('lake down')
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 500
    assert _obligation(tombstone_db, 'c1')


# --- the reconciler and runner own completion (finding 2) ---


@pytest.fixture
def armed(tombstone_db):
    with conversation_tombstones.defer_batch_purges(UID):
        conversation_tombstones.record_deletion(UID, 'c1')
    return purge_jobs.job_id(UID, 'c1')


@pytest.fixture
def dispatch(monkeypatch):
    sent = []
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    # Default: the previous generation's task is gone (ran, exhausted, or never enqueued).
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    monkeypatch.setattr(
        deletion_batch_purge,
        'enqueue_conversation_batch_purge',
        lambda job, gen, erasure=False: sent.append((job, gen, 'erasure') if erasure else (job, gen)),
    )
    monkeypatch.setattr(
        purge_jobs,
        'due_jobs',
        lambda **kwargs: _due(kwargs.get('now'), kwargs.get('collection', purge_jobs.COLLECTION), kwargs.get('limit')),
    )
    return sent


_PLANE: list = []


def _due(now=None, collection=purge_jobs.COLLECTION, limit=None):
    client = _PLANE[0]
    now = now or purge_jobs._now()
    prefix = f'{collection}/'
    rows = [
        (row['due_at'], path)
        for path, row in client.docs.items()
        if path.startswith(prefix) and path.count('/') == 1 and row.get('due_at') is not None and row['due_at'] <= now
    ]
    # Oldest first, like the single-field ``due_at`` query.
    return [_Ref(client, path).get() for _due_at, path in sorted(rows)][:limit]


@pytest.fixture(autouse=True)
def _plane(request):
    _PLANE[:] = [request.getfixturevalue('tombstone_db')] if 'tombstone_db' in request.fixturenames else []
    yield
    _PLANE.clear()


def _advance(client, job, seconds):
    """Pretend the obligation's timers elapsed."""
    row = client.docs[f'{purge_jobs.COLLECTION}/{job}']
    for field in ('due_at', 'lease_until'):
        if row.get(field) is not None:
            row[field] = row[field] - purge_jobs.timedelta(seconds=seconds)


def _purge(monkeypatch, effect=None):
    from database import batch_pipeline_conversation_purge

    purge = MagicMock(side_effect=effect)
    monkeypatch.setattr(batch_pipeline_conversation_purge, 'purge_conversation', purge)
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda *a, **k: None)
    return purge


def test_reconciler_dispatches_new_generations_and_only_completion_clears(monkeypatch, tombstone_db, armed, dispatch):
    purge = _purge(monkeypatch)
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['dispatched'] == 1
    assert dispatch == [(armed, 1)]
    assert deletion_batch_purge.reconcile_conversation_batch_purges() == {}  # redrive not due yet
    assert purge_jobs.run_job(armed, 1) == 'purged'
    purge.assert_called_once()
    assert purge.call_args.args[:2] == (UID, 'c1')
    assert isinstance(purge.call_args.args[2], purge_jobs.RunProgress)
    assert _obligation(tombstone_db, 'c1') is None
    assert purge_jobs.run_job(armed, 1) == 'missing'  # duplicate delivery after completion


def test_lost_or_exhausted_task_is_redriven_under_a_fresh_name(monkeypatch, tombstone_db, armed, dispatch):
    _purge(monkeypatch)
    deletion_batch_purge.reconcile_conversation_batch_purges()  # generation 1 never runs (old consumer / lost)
    _advance(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch == [(armed, 1), (armed, 2)]
    names = {cloud_tasks.conversation_batch_purge_task_id(job, gen) for job, gen in dispatch}
    assert len(names) == 2  # a spent or reserved name never swallows the redrive
    assert purge_jobs.run_job(armed, 1) == 'superseded'  # a late generation-1 delivery cannot clear generation 2
    assert _obligation(tombstone_db, 'c1')
    assert purge_jobs.run_job(armed, 2) == 'purged'
    assert _obligation(tombstone_db, 'c1') is None


def test_generation_still_in_its_queue_is_not_redriven(monkeypatch, tombstone_db, armed, dispatch):
    """A backlog past the redrive delay must not add a second task per waiting obligation (prod 2026-11-14)."""
    _purge(monkeypatch)
    probes = []

    def pending(job, generation, erasure=False):
        probes.append((job, generation, erasure))
        return True

    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', pending)
    deletion_batch_purge.reconcile_conversation_batch_purges()  # generation 1 waits in a backed-up queue
    _advance(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    result = deletion_batch_purge.reconcile_conversation_batch_purges()
    assert result['queued'] == 1 and result['dispatched'] == 0
    assert dispatch == [(armed, 1)] and probes == [(armed, 1, False)]
    row = _obligation(tombstone_db, 'c1')
    assert row['generation'] == 1 and row['attempts'] == 1
    assert row['due_at'] > purge_jobs._now() + purge_jobs.timedelta(seconds=purge_jobs.REDRIVE_SECONDS - 5)
    assert purge_jobs.run_job(armed, 1) == 'purged'  # the waiting task still owns the obligation
    assert _obligation(tombstone_db, 'c1') is None


def test_generation_gone_from_its_queue_is_redriven(monkeypatch, tombstone_db, armed, dispatch):
    _purge(monkeypatch)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    _advance(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['dispatched'] == 1
    assert dispatch == [(armed, 1), (armed, 2)]


def test_unanswered_probe_redrives_rather_than_strand(monkeypatch, tombstone_db, armed, dispatch):
    _purge(monkeypatch)
    fallback = MagicMock()
    monkeypatch.setattr(deletion_batch_purge, 'record_fallback', fallback)
    monkeypatch.setattr(
        deletion_batch_purge,
        'conversation_batch_purge_task_pending',
        MagicMock(side_effect=RuntimeError('tasks api down')),
    )
    deletion_batch_purge.reconcile_conversation_batch_purges()
    _advance(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    result = deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch == [(armed, 1), (armed, 2)] and result['probe_failed'] == 1
    assert fallback.call_args.kwargs['to_mode'] == 'blind_redrive'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'


def test_one_unanswered_probe_per_pass(monkeypatch, tombstone_db, dispatch):
    _purge(monkeypatch)
    jobs = []
    for conversation_id in ('c1', 'c2', 'c3'):
        with conversation_tombstones.defer_batch_purges(UID):
            conversation_tombstones.record_deletion(UID, conversation_id)
        jobs.append(purge_jobs.job_id(UID, conversation_id))
    deletion_batch_purge.reconcile_conversation_batch_purges()
    for job in jobs:
        _advance(tombstone_db, job, purge_jobs.REDRIVE_SECONDS + 1)
    probe = MagicMock(side_effect=TimeoutError('tasks api timeout'))
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', probe)
    monkeypatch.setattr(deletion_batch_purge, 'record_fallback', MagicMock())
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['dispatched'] == 3
    assert probe.call_count == 1


def test_running_generation_is_skipped_without_a_probe(monkeypatch, tombstone_db, armed, dispatch):
    probe = MagicMock(return_value=True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', probe)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    row = _obligation(tombstone_db, 'c1')
    row['due_at'] = purge_jobs._now() - purge_jobs.timedelta(seconds=1)  # lease renewals never move due_at
    row['lease_until'] = purge_jobs._now() + purge_jobs.timedelta(seconds=60)
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['skipped'] == 1
    probe.assert_not_called()


def test_queued_hold_never_touches_a_newer_generation(tombstone_db, armed):
    row = _obligation(tombstone_db, 'c1')
    row['generation'], due = 2, row['due_at']
    purge_jobs.defer(armed, purge_jobs.REDRIVE_SECONDS, generation=1)
    assert _obligation(tombstone_db, 'c1')['due_at'] == due


def test_held_obligation_is_redriven_automatically_after_release(monkeypatch, tombstone_db, armed, dispatch):
    purge = _purge(monkeypatch)

    def held(*args, **kwargs):
        raise legal_holds.LegalHoldActive('held')

    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', held)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert purge_jobs.run_job(armed, 1) == 'held'
    purge.assert_not_called()
    assert _obligation(tombstone_db, 'c1')['last_outcome'] == 'held'
    assert deletion_batch_purge.reconcile_conversation_batch_purges() == {}  # rechecked hourly, not hot
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda *a, **k: None)  # hold released
    _advance(tombstone_db, armed, purge_jobs.HOLD_RECHECK_SECONDS + 1)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch[-1] == (armed, 2)
    assert purge_jobs.run_job(armed, 2) == 'purged'
    assert _obligation(tombstone_db, 'c1') is None


def test_failed_run_keeps_the_obligation_and_duplicate_delivery_does_not_overlap(
    monkeypatch, tombstone_db, armed, dispatch
):
    entered = []

    def failing_scan(*args, **kwargs):
        entered.append(purge_jobs.run_job(armed, 1))  # a concurrent duplicate of the same generation
        raise RuntimeError('firestore deadline')

    _purge(monkeypatch, failing_scan)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    with pytest.raises(RuntimeError):
        purge_jobs.run_job(armed, 1)
    assert entered == ['in_progress']
    row = _obligation(tombstone_db, 'c1')
    assert row['last_outcome'] == 'failed' and row['lease_until'] is None


def test_consumer_without_the_route_holds_dispatch(monkeypatch, tombstone_db, armed, dispatch):
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: False)
    result = deletion_batch_purge.reconcile_conversation_batch_purges()
    assert result == {'due': 1, 'held_for_consumer': 1}
    assert dispatch == []
    assert _obligation(tombstone_db, 'c1')['due_at'] <= purge_jobs._now()  # still due for the new consumer


def test_enqueue_failure_makes_the_obligation_due_again_soon(monkeypatch, tombstone_db, armed, dispatch):
    monkeypatch.setattr(
        deletion_batch_purge, 'enqueue_conversation_batch_purge', MagicMock(side_effect=RuntimeError('tasks down'))
    )
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['enqueue_failed'] == 1
    due = _obligation(tombstone_db, 'c1')['due_at']
    assert due <= purge_jobs._now() + purge_jobs.timedelta(seconds=deletion_batch_purge.ENQUEUE_RETRY_SECONDS + 1)


def test_wiped_account_completes_without_a_tombstone(monkeypatch, tombstone_db, armed, dispatch):
    purge = _purge(monkeypatch)
    tombstone_db.docs.pop(f'users/{UID}/{conversation_tombstones.COLLECTION}/c1')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert purge_jobs.run_job(armed, 1) == 'no_tombstone'
    purge.assert_not_called()
    assert _obligation(tombstone_db, 'c1') is None


def test_transaction_bodies_read_before_they_write():
    """Real ``@transactional`` bodies over the strict fixture (reads after a write fail)."""
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    job = purge_jobs.job_id(UID, 'c1')
    store = StrictFirestore({(purge_jobs.COLLECTION, job): purge_jobs.arm_fields(UID, 'c1')})
    assert purge_jobs.claim_dispatch(job, firestore_client=store) == (1, 1)
    later = purge_jobs._now() + purge_jobs.timedelta(seconds=1)
    claim, _row, token = purge_jobs.begin_run(job, 1, now=later, firestore_client=store)
    assert claim == 'run' and token
    assert purge_jobs.begin_run(job, 1, now=later, firestore_client=store)[0] == 'in_progress'
    assert purge_jobs.finish_run(job, 1, 'not-the-owner', 'completed', firestore_client=store) is False
    assert purge_jobs.finish_run(job, 1, token, 'completed', firestore_client=store) is True
    assert not store.collection(purge_jobs.COLLECTION).document(job).get().exists


# --- legal hold / account wipe fence each erasure unit (finding 1) ---


def test_account_wipe_gate_stops_purge_units(gate_client):
    gate_client.docs[GATE_PATH] = _gate_doc(kind='account_deletion')
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.destructive_operation_gate(UID, kind='explicit_memory_deletion', wait_seconds=0):
            pytest.fail('erased while the account wipe owns the gate')


# --- the task handler ---


class _Request:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.mark.parametrize(
    'effect,status,body_status',
    [
        (lambda *a: 'purged', 200, 'done'),
        (lambda *a: 'held', 200, 'done'),
        (MagicMock(side_effect=RuntimeError('firestore down')), 500, 'retry'),
    ],
)
def test_task_handler_maps_run_outcomes_to_queue_retry(monkeypatch, effect, status, body_status):
    monkeypatch.setattr(purge_jobs, 'run_job', effect)
    response = asyncio.run(users_router.run_conversation_batch_purge(_Request({'job_id': 'j1', 'generation': 1}), 0))
    assert response.status_code == status
    assert body_status.encode() in response.body


def test_task_handler_runs_on_its_own_pool_not_the_account_wipe_pool(monkeypatch):
    from utils import executors

    pools = []

    async def run_blocking(pool, fn, *args):
        pools.append(pool)
        return fn(*args)

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(purge_jobs, 'run_job', lambda *a: 'purged')
    asyncio.run(users_router.run_conversation_batch_purge(_Request({'job_id': 'j1', 'generation': 1}), 0))
    assert pools == [executors.erasure_executor]
    assert executors.erasure_executor is not executors.cleanup_executor
    # Every task the conversation-erasure queue delivers at once gets a thread on one instance.
    assert executors.erasure_executor._max_workers == 20


@pytest.mark.parametrize('payload', [{'job_id': 'j1'}, {'generation': 1}, {'job_id': 'j1', 'generation': 0}, ['x']])
def test_task_handler_drops_invalid_payloads(monkeypatch, payload):
    runner = MagicMock()
    monkeypatch.setattr(purge_jobs, 'run_job', runner)
    response = asyncio.run(users_router.run_conversation_batch_purge(_Request(payload), 0))
    assert response.status_code == 200
    runner.assert_not_called()


def test_handler_route_verifies_its_own_task_audience():
    routes = [route for route in users_router.router.routes if route.path == cloud_tasks.CONVERSATION_BATCH_PURGE_PATH]
    assert routes and 'POST' in routes[0].methods
    dependencies = [dep.call for dep in routes[0].dependant.dependencies]
    assert cloud_tasks.verify_conversation_batch_purge_cloud_tasks_oidc in dependencies


@pytest.fixture
def purge_env(monkeypatch):
    monkeypatch.setenv('ACCOUNT_DELETION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setenv('ACCOUNT_DELETION_TASKS_QUEUE', 'account-deletion')
    monkeypatch.delenv('CONVERSATION_ERASURE_TASKS_QUEUE', raising=False)  # unset: the shared queue, as before
    monkeypatch.setenv(
        'ACCOUNT_DELETION_HANDLER_URL', 'https://backend-sync.example.invalid/v1/users/account-deletion-wipes/run'
    )
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    return 'https://backend-sync.example.invalid/v1/conversations/deletion-batch-purges/run'


def test_units_ride_the_conversation_erasure_queue_apart_from_account_wipes(monkeypatch, purge_env):
    enqueue = MagicMock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    monkeypatch.setenv('CONVERSATION_ERASURE_TASKS_QUEUE', 'conversation-erasure')
    assert cloud_tasks.conversation_erasure_queues() == ('conversation-erasure', 'account-deletion')
    cloud_tasks.enqueue_conversation_batch_purge('j1', 3)
    cloud_tasks.enqueue_conversation_batch_purge('j2', 1, erasure=True)
    assert [call.args[0] for call in enqueue.call_args_list] == ['conversation-erasure', 'conversation-erasure']
    assert enqueue.call_args.args[2] == 'conversation-erasure-j2-g1'
    cloud_tasks.enqueue_account_deletion_wipe('wipe-1')
    assert enqueue.call_args.args[0] == 'account-deletion'  # wipes stay alone on their queue
    cloud_tasks.enqueue_conversation_batch_purge('j3', 1, queue='account-deletion')
    assert enqueue.call_args.args[0] == 'account-deletion'


def test_task_probe_looks_in_the_erasure_queue_then_the_shared_one(monkeypatch, purge_env):
    monkeypatch.setenv('CONVERSATION_ERASURE_TASKS_QUEUE', 'conversation-erasure')
    probes = []
    held_by = {'account-deletion'}  # dispatched by a revision that predates the split

    def exists(queue, task_id):
        probes.append((queue, task_id))
        return queue in held_by

    monkeypatch.setattr(cloud_tasks, 'named_task_exists', exists)
    assert cloud_tasks.conversation_batch_purge_task_pending('j1', 2) is True
    assert probes == [
        ('conversation-erasure', 'conversation-batch-purge-j1-g2'),
        ('account-deletion', 'conversation-batch-purge-j1-g2'),
    ]
    held_by.clear()
    assert cloud_tasks.conversation_batch_purge_task_pending('j1', 2, erasure=True) is False
    assert probes[-1] == ('account-deletion', 'conversation-erasure-j1-g2')

    def denied(queue, task_id):
        raise PermissionError('denied')

    monkeypatch.setattr(cloud_tasks, 'named_task_exists', denied)
    with pytest.raises(PermissionError):
        cloud_tasks.conversation_batch_purge_task_pending('j1', 2)  # unknown is never "gone"


def test_missing_erasure_queue_keeps_units_on_the_shared_queue(monkeypatch, purge_env):
    from google.api_core.exceptions import NotFound

    monkeypatch.setenv('CONVERSATION_ERASURE_TASKS_QUEUE', 'conversation-erasure')
    sent = []

    def enqueue(job, generation, erasure=False, queue=None):
        if queue is None:
            raise NotFound('queue conversation-erasure')
        sent.append((job, generation, erasure, queue))

    fallback = MagicMock()
    monkeypatch.setattr(deletion_batch_purge, 'enqueue_conversation_batch_purge', enqueue)
    monkeypatch.setattr(deletion_batch_purge, 'record_fallback', fallback)
    deletion_batch_purge._enqueue('j1', 1, True)
    assert sent == [('j1', 1, True, 'account-deletion')]
    assert fallback.call_args.kwargs['to_mode'] == 'account_deletion_queue'
    monkeypatch.delenv('CONVERSATION_ERASURE_TASKS_QUEUE')
    with pytest.raises(NotFound):
        deletion_batch_purge._enqueue('j1', 1, True)  # no second queue to fall back to


def test_enqueue_sends_an_opaque_generation_task_with_its_own_audience(monkeypatch, purge_env):
    enqueue = MagicMock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    assert cloud_tasks.is_conversation_batch_purge_dispatch_configured()
    cloud_tasks.enqueue_conversation_batch_purge('j1', 3)
    queue, url, task_id, payload = enqueue.call_args.args
    assert (queue, url) == ('account-deletion', purge_env)
    assert task_id == 'conversation-batch-purge-j1-g3'
    assert payload == {'job_id': 'j1', 'generation': 3}  # no uid or conversation id in the queue
    # FC-oidc-audience-borrowed-from-sibling-handler: mint and verify for this handler's own URL.
    assert enqueue.call_args.kwargs['audience'] == purge_env
    verified = MagicMock(return_value=3)
    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verified)
    assert cloud_tasks.verify_conversation_batch_purge_cloud_tasks_oidc(MagicMock()) == 3
    assert verified.call_args.kwargs == {'audience': purge_env, 'invoker_sa': 'invoker@example.invalid'}
    monkeypatch.setenv('ACCOUNT_DELETION_DISPATCH_MODE', 'inline')
    assert not cloud_tasks.is_conversation_batch_purge_dispatch_configured()


@pytest.mark.parametrize(
    'status,body,ready',
    [
        (403, b'{"detail": "Missing bearer token"}', True),  # new consumer: route + verifier
        (404, b'{"detail": "Not Found"}', False),  # old consumer: no route
        (405, b'{}', False),
        (403, b'{"detail": "Forbidden"}', False),  # something else answered
    ],
)
def test_consumer_probe_tells_the_new_route_from_an_old_revision(monkeypatch, purge_env, status, body, ready):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs.get('headers')))
        return SimpleNamespace(status=status, data=body)

    monkeypatch.setattr(cloud_tasks, '_get_auth_request', lambda: request)
    assert cloud_tasks.conversation_batch_purge_consumer_ready() is ready
    assert calls[0][0] == purge_env and 'Authorization' not in (calls[0][1] or {})


def test_consumer_probe_network_failure_is_unknown_not_ready(monkeypatch, purge_env):
    def unreachable(url, **kwargs):
        raise OSError('no route')

    monkeypatch.setattr(cloud_tasks, '_get_auth_request', lambda: unreachable)
    assert cloud_tasks.conversation_batch_purge_consumer_ready() is None


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


def test_rollout_and_rollback_order_cannot_strand_an_obligation(monkeypatch, tombstone_db, armed, dispatch):
    """Producers never dispatch; the dispatcher waits for the live route and redrives lost generations."""
    serving = {'route': False}
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: serving['route'])
    _purge(monkeypatch)
    # New producers, old backend-sync still serving: nothing is sent.
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['held_for_consumer'] == 1
    assert dispatch == []
    # New consumer serving: generation 1 goes out ...
    serving['route'] = True
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch == [(armed, 1)]
    # ... then backend-sync rolls back before it runs: the task 404s to exhaustion and never runs.
    serving['route'] = False
    _advance(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    assert deletion_batch_purge.reconcile_conversation_batch_purges()['held_for_consumer'] == 1
    assert _obligation(tombstone_db, 'c1')  # still owed
    # Roll forward again: a fresh generation and name, which completes.
    serving['route'] = True
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch[-1] == (armed, 2)
    assert purge_jobs.run_job(armed, 2) == 'purged'
    assert _obligation(tombstone_db, 'c1') is None
