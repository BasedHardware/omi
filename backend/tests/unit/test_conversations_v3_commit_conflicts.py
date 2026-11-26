"""Deterministic reconcile conflicts: adoption, owner backoff, kept outlines and late-text coverage."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict, service
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, builder, source  # noqa: F401
from tests.unit.test_conversations_v3_transactions import L, R, strict  # noqa: F401

REAL_COMMIT = service._commit


@pytest.mark.asyncio
async def test_planned_id_outside_the_closure_is_adopted_as_prior(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    planned = []

    def adoptable(uid, ids):
        planned.extend(ids)
        return {
            ids[0]: {
                'id': ids[0],
                'v3_derived': True,
                'started_at': AT,
                'finished_at': AT + timedelta(seconds=10),
                'status': 'completed',
                'tile_state': 'done',
                'title_locked': True,
                'v3_recording_ids': ['r'],
                'transcript_segments': [{'text': 'speech for a synthetic plan', 'start': 0, 'end': 10}],
            }
        }

    monkeypatch.setattr(store, 'adoptable', adoptable)
    assert await service.reconcile('u') == 'committed'
    _uid, _token, _recordings, existing, rows, _cache = committed[0]
    assert len(planned) == 1 and planned[0] in existing
    assert [row['id'] for row in rows] == planned
    # Replanned with the stored row as prior: the user's lock survives instead of a blind overwrite.
    assert rows[0]['title_locked'] is True


@pytest.mark.asyncio
async def test_no_adoption_read_when_every_planned_row_is_loaded(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    await service.reconcile('u')
    planned = committed[0][4][0]
    prior = {**planned, '_v3_revision': 1}
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {prior['id']: prior}, committed[0][5]))
    monkeypatch.setattr(store, 'adoptable', lambda *a: pytest.fail('loaded rows need no adoption read'))
    await service.reconcile('u')
    assert committed[1][4][0]['id'] == planned['id']


@pytest.mark.asyncio
async def test_backfill_never_adopts_and_never_parks_the_live_builder(builder, monkeypatch):
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: ({'r': source()}, {}, []))
    monkeypatch.setattr(store, 'adoptable', lambda *a: pytest.fail('backfill must not adopt a live row'))

    def conflict(*a, **kw):
        raise Conflict('target_exists')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(store, 'record_blocked', lambda *a: pytest.fail('backfill must not park the owner'))
    assert await service.reconcile('u', derive=True) == 'blocked'


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['target_exists', 'multiple_open_conversations', 'v3_derived_budget'])
async def test_deterministic_conflict_answers_the_task_and_backs_the_owner_off(builder, monkeypatch, reason):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict(reason)

    monkeypatch.setattr(service, '_commit', conflict)
    blocked = []
    monkeypatch.setattr(store, 'record_blocked', lambda uid, token, why, **kw: blocked.append((token, why)))
    assert await service.reconcile('u') == 'blocked'
    assert blocked == [('token', reason)]


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['source_changed', 'lease_lost'])
async def test_live_capture_race_answers_the_task_and_wakes_the_owner_next_minute(builder, monkeypatch, reason):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict(reason)

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(store, 'record_blocked', lambda *a: pytest.fail('a race is not a blocked owner'))
    wakes = []
    monkeypatch.setattr(service, 'enqueue', lambda uid, at=None, **kw: wakes.append((uid, at, kw)))
    raced = service.metrics.RACES.labels(reason)._value.get()
    outcomes = service.metrics.RECONCILES.labels('raced')._value.get()
    before = datetime.now(timezone.utc)
    assert await service.reconcile('u') == 'raced'
    # One coalesced named wake for a later minute than the executing task's, never a 500 retry.
    assert len(wakes) == 1 and wakes[0][0] == 'u' and wakes[0][2] == {}
    assert int(wakes[0][1].timestamp()) // 60 > int(before.timestamp()) // 60
    assert wakes[0][1] - before <= service.RACE_RETRY + timedelta(seconds=5)
    assert service.metrics.RACES.labels(reason)._value.get() == raced + 1
    assert service.metrics.RECONCILES.labels('raced')._value.get() == outcomes + 1


@pytest.mark.asyncio
async def test_race_without_a_scheduled_wake_still_raises_for_a_task_retry(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict('source_changed')

    def unavailable(*a, **kw):
        raise RuntimeError('conversations_v3_task_target_unconfigured')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(service, 'enqueue', unavailable)
    with pytest.raises(Conflict, match='source_changed'):
        await service.reconcile('u')


@pytest.mark.asyncio
async def test_backfill_race_still_raises_for_its_own_task_retry(builder, monkeypatch):
    monkeypatch.setattr(store, 'load_derive', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict('source_changed')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: pytest.fail('backfill owns its own retry'))
    with pytest.raises(Conflict):
        await service.reconcile('u', derive=True)


@pytest.mark.asyncio
async def test_backed_off_owner_skips_without_taking_the_lease(builder, monkeypatch):
    monkeypatch.setattr(
        store, 'backoff_state', lambda uid: (datetime.now(timezone.utc) + timedelta(minutes=5), 'target_exists')
    )
    monkeypatch.setattr(service.leases, 'acquire', lambda *a: pytest.fail('backoff must not take the lease'))
    drained = []

    async def drain(uid):
        drained.append(uid)

    monkeypatch.setattr(service, 'drain_processing', drain)
    assert await service.reconcile('u') == 'backoff'
    # Already committed rows still get their notes while the builder is parked.
    assert drained == ['u']


@pytest.mark.asyncio
async def test_open_conversation_bypasses_owner_backoff(builder, monkeypatch):
    monkeypatch.setattr(store, 'backoff_state', lambda uid: pytest.fail('on-open is the user waiting'))
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({}, {}, []))
    await service.reconcile('u', on_open=True, conversation_id='c')


@pytest.mark.asyncio
async def test_paid_outline_is_kept_when_the_commit_conflicts(builder, monkeypatch):
    _, messages = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    saved = []
    monkeypatch.setattr(store, 'save_outline', lambda uid, token, fp, entries: saved.append((fp, entries)))

    def conflict(*a, **kw):
        raise Conflict('target_exists')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(store, 'record_blocked', lambda *a, **kw: None)
    await service.reconcile('u')
    assert len(messages) == 1
    assert len(saved) == 1 and saved[0][1][0]['title'] == 'A plan'


def test_backoff_is_fenced_doubles_to_an_hour_and_a_commit_clears_it(strict):
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    delays = []
    for _ in range(9):
        before = datetime.now(timezone.utc)
        assert store.record_blocked('synthetic', token, 'target_exists', firestore_client=strict)
        delays.append(strict.rows[L]['v3_backoff_until'] - before)
    assert delays[0] <= timedelta(minutes=5, seconds=1) and delays[1] > delays[0]
    assert max(delays) <= store.BLOCKED_BACKOFF_MAX + timedelta(seconds=1)
    assert store.backoff_until('synthetic', firestore_client=strict) == strict.rows[L]['v3_backoff_until']
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    store.commit_projection(
        'synthetic',
        token,
        {'r': {'id': 'r', 'recording': True, '_v3_revision': 1}},
        {},
        [],
        [],
        firestore_client=strict,
    )
    assert strict.rows[L]['v3_backoff_until'] is None and strict.rows[L]['v3_blocked_count'] == 0


def test_stale_pass_cannot_park_a_successor(strict):
    old = leases.acquire(
        'synthetic', 'builder', now=datetime.now(timezone.utc) - timedelta(hours=1), firestore_client=strict
    )
    leases.acquire('synthetic', 'builder', firestore_client=strict)
    assert not store.record_blocked('synthetic', old, 'target_exists', firestore_client=strict)
    assert 'v3_backoff_until' not in strict.rows[L]


def test_saved_outline_survives_and_is_fenced(strict, monkeypatch):
    monkeypatch.setattr(store, 'decrypt', lambda value, uid: value)
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.save_outline('synthetic', token, 'fp', [{'title': 'first'}], firestore_client=strict)
    store.save_outline('synthetic', token, 'fp', [{'title': 'second'}], firestore_client=strict)
    for n in range(130):
        store.save_outline('synthetic', token, f'other-{n}', [], firestore_client=strict)
    cache = json.loads(strict.rows[L]['outline_cache'])
    assert len(cache) == 128 and not any(c['fingerprint'] == 'fp' for c in cache)
    store.save_outline('synthetic', token, 'fp', [{'title': 'kept'}], firestore_client=strict)
    cache = json.loads(strict.rows[L]['outline_cache'])
    assert [c['entries'] for c in cache if c['fingerprint'] == 'fp'] == [[{'title': 'kept'}]]
    leases.release('synthetic', 'builder', token, firestore_client=strict)
    with pytest.raises(Conflict, match='lease_lost'):
        store.save_outline('synthetic', token, 'fp', [], firestore_client=strict)


def test_closure_follows_a_six_hop_link_chain(monkeypatch):
    # r0 is pending; derived row d_i (hour i) links r_i to r_{i+1}, hours apart, so each hop is a new round.
    rows = {}
    for i in range(6):
        rows[f'/users/u/conversations/r{i}'] = source(
            f'r{i}',
            started_at=AT + timedelta(hours=i),
            finished_at=AT + timedelta(hours=i, seconds=10),
            v3_pending=i == 0,
            v3_pending_since=AT,
        )
        rows[f'/users/u/conversations/d{i}'] = {
            'id': f'd{i}',
            'v3_derived': True,
            'started_at': AT + timedelta(hours=i),
            'finished_at': AT + timedelta(hours=i, seconds=10),
            'v3_recording_ids': [f'r{i}'] + ([f'r{i + 1}'] if i < 5 else []),
        }
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1} if snap.exists else None
    )
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert set(recordings) == {f'r{i}' for i in range(6)}
    assert set(existing) == {f'd{i}' for i in range(6)}


def test_late_text_past_finished_at_extends_the_closure_window():
    row = source(
        finished_at=AT + timedelta(seconds=10),
        transcript_segments=[
            {'text': 'early', 'start': 0, 'end': 10},
            {'text': 'late text appended after completion', 'start': 3600, 'end': 3610},
        ],
    )
    assert store.speech_end(row) == AT + timedelta(seconds=3610)
    assert store.speech_end(source()) == AT + timedelta(seconds=10)


def test_adoptable_skips_deleted_tombstoned_and_recording_rows(monkeypatch):
    live = {'id': 'live', 'v3_derived': True}
    rows = {
        '/users/u/conversations/live': live,
        '/users/u/conversations/deleted': {'id': 'deleted', 'v3_derived': True, 'deleted': True},
        '/users/u/conversations/tomb': {'id': 'tomb', 'v3_derived': True},
        '/users/u/deleted_conversations/tomb': {'id': 'tomb'},
        '/users/u/conversations/rec': {'id': 'rec', 'v3_derived': True, 'recording': True},
        '/users/u/conversations/legacy': {'id': 'legacy'},
    }
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1})
    found = store.adoptable(
        'u', ['live', 'deleted', 'tomb', 'rec', 'legacy', 'missing'], firestore_client=MemoryQuery(rows)
    )
    assert list(found) == ['live']


def _open_loop_row(level):
    return {
        'id': 'c',
        'status': 'processing',
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': ['r'],
        'transcript_segments': [],
        'structured': {},
        'data_protection_level': level,
        'open_loop_extractions': 'stored-protected-blob',
        'open_loop_extractions_compressed': True,
    }


def test_prior_open_loop_blob_is_carried_verbatim(strict, monkeypatch):
    seen = []
    real = store.conversations._prepare_conversation_for_write

    def prepare(row, *a, **kw):
        seen.append(dict(row))
        return real(row, *a, **kw)

    monkeypatch.setattr(store.conversations, '_prepare_conversation_for_write', prepare)
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    strict.rows[('users', 'synthetic', 'conversations', 'c')] = {'id': 'c'}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    prior = {**_open_loop_row('standard'), '_v3_revision': 1}
    store.commit_projection(
        'synthetic',
        token,
        {'r': {'id': 'r', 'recording': True, '_v3_revision': 1}},
        {'c': prior},
        [_open_loop_row('standard')],
        [],
        firestore_client=strict,
    )
    # The protected blob never reaches the codec, which accepts only the decoded object.
    assert all('open_loop_extractions' not in row for row in seen)
    stored = strict.rows[('users', 'synthetic', 'conversations', 'c')]
    assert stored['open_loop_extractions'] == 'stored-protected-blob'
    assert stored['open_loop_extractions_compressed'] is True


def test_open_loop_blob_is_reprotected_on_a_level_change(strict, monkeypatch):
    decoded = []
    monkeypatch.setattr(
        store.conversations,
        'decode_open_loop_extractions',
        lambda uid, raw, compressed: decoded.append((raw, compressed)) or {'loops': []},
    )
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    strict.rows[('users', 'synthetic', 'conversations', 'c')] = {'id': 'c'}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    prior = {**_open_loop_row('standard'), '_v3_revision': 1}
    store.commit_projection(
        'synthetic',
        token,
        {'r': {'id': 'r', 'recording': True, '_v3_revision': 1}},
        {'c': prior},
        [_open_loop_row('enhanced')],
        [],
        firestore_client=strict,
    )
    assert decoded == [('stored-protected-blob', True)]
    assert strict.rows[('users', 'synthetic', 'conversations', 'c')]['open_loop_extractions'] == {'loops': []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'message',
    [
        "Document 'x' cannot be written because its size (1,048,630 bytes) exceeds the maximum allowed size of 1,048,576 bytes.",
        'The value of property "transcript_segments" is longer than 1048487 bytes.',
    ],
)
async def test_oversized_document_parks_the_owner_instead_of_retrying(builder, monkeypatch, message):
    from google.api_core.exceptions import InvalidArgument

    from utils.conversations import lifecycle

    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    monkeypatch.setattr(service, '_commit', REAL_COMMIT)

    def too_large(*a, **kw):
        raise InvalidArgument(message)

    monkeypatch.setattr(lifecycle, 'commit_v3_projection', too_large)
    blocked = []
    monkeypatch.setattr(store, 'record_blocked', lambda uid, token, why, **kw: blocked.append(why))
    assert await service.reconcile('u') == 'blocked'
    assert blocked == ['document_too_large']


def test_other_invalid_arguments_still_raise(monkeypatch):
    from google.api_core.exceptions import InvalidArgument

    from utils.conversations import lifecycle

    def bad(*a, **kw):
        raise InvalidArgument('some other invalid write')

    monkeypatch.setattr(lifecycle, 'commit_v3_projection', bad)
    with pytest.raises(InvalidArgument):
        REAL_COMMIT('u', 't', {}, {}, [], [])


@pytest.mark.asyncio
async def test_handled_race_still_surfaces_lease_release_failure(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    wakes = []

    def conflict(*a, **kw):
        raise Conflict('source_changed')

    def release_failure(*_args):
        raise RuntimeError('release failed after race')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(service, 'enqueue', lambda uid, **_kwargs: wakes.append(uid))
    monkeypatch.setattr(leases, 'release', release_failure)
    with pytest.raises(RuntimeError, match='release failed after race'):
        await service.reconcile('u')
    assert wakes == ['u']
