"""A recording that keeps receiving speech during a pass must not starve its owner's projection."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import conversations, conversations_v3 as store, conversations_v3_leases as leases, memories
from database.conversations_v3_undo_removals import removal_ref
from utils.conversations.v3 import Conflict, created, service
from tests.unit.test_conversations_v3_transactions import R, strict  # noqa: F401
from tests.unit.test_conversations_v3_engine import native_ready_fields
from tests.unit.test_conversations_v3_review import MemoryQuery

C = ('users', 'synthetic', 'conversations', 'c')


def live(start, words=4, **updates):
    return {
        'id': 'r',
        'recording': True,
        'v3_pending': True,
        'v3_pending_since': start,
        'status': 'in_progress',
        'source': 'omi',
        'started_at': start,
        'finished_at': start + timedelta(seconds=words * 5),
        'data_protection_level': 'standard',
        'claims': [],
        'transcript_segments': [
            {'text': f'synthetic live speech number {n}', 'start': n * 5, 'end': n * 5 + 4, 'is_user': True}
            for n in range(words)
        ],
        **updates,
    }


def loaded(raw, revision):
    return {**deepcopy(raw), '_v3_revision': revision, '_v3_fence': store.source_fence(raw)}


def window(start, status='in_progress'):
    return {
        'id': 'c',
        'v3_derived': True,
        'status': status,
        'started_at': start,
        'finished_at': start + timedelta(seconds=20),
        'v3_recording_ids': ['r'],
        'transcript_segments': [],
        'structured': {},
    }


def appended(raw, revision, **updates):
    later = deepcopy(raw)
    later['transcript_segments'].append({'text': 'more speech while the pass ran', 'start': 40, 'end': 44})
    later['finished_at'] = raw['started_at'] + timedelta(seconds=44)
    later.update(updates, _test_revision=revision)
    return later


def test_speech_appended_during_the_pass_still_commits_and_stays_owed(strict):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    raw = live(start)
    snapshot = loaded(raw, 1)
    strict.rows[R] = appended(raw, 2, v3_manual_end=True)
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    moved = store.commit_projection(
        'synthetic', token, {'r': snapshot}, {}, [window(start)], [], firestore_client=strict
    )
    assert moved == {'r'}
    assert strict.rows[C]['status'] == 'in_progress'
    # The new speech is owed to the next pass; the concurrent writer's fields are never clobbered.
    assert strict.rows[R]['v3_pending'] is True and strict.rows[R]['v3_pending_since'] == start
    assert len(strict.rows[R]['transcript_segments']) == 5 and strict.rows[R]['v3_manual_end'] is True
    assert strict.rows[R]['claims'] == [{'conversation_id': 'c', 'start': start, 'end': start + timedelta(seconds=20)}]
    assert 'v3_audio_purge_pending' not in strict.rows[R]


def test_an_unmoved_source_is_still_settled(strict):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    raw = live(start, _test_revision=1)
    strict.rows[R] = deepcopy(raw)
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    moved = store.commit_projection(
        'synthetic', token, {'r': loaded(raw, 1)}, {}, [window(start)], [], firestore_client=strict
    )
    assert moved == set() and strict.rows[R]['v3_pending'] is False


@pytest.mark.parametrize(
    'change',
    [
        {'deleted': True},
        {'deleted_spans': [{'start': 0, 'end': 5}]},
        {'sync_merged_into': 'other'},
        {'data_protection_level': 'enhanced'},
        {'is_locked': True},
        {'claims': [{'conversation_id': 'elsewhere'}]},
        {'recording': False},
        {'v3_native_manual_stop': {'revision': 1}},
        {'v3_native_manual_ready_revision': 7, 'v3_manual_end': True},
    ],
)
def test_any_non_speech_source_change_keeps_the_strict_fence(strict, change):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    raw = live(start)
    strict.rows[R] = appended(raw, 2, **change)
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    with pytest.raises(Conflict, match='source_changed'):
        store.commit_projection(
            'synthetic', token, {'r': loaded(raw, 1)}, {}, [window(start)], [], firestore_client=strict
        )
    assert C not in strict.rows and strict.rows[R]['v3_pending'] is True


def test_a_changed_derived_row_still_conflicts(strict):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    raw = live(start, _test_revision=1)
    strict.rows[R] = deepcopy(raw)
    strict.rows[C] = {**window(start), '_test_revision': 2}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    prior = {**window(start), '_v3_revision': 1, '_v3_fence': store.source_fence(window(start))}
    with pytest.raises(Conflict, match='source_changed'):
        store.commit_projection(
            'synthetic', token, {'r': loaded(raw, 1)}, {'c': prior}, [window(start)], [], firestore_client=strict
        )


def test_a_source_without_a_load_fence_keeps_the_strict_revision_check(strict):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    raw = live(start)
    strict.rows[R] = appended(raw, 2)
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    with pytest.raises(Conflict, match='source_changed'):
        store.commit_projection(
            'synthetic', token, {'r': {**deepcopy(raw), '_v3_revision': 1}}, {}, [], [], firestore_client=strict
        )


@pytest.mark.asyncio
async def test_manual_end_during_a_pass_lands_a_processing_row_within_one_follow_up(strict, monkeypatch):
    # Started two minutes ago; the double-tap closes it at the last spoken line, inside the silence gap.
    start = datetime.now(timezone.utc) - timedelta(minutes=2)
    raw = live(start, _test_revision=1)
    strict.rows[R] = deepcopy(raw)
    snapshots = [{'r': loaded(raw, 1)}]
    original_load = store.load
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))

    def load_current():
        current = strict.rows[R]
        existing = {
            path[-1]: {**deepcopy(row), '_v3_revision': row.get('_test_revision', 1)}
            for path, row in strict.rows.items()
            if path[2] == 'conversations' and row.get('v3_derived')
        }
        return {'r': loaded(current, current.get('_test_revision', 1))}, existing, []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.clear_terminal_pending:
            return None
        if fn is original_load:
            if snapshots:
                stale = snapshots.pop()
                # The wearer double-taps while this pass runs: speech lands and the capture ends.
                strict.rows[R] = appended(raw, 2, status='completed', v3_manual_end=True)
                return stale, {}, []
            return load_current()
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    wakes = []
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: pytest.fail('a moved source waits for its wake'))
    monkeypatch.setattr(service, 'enqueue', lambda uid, at=None, **kw: wakes.append(at))
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda uid, messages: json.dumps(
            {'conversations': [{'first_line': 1, 'kind': 'conversation', 'title': 'Live plan', 'line': 'You planned.'}]}
        ),
    )
    before = datetime.now(timezone.utc)
    assert await service.reconcile('synthetic') == 'committed'
    derived = [r for path, r in strict.rows.items() if path[2] == 'conversations' and r.get('v3_derived')]
    # First pass: the live tile exists even though the recording moved under it.
    assert len(derived) == 1 and derived[0]['status'] == 'in_progress'
    assert strict.rows[R]['v3_pending'] is True
    assert wakes and min(int(w.timestamp()) // 60 for w in wakes) > int(before.timestamp()) // 60

    # The follow-up wake reads the manual end and commits the processing row.
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    assert await service.reconcile('synthetic') == 'committed'
    derived = [r for path, r in strict.rows.items() if path[2] == 'conversations' and r.get('v3_derived')]
    assert len(derived) == 1 and derived[0]['status'] == 'processing' and derived[0]['v3_process_pending'] is True
    assert derived[0]['manual_end'] is True
    assert strict.rows[R]['v3_pending'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case', ['steady', 'reopened_before_notes', 'reopened_before_settlement', 'reopened_after_notes_cleared']
)
async def test_promoted_native_stop_commits_one_tail_summary_across_a_ready_replay(strict, monkeypatch, case):
    # The injected loader models the recording closure, not the pending-queue query.
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'off')
    revoked = case != 'steady'
    notes_committed = case == 'reopened_before_settlement'
    notes_cleared = case == 'reopened_after_notes_cleared'
    end = datetime.now(timezone.utc) - timedelta(seconds=10)
    start = end - timedelta(seconds=20)
    successor_key = ('users', 'synthetic', 'conversations', 'successor')
    old = live(start, **native_ready_fields(end))
    old['transcript_segments'][-1].update(text='The final decision was to ship tomorrow.', end=20)
    strict.rows[R] = old
    if not revoked:
        strict.rows[successor_key] = live(end, words=1, id='successor')
    clock = end + timedelta(seconds=10)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    def load(uid, **kw):
        existing = {
            key[-1]: {**deepcopy(row), '_v3_revision': 1}
            for key, row in strict.rows.items()
            if key[2] == 'conversations' and row.get('v3_derived')
        }
        open_recordings = {
            rid for row in existing.values() if row['status'] == 'in_progress' for rid in row['v3_recording_ids']
        }
        if not open_recordings and not any(
            strict.rows[key].get('v3_pending') for key in (R, successor_key) if key in strict.rows
        ):
            return {}, {}, []
        # Pending or open inputs load related derived windows and their recording closure.
        sources = {key[-1]: loaded(strict.rows[key], 1) for key in (R, successor_key) if key in strict.rows}
        return sources, existing, []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def no_fanout(uid):
        return None

    def pending(uid):
        return [
            deepcopy(row)
            for key, row in strict.rows.items()
            if key[2] == 'conversations' and row.get('v3_process_pending')
        ]

    summary_writes = []

    async def write_synthetic_summary(uid, row, token):
        if not service.writers.begin_processing(uid, row, token, firestore_client=strict):
            return
        assert row['manual_end'] is not revoked and row['v3_recording_ids'] == ['r']
        assert row['transcript_segments'][-1]['text'] == 'The final decision was to ship tomorrow.'
        summary = {'overview': row['transcript_segments'][-1]['text']}
        strict.rows[('users', uid, 'conversations', row['id'])].update(structured=summary, status='completed')
        service.writers.settle_processing(
            uid, row['id'], token, row['sync_content_revision'], row['finished_at'], notes=True, firestore_client=strict
        )
        summary_writes.append(row['id'])

    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    monkeypatch.setattr(service, 'pending_processing', pending)
    monkeypatch.setattr(
        service,
        '_load_processing_row',
        lambda uid, cid: deepcopy(strict.rows.get(('users', uid, 'conversations', cid))),
    )
    monkeypatch.setattr(service, '_process_leased', write_synthetic_summary)
    enqueued = []
    monkeypatch.setattr(service, 'enqueue', lambda uid, *, at=None: enqueued.append((uid, at)))
    monkeypatch.setattr(service, 'datetime', Clock)
    monkeypatch.setattr(
        strict,
        'collection_group',
        lambda name: MemoryQuery({'/' + '/'.join(key): row for key, row in strict.rows.items()}).collection_group(name),
        raising=False,
    )
    monkeypatch.setattr(created, 'deliver', no_fanout)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda uid, messages: json.dumps(
            {'conversations': [{'first_line': 1, 'kind': 'conversation', 'title': 'Plan', 'line': 'You planned.'}]}
        ),
    )
    if revoked:
        drain = service.drain_processing
        monkeypatch.setattr(service, 'drain_processing', no_fanout)
        assert await service.reconcile('synthetic') == 'committed'
        monkeypatch.setattr(service, 'drain_processing', drain)
        assert not strict.rows[R]['v3_pending']
        (before,) = [row for row in strict.rows.values() if row.get('v3_derived')]
        assert before['manual_end'] and before['v3_process_pending']
        if notes_committed or notes_cleared:
            # The core write had authorized substantive notes, but the notes lease had not settled yet.
            receipt = service.policy.native_manual_notes_receipt(before)
            assert receipt
            before.update(
                status='completed',
                structured={'overview': 'The final decision was to ship tomorrow.'},
                v3_native_manual_notes_visibility=receipt,
            )
            if notes_cleared:
                db = store.conversations
                monkeypatch.setattr(db, 'db', strict)
                monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
                assert db.update_conversation_summary('synthetic', before['id'], None, '') == 'ok'
                cleared = strict.rows[(*R[:-1], before['id'])]
                assert cleared['structured']['overview'] == ''
                assert not cleared.get(service.policy.NATIVE_MANUAL_NOTES_VISIBILITY)
            else:
                summary_writes.append(before['id'])
        strict.rows[R].update(record_upload_revision=8, record_audio_closed=False)

        # The next notes admission rejects the old proof and rearms the exact source.
        await drain('synthetic')
        assert len(summary_writes) == int(notes_committed) and strict.rows[R]['v3_pending']
        pending_since = strict.rows[R]['v3_pending_since']
        await drain('synthetic')
        assert strict.rows[R]['v3_pending_since'] == pending_since

        assert await service.sweep() == 1
        assert enqueued[-1] == ('synthetic', None)  # The still-owed derived row wakes the owner.
        assert await service.reconcile('synthetic') == 'committed'
        (after,) = [row for row in strict.rows.values() if row.get('v3_derived')]
        assert after['id'] == before['id'] and not after['v3_process_pending']
        assert not strict.rows[R]['v3_pending'] and len(summary_writes) == int(notes_committed)

        if notes_committed:
            assert after['status'] == 'completed' and not after['manual_end']
            assert after['v3_native_manual_notes_visibility'] == before['v3_native_manual_notes_visibility']
            assert after['tile_state'] == 'done' and after['v3_created_pending']
        else:
            assert after['status'] == 'in_progress' and not after['manual_end']
            if notes_cleared:
                assert not after.get(service.policy.NATIVE_MANUAL_NOTES_VISIBILITY)
                assert not after.get('v3_notes_written')
                assert after.get('summary_covers_through') is None
            clock = end + timedelta(minutes=5)
            strict.rows[R].update(record_audio_closed=True, record_sealed_at=clock.timestamp())
            assert await service.reconcile('synthetic') == 'committed'
        assert await service.sweep() == 0
    else:
        assert await service.reconcile('synthetic') == 'committed'
        assert await service.reconcile('synthetic') == 'committed'
    assert len(summary_writes) == 1
    produced = strict.rows[('users', 'synthetic', 'conversations', summary_writes[0])]
    assert produced['v3_notes_written'] and produced['summary_covers_through'] == end
    if not revoked:
        windows = [row for row in strict.rows.values() if row.get('v3_derived')]
        (successor,) = [row for row in windows if row['status'] == 'in_progress']
        assert successor['v3_recording_ids'] == ['successor']


@pytest.mark.parametrize(
    'change',
    [
        {'record_upload_revision': 8, 'record_audio_closed': False},
        {'record_upload_sessions': {'producer': True}},
        {'record_sealed_at': 1234.0},
        {'record_audio_partial': {'generation': 1}},
    ],
)
def test_promoted_native_source_custody_change_is_not_a_speech_only_race(strict, change):
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    before = live(start, **native_ready_fields(start + timedelta(seconds=20)))
    strict.rows[R] = {**before, **change, '_test_revision': 2}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    with pytest.raises(Conflict, match='source_changed'):
        store.commit_projection(
            'synthetic', token, {'r': loaded(before, 1)}, {}, [window(start)], [], firestore_client=strict
        )
    assert C not in strict.rows and strict.rows[R]['v3_pending'] is True


@pytest.mark.asyncio
async def test_adjacent_revoked_native_windows_settle_unmatched_tile_with_links(strict, monkeypatch):
    # The injected loader models the recording closure, not the pending-queue query.
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'off')
    start = datetime.now(timezone.utc) - timedelta(minutes=2)
    rid_paths = {'r': R, 'second': (*R[:-1], 'second')}
    for offset, (rid, path) in enumerate(rid_paths.items()):
        began = start + timedelta(seconds=30 * offset)
        strict.rows[path] = live(began, id=rid, **native_ready_fields(began + timedelta(seconds=20)))

    def load(uid, **kw):
        existing = {
            path[-1]: {**deepcopy(row), '_v3_revision': 1}
            for path, row in strict.rows.items()
            if path[2] == 'conversations' and row.get('v3_derived')
        }
        return {rid: loaded(strict.rows[path], 1) for rid, path in rid_paths.items()}, existing, []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda *a: json.dumps(
            {'conversations': [{'first_line': 1, 'kind': 'conversation', 'title': 'Live plan', 'line': 'You planned.'}]}
        ),
    )
    assert await service.reconcile('synthetic') == 'committed'
    pending = sorted(load('synthetic')[1].values(), key=lambda row: row['started_at'])
    assert len(pending) == 2 and all(row['v3_process_pending'] for row in pending)
    for path in rid_paths.values():
        strict.rows[path].update(record_upload_revision=8, v3_pending=True)

    donor_id = pending[1]['id']
    task_path = ('users', 'synthetic', 'action_items', 'linked-task')
    strict.rows[task_path] = {'conversation_id': donor_id, 'description': 'Keep this linked task'}
    strict.rows[('users', 'synthetic', 'memories', 'linked-memory')] = {
        'evidence': [{'source_type': 'conversation', 'source_id': donor_id}]
    }

    strict.rows[(*R[:-1], donor_id)]['has_photos'] = False
    for _ in range(2):
        assert await service.reconcile('synthetic') == 'committed'
        _, existing, _ = load('synthetic')
        (replacement,) = existing.values()
        assert replacement['id'] == pending[0]['id']
        assert replacement['v3_recording_ids'] == ['r', 'second']
        assert replacement['status'] == 'in_progress' and not replacement['v3_process_pending']
        assert not replacement['home_hidden']
        task = strict.document('/'.join(task_path)).get().to_dict()
        memory = memories.get_memory('synthetic', 'linked-memory', firestore_client=strict)
        for linked_id in (task['conversation_id'], memory['evidence'][0]['source_id']):
            kept = conversations.get_conversation('synthetic', linked_id, firestore_client=strict)
            assert kept['id'] == donor_id and not kept.get('deleted')
            assert kept['home_hidden'] and not kept['v3_process_pending'] and not kept['summary_retryable']
            assert kept[service.policy.NATIVE_MANUAL_BINDING] is None and kept['summary_due_at'] is None
        assert not removal_ref(strict.document('users/synthetic'), donor_id).get().exists
        assert not strict.rows.get(('users', 'synthetic', 'deleted_conversations', donor_id))
        for path in rid_paths.values():
            assert {claim['conversation_id'] for claim in strict.rows[path]['claims']} == {replacement['id']}


@pytest.mark.asyncio
async def test_backfill_rederive_fails_before_native_finish_can_expand_delete_set(strict, monkeypatch):
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    source = live(start, **native_ready_fields(start + timedelta(seconds=20)))
    source['record_upload_revision'] = 8
    prior = window(start, status='processing')
    prior.update(
        backfilled=True,
        v3_process_pending=True,
        **{service.policy.NATIVE_MANUAL_BINDING: {'recording_id': 'r', 'upload_revision': 7}},
    )
    strict.rows[R] = source
    strict.rows[C] = prior
    before = deepcopy((source, prior))

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: ({'r': loaded(source, 1)}, {'c': prior}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: pytest.fail('unsafe backfill reached projection'))
    report = {}
    assert await service.reconcile('synthetic', derive=True, rederive=True, run_id='run', report=report) == 'blocked'
    assert report['blocked_reason'] == 'backfill_native_finish_unsupported'
    with pytest.raises(Conflict, match='backfill_native_finish_unsupported'):
        store.commit_projection('synthetic', 'unused', {}, {'c': prior}, [], [], remove=['c'], firestore_client=strict)
    assert (strict.rows[R], strict.rows[C]) == before
