"""A recording that keeps receiving speech during a pass must not starve its owner's projection."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict, service
from tests.unit.test_conversations_v3_transactions import R, strict  # noqa: F401

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
