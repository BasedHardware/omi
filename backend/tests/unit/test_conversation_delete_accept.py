"""Same-account conversation deletes are accepted at once and erased in order.

Prod 2026-11-12: 1,021 phone cascade deletes, 848 answered 409 after the full
~20 s gate wait; one phone sent 53 deletes in the same second and only ~4 fit
behind a ~5 s serialized delete. A delete that finds a same-account delete
holding the account gate is now accepted (tombstone + hidden row + durable
erasure obligation in one commit, 204 at once) and the obligation runner
performs the request's own cascade under the gate, one at a time.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversation_batch_purge_jobs as purge_jobs
from database import conversation_tombstones, legal_holds
from routers import conversations
from routers import users as users_router
from utils import cloud_tasks
from utils.conversations import deletion_batch_purge
from tests.unit.test_conversation_delete_gate_wait import (  # noqa: F401 - fixtures
    GATE_PATH,
    HOLD_PATH,
    UID,
    _Transaction,
    _gate_doc,
    gate_client,
)

ERASURES = purge_jobs.ERASURE_COLLECTION


def _conversation_path(conversation_id):
    return f'users/{UID}/conversations/{conversation_id}'


def _tombstone(client, conversation_id):
    return client.docs.get(f'users/{UID}/{conversation_tombstones.COLLECTION}/{conversation_id}')


def _erasure(client, conversation_id):
    return client.docs.get(f'{ERASURES}/{purge_jobs.erasure_job_id(UID, conversation_id)}')


def _hidden(client, conversation_id):
    row = client.docs.get(_conversation_path(conversation_id))
    return row is None or conversations.conversations_db.is_soft_deleted(row)


def _hold(client, active=True):
    client.docs[HOLD_PATH] = {
        'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION,
        'issuer': 'legal_hold_service',
        'active': active,
    }


def _due(client, now=None, collection=purge_jobs.COLLECTION, limit=None):
    now = now or purge_jobs._now()
    rows = sorted(
        (row['due_at'], path)
        for path, row in client.docs.items()
        if path.startswith(f'{collection}/') and path.count('/') == 1 and row.get('due_at') and row['due_at'] <= now
    )
    return [_RefSnapshot(client, path) for _due_at, path in rows][:limit]


class _RefSnapshot:
    def __init__(self, client, path):
        self.id = path.rsplit('/', 1)[-1]
        self._row = dict(client.docs[path])

    def to_dict(self):
        return dict(self._row)


def _advance(client, seconds):
    """Pretend every erasure obligation's timers elapsed."""
    for path, row in client.docs.items():
        if path.startswith(f'{ERASURES}/') and path.count('/') == 1:
            for field in ('due_at', 'lease_until'):
                if row.get(field) is not None:
                    row[field] = row[field] - purge_jobs.timedelta(seconds=seconds)


@pytest.fixture
def plane(monkeypatch, gate_client):
    """One in-memory Firestore for rows, tombstones, obligations, the gate and the hold."""
    client = gate_client
    monkeypatch.setattr(conversation_tombstones, 'db', client)
    monkeypatch.setattr(conversation_tombstones, '_in_transaction', lambda _c, body: body(_Transaction(client)))
    monkeypatch.setattr('database._client.get_firestore_client', lambda: client)
    monkeypatch.setattr(purge_jobs, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(purge_jobs, '_in_transaction', lambda _c, body: body(_Transaction(client)))
    from database import from_segments_chunks

    monkeypatch.setattr(from_segments_chunks, 'purge_chunks', lambda *args, **kwargs: None)
    monkeypatch.setattr(legal_holds, '_gate_wait_sleep', lambda seconds: time.sleep(min(seconds, 0.01)))
    monkeypatch.setattr(legal_holds, '_gate_wait_jitter', lambda: 0.0)
    for index in range(60):
        client.docs[_conversation_path(f'c{index}')] = {'created_at': 'original', 'sync_merged_from': []}
    return client


@pytest.fixture
def cascade(monkeypatch, plane):
    """The real route, gate, accept writer and eraser; only storage side effects are stubbed."""
    state = type('State', (), {})()
    state.erased, state.inside, state.peak = [], [0], [0]
    lock = threading.Lock()
    for name in (
        'delete_owner_prompt_embedding_cache',
        'delete_conversation_screen_frames',
        'delete_conversation_audio_under_gate',
        'delete_vector',
        'delete_transcript_chunk_vectors',
        'delete_action_item_vectors_batch',
        'record_product_event',
        'MemoryService',
    ):
        monkeypatch.setattr(conversations, name, MagicMock())
    monkeypatch.setattr(conversations.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **k: {})
    monkeypatch.setattr(conversations, 'retraction_can_be_skipped', lambda *args, **kwargs: True)
    monkeypatch.setattr(conversations.action_items_db, 'get_action_items_by_conversation', lambda *a, **k: [])
    monkeypatch.setattr(conversations.action_items_db, 'delete_action_items_for_conversation', MagicMock())
    monkeypatch.setattr(conversations, 'db_client_module', MagicMock(db=plane))

    def hard_delete(uid, conversation_id):
        with lock:
            state.inside[0] += 1
            state.peak[0] = max(state.peak[0], state.inside[0])
        time.sleep(0.1)  # a real cascade holds the account gate for seconds
        with lock:
            state.inside[0] -= 1
            state.erased.append(conversation_id)
            plane.docs.pop(_conversation_path(conversation_id), None)

    monkeypatch.setattr(conversations, 'delete_conversation_and_frame_evidence', hard_delete)
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    state.sent, state.audio_sent = [], []
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    monkeypatch.setattr(
        deletion_batch_purge,
        'enqueue_conversation_batch_purge',
        lambda job, gen, erasure=False, audio=False: (state.audio_sent if audio else state.sent).append(
            (job, gen) if audio else (job, gen, erasure)
        ),
    )
    monkeypatch.setattr(
        purge_jobs,
        'due_jobs',
        lambda **kwargs: _due(
            plane, kwargs.get('now'), kwargs.get('collection', purge_jobs.COLLECTION), kwargs.get('limit')
        ),
    )
    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: UID
    state.app = app
    return state


def _drain_erasures(plane, cascade, *, passes=40):
    """Reconciler passes plus the consumer running each dispatched erasure, until none is owed."""
    outcomes, per_pass = [], []
    for _ in range(passes):
        if not any(path.startswith(f'{ERASURES}/') for path in plane.docs):
            break
        cascade.sent.clear()
        deletion_batch_purge.reconcile_conversation_batch_purges()
        erasures = [(job, gen) for job, gen, erasure in cascade.sent if erasure]
        per_pass.append(len(erasures))
        for job, gen in erasures:
            outcomes.append(purge_jobs.run_erasure_job(job, gen, erase=conversations.erase_accepted_conversation))
        _advance(plane, deletion_batch_purge.ERASURE_SPREAD_SECONDS + purge_jobs.BUSY_RETRY_SECONDS)
    return outcomes, per_pass


def test_53_same_second_deletes_all_return_204_fast_and_all_end_erased(plane, cascade):
    statuses, elapsed = [], []
    record = threading.Lock()
    start = threading.Barrier(53)

    def delete(conversation_id):
        with TestClient(cascade.app) as client:
            start.wait()
            began = time.monotonic()
            status = client.delete(f'/v1/conversations/{conversation_id}?cascade=true').status_code
            with record:
                statuses.append(status)
                elapsed.append(time.monotonic() - began)

    threads = [threading.Thread(target=delete, args=(f'c{i}',)) for i in range(53)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert statuses == [204] * 53
    # Serialized behind the gate this took 53 x 0.1 s = 5.3 s, and past 20 s it answered 409.
    assert max(elapsed) < 3.0
    for index in range(53):
        assert _tombstone(plane, f'c{index}'), 'every accepted delete records its intent'
        assert _hidden(plane, f'c{index}'), 'the conversation disappears for the user at once'
    accepted = [f'c{i}' for i in range(53) if _erasure(plane, f'c{i}')]
    assert accepted, 'the burst must exercise the accept path'
    assert len(accepted) + len(cascade.erased) == 53

    outcomes, per_pass = _drain_erasures(plane, cascade)

    assert sorted(cascade.erased) == sorted(f'c{i}' for i in range(53))
    assert all(plane.docs.get(_conversation_path(f'c{i}')) is None for i in range(53))
    assert not any(path.startswith(f'{ERASURES}/') for path in plane.docs)
    assert cascade.peak[0] == 1, 'two same-account cascades ran inside the account gate at once'
    assert max(per_pass) <= deletion_batch_purge.MAX_ERASURES_PER_ACCOUNT
    assert outcomes.count('erased') == len(accepted)
    # Each erasure ran the request's cascade, which arms the batch purge next to its tombstone.
    for conversation_id in accepted:
        assert plane.docs.get(f'{purge_jobs.COLLECTION}/{purge_jobs.job_id(UID, conversation_id)}')
    # Untouched conversations stay.
    assert plane.docs.get(_conversation_path('c59')) is not None


def _accept_behind_peer(cascade, conversation_id='c1'):
    with TestClient(cascade.app) as client:
        return client.delete(f'/v1/conversations/{conversation_id}?cascade=true')


def test_busy_peer_gate_accepts_without_waiting_and_erases_nothing(plane, cascade):
    plane.docs[GATE_PATH] = _gate_doc()  # another delete of this account holds the gate
    began = time.monotonic()
    response = _accept_behind_peer(cascade)
    assert response.status_code == 204 and response.content == b''
    assert response.headers['X-Omi-Delete-Outcome'] == 'accepted_deferred'
    assert time.monotonic() - began < 1.0
    assert cascade.erased == []
    assert _tombstone(plane, 'c1') and _hidden(plane, 'c1')
    assert plane.docs[_conversation_path('c1')]['deleted'] is True  # retained until the runner erases
    owed = _erasure(plane, 'c1')
    assert owed['uid'] == UID and owed['conversation_id'] == 'c1' and owed['due_at']
    conversations.record_product_event.assert_called_once()


def test_hold_placed_after_acceptance_stops_erasure_and_keeps_it_hidden_and_retained(plane, cascade):
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    plane.docs.pop(GATE_PATH)
    _hold(plane)

    outcomes, _per_pass = _drain_erasures(plane, cascade, passes=1)

    assert outcomes == ['held']
    assert cascade.erased == []
    assert plane.docs[_conversation_path('c1')]['deleted'] is True  # retained under the hold
    assert _tombstone(plane, 'c1') and _hidden(plane, 'c1')
    owed = _erasure(plane, 'c1')
    assert owed['last_outcome'] == 'held'
    drained = deletion_batch_purge.ERASURE_SPREAD_SECONDS + purge_jobs.BUSY_RETRY_SECONDS  # the helper's advance
    recheck = purge_jobs.HOLD_RECHECK_SECONDS - drained - 5
    assert owed['due_at'] >= purge_jobs._now() + purge_jobs.timedelta(seconds=recheck)

    _hold(plane, active=False)  # released: the hourly recheck erases it
    _advance(plane, purge_jobs.HOLD_RECHECK_SECONDS + 1)
    outcomes, _per_pass = _drain_erasures(plane, cascade, passes=1)
    assert outcomes == ['erased'] and cascade.erased == ['c1']


def test_hold_racing_the_gate_inside_the_eraser_still_wins(plane, cascade, monkeypatch):
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    plane.docs.pop(GATE_PATH)
    # The preflight passed; the hold lands before the eraser's gate acquisition.
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda *a, **k: _hold(plane))
    outcomes, _per_pass = _drain_erasures(plane, cascade, passes=1)
    assert outcomes == ['held']
    assert cascade.erased == []
    assert plane.docs[_conversation_path('c1')]['deleted'] is True


def test_account_deletion_supersedes_an_accepted_delete(plane, cascade):
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    plane.docs[GATE_PATH] = _gate_doc(kind='account_deletion')  # the wipe is running
    deletion_batch_purge.reconcile_conversation_batch_purges()
    job, gen, _erasure_kind = cascade.sent[-1]
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        purge_jobs.run_erasure_job(job, gen, erase=conversations.erase_accepted_conversation)
    assert cascade.erased == []
    assert _erasure(plane, 'c1')['last_outcome'] == 'failed'  # kept and redriven, never dropped
    # The wipe finishes: the user's subtree (row and tombstone) is gone.
    for path in [path for path in plane.docs if path.startswith(f'users/{UID}/')]:
        plane.docs.pop(path)
    plane.docs.pop(GATE_PATH)
    _advance(plane, purge_jobs.REDRIVE_SECONDS + 1)
    outcomes, _per_pass = _drain_erasures(plane, cascade, passes=1)
    assert outcomes == ['no_tombstone']
    assert cascade.erased == []
    assert _erasure(plane, 'c1') is None


def test_reconciler_redrives_a_lost_erasure_task_and_an_old_consumer_cannot_drop_it(plane, cascade):
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    plane.docs.pop(GATE_PATH)
    job = purge_jobs.erasure_job_id(UID, 'c1')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert cascade.sent == [(job, 1, True)]
    # Generation 1 is lost, or reaches a consumer that predates erasures (it looks among purge jobs).
    assert purge_jobs.run_job(job, 1) == 'missing'
    assert _erasure(plane, 'c1')
    assert deletion_batch_purge.reconcile_conversation_batch_purges().get('erasures_dispatched', 0) == 0
    _advance(plane, purge_jobs.REDRIVE_SECONDS + 1)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert cascade.sent[-1] == (job, 2, True)
    names = {cloud_tasks.conversation_erasure_task_id(job, gen) for job, gen, _e in cascade.sent}
    assert len(names) == 2
    assert purge_jobs.run_erasure_job(job, 1, erase=conversations.erase_accepted_conversation) == 'superseded'
    assert purge_jobs.run_erasure_job(job, 2, erase=conversations.erase_accepted_conversation) == 'erased'
    assert cascade.erased == ['c1'] and _erasure(plane, 'c1') is None


def test_erasure_behind_a_busy_gate_retries_soon_without_failing(plane, cascade, monkeypatch):
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    monkeypatch.setattr(conversations, 'ACCEPTED_ERASURE_GATE_WAIT_SECONDS', 0.05)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    job, gen, _erasure_kind = cascade.sent[-1]
    assert purge_jobs.run_erasure_job(job, gen, erase=conversations.erase_accepted_conversation) == 'busy'
    owed = _erasure(plane, 'c1')
    assert owed['last_outcome'] == 'busy' and owed['attempts'] == 0 and owed['lease_until'] is None
    assert owed['due_at'] <= purge_jobs._now() + purge_jobs.timedelta(seconds=purge_jobs.BUSY_RETRY_SECONDS + 1)
    assert cascade.erased == []


def test_account_wipe_at_request_time_still_rejects_and_writes_nothing(plane, cascade):
    plane.docs[GATE_PATH] = _gate_doc(kind='account_deletion')
    with TestClient(cascade.app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 409
    assert _tombstone(plane, 'c1') is None and _erasure(plane, 'c1') is None
    assert 'deleted' not in plane.docs[_conversation_path('c1')]


def test_held_cascade_delete_is_hidden_and_retained_until_release_then_erased(plane, cascade):
    # P7 Decision 4: a hold blocks physical disposal, never product access.
    _hold(plane)
    with TestClient(cascade.app) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 204
    assert response.headers['X-Omi-Delete-Outcome'] == 'held_deferred'
    tombstone = _tombstone(plane, 'c1')
    assert tombstone['legal_hold_deferred'] is True and tombstone['erasure_armed'] is True
    assert _hidden(plane, 'c1') and _erasure(plane, 'c1')

    outcomes, _ = _drain_erasures(plane, cascade, passes=2)
    assert outcomes and set(outcomes) == {'held'}
    assert cascade.erased == [] and plane.docs.get(_conversation_path('c1')) is not None

    _hold(plane, active=False)
    _advance(plane, 3600)
    outcomes, _ = _drain_erasures(plane, cascade)
    assert 'erased' in outcomes and cascade.erased == ['c1']


def test_held_non_cascade_delete_is_hidden_retained_and_arms_no_erasure(plane, cascade):
    _hold(plane)
    with TestClient(cascade.app) as client:
        response = client.delete('/v1/conversations/c1')
    assert response.status_code == 204
    assert response.headers['X-Omi-Delete-Outcome'] == 'held_deferred'
    tombstone = _tombstone(plane, 'c1')
    assert tombstone['legal_hold_deferred'] is True and tombstone['erasure_armed'] is False
    assert _hidden(plane, 'c1')
    assert _erasure(plane, 'c1') is None, 'the runner only cascades; a non-cascade delete must not arm it'
    assert cascade.erased == [] and plane.docs.get(_conversation_path('c1')) is not None
    conversations.delete_conversation_audio_under_gate.assert_not_called()
    conversations.delete_conversation_screen_frames.assert_not_called()


def test_held_delete_kill_switch_restores_previous_non_cascade_behavior(plane, cascade, monkeypatch):
    monkeypatch.setenv('LEGAL_HOLD_DEFER_SINGLE_DELETE', 'false')
    _hold(plane)
    with TestClient(cascade.app) as client:
        response = client.delete('/v1/conversations/c1')
    assert response.status_code == 204
    assert response.headers['X-Omi-Delete-Outcome'] == 'tombstoned'
    assert cascade.erased == ['c1']


def test_hold_released_during_a_held_non_cascade_delete_falls_through_to_normal_deletion(plane, cascade, monkeypatch):
    # The hold is on another Firestore client, so it cannot join the tombstone transaction.
    # A release (and its follow-up scan) that lands between them must not strand an unarmed tombstone.
    from database import conversation_tombstones as tombstones

    accept = tombstones.accept_deletion

    def accept_then_release(*args, **kwargs):
        accept(*args, **kwargs)
        _hold(plane, active=False)

    monkeypatch.setattr(tombstones, 'accept_deletion', accept_then_release)
    _hold(plane)
    with TestClient(cascade.app) as client:
        response = client.delete('/v1/conversations/c1')
    assert response.status_code == 204
    assert response.headers['X-Omi-Delete-Outcome'] == 'tombstoned'
    assert cascade.erased == ['c1']
    assert _tombstone(plane, 'c1')['legal_hold_deferred'] is False, 'erased: release follow-up owes nothing'


def test_a_failed_normal_delete_after_release_keeps_the_follow_up_marker(plane, cascade, monkeypatch):
    from fastapi import HTTPException

    from database import conversation_tombstones as tombstones

    accept = tombstones.accept_deletion

    def accept_then_release(*args, **kwargs):
        accept(*args, **kwargs)
        _hold(plane, active=False)

    def lake_unavailable(*args, **kwargs):
        raise HTTPException(status_code=503, detail='lake unavailable')

    monkeypatch.setattr(tombstones, 'accept_deletion', accept_then_release)
    monkeypatch.setattr(conversations, '_delete_conversation_under_gate', lake_unavailable)
    _hold(plane)
    with TestClient(cascade.app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1')
    assert response.status_code == 503
    assert _tombstone(plane, 'c1')['legal_hold_deferred'] is True, 'still retained: release follow-up must list it'


def test_held_non_cascade_delete_keeps_an_obligation_an_earlier_accept_armed(plane, cascade):
    plane.docs[f'users/{UID}/{conversation_tombstones.COLLECTION}/c1'] = {'conversation_id': 'c1'}
    plane.docs[f'{ERASURES}/{purge_jobs.erasure_job_id(UID, "c1")}'] = {'uid': UID, 'conversation_id': 'c1'}
    _hold(plane)
    with TestClient(cascade.app) as client:
        assert client.delete('/v1/conversations/c1').status_code == 204
    tombstone = _tombstone(plane, 'c1')
    assert tombstone['legal_hold_deferred'] is True and tombstone['erasure_armed'] is True


def test_held_retry_marks_the_existing_tombstone_and_never_unarms_erasure(plane, cascade):
    _hold(plane)
    plane.docs[f'users/{UID}/deleted_conversations/c1'] = {'conversation_id': 'c1'}  # earlier partial delete
    with TestClient(cascade.app) as client:
        assert client.delete('/v1/conversations/c1').status_code == 204
        tombstone = _tombstone(plane, 'c1')
        assert tombstone['legal_hold_deferred'] is True and tombstone['erasure_armed'] is False
        assert client.delete('/v1/conversations/c1?cascade=true').status_code == 204
        assert _tombstone(plane, 'c1')['erasure_armed'] is True and _erasure(plane, 'c1')
        assert client.delete('/v1/conversations/c1').status_code == 204
    assert _tombstone(plane, 'c1')['erasure_armed'] is True


def test_held_cascade_delete_with_kill_switch_off_answers_gate_busy(plane, cascade, monkeypatch):
    monkeypatch.setenv('LEGAL_HOLD_DEFER_SINGLE_DELETE', 'false')
    _hold(plane)
    with TestClient(cascade.app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1?cascade=true')
    assert response.status_code == 409
    assert cascade.erased == []


def test_unreadable_hold_authority_answers_gate_busy_and_writes_nothing(plane, cascade):
    plane.docs[HOLD_PATH] = {'schema_version': 'unknown', 'issuer': 'admin', 'active': True}
    with TestClient(cascade.app, raise_server_exceptions=False) as client:
        response = client.delete('/v1/conversations/c1')
    assert response.status_code == 409
    assert _tombstone(plane, 'c1') is None and cascade.erased == []


def test_free_gate_keeps_the_synchronous_cascade(plane, cascade):
    response = _accept_behind_peer(cascade)
    assert response.status_code == 204
    assert cascade.erased == ['c1'] and _erasure(plane, 'c1') is None
    assert plane.docs.get(f'{purge_jobs.COLLECTION}/{purge_jobs.job_id(UID, "c1")}')  # batch purge armed


def test_eraser_owes_merge_donor_audio_recorded_at_acceptance(plane, cascade):
    plane.docs[_conversation_path('c1')]['sync_merged_from'] = ['donor-a', 'c1']
    plane.docs[GATE_PATH] = _gate_doc()
    assert _accept_behind_peer(cascade).status_code == 204
    assert _erasure(plane, 'c1')['audio_source_ids'] == ['donor-a']
    plane.docs[_conversation_path('c1')]['sync_merged_from'] = []  # a partial earlier attempt lost the link
    assert _accept_behind_peer(cascade).status_code == 204  # a retried delete keeps what was recorded
    assert _erasure(plane, 'c1')['audio_source_ids'] == ['donor-a']
    plane.docs.pop(GATE_PATH)
    _drain_erasures(plane, cascade, passes=1)
    # The cascade owes its audio to the durable audio obligation, donors recorded at acceptance included.
    conversations.delete_conversation_audio_under_gate.assert_not_called()
    owed = plane.docs[f'{purge_jobs.AUDIO_COLLECTION}/{purge_jobs.audio_job_id(UID, "c1")}']
    assert owed['audio_source_ids'] == ['donor-a']
    cascade.audio_sent.clear()
    deletion_batch_purge.reconcile_conversation_batch_purges()
    erase = MagicMock()
    for job, gen in cascade.audio_sent:
        assert purge_jobs.run_audio_erasure_job(job, gen, erase=erase) == 'erased'
    erase.assert_called_once_with(UID, 'c1', ['donor-a'], staging={}, settled=[], deleted_siblings=[])


def test_accept_transaction_reads_before_it_writes_and_keeps_the_first_tombstone(monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore(
        {('users', UID, 'conversations', 'c1'): {'created_at': 'original', 'sync_merged_from': ['donor']}}
    )
    monkeypatch.setattr(legal_holds, 'assert_account_deletion_permitted', lambda *a, **k: None)
    conversation_tombstones.accept_deletion(UID, 'c1', firestore_client=store)
    first = dict(store.rows[('users', UID, conversation_tombstones.COLLECTION, 'c1')])
    conversation_tombstones.accept_deletion(UID, 'c1', firestore_client=store)
    assert store.rows[('users', UID, conversation_tombstones.COLLECTION, 'c1')] == first
    assert store.rows[('users', UID, 'conversations', 'c1')]['deleted'] is True
    owed = store.rows[(ERASURES, purge_jobs.erasure_job_id(UID, 'c1'))]
    assert owed['audio_source_ids'] == ['donor'] and owed['uid'] == UID


def test_task_handler_routes_erasures_to_the_eraser(monkeypatch):
    import asyncio

    calls = []

    def run_erasure_job(job, generation, *, erase):
        calls.append((job, generation, erase))
        return 'erased'

    monkeypatch.setattr(purge_jobs, 'run_erasure_job', run_erasure_job)
    monkeypatch.setattr(purge_jobs, 'run_job', MagicMock(side_effect=AssertionError('not a batch purge')))

    class _Request:
        async def json(self):
            return {'job_id': 'j1', 'generation': 3, 'kind': 'erasure'}

    response = asyncio.run(users_router.run_conversation_batch_purge(_Request(), 0))
    assert response.status_code == 200
    assert calls == [('j1', 3, conversations.erase_accepted_conversation)]


def test_task_handler_routes_audio_erasures_to_the_audio_eraser(monkeypatch):
    import asyncio

    from utils.other.storage import erase_conversation_audio

    calls = []

    def run_audio_erasure_job(job, generation, *, erase, enabled):
        calls.append((job, generation, erase, enabled))
        return 'erased'

    monkeypatch.setattr(purge_jobs, 'run_audio_erasure_job', run_audio_erasure_job)
    monkeypatch.setattr(purge_jobs, 'run_erasure_job', MagicMock(side_effect=AssertionError('not a cascade')))
    monkeypatch.setattr(purge_jobs, 'run_job', MagicMock(side_effect=AssertionError('not a batch purge')))

    class _Request:
        async def json(self):
            return {'job_id': 'j1', 'generation': 2, 'kind': 'audio_erasure'}

    response = asyncio.run(users_router.run_conversation_batch_purge(_Request(), 0))
    assert response.status_code == 200
    from utils.conversations.deletion_batch_purge import durable_audio_erasure

    assert calls == [('j1', 2, erase_conversation_audio, durable_audio_erasure)]


@pytest.mark.parametrize('token', ['off', 'false', '0', 'no', ' OFF '])
def test_kill_switch_off_arms_no_audio_obligation_and_erases_after_the_response(monkeypatch, plane, cascade, token):
    """Dispatch is configured, but the switch is off: the default delete keeps the background erasure."""
    monkeypatch.setenv(deletion_batch_purge.AUDIO_ERASURE_SWITCH, token)
    with TestClient(cascade.app) as client:
        assert client.delete('/v1/conversations/c1').status_code == 204
    assert not any(path.startswith(f'{purge_jobs.AUDIO_COLLECTION}/') for path in plane.docs)
    conversations.delete_conversation_audio_under_gate.assert_called_once()
    assert conversations.delete_conversation_audio_under_gate.call_args.args[:2] == (UID, 'c1')


def test_kill_switch_on_arms_the_audio_obligation_for_a_default_delete(monkeypatch, plane, cascade):
    monkeypatch.delenv(deletion_batch_purge.AUDIO_ERASURE_SWITCH, raising=False)
    with TestClient(cascade.app) as client:
        assert client.delete('/v1/conversations/c1').status_code == 204
    assert plane.docs[f'{purge_jobs.AUDIO_COLLECTION}/{purge_jobs.audio_job_id(UID, "c1")}']['conversation_id'] == 'c1'
    conversations.delete_conversation_audio_under_gate.assert_not_called()
