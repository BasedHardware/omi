"""Source claims stay bounded across builder passes (document_too_large incident, 2026-11-18).

A late recording whose speech starts before a finished conversation and overlaps it formed a fresh
window that sorted before the conversation's retained window. The fresh window time-matched the
retained id, so two planned rows shared one id; each re-added the source's held claims and the claims
array doubled on every pass until the recording outgrew Firestore's 1 MiB document limit.
"""

from database import conversations_v3_leases as leases

from datetime import datetime, timedelta, timezone
from copy import deepcopy
import importlib
import json
import logging

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import service
from utils.sync.assignment import assign_in_transaction
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

UID = 'synthetic'
T0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def path(cid):
    return ('users', UID, 'conversations', cid)


@pytest.fixture(scope='module', autouse=True)
def owners_import():
    importlib.import_module('utils.conversations.lifecycle')
    return importlib.import_module('utils.speakers.evidence')


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)

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


def recording(cid, start, segments, claims, **extra):
    return {
        'id': cid,
        'recording': True,
        'status': 'completed',
        'source': 'omi',
        'started_at': start,
        'finished_at': start + timedelta(seconds=max(s['end'] for s in segments)),
        'data_protection_level': 'standard',
        'claims': claims,
        'transcript_segments': segments,
        **extra,
    }


def speech(count, step=30):
    return [
        {'text': f'Synthetic speech {i}', 'start': i * step, 'end': i * step + 20, 'is_user': True}
        for i in range(count)
    ]


def seed(strict, *, a_claims):
    strict.rows[path('a')] = recording('a', T0, speech(20), a_claims)
    # "b" synced late: it starts a minute before "x" and overlaps its first twenty seconds.
    strict.rows[path('b')] = recording(
        'b',
        T0 - timedelta(seconds=60),
        [{'text': 'Synthetic late speech', 'start': 0, 'end': 80, 'is_user': True}],
        [],
        v3_pending=True,
    )
    strict.rows[path('x')] = {
        'id': 'x',
        'v3_derived': True,
        'status': 'completed',
        'tile_state': 'done',
        'started_at': T0,
        'finished_at': T0 + timedelta(seconds=590),
        'v3_recording_ids': ['a'],
        'transcript_segments': [],
        'structured': {'title': 'Earlier'},
    }


async def run_pass(strict, monkeypatch, sources):
    for row in strict.rows.values():
        row['_test_revision'] = 1
    recordings = {cid: {**deepcopy(strict.rows[path(cid)]), '_v3_revision': 1} for cid in sources}
    existing = {
        p[3]: {**deepcopy(r), '_v3_revision': 1}
        for p, r in strict.rows.items()
        if p[2] == 'conversations' and r.get('v3_derived')
    }
    original_load = store.load
    committed = []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is original_load:
            return deepcopy(recordings), deepcopy(existing), []
        if fn is store.adoptable:
            return {}
        if fn is service._commit:
            committed.append([row['id'] for row in args[4]])
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    def outline(uid, messages):
        entry = {'first_line': 1, 'kind': 'conversation', 'title': 'Planning', 'line': '', 'people': [], 'sections': []}
        return json.dumps({'conversations': [entry]})

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    monkeypatch.setattr(service.models, 'outline', outline)
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda uid, recordings, windows: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    assert await service.reconcile(UID) == 'committed'
    return committed


def claim_keys(cid, strict):
    return [(c['conversation_id'], c['start'], c['end']) for c in strict.rows[path(cid)].get('claims') or []]


@pytest.mark.asyncio
async def test_late_overlapping_recording_never_plans_a_finished_conversation_twice(strict, monkeypatch):
    seed(strict, a_claims=[{'conversation_id': 'x', 'start': T0, 'end': T0 + timedelta(seconds=590)}])
    for _ in range(4):
        committed = await run_pass(strict, monkeypatch, ['a', 'b'])
        assert committed and all(len(ids) == len(set(ids)) for ids in committed), committed
    # Unfixed, "a" held 2**4 copies of x's claim here.
    assert claim_keys('a', strict) == [('x', T0, T0 + timedelta(seconds=590))]
    keys = claim_keys('b', strict)
    assert len(keys) == len(set(keys)) == 1 and keys[0][0] != 'x'
    # The finished conversation keeps its published boundaries; the late speech is its own conversation.
    assert strict.rows[path('x')]['started_at'] == T0
    late = strict.rows[path(keys[0][0])]
    assert late['v3_derived'] and late['v3_recording_ids'] == ['b']


@pytest.mark.asyncio
async def test_bloated_source_claims_collapse_on_the_next_commit(strict, monkeypatch):
    claim = {'conversation_id': 'x', 'start': T0, 'end': T0 + timedelta(seconds=590)}
    seed(strict, a_claims=[dict(claim) for _ in range(4096)] + [{'conversation_id': 'other', 'start': T0, 'end': T0}])
    await run_pass(strict, monkeypatch, ['a', 'b'])
    assert sorted(claim_keys('a', strict)) == [('other', T0, T0), ('x', T0, T0 + timedelta(seconds=590))]


def test_commit_dedupes_claims_on_untouched_and_moved_sources(strict):
    span = {'start': T0, 'end': T0 + timedelta(minutes=1)}
    stale = [{'conversation_id': 'kept', **span}] * 3
    strict.rows[path('r')] = {'recording': True, 'v3_pending': True, 'claims': stale, '_test_revision': 1}
    strict.rows[path('m')] = {
        'recording': True,
        'v3_pending': True,
        'claims': stale,
        'started_at': T0,
        '_test_revision': 2,
    }
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    moved_source = {'id': 'm', 'recording': True, 'started_at': T0, 'claims': stale, '_v3_revision': 1}
    moved_source['_v3_fence'] = store.source_fence(strict.rows[path('m')])
    row = {
        'id': 'c',
        'status': 'processing',
        'created_at': T0,
        'started_at': T0,
        'finished_at': T0,
        'v3_recording_ids': ['r', 'm'],
        'transcript_segments': [],
        'structured': {},
        '_v3_claims': {'r': [span, span], 'm': [span, span]},
    }
    moved = store.commit_projection(
        UID,
        token,
        {'r': {'id': 'r', 'recording': True, 'claims': stale, '_v3_revision': 1}, 'm': moved_source},
        {},
        [row],
        [],
        firestore_client=strict,
    )
    assert moved == {'m'}
    for cid in ('r', 'm'):
        assert claim_keys(cid, strict) == [
            ('kept', T0, T0 + timedelta(minutes=1)),
            ('c', T0, T0 + timedelta(minutes=1)),
        ]


def test_too_large_commit_logs_the_document_kind_and_size_only(strict, monkeypatch, caplog):
    from google.api_core.exceptions import InvalidArgument

    strict.rows[path('r')] = {'recording': True, 'v3_pending': True, 'transcript_segments': 'x' * 50000}
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    original = store.firestore.transactional

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            wrapped(tx, *args)
            raise InvalidArgument('Document cannot be written because its size exceeds the maximum allowed size')

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    row = {
        'id': 'secret-conversation-id',
        'status': 'processing',
        'created_at': T0,
        'started_at': T0,
        'finished_at': T0,
        'v3_recording_ids': ['r'],
        'transcript_segments': [{'text': 'secret words', 'start': 0, 'end': 1, 'is_user': True}],
        'structured': {},
    }
    with caplog.at_level(logging.WARNING, logger=store.logger.name), pytest.raises(InvalidArgument):
        store.commit_projection(
            UID, token, {'r': {**strict.rows[path('r')], '_v3_revision': 1}}, {}, [row], [], firestore_client=strict
        )
    [record] = [r for r in caplog.records if 'write too large' in r.getMessage()]
    message = record.getMessage()
    assert 'kind=recording' in message and 'claims=1' in message and 'batch=0 batches=1' in message
    assert 'secret' not in message and UID not in message


@pytest.mark.asyncio
async def test_blocked_live_pass_still_drains_committed_notes(monkeypatch):
    drained, parked = [], []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.backoff_state:
            return None, None
        if fn is leases.acquire:
            return 'token'
        if fn is store.load:
            raise service.Conflict('document_too_large')
        if fn is store.record_blocked:
            parked.append(args[2])
            return True
        return None

    async def drain(uid):
        drained.append(uid)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', drain)
    assert await service.reconcile(UID) == 'blocked'
    assert parked == ['document_too_large'] and drained == [UID]


@pytest.mark.asyncio
@pytest.mark.parametrize('reason,kwargs', [('account_deletion', {}), ('document_too_large', {'on_open': True})])
async def test_blocked_pass_skips_drain_for_deletion_and_open(monkeypatch, reason, kwargs):
    drained = []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.backoff_state:
            return None, None
        if fn is leases.acquire:
            return 'token'
        if fn is store.load:
            raise service.Conflict(reason)
        return None

    async def drain(uid):
        drained.append(uid)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', drain)
    assert await service.reconcile(UID, **kwargs) == 'blocked'
    assert drained == []


@pytest.mark.asyncio
@pytest.mark.parametrize('parked,drains', [('document_too_large', True), ('account_deletion', False)])
async def test_backoff_pass_drains_committed_notes_except_for_deletion(monkeypatch, parked, drains):
    drained = []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.backoff_state:
            return datetime.now(timezone.utc) + timedelta(minutes=30), parked
        raise AssertionError('a parked owner takes no lease and loads nothing')

    async def drain(uid):
        drained.append(uid)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', drain)
    assert await service.reconcile(UID) == 'backoff'
    assert drained == ([UID] if drains else [])


@pytest.mark.parametrize(
    'message,reason',
    [
        (
            'Document cannot be written because its size (1100000 bytes) exceeds the maximum allowed size',
            'document_too_large',
        ),
        ('Request payload size exceeds the limit: 18874368 bytes.', 'request_too_large'),
    ],
)
def test_commit_maps_both_size_limits_to_blocked_conflicts(monkeypatch, message, reason):
    from google.api_core.exceptions import InvalidArgument
    from utils.conversations import lifecycle

    def fail(*args, **kwargs):
        raise InvalidArgument(message)

    monkeypatch.setattr(lifecycle, 'commit_v3_projection', fail)
    with pytest.raises(service.Conflict, match=reason) as raised:
        service._commit(UID, 'token', {}, {}, [], [])
    assert reason in service.BLOCKED and isinstance(raised.value.__cause__, InvalidArgument)


def test_other_invalid_argument_still_raises(monkeypatch):
    from google.api_core.exceptions import InvalidArgument
    from utils.conversations import lifecycle

    def fail(*args, **kwargs):
        raise InvalidArgument('Cannot have an array inside an array')

    monkeypatch.setattr(lifecycle, 'commit_v3_projection', fail)
    with pytest.raises(InvalidArgument):
        service._commit(UID, 'token', {}, {}, [], [])


@pytest.mark.asyncio
async def test_blocked_log_names_cause_and_owner_hash_without_ids(monkeypatch, caplog):
    from google.api_core.exceptions import InvalidArgument

    secret_uid = 'AbCdEfGhIjKlMnOpQrStUvWxYz12'

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.backoff_state:
            return None, None
        if fn is leases.acquire:
            return 'token'
        if fn is store.load:
            try:
                raise InvalidArgument(
                    f'Document projects/p/databases/(default)/documents/users/{secret_uid}/conversations/c1 cannot '
                    'be written because its size (1100000 bytes) exceeds the maximum allowed size'
                )
            except InvalidArgument as error:
                raise service.Conflict('document_too_large') from error
        return None

    async def drain(uid):
        return None

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', drain)
    with caplog.at_level(logging.WARNING, logger=service.logger.name):
        assert await service.reconcile(secret_uid) == 'blocked'
    [message] = [r.getMessage() for r in caplog.records if 'reconcile blocked reason=' in r.getMessage()]
    assert 'cause=InvalidArgument limit=document bytes=1100000' in message and 'projects/' not in message
    assert f'owner={service.owner_tag(secret_uid)}' in message and secret_uid not in message


def test_batches_count_source_claim_rewrites_against_the_request(strict, monkeypatch):
    strict.rows[path('r')] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    commits = []
    original = store.firestore.transactional

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            commits.append(len(args[0]))
            return wrapped(tx, *args)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    # Rows alone (8 x ~100 KB) fit one 2 MiB batch; the sources each batch rewrites do not.
    monkeypatch.setattr(store, 'fixed_write_bytes', lambda *a: store.BATCH_WRITE_BYTES - 300 * 1024)
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'created_at': T0,
            'started_at': T0,
            'finished_at': T0,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * 100000, 'start': 0, 'end': 1, 'is_user': True}],
            'structured': {},
        }
        for i in range(8)
    ]
    store.commit_projection(
        UID, token, {'r': {**strict.rows[path('r')], '_v3_revision': 1}}, {}, rows, [], firestore_client=strict
    )
    assert len(commits) > 1 and sum(commits) == 8 and max(commits) <= 3


def test_fixed_write_bytes_counts_every_source_claim_update():
    claim = {'conversation_id': 'x', 'start': T0, 'end': T0}
    small = store.fixed_write_bytes({'r': {'claims': [claim]}}, [], 'cache')
    large = store.fixed_write_bytes(
        {'r': {'claims': [claim]}, 's': {'claims': [dict(claim, conversation_id=str(i)) for i in range(500)]}},
        [],
        'cache',
    )
    assert large - small > 500 * 40


@pytest.mark.asyncio
async def test_fresh_window_at_a_retained_start_gets_its_own_id(strict, monkeypatch):
    # The retained conversation's id is the start-keyed id a fresh window at the same instant derives.
    from uuid import NAMESPACE_URL, uuid5

    xid = str(uuid5(NAMESPACE_URL, f'v3:{UID}:{T0.isoformat()}'))
    seed(
        strict,
        a_claims=[{'conversation_id': xid, 'start': T0 + timedelta(seconds=30), 'end': T0 + timedelta(seconds=590)}],
    )
    strict.rows[path(xid)] = {**strict.rows.pop(path('x')), 'id': xid}
    strict.rows[path('a')]['transcript_segments'] = speech(20)[1:]
    strict.rows[path('b')] = recording(
        'b', T0, [{'text': 'Synthetic late speech', 'start': 0, 'end': 20, 'is_user': True}], [], v3_pending=True
    )
    for _ in range(3):
        committed = await run_pass(strict, monkeypatch, ['a', 'b'])
        assert committed and all(len(ids) == len(set(ids)) for ids in committed), committed
    keys = claim_keys('a', strict)
    assert len(keys) == len(set(keys)) == 1


def sync_recording(strict, cid, offset, *, candidate=None):
    row = recording(
        cid,
        T0 + timedelta(seconds=offset),
        [
            {
                'id': cid,
                'start': 0,
                'end': 20,
                'text': f'The synthetic speaker described {cid} in detail.',
                'is_user': True,
            }
        ],
        [],
    )
    return assign_in_transaction(
        strict.transaction(),
        strict.collection('users').document(UID),
        row,
        candidate_id=candidate,
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda payload: None,
    )[0]


def publish_card(strict, rid, cid):
    source = strict.rows[path(rid)]
    card = {
        'id': cid,
        'v3_derived': True,
        'status': 'completed',
        'tile_state': 'done',
        'started_at': source['started_at'],
        'finished_at': source['finished_at'],
        'v3_recording_ids': [rid],
        'transcript_segments': deepcopy(source['transcript_segments']),
        'structured': {'title': 'A user-edited title'},
        'user_title': True,
    }
    strict.rows[path(cid)] = card
    source['claims'] = [{'conversation_id': cid, 'start': card['started_at'], 'end': card['finished_at']}]
    return deepcopy(card)


@pytest.mark.asyncio
async def test_sync_redirect_chain_preserves_finished_claims_and_unrelated_speech(strict, monkeypatch):
    sync_recording(strict, 'early', 0)
    sync_recording(strict, 'middle', 180)
    sync_recording(strict, 'late', 360)
    card = publish_card(strict, 'late', 'finished')
    claimed = [(card['id'], card['started_at'], card['finished_at'])]

    assert sync_recording(strict, 'bridge-late', 270, candidate='late')['id'] == 'middle'
    assert strict.rows[path('late')]['sync_merged_into'] == 'middle'
    assert claim_keys('late', strict) == []
    assert claim_keys('middle', strict) == claimed
    assert strict.rows[path('finished')] == {**card, 'v3_recording_ids': ['middle']}

    for _ in range(2):
        assert sync_recording(strict, 'bridge-early', 90, candidate='middle')['id'] == 'early'
    assert strict.rows[path('middle')]['sync_merged_into'] == 'early'
    assert claim_keys('middle', strict) == []
    assert claim_keys('early', strict) == claimed
    assert strict.rows[path('finished')] == {**card, 'v3_recording_ids': ['early']}

    await run_pass(strict, monkeypatch, ['early'])
    rows = [row for row in strict.rows.values() if row.get('v3_derived') and not row.get('deleted')]
    by_segment = {}
    for row in rows:
        for segment in row['transcript_segments']:
            by_segment.setdefault(segment['id'], []).append(row['id'])
    assert by_segment['late'] == ['finished']
    assert set(by_segment) == {'early', 'bridge-early', 'middle', 'bridge-late', 'late'}
    assert all(len(owners) == 1 for owners in by_segment.values())


@pytest.mark.parametrize('condition', ['playback', 'tombstone', 'different_speech'])
def test_sync_keeps_donor_when_custody_cannot_be_transferred(strict, condition):
    sync_recording(strict, 'early', 0)
    sync_recording(strict, 'late', 180)
    card = publish_card(strict, 'late', 'finished')
    if condition == 'playback':
        strict.rows[path('late')]['audio_files'] = [{'id': 'source-file'}]
    elif condition == 'tombstone':
        strict.rows[('users', UID, 'deleted_conversations', 'finished')] = {'deleted': True}
    elif condition == 'different_speech':
        strict.rows[path('finished')]['transcript_segments'][0]['text'] = 'Edited by the user.'
    before = deepcopy(strict.rows[path('late')])
    assert sync_recording(strict, 'bridge', 90, candidate='late')['id'] == 'early'
    assert strict.rows[path('late')] == before
    assert strict.rows[path('finished')]['v3_recording_ids'] == ['late']
    assert claim_keys('early', strict) == []
    assert claim_keys('late', strict) == [(card['id'], card['started_at'], card['finished_at'])]
