"""Strict read-before-write contracts using synthetic document boundaries."""

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from database import conversations_v3 as store
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

AT = datetime.now(timezone.utc)
R = ('users', 'synthetic', 'conversations', 'r')
L = ('users', 'synthetic', 'conversation_v3_leases', 'builder')


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()

    def transactional(body):
        def run(tx):
            with client.lock:
                return body(tx)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda s: (s.to_dict() or {}).get('_test_revision', 1)),
        raising=False,
    )
    monkeypatch.setattr(store, 'encrypt', lambda value, uid: value)
    monkeypatch.setattr(store.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: deepcopy(row))
    return client


def test_two_workers_get_one_lease(strict):
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: store.acquire('synthetic', 'builder', firestore_client=strict), range(2)))
    assert sum(token is not None for token in tokens) == 1


def test_expired_worker_cannot_release_successor(strict):
    old = store.acquire('synthetic', 'builder', now=AT - timedelta(hours=1), firestore_client=strict)
    new = store.acquire('synthetic', 'builder', now=AT, firestore_client=strict)
    store.release('synthetic', 'builder', old, firestore_client=strict)
    assert strict.rows[L]['token'] == new


def test_atomic_projection_and_claim(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    token = store.acquire('synthetic', 'builder', firestore_client=strict)
    source = {'id': 'r', 'recording': True, '_v3_revision': 1}
    row = {
        'id': 'c',
        'status': 'processing',
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': ['r'],
        'transcript_segments': [],
        'structured': {},
    }
    store.commit_projection('synthetic', token, {'r': source}, {}, [row], [], firestore_client=strict)
    assert strict.rows[R]['v3_pending'] is False
    assert strict.rows[R]['claims'] == [{'conversation_id': 'c', 'start': AT, 'end': AT}]
    assert strict.rows[('users', 'synthetic', 'conversations', 'c')]['id'] == 'c'


def test_new_speech_preserves_pending_on_conflict(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True, '_test_revision': 2}
    token = store.acquire('synthetic', 'builder', firestore_client=strict)
    with pytest.raises(store.Conflict, match='source_changed'):
        store.commit_projection('synthetic', token, {'r': {'_v3_revision': 1}}, {}, [], [], firestore_client=strict)
    assert strict.rows[R]['v3_pending'] is True


@pytest.mark.parametrize('claims,left', [(0, 0), (1, 0), (2, 1)])
def test_delete_claims_zero_one_two(strict, claims, left):
    row = {
        'id': 'c',
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=1),
    }
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [
            {'conversation_id': cid, 'start': AT + timedelta(minutes=i * 2), 'end': AT + timedelta(minutes=i * 2 + 1)}
            for i, cid in enumerate(['c', 'neighbour'][:claims])
        ],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert len(strict.rows[R]['claims']) == left
    assert strict.rows[R]['v3_audio_purge_pending'] is (left == 0)
    store.release_claims('synthetic', row, firestore_client=strict)
    assert len(strict.rows[R]['deleted_spans']) == 1


def test_pending_recording_audio_is_retained(strict):
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'v3_pending': True,
        'claims': [],
        'v3_audio_purge_pending': True,
    }
    assert not store.claim_audio_purge('synthetic', 'r', firestore_client=strict)
    assert not strict.rows[R].get('deleted')


def test_purge_closes_recording_owner_before_storage_delete(strict):
    strict.rows[R] = {'recording': True, 'status': 'completed', 'claims': [], 'v3_audio_purge_pending': True}
    assert store.claim_audio_purge('synthetic', 'r', firestore_client=strict)
    assert strict.rows[R]['deleted'] is True
    assert ('users', 'synthetic', 'deleted_conversations', 'r') in strict.rows


def test_delete_subtracts_surviving_claim_from_merged_window(strict):
    row = {
        'id': 'c',
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=3),
    }
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'recording': True,
        'status': 'completed',
        'claims': [
            {'conversation_id': 'c', 'start': AT, 'end': AT + timedelta(minutes=3)},
            {'conversation_id': 'neighbour', 'start': AT + timedelta(minutes=1), 'end': AT + timedelta(minutes=2)},
        ],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert [(s['start'], s['end']) for s in strict.rows[R]['deleted_spans']] == [
        (AT, AT + timedelta(minutes=1)),
        (AT + timedelta(minutes=2), AT + timedelta(minutes=3)),
    ]
    assert strict.rows[R]['v3_audio_purge_pending'] is False


def test_merge_claim_transfer_is_idempotent_and_preserves_gaps(strict):
    sources = [{'id': 'a', 'v3_recording_ids': ['r']}, {'id': 'c', 'v3_recording_ids': ['r']}]
    target = {'id': 'merged', 'started_at': AT, 'finished_at': AT + timedelta(minutes=3)}
    strict.rows[('users', 'synthetic', 'conversations', 'merged')] = target
    strict.rows[R] = {
        'recording': True,
        'claims': [
            {'conversation_id': cid, 'start': AT + timedelta(minutes=i), 'end': AT + timedelta(minutes=i + 1)}
            for i, cid in enumerate(['a', 'neighbour', 'c'])
        ],
    }
    store.transfer_claims('synthetic', sources, target, firestore_client=strict)
    claims = strict.rows[R]['claims']
    assert [c['conversation_id'] for c in claims].count('merged') == 2
    assert [c['conversation_id'] for c in claims].count('neighbour') == 1
    store.transfer_claims('synthetic', sources, target, firestore_client=strict)
    assert strict.rows[R]['claims'] == claims


@pytest.mark.asyncio
async def test_two_concurrent_reconciles_publish_one_copy(strict, monkeypatch):
    import asyncio
    import json
    from utils.conversations.v3 import service

    start = AT - timedelta(hours=1)
    strict.rows[R] = {
        'id': 'r',
        'recording': True,
        'v3_pending': True,
        'status': 'completed',
        'source': 'omi',
        'started_at': start,
        'finished_at': start + timedelta(seconds=20),
        'data_protection_level': 'standard',
        'transcript_segments': [{'text': 'Synthetic planning speech', 'start': 0, 'end': 20, 'is_user': True}],
    }
    source = {**deepcopy(strict.rows[R]), '_v3_revision': 1}
    entered, resume = asyncio.Event(), asyncio.Event()
    original_load = store.load
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)

    async def blocking(pool, fn, *args, **kwargs):
        if fn is original_load:
            entered.set()
            await resume.wait()
            return {'r': source}, {}, []
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    calls = []

    def outline(uid, messages):
        calls.append(uid)
        return json.dumps(
            {
                'conversations': [
                    {
                        'first_line': 1,
                        'kind': 'conversation',
                        'title': 'Planning',
                        'line': 'You planned a visit.',
                        'emoji': '🌳',
                        'people': [],
                        'sections': [],
                    }
                ]
            }
        )

    monkeypatch.setattr(service.models, 'outline', outline)
    first = asyncio.create_task(service.reconcile('synthetic'))
    await entered.wait()
    assert await service.reconcile('synthetic') == 'busy'
    resume.set()
    assert await first == 'committed'
    copies = [r for path, r in strict.rows.items() if path[2] == 'conversations' and r.get('v3_derived')]
    assert len(copies) == 1 and len(strict.rows[R]['claims']) == 1
    assert calls == ['synthetic']
