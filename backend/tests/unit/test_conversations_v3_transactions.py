"""Strict read-before-write contracts using synthetic document boundaries."""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import service, summary
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

AT = datetime.now(timezone.utc)
R = ('users', 'synthetic', 'conversations', 'r')
L = ('users', 'synthetic', 'conversation_v3_leases', 'builder')


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)

    def transactional(body):
        def run(tx, *args, **kwargs):
            with client.lock:
                return body(tx, *args, **kwargs)

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
        tokens = list(pool.map(lambda _: leases.acquire('synthetic', 'builder', firestore_client=strict), range(2)))
    assert sum(token is not None for token in tokens) == 1


def test_expired_worker_cannot_release_successor(strict):
    old = leases.acquire('synthetic', 'builder', now=AT - timedelta(hours=1), firestore_client=strict)
    new = leases.acquire('synthetic', 'builder', now=AT, firestore_client=strict)
    leases.release('synthetic', 'builder', old, firestore_client=strict)
    assert strict.rows[L]['token'] == new


def test_atomic_projection_and_claim(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
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
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
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


def test_delete_during_capture_rearms_purge_at_settlement(strict, monkeypatch):
    row = {'id': 'c', 'v3_derived': True, 'v3_recording_ids': ['r'], 'started_at': AT, 'finished_at': AT}
    strict.rows[('users', 'synthetic', 'deleted_conversations', 'c')] = {'conversation_id': 'c'}
    strict.rows[R] = {
        'id': 'r',
        'recording': True,
        'status': 'in_progress',
        'v3_pending': True,
        'claims': [{'conversation_id': 'c', 'start': AT, 'end': AT}],
    }
    store.release_claims('synthetic', row, firestore_client=strict)
    assert strict.rows[R]['v3_audio_purge_pending'] is False
    strict.rows[R]['status'] = 'completed'
    source = {**strict.rows[R], '_v3_revision': 1}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection('synthetic', token, {'r': source}, {}, [], [], firestore_client=strict)
    assert strict.rows[R]['v3_audio_purge_pending'] is True
    from utils.other import storage

    erased = []
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(storage, 'delete_privacy_conversation_audio', lambda *a: erased.append(a))
    monkeypatch.setattr(
        service.conversations_db, 'update_conversation', lambda uid, cid, patch: strict.rows[R].update(patch)
    )
    service.purge_audio('synthetic', 'r')
    assert erased == [('synthetic', 'r')]
    assert strict.rows[R]['v3_audio_erased'] is True
    assert strict.rows[R]['v3_audio_purge_pending'] is False


@pytest.mark.parametrize('state', ['deleted', 'is_locked'])
def test_terminal_processing_settles_pending(strict, state):
    cid = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[cid] = {'id': 'c', state: True, 'v3_process_pending': True}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    writers.settle_processing('synthetic', 'c', token, None, None, skipped=True, firestore_client=strict)
    assert strict.rows[cid]['v3_process_pending'] is False
    assert strict.rows[cid]['tile_state'] == 'done'
    assert 'summary_covers_through' not in strict.rows[cid]


def test_paid_processing_and_outline_retries_are_content_bounded(strict):
    cid = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'transcript_segments': [{'text': 'synthetic content'}]}
    strict.rows[cid] = dict(row, v3_process_pending=True)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert not writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert strict.rows[cid]['v3_process_pending'] is False
    row['transcript_segments'].append({'text': 'changed content'})
    assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    builder = leases.acquire('synthetic', 'builder', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert not store.outline_attempt('synthetic', builder, 'fp', firestore_client=strict)
    assert store.outline_attempt('synthetic', builder, 'new-fp', firestore_client=strict)


def test_projection_allows_transcript_offload(strict, monkeypatch):
    calls = []
    monkeypatch.setattr(
        store.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: calls.append(kw) or dict(row)
    )
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection(
        'synthetic', token, {}, {}, [{'id': 'c', 'status': 'completed'}], [], firestore_client=strict
    )
    assert calls[0]['allow_offload'] is True


def test_projection_partitions_bytes_and_keeps_pending_until_last_batch(strict, monkeypatch):
    strict.rows[R] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    original = store.firestore.transactional
    observations = []

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            result = wrapped(tx, *args)
            observations.append(strict.rows[R]['v3_pending'])
            return result

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': AT,
            'finished_at': AT,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 60000}],
        }
        for i in range(128)
    ]
    store.commit_projection(
        'synthetic', token, {'r': {**strict.rows[R], '_v3_revision': 1}}, {}, rows, [], firestore_client=strict
    )
    assert len(observations) >= 4
    assert all(observations[:-1]) and observations[-1] is False
    assert len(strict.rows[R]['claims']) == 128


def test_multi_batch_backfill_conversion_is_not_its_own_race_and_keeps_an_obligation(strict, monkeypatch):
    # A backfill donor is a plain conversation until the first batch hides it as a recording.
    strict.rows[R] = {'id': 'r', 'status': 'completed', 'structured': {'title': 'Old notes'}}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    original = store.firestore.transactional
    observations = []

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            result = wrapped(tx, *args)
            observations.append((strict.rows[R].get('recording'), strict.rows[R].get('v3_pending')))
            return result

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': AT,
            'finished_at': AT,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 60000}],
        }
        for i in range(128)
    ]
    donor = {**strict.rows[R], 'recording': True, '_v3_derive': True, '_v3_revision': 1}
    store.commit_projection('synthetic', token, {'r': donor}, {}, rows, [], firestore_client=strict)
    assert len(observations) >= 4
    # Hidden as a recording from the first batch, with a durable obligation until the last one lands.
    assert all(recording is True and pending is True for recording, pending in observations[:-1])
    assert observations[-1] == (True, False)
    assert len(strict.rows[R]['claims']) == 128


def test_metadata_revision_change_does_not_rebill_unchanged_content(strict, monkeypatch):
    cid = ('users', 'synthetic', 'conversations', 'c')
    original = {'id': 'c', 'transcript_segments': [{'text': 'same real content'}], 'sync_content_revision': 1}
    strict.rows[cid] = dict(original, v3_process_pending=True, sync_content_revision=2)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict())
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    writers.settle_processing(
        'synthetic', 'c', token, 1, AT, content_hash=writers.processing_hash(original), firestore_client=strict
    )
    assert strict.rows[cid]['v3_process_pending'] is False
    strict.rows[cid]['transcript_segments'] = [{'text': 'actually changed content'}]
    with pytest.raises(store.Conflict, match='processing_source_changed'):
        writers.settle_processing(
            'synthetic', 'c', token, 1, AT, content_hash=writers.processing_hash(original), firestore_client=strict
        )


@pytest.mark.asyncio
async def test_summary_holder_stores_before_releasing_lease_and_detail_sees_result(strict, monkeypatch):
    from utils.conversations.v3 import summary

    cid = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'created_at': AT, 'started_at': AT, 'finished_at': AT, 'structured': {'title': 'Stable'}}
    strict.rows[cid] = row
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict())

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(
        summary,
        'write',
        lambda *a: {'title': 'Stable', 'sections': [{'heading': 'Plan', 'body_markdown': 'Full notes.'}]},
    )
    original = writers.store_summary

    def persist(*args):
        assert leases.acquire('synthetic', 'summary-c', firestore_client=strict) is None
        return original(*args)

    monkeypatch.setattr(writers, 'store_summary', persist)
    token = await summary.prepare('synthetic', row)
    frames = [frame async for frame in summary.stream('synthetic', row, token=token)]
    assert frames[-1].startswith('done: ')
    assert strict.rows[cid]['structured']['sections'][0]['body_markdown'] == 'Full notes.'
    assert strict.rows[cid]['summary_covers_through'] == AT
    assert leases.acquire('synthetic', 'summary-c', firestore_client=strict) is not None


def test_on_open_projection_keeps_background_pending_obligation(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': True, 'v3_pending_since': AT}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection(
        'synthetic',
        token,
        {'r': {**strict.rows[R], '_v3_revision': 1}},
        {},
        [],
        [],
        clear_pending=False,
        firestore_client=strict,
    )
    assert strict.rows[R]['v3_pending'] is True and strict.rows[R]['v3_pending_since'] == AT


def test_exhausted_retry_budget_is_failed_and_retryable(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'transcript_segments': [{'text': 'real speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(2):
        assert writers.begin_processing('synthetic', row, token, firestore_client=strict)
    assert not writers.begin_processing('synthetic', row, token, firestore_client=strict)
    failed = strict.rows[path]
    assert failed['tile_state'] == 'failed' and failed['status'] == 'completed'
    assert failed['summary_retryable'] and failed['v3_process_failed']
    assert writers.begin_processing('synthetic', row, token, force=True, firestore_client=strict)
    assert strict.rows[path]['tile_state'] == 'writing'
    assert strict.rows[path]['v3_process_attempts'] == 1


def test_failure_never_replaces_a_locked_presentation(strict):
    path = ('users', 'synthetic', 'conversations', 'c')
    strict.rows[path] = {'id': 'c', 'is_locked': True, 'tile_state': 'writing'}
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert not writers.fail_processing('synthetic', 'c', token, None, firestore_client=strict)
    assert strict.rows[path]['is_locked'] and strict.rows[path]['tile_state'] != 'failed'


def test_multiple_open_rows_are_rejected_before_any_batch_or_codec_write(strict, monkeypatch):
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    monkeypatch.setattr(
        store.conversations,
        '_prepare_conversation_for_write',
        lambda *a, **kw: pytest.fail('codec/offload ran before global open check'),
    )
    rows = [{'id': cid, 'status': 'in_progress', 'padding': 'x' * 2100000} for cid in ['a', 'b']]
    with pytest.raises(store.Conflict, match='multiple_open'):
        store.commit_projection('synthetic', token, {}, {}, rows, [], firestore_client=strict)
    assert not any(p[2] == 'conversations' for p in strict.rows)


def test_terminal_failure_counter_counts_committed_transitions_once(strict):
    from utils.conversations.v3 import metrics

    path = ('users', 'synthetic', 'conversations', 'c')
    row = {'id': 'c', 'v3_derived': True, 'sync_content_revision': 1, 'transcript_segments': [{'text': 'speech'}]}
    strict.rows[path] = dict(row)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = metrics.TERMINAL_FAILURES.labels('processing')._value.get()
    assert writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    assert not writers.fail_processing('synthetic', 'c', token, 1, firestore_client=strict)
    assert metrics.TERMINAL_FAILURES.labels('processing')._value.get() == before + 1
