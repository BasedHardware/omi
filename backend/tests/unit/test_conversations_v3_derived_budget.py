"""The live closure loads a heavy owner's claimed rows without chaining through settled history."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases, memories
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.conversations.v3 import Conflict, UnlockedPage, planner, service, triggers
from tests.unit.test_conversations_v3_claim_growth import T0, UID, path, strict  # noqa: F401
from tests.unit.test_conversations_v3_lock_timing import _locked_pair
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, builder, source  # noqa: F401

C = '/users/u/conversations/'


@pytest.fixture(autouse=True)
def origin_bound(monkeypatch):
    # The bound tests below pin the kill-switched (origin) bound; the locked allowance has its own tests.
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 0)


@pytest.fixture(autouse=True)
def plain_rows(monkeypatch):
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1} if snap.exists else None
    )


def derived(cid, start, seconds, recordings, **extra):
    return {
        'id': cid,
        'v3_derived': True,
        'status': 'completed',
        'started_at': start,
        'finished_at': start + timedelta(seconds=seconds),
        'v3_recording_ids': recordings,
        'transcript_segments': [{'text': 'short window', 'start': 0, 'end': seconds}],
        **extra,
    }


def claim(cid, start, seconds):
    return {'conversation_id': cid, 'start': start, 'end': start + timedelta(seconds=seconds)}


def fragmented(n):
    """One pending 50-minute recording that n back-to-back short windows own (the parked owners' shape)."""
    rows, claims = {}, []
    for i in range(n):
        start = AT + timedelta(seconds=10 * i)
        rows[C + f'd{i}'] = derived(f'd{i}', start, 10, ['r'])
        claims.append(claim(f'd{i}', start, 10))
    rows[C + 'r'] = source(
        'r', finished_at=AT + timedelta(seconds=10 * n), claims=claims, v3_pending_since=AT, v3_pending=True
    )
    return rows


def test_a_recording_owned_by_hundreds_of_short_windows_loads():
    # Production shape (2026-11-19): one pending recording owned by up to ~450 contiguous sub-minute
    # windows. All of them are needed to replan it; 128 rows parked the owner on every retry.
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(fragmented(450)))
    assert set(recordings) == {'r'}
    assert len(existing) == 450


def neighbours():
    # p is pending; q (10 minutes later, inside p's margin) is settled and claimed by dq; s (15 minutes after
    # q, outside p's margin but inside q's) is settled and claimed by ds.
    q_at, s_at = AT + timedelta(minutes=10), AT + timedelta(minutes=25)
    rows = {
        C + 'p': source('p', claims=[claim('dp', AT, 10)], v3_pending_since=AT),
        C + 'dp': derived('dp', AT, 10, ['p']),
        C + 'q': source('q', started_at=q_at, finished_at=q_at + timedelta(seconds=10), v3_pending=False),
        C + 'dq': derived('dq', q_at, 10, ['q']),
        C + 's': source('s', started_at=s_at, finished_at=s_at + timedelta(seconds=10), v3_pending=False),
        C + 'ds': derived('ds', s_at, 10, ['s']),
    }
    rows[C + 'q']['claims'] = [claim('dq', q_at, 10)]
    rows[C + 's']['claims'] = [claim('ds', s_at, 10)]
    return rows


def test_settled_neighbours_do_not_chain_the_closure():
    # The old closure queried q's margin too and pulled ds, s, and so on through the owner's whole day.
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(neighbours()))
    assert set(recordings) == {'p', 'q'}
    assert set(existing) == {'dp', 'dq'}


def test_kill_switch_restores_the_time_query_around_every_source(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_CLOSURE_BY_CLAIMS', 'off')
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(neighbours()))
    assert set(recordings) == {'p', 'q', 's'}
    assert set(existing) == {'dp', 'dq', 'ds'}


def test_overflowing_claim_ids_refuse_before_reading_them(monkeypatch):
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)
    rows = fragmented(11)
    client = MemoryQuery(rows)
    reads = []
    real = MemoryQuery.get_all
    monkeypatch.setattr(MemoryQuery, 'get_all', lambda self, refs, **kw: reads.append(len(refs)) or real(self, refs))
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=client)
    assert reads == []


def test_claimants_are_read_in_chunks(monkeypatch):
    monkeypatch.setattr(store, 'CLAIM_READ_CHUNK', 7)
    reads = []
    real = MemoryQuery.get_all
    monkeypatch.setattr(MemoryQuery, 'get_all', lambda self, refs, **kw: reads.append(len(refs)) or real(self, refs))
    rows = fragmented(20)
    # Push the claimants out of the pending recording's time window so only the claims path finds them.
    for i in range(20):
        rows[C + f'd{i}']['started_at'] += timedelta(hours=3)
        rows[C + f'd{i}']['finished_at'] += timedelta(hours=3)
    _, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert len(existing) == 20 and reads == [7, 7, 6]


@pytest.mark.parametrize('remove, expected', [((), [3, 3, 2]), (('old0', 'old1'), [1] * 8)])
def test_commit_batches_stay_under_the_write_cap(strict, monkeypatch, remove, expected):
    strict.rows[path('r')] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    commits = []
    original = store.firestore.transactional

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            if body.__name__ == 'commit':  # lease renewals between batches are transactions too
                commits.append(len(args[0]))
            return wrapped(tx, *args)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    # A removal consumes two writes: its marker and delete. Keep just one row slot in that case.
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 7 if remove else 5)
    monkeypatch.setattr(memories, 'linked_conversation_ids', lambda *a, **kw: set())
    for cid in remove:
        strict.rows[path(cid)] = {'id': cid, 'v3_derived': True, 'backfilled': True}
    rows = [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': T0,
            'finished_at': T0,
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'short'}],
        }
        for i in range(8)
    ]
    existing = {cid: {**strict.rows[path(cid)], '_v3_revision': 1} for cid in remove}
    store.commit_projection(
        UID,
        token,
        {'r': {**strict.rows[path('r')], '_v3_revision': 1}},
        existing,
        rows,
        [],
        remove=list(remove),
        firestore_client=strict,
    )
    assert commits == expected


def test_every_claimant_of_a_loaded_recording_is_loaded_by_id():
    # dq links p and q, so q is replanned; q's claims also name dx, far outside any queried window. Without
    # dx the replan would see q's lines it owns as unowned speech and duplicate them.
    q_at, x_at = AT + timedelta(minutes=1), AT + timedelta(hours=5)
    rows = {
        C + 'p': source('p', claims=[claim('dq', AT, 10)], v3_pending_since=AT),
        C
        + 'q': source(
            'q',
            started_at=q_at,
            finished_at=q_at + timedelta(seconds=10),
            v3_pending=False,
            claims=[claim('dq', q_at, 10), claim('dx', x_at, 10)],
        ),
        C + 'dq': derived('dq', AT, 70, ['p', 'q']),
        C + 'dx': derived('dx', x_at, 10, ['q']),
        C + 'legacy': {'id': 'legacy', 'started_at': x_at, 'finished_at': x_at},
    }
    rows[C + 'q']['claims'].append(claim('legacy', x_at, 10))
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert set(recordings) == {'p', 'q'}
    assert set(existing) == {'dq', 'dx'}


def test_an_open_windows_settled_source_still_queries_its_neighbours():
    # The open row's recording is settled (claims, not pending), but the open window is still replanned, so
    # its neighbours by time stay in the closure exactly as before.
    n_at = AT - timedelta(minutes=10)
    rows = {
        C + 'r': source('r', v3_pending=False, claims=[claim('open', AT, 10)]),
        C + 'open': derived('open', AT, 10, ['r'], status='in_progress'),
        C + 'n': source('n', started_at=n_at, finished_at=n_at + timedelta(seconds=10), v3_pending=False),
        C + 'dn': derived('dn', n_at, 10, ['n']),
        '/users/u/conversation_v3_leases/builder': {'open_id': 'open'},
    }
    rows[C + 'n']['claims'] = [claim('dn', n_at, 10)]
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert set(existing) == {'open', 'dn'}
    assert set(recordings) == {'r', 'n'}


def test_the_closure_stays_bounded_by_rows(monkeypatch):
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 100)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(101)))
    store.load('u', firestore_client=MemoryQuery(fragmented(100)))


def test_the_closure_stays_bounded_by_stored_speech(monkeypatch):
    rows = fragmented(10)
    per_row = store._encoded_bytes(rows[C + 'd0']['transcript_segments'])
    monkeypatch.setattr(store, 'DERIVED_BYTES', per_row * 10 - 1)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))
    monkeypatch.setattr(store, 'DERIVED_BYTES', per_row * 10)
    store.load('u', firestore_client=MemoryQuery(rows))


def test_an_overflowing_closure_stops_decoding_at_the_bound(monkeypatch):
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)
    decoded = []
    monkeypatch.setattr(
        store,
        'decode_row',
        lambda uid, snap: decoded.append(snap.id) or ({**snap.to_dict(), '_v3_revision': 1} if snap.exists else None),
    )
    rows = fragmented(30)
    rows[C + 'r']['claims'] = []  # only the time query finds the 30 windows
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))
    assert len([cid for cid in decoded if cid.startswith('d')]) == 10


def test_the_closure_bounds_its_sources(monkeypatch):
    monkeypatch.setattr(store, 'SOURCE_LIMIT', 3)
    rows = {C + 'p': source('p', claims=[claim('d', AT, 10)], v3_pending_since=AT)}
    rows[C + 'd'] = derived('d', AT, 10, ['p', 'a', 'b', 'c'])
    for rid in 'abc':
        rows[C + rid] = source(rid, v3_pending=False, claims=[claim('d', AT, 10)])
    with pytest.raises(Conflict, match='v3_source_closure_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))


def test_missing_sources_count_and_the_source_bound_holds_before_reading(monkeypatch):
    monkeypatch.setattr(store, 'SOURCE_LIMIT', 3)
    reads = []
    real = store.recording_input
    monkeypatch.setattr(
        store, 'recording_input', lambda uid, snap, **kw: reads.append(snap.id) or real(uid, snap, **kw)
    )
    rows = {C + 'p': source('p', claims=[claim('d', AT, 10)], v3_pending_since=AT)}
    rows[C + 'd'] = derived('d', AT, 10, ['p', 'gone1', 'gone2', 'gone3'])
    with pytest.raises(Conflict, match='v3_source_closure_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))
    assert not any(rid.startswith('gone') for rid in reads)


@pytest.mark.asyncio
async def test_large_pending_backlog_commits_oldest_complete_slice(strict, monkeypatch, caplog):

    rows = {}
    for i in range(1000):
        start = AT + timedelta(hours=i)
        rid, cid = f'r{i}', f'd{i}'
        rows[C + rid] = source(
            rid,
            started_at=start,
            finished_at=start + timedelta(seconds=10),
            v3_pending_since=start,
            claims=[claim(cid, start, 10)],
        )
        rows[C + cid] = derived(cid, start, 10, [rid])
    client = MemoryQuery(rows)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 12)

    async def run_fixture(_, fn, *args, **kwargs):
        if fn in (store.mark_bounded_attempt, store.clear_terminal_pending):
            return None  # the lease marker is covered by test_early_attempt_is_spent_under_the_lease_before_work
        return fn(*args, firestore_client=client, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    for _ in range(2):
        with pytest.raises(Conflict, match='v3_derived_budget'):
            store.load('u', firestore_client=client)
    with caplog.at_level('INFO'):
        recordings, existing, _, limit = await service._load_live_batch('u', 'token', 'v3_derived_budget')
    assert list(recordings) == [f'r{i}' for i in range(8)]
    assert set(existing) == {f'd{i}' for i in range(8)}
    assert 'event=v3_bounded_pending pending_limit=8' in caplog.messages

    for row in (*recordings.values(), *existing.values(), rows[C + 'r8']):
        rid = row['id']
        strict.rows[path(rid)] = rows[C + rid].copy()
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    store.commit_projection(
        UID, token, recordings, existing, [], [], bounded_pending_limit=limit, firestore_client=strict
    )
    held = leases.lease_ref(strict, UID, 'builder')
    assert held.get().to_dict()['v3_bounded_pending_limit'] == 8
    store.commit_projection(UID, token, {}, {}, [], [], bounded_pending_limit=32, firestore_client=strict)
    assert held.get().to_dict()['v3_bounded_pending_limit'] is None
    for rid, row in recordings.items():
        stored = strict.rows[path(rid)]
        assert stored['v3_pending'] is False
        assert stored['claims'] == row['claims']
    assert strict.rows[path('r8')]['v3_pending'] is True


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('terminal', ['discarded', 'deleted'])
def test_terminal_pending_avoids_transcript_decode_and_claim_closure(monkeypatch, terminal, enabled):
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'on' if enabled else 'off')
    rows = fragmented(20)
    rows[C + 'r'][terminal] = True
    decode = store.decode_row
    decoded = []

    def track(uid, doc):
        decoded.append(doc.id)
        return decode(uid, doc)

    monkeypatch.setattr(store, 'decode_row', track)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 1)
    if not enabled:
        with pytest.raises(Conflict, match='v3_derived_budget'):
            store.load('u', firestore_client=MemoryQuery(rows))
        assert decoded == ['r']
    else:
        recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
        assert recordings['r']['_v3_unreadable']
        assert not existing
        assert not decoded


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('terminal', ['discarded', 'deleted'])
def test_projection_clears_only_the_terminal_pending_fields(strict, monkeypatch, terminal, enabled):
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'on' if enabled else 'off')
    rid = 'r'
    raw = source(rid, v3_pending_since=AT, claims=[claim('held', AT, 10)], **{terminal: True})
    strict.rows[path(rid)] = raw.copy()
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    store.commit_projection(UID, token, {rid: {**raw, '_v3_revision': 1}}, {}, [], [], firestore_client=strict)
    expected = {**raw, 'v3_pending': False, 'v3_pending_since': None} if enabled or terminal == 'deleted' else raw
    assert strict.rows[path(rid)] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('overflow', ['count', 'bytes'])
async def test_terminal_marker_clears_before_unlocked_index_overflow(strict, monkeypatch, overflow):
    raw = source('r', discarded=True, claims=[claim('preview', AT, 10)], v3_pending_since=AT)
    strict.rows[path('r')] = raw.copy()
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = leases.lease_ref(strict, UID, 'builder')
    strict.rows[('users', UID, 'conversation_v3_leases', 'builder')].update(unlocked_ids=['preview', 'second'])
    before = held.get().to_dict()
    preview = derived('preview', AT, 10, ['r'], v3_unlocked=True)
    second = derived('second', AT, 10, ['r'], v3_unlocked=True)
    if overflow == 'count':
        monkeypatch.setattr(store, 'DERIVED_LIMIT', 1)
    else:
        monkeypatch.setattr(store, 'DERIVED_BYTES', 1)
    prefix = f'/users/{UID}/'
    query = store._oldest_pending
    monkeypatch.setattr(
        store,
        '_oldest_pending',
        lambda coll, limit: query(
            (
                coll
                if isinstance(coll, MemoryQuery)
                else MemoryQuery({prefix + 'conversations/r': raw}, prefix + 'conversations')
            ),
            limit,
        ),
    )

    async def run_fixture(_, fn, *args, **kwargs):
        if fn is leases.renew:
            return None
        if fn is store.load:
            client = MemoryQuery(
                {
                    prefix + 'conversations/r': strict.rows[path('r')],
                    prefix + 'conversations/preview': preview,
                    prefix + 'conversations/second': second,
                    prefix + 'conversation_v3_leases/builder': before,
                }
            )
        else:
            client = strict
        return fn(*args, firestore_client=client, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        await service._load_live_batch(UID, token, None)
    assert strict.rows[path('r')] == {**raw, 'v3_pending': False, 'v3_pending_since': None}
    assert held.get().to_dict() == before


@pytest.mark.parametrize('moved', ['revision', 'status', 'lease'])
def test_terminal_cleanup_rechecks_the_recording_and_lease(strict, monkeypatch, moved):
    raw = source('r', discarded=True, v3_pending_since=AT)
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    current = {
        'revision': {**raw, '_test_revision': 2},
        'status': {**raw, 'discarded': False},
        'lease': raw,
    }[moved]
    strict.rows[path('r')] = current.copy()
    query = store._oldest_pending
    coll = '/users/synthetic/conversations'
    monkeypatch.setattr(store, '_oldest_pending', lambda _, limit: query(MemoryQuery({coll + '/r': raw}, coll), limit))
    if moved == 'lease':
        with pytest.raises(Conflict, match='lease_lost'):
            store.clear_terminal_pending(UID, 'stale-token', firestore_client=strict)
    else:
        store.clear_terminal_pending(UID, token, firestore_client=strict)
    assert strict.rows[path('r')] == current


@pytest.mark.parametrize('reason', ['v3_derived_budget', 'document_too_large'])
def test_legacy_park_gets_one_early_attempt(strict, monkeypatch, reason):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'off')
    assert store.record_blocked(UID, token, reason, firestore_client=strict)
    assert store.backoff_until(UID, firestore_client=strict)
    monkeypatch.delenv('CONVERSATIONS_V3_BOUNDED_PENDING')
    assert store.backoff_state(UID, firestore_client=strict) == (None, reason)
    assert store.record_blocked(UID, token, reason, on_open=True, firestore_client=strict)
    assert store.backoff_state(UID, firestore_client=strict) == (None, reason)
    assert store.record_blocked(UID, token, reason, firestore_client=strict)
    assert store.backoff_until(UID, firestore_client=strict)


@pytest.mark.parametrize('reason', ['v3_derived_budget', 'document_too_large'])
def test_early_attempt_is_spent_under_the_lease_before_work(strict, monkeypatch, reason):
    # A transient failure in the early attempt (no record_blocked) must not reopen the bypass.
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    monkeypatch.setenv('CONVERSATIONS_V3_BOUNDED_PENDING', 'off')
    assert store.record_blocked(UID, token, reason, firestore_client=strict)
    monkeypatch.delenv('CONVERSATIONS_V3_BOUNDED_PENDING')
    assert store.backoff_state(UID, firestore_client=strict) == (None, reason)
    store.mark_bounded_attempt(UID, 'other-token', firestore_client=strict)
    assert store.backoff_state(UID, firestore_client=strict) == (None, reason)
    store.mark_bounded_attempt(UID, token, firestore_client=strict)
    backoff, parked = store.backoff_state(UID, firestore_client=strict)
    assert backoff and parked == reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'parked,error,remembered,sizes',
    [
        ('document_too_large', None, 8, [1]),
        ('v3_derived_budget', 'v3_derived_budget', None, [8, 1]),
        (None, 'account_deletion', None, [32]),
        (None, None, 8, [8]),
        (None, None, 1, [1]),
    ],
)
async def test_bounded_loader_only_shrinks_budget_failures(monkeypatch, parked, error, remembered, sizes):
    attempted, renewals, marked = [], [], []

    async def run_fixture(_, fn, *args, **kwargs):
        if fn is leases.renew:
            renewals.append(args)
            return
        if fn is store.mark_bounded_attempt:
            marked.append(args)
            return
        if fn is store.clear_terminal_pending:
            return remembered
        attempted.append(kwargs.get('pending_limit', 32))
        if error and len(attempted) == 1:
            raise Conflict(error)
        return {}, {}, []

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    if error == 'account_deletion':
        with pytest.raises(Conflict, match=error):
            await service._load_live_batch('u', 'token', parked)
    else:
        assert await service._load_live_batch('u', 'token', parked) == ({}, {}, [], sizes[-1])
    assert attempted == sizes
    assert renewals == [('u', 'builder', 'token')] * (len(sizes) - 1)
    assert marked == ([('u', 'token')] if parked else [])


@pytest.mark.parametrize('terminal', ['discarded', 'deleted'])
def test_successor_check_ignores_undecoded_terminal_pointer(terminal):
    # A terminal row loaded undecoded can still carry an offloaded transcript pointer (a dict), not segments.
    pointer = {'uri': 'gs://bucket/transcript', 'revision': 3}
    row = {'id': 'r', 'started_at': AT, 'transcript_segments': pointer, terminal: True}
    store._mark_successor_pending(None, {'r': row})


def test_backfill_rederive_keeps_both_prior_windows_when_merge_would_strand_a_memory_link(strict, monkeypatch):
    first = derived('first', T0, 10, ['r'], backfilled=True)
    second_start = T0 + timedelta(seconds=10)
    linked = derived('linked', second_start, 10, ['r'], backfilled=True)
    claims = [claim('first', T0, 10), claim('linked', second_start, 10)]
    recording = {'id': 'r', 'recording': True, 'status': 'completed', 'claims': claims}
    strict.rows.update({path('first'): first, path('linked'): linked, path('r'): recording})
    token = leases.acquire(UID, store.BACKFILL_LEASE, firestore_client=strict)
    monkeypatch.setattr(memories, 'linked_conversation_ids', lambda uid, ids, **kw: {'linked'} & ids)
    merged = derived('merged', T0, 20, ['r'], backfilled=True)
    removed = set()

    with pytest.raises(Conflict, match='backfill_rederive_linked_claims'):
        store.commit_projection(
            UID,
            token,
            {'r': {**recording, '_v3_revision': 1}},
            {row['id']: {**row, '_v3_revision': 1} for row in (first, linked)},
            [merged],
            [],
            remove=('first', 'linked'),
            removed_ids=removed,
            key=store.BACKFILL_LEASE,
            firestore_client=strict,
        )

    assert strict.rows[path('first')] == first
    assert strict.rows[path('linked')] == linked
    assert strict.rows[path('r')]['claims'] == claims
    assert path('merged') not in strict.rows
    assert not removed


def test_multi_batch_replacement_of_claiming_windows_refuses_before_any_batch_commits(strict, monkeypatch):
    # The replacement spans several transactions and shares recording r with windows it removes:
    # an earlier batch must not commit before a later one finds the linked prior.
    first = derived('first', T0, 10, ['r'], backfilled=True)
    second_start = T0 + timedelta(seconds=10)
    linked = derived('linked', second_start, 10, ['r'], backfilled=True)
    claims = [claim('first', T0, 10), claim('linked', second_start, 10)]
    recording = {'id': 'r', 'recording': True, 'status': 'completed', 'claims': claims}
    strict.rows.update({path('first'): first, path('linked'): linked, path('r'): recording})
    token = leases.acquire(UID, store.BACKFILL_LEASE, firestore_client=strict)
    monkeypatch.setattr(memories, 'linked_conversation_ids', lambda uid, ids, **kw: {'linked'} & ids)
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 7)
    replacements = [derived(f'm{i}', T0 + timedelta(seconds=2 * i), 2, ['r'], backfilled=True) for i in range(8)]
    before = {key: dict(value) for key, value in strict.rows.items()}
    removed = set()

    with pytest.raises(Conflict, match='backfill_partition_budget'):
        store.commit_projection(
            UID,
            token,
            {'r': {**recording, '_v3_revision': 1}},
            {row['id']: {**row, '_v3_revision': 1} for row in (first, linked)},
            replacements,
            [],
            remove=('first', 'linked'),
            removed_ids=removed,
            key=store.BACKFILL_LEASE,
            firestore_client=strict,
        )

    assert all(path(row['id']) not in strict.rows for row in replacements)
    assert strict.rows[path('first')] == first and strict.rows[path('linked')] == linked
    assert strict.rows[path('r')]['claims'] == claims
    assert not removed
    assert {k: v for k, v in strict.rows.items() if k in before} == before


@pytest.mark.parametrize('overflow', ['count', 'bytes'])
@pytest.mark.parametrize('pending_limit', [32, 8, 1])
def test_unlocked_index_overflow_reproduces_at_every_pending_seed_size(monkeypatch, overflow, pending_limit):
    rows = {C + f'd{i}': derived(f'd{i}', AT, 10, [], v3_unlocked=True) for i in range(9)}
    rows['/users/u/conversation_v3_leases/builder'] = {'unlocked_ids': [f'd{i}' for i in range(9)]}
    if overflow == 'count':
        monkeypatch.setattr(store, 'DERIVED_LIMIT', 8)
    else:
        monkeypatch.setattr(store, 'DERIVED_BYTES', store._encoded_bytes(rows[C + 'd0']['transcript_segments']) * 8)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(rows), pending_limit=pending_limit)


@pytest.mark.parametrize('overflow', ['count', 'bytes'])
def test_paged_unlocked_load_closes_claims_and_rotates_past_an_unlocked_preview(strict, monkeypatch, overflow):
    lease_path = '/users/u/conversation_v3_leases/builder'
    rows = {lease_path: {'unlocked_ids': ['a', 'b', 'c']}}
    for index, cid in enumerate('abc'):
        start = AT + timedelta(hours=index * 3)
        rid = f'r{cid}'
        rows[C + cid] = derived(cid, start, 10, [rid], v3_unlocked=True)
        rows[C + rid] = source(
            rid,
            started_at=start,
            finished_at=start + timedelta(seconds=10),
            v3_pending=False,
            claims=[claim(cid, start, 10)],
        )
    # A claimant outside the source's time margin must still enter the closure.
    rows[C + 'd'] = derived('d', AT - timedelta(hours=3), 10, ['ra'])
    rows[C + 'ra']['claims'].append(claim('d', AT - timedelta(hours=3), 10))
    if overflow == 'count':
        monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)
    else:
        monkeypatch.setattr(store, 'DERIVED_BYTES', store._encoded_bytes(rows[C + 'a']['transcript_segments']) * 2)

    page = store.UnlockedPage()
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows), pending_limit=1, unlocked_page=page)
    assert set(recordings) == {'ra'}
    assert set(existing) == {'a', 'd'}
    assert page.remaining == {'b', 'c'}

    # The selected preview remains unlocked. The final transaction must preserve
    # even an omitted ID with no loaded source and advance past the selected ID.
    strict.rows.update({path(row['id']): row.copy() for key, row in rows.items() if key.startswith(C)})
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = leases.lease_ref(strict, UID, 'builder')
    strict.rows[held.path]['unlocked_ids'] = ['a', 'b', 'c']
    store.commit_projection(
        UID, token, recordings, existing, [existing['a']], [], unlocked_page=page, firestore_client=strict
    )
    state = held.get().to_dict()
    assert state['unlocked_ids'] == ['a', 'b', 'c']
    assert state['v3_unlocked_cursor'] == 'a'
    rows[lease_path] = state
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows), pending_limit=1, unlocked_page=page)
    assert set(recordings) == {'rb'}
    assert set(existing) == {'b'}
    assert page.remaining == {'a', 'c'}


@pytest.mark.asyncio
async def test_seed_lanes_that_overflow_together_each_advance_on_successive_passes(monkeypatch):
    lease_path = '/users/u/conversation_v3_leases/builder'
    late = AT + timedelta(hours=6)
    rows = {
        lease_path: {'unlocked_ids': ['u']},
        C + 'u': derived('u', late, 10, ['ru'], v3_unlocked=True),
        C
        + 'ru': source(
            'ru',
            started_at=late,
            finished_at=late + timedelta(seconds=10),
            v3_pending=False,
            claims=[claim('u', late, 10)],
        ),
        C + 'p1': derived('p1', AT, 5, ['rp']),
        C + 'p2': derived('p2', AT + timedelta(seconds=5), 5, ['rp']),
        C
        + 'rp': source(
            'rp',
            started_at=AT,
            finished_at=AT + timedelta(seconds=10),
            v3_pending_since=AT,
            claims=[claim('p1', AT, 5), claim('p2', AT + timedelta(seconds=5), 5)],
        ),
    }
    client = MemoryQuery(rows)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)  # Each lane's closure fits alone; together they overflow.

    async def run_fixture(_, fn, *args, **kwargs):
        if fn in (store.mark_bounded_attempt, store.clear_terminal_pending, leases.renew):
            return None
        return fn(*args, firestore_client=client, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    loaded = []
    for minute in (0, 1):  # Successive passes lead with alternate lanes.
        clock = AT.replace(minute=minute)
        monkeypatch.setattr(
            service, 'datetime', type('Clock', (datetime,), {'now': staticmethod(lambda tz=None: clock)})
        )
        page = store.UnlockedPage()
        recordings, existing, _, limit = await service._load_live_batch('u', 'token', None, page)
        loaded.append((set(recordings), set(existing), page.remaining, limit))
    assert loaded[0] == ({'rp'}, {'p1', 'p2'}, {'u'}, 1)  # The unvisited window stays owed to a later pass.
    assert loaded[1] == ({'ru'}, {'u'}, frozenset(), None)  # An unlocked-only pass leaves the remembered page alone.


@pytest.mark.asyncio
@pytest.mark.parametrize('overflowing', ['pending', 'unlocked'])
@pytest.mark.parametrize('minute', [0, 1])
async def test_an_empty_seed_lane_does_not_clear_the_other_lanes_overflow(monkeypatch, overflowing, minute):
    rp_claims = [claim(f'p{i}', AT + timedelta(seconds=i), 1) for i in range(3)]
    rows = {C + f'p{i}': derived(f'p{i}', AT + timedelta(seconds=i), 1, ['rp']) for i in range(3)}
    if overflowing == 'pending':
        rows[C + 'rp'] = source(
            'rp', started_at=AT, finished_at=AT + timedelta(seconds=3), v3_pending_since=AT, claims=rp_claims
        )
    else:
        rows[C + 'p0']['v3_unlocked'] = True
        rows['/users/u/conversation_v3_leases/builder'] = {'unlocked_ids': ['p0']}
        rows[C + 'rp'] = source(
            'rp', started_at=AT, finished_at=AT + timedelta(seconds=3), v3_pending=False, claims=rp_claims
        )
    client = MemoryQuery(rows)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)

    async def run_fixture(_, fn, *args, **kwargs):
        if fn in (store.mark_bounded_attempt, store.clear_terminal_pending, leases.renew):
            return None
        return fn(*args, firestore_client=client, **kwargs)

    clock = AT.replace(minute=minute)
    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    monkeypatch.setattr(service, 'datetime', type('Clock', (datetime,), {'now': staticmethod(lambda tz=None: clock)}))
    with pytest.raises(Conflict, match='v3_derived_budget'):  # Parks instead of an empty successful pass.
        await service._load_live_batch('u', 'token', None, store.UnlockedPage())


@pytest.mark.asyncio
async def test_unvisited_unlocked_wake_is_independent_of_pending_seeds(monkeypatch):
    calls = []

    async def run_fixture(_, fn, uid, *, at, wake_key):
        assert fn is service.enqueue and wake_key == 'pass-token'
        calls.append((uid, at))

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    await service._wake_unvisited_unlocked('u', store.UnlockedPage(), 'pass-token')
    assert not calls
    await service._wake_unvisited_unlocked('u', store.UnlockedPage(frozenset({'later'})), 'pass-token')
    assert len(calls) == 1
    assert calls[0][0] == 'u' and calls[0][1] > AT


@pytest.mark.asyncio
@pytest.mark.parametrize('outlasts_wake', [False, True])
async def test_reconcile_wakes_unvisited_unlocked_windows_once_per_pass(builder, monkeypatch, outlasts_wake):
    _window, existing, recordings = _locked_pair(datetime.now(timezone.utc) - timedelta(hours=2))
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    recordings['r'].update(recording=True, status='completed', v3_pending=True)
    pages, wakes = [], []
    omitted = {'fingerprint': 'later-outline', 'entries': [], 'preview_key': '0:later'}

    def load(*a, unlocked_page=None, **kw):
        unlocked_page.remaining, unlocked_page.cursor = frozenset({'later'}), 'early'
        pages.append(unlocked_page)
        return recordings, existing, [omitted]

    def commit(*a, unlocked_page=None, **kw):
        assert unlocked_page is pages[0]  # The page's cursor reaches the lease write.
        assert omitted in a[5]  # The unvisited window's paid outline survives the cache rewrite.
        if outlasts_wake:  # This pass's own wake ran (busy) under the lease.
            late = datetime.now(timezone.utc) + timedelta(minutes=2)
            monkeypatch.setattr(
                service, 'datetime', type('Clock', (datetime,), {'now': staticmethod(lambda tz=None: late)})
            )

    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, '_commit', commit)
    names = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    monkeypatch.setattr(triggers, 'enqueue_named_task', lambda queue, url, task_id, *a, **kw: names.append(task_id))

    def wake(uid, **kw):
        if kw.get('wake_key'):
            wakes.append(kw['at'])
            triggers.enqueue(uid, **kw)

    monkeypatch.setattr(service, 'enqueue', wake)
    started = datetime.now(timezone.utc)
    assert await service.reconcile('synthetic') == 'committed'
    assert len(pages) == 1 and wakes[0] - started >= timedelta(seconds=59)
    # One wake per pass, re-armed after the lease only when this pass outlasted it, under a fresh task name.
    assert len(wakes) == len(set(names)) == (2 if outlasts_wake else 1)
    if outlasts_wake:
        assert wakes[1] > wakes[0] + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_parked_paged_pass_wakes_its_unvisited_windows_after_the_backoff(builder, monkeypatch):
    _window, existing, recordings = _locked_pair(datetime.now(timezone.utc) - timedelta(hours=2))
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    recordings['r'].update(recording=True, status='completed', v3_pending=True)
    until = datetime.now(timezone.utc) + timedelta(minutes=5)
    parked, wakes = [], []

    def load(*a, unlocked_page=None, **kw):
        unlocked_page.remaining, unlocked_page.cursor = frozenset({'later'}), 'early'
        return recordings, existing, []

    def commit(*a, **kw):
        raise Conflict('v3_derived_budget')

    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, '_commit', commit)
    monkeypatch.setattr(store, 'record_blocked', lambda *a, **kw: parked.append(a))
    monkeypatch.setattr(store, 'backoff_state', lambda *a: (until if parked else None, None))
    monkeypatch.setattr(service, '_drain_blocked', AsyncMock())
    monkeypatch.setattr(service, 'enqueue', lambda uid, **kw: kw.get('wake_key') and wakes.append(kw['at']))
    assert await service.reconcile('synthetic') == 'blocked'
    # The pre-commit continuation lands inside the backoff; a second wake follows its end.
    assert len(wakes) == 2 and wakes[0] < until < wakes[1] <= until + timedelta(seconds=5)


def test_unlocked_continuation_is_not_swallowed_by_an_earlier_same_minute_wake(monkeypatch):
    names = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    monkeypatch.setattr(triggers, 'enqueue_named_task', lambda queue, url, task_id, *a, **kw: names.append(task_id))
    minute = AT + timedelta(minutes=1)
    triggers.enqueue('u', at=minute)  # An earlier wake: it can run busy under this pass's lease and be consumed.
    triggers.enqueue('u', at=minute + timedelta(seconds=20), wake_key='pass-token')
    triggers.enqueue('u', at=minute + timedelta(seconds=40), wake_key='pass-token')  # Same pass stays idempotent.
    assert names[0] != names[1] == names[2]


def test_previous_bounded_pending_park_gets_one_unlocked_paging_attempt(strict):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    held = leases.lease_ref(strict, UID, 'builder')
    assert store.record_blocked(UID, token, 'v3_derived_budget', firestore_client=strict)
    strict.rows[held.path]['unlocked_ids'] = ['owed']
    assert store.backoff_state(UID, firestore_client=strict) == (None, 'v3_derived_budget')
    store.mark_bounded_attempt(UID, token, firestore_client=strict)
    backoff, reason = store.backoff_state(UID, firestore_client=strict)
    assert backoff is not None and reason == 'v3_derived_budget'


def test_park_with_indexed_unlocked_windows_spends_the_paging_attempt(strict):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    strict.rows[leases.lease_ref(strict, UID, 'builder').path]['unlocked_ids'] = ['owed']
    # A builder pass that already paged the unlocked windows and still parked gets no early retry.
    assert store.record_blocked(UID, token, 'v3_derived_budget', firestore_client=strict)
    backoff, reason = store.backoff_state(UID, firestore_client=strict)
    assert backoff is not None and reason == 'v3_derived_budget'


# Locked-claimant allowance (2026-11-26): 21 owners were parked because a single seed's closure was 1,026-1,994
# rows. One long recording owned up to ~1,000 locked 8-second windows left by the old moving cap cut.


CHARGE = store._charge_locked_attempt
REAL_COMMIT = service._commit
REAL_BACKOFF_STATE = store.backoff_state
REAL_LOAD = store.load
REAL_PLAN = service._plan_projection
REAL_MARK_BOUNDED_ATTEMPT = store.mark_bounded_attempt


def allowance(monkeypatch, rows, nbytes=1 << 30, owners='*', counted=True):
    """List the owner and stand in for the attempt charge (its own tests use a transactional client)."""
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', owners)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', rows)
    monkeypatch.setattr(store, 'LOCKED_DERIVED_BYTES', nbytes)
    attempts = []
    monkeypatch.setattr(store, '_charge_locked_attempt', lambda client, uid, token: attempts.append(uid) or counted)
    return attempts


def test_locked_fragments_past_the_derived_limit_load_within_the_allowance(monkeypatch):
    allowance(monkeypatch, 20)
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(fragmented(30)))
    assert set(recordings) == {'r'} and len(existing) == 30


def test_locked_fragments_found_by_time_load_within_the_allowance(monkeypatch):
    allowance(monkeypatch, 20)
    rows = fragmented(30)
    rows[C + 'r']['claims'] = []  # only the time query finds them
    _, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert len(existing) == 30


def test_the_allowance_has_a_total_bound_checked_before_reading(monkeypatch):
    allowance(monkeypatch, 20)
    reads = []
    real = MemoryQuery.get_all
    monkeypatch.setattr(MemoryQuery, 'get_all', lambda self, refs, **kw: reads.append(len(refs)) or real(self, refs))
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(31)))
    assert reads == []


@pytest.mark.parametrize('field', ['v3_unlocked', 'in_progress', 'transferred'])
def test_rewritable_rows_keep_the_derived_limit(monkeypatch, field):
    allowance(monkeypatch, 20)
    rows = fragmented(11)
    for i in range(11):
        row = rows[C + f'd{i}']
        if field == 'v3_unlocked':
            row['v3_unlocked'] = True
        elif field == 'in_progress':
            row['status'] = 'in_progress'
        else:
            row.update(v3_refined=True, v3_claims_transferred_to='elsewhere')
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))


def test_rewritable_rows_keep_the_byte_bound_and_locked_rows_use_the_byte_allowance(monkeypatch):
    rows = fragmented(10)
    per_row = store._encoded_bytes(rows[C + 'd0']['transcript_segments'])
    allowance(monkeypatch, 20, nbytes=per_row * 6)
    monkeypatch.setattr(store, 'DERIVED_BYTES', per_row * 4)
    _, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))  # 10 locked rows: 4 + 6
    assert len(existing) == 10
    rows = fragmented(11)
    with pytest.raises(Conflict, match='v3_derived_budget'):  # total bytes over 4 + 6
        store.load('u', firestore_client=MemoryQuery(rows))
    rows = fragmented(5)
    for i in range(5):
        rows[C + f'd{i}']['v3_unlocked'] = True
    with pytest.raises(Conflict, match='v3_derived_budget'):  # 5 rewritable rows over 4
        store.load('u', firestore_client=MemoryQuery(rows))


SHAPES = [
    dict(
        status=status,
        unlocked=unlocked,
        started=started,
        finished=finished,
        refined=refined,
        moved=moved,
        deleted=deleted,
    )
    for status in ('completed', 'processing', 'in_progress')
    for unlocked in (False, True)
    for started in (True, False)
    for finished in (True, False)
    for refined in (False, True)
    for moved in (False, True)
    for deleted in (False, True)
]


def shaped(index, shape):
    start = AT + timedelta(seconds=30 * index)
    row = {
        'id': f'm{index}',
        'v3_derived': True,
        'status': shape['status'],
        'v3_recording_ids': ['r'],
        'transcript_segments': [{'id': f's{index}', 'text': f'line {index}', 'start': 0.0, 'end': 10.0}],
    }
    row.update({'started_at': start} if shape['started'] else {})
    row.update({'finished_at': start + timedelta(seconds=10)} if shape['finished'] else {})
    row.update({'v3_unlocked': True} if shape['unlocked'] else {})
    row.update({'v3_refined': True} if shape['refined'] else {})
    row.update({'v3_claims_transferred_to': 'elsewhere'} if shape['moved'] else {})
    row.update({'deleted': True} if shape['deleted'] else {})
    return row


def test_locked_claimant_is_the_planners_protected_predicate():
    for index, shape in enumerate(SHAPES):
        row = shaped(index, shape)
        expected = (
            not planner.is_unlocked(row)
            and bool(row.get('started_at'))
            and bool(row.get('finished_at'))
            and not (row.get('v3_refined') and row.get('v3_claims_transferred_to'))
        )
        assert store.locked_claimant(row) is expected, shape


def test_every_row_load_counts_as_locked_is_one_preserve_finished_windows_keeps_fixed():
    # One recording line per row, held exactly by that row. preserve_finished_windows retains a line to its
    # owner only when the owner is protected, so the retained ids are its protected set over these shapes.
    existing, lines, claims = {}, [], []
    for index, shape in enumerate(SHAPES):
        row = shaped(index, shape)
        existing[row['id']] = row
        start = AT + timedelta(seconds=30 * index)
        segment = {'id': f's{index}', 'text': f'line {index}', 'start': 30.0 * index, 'end': 30.0 * index + 10}
        lines.append(
            {
                'conversation_id': 'r',
                'start': start,
                'end': start + timedelta(seconds=10),
                'segment': segment,
                'text': segment['text'],
            }
        )
        claims.append({'conversation_id': row['id'], 'start': start, 'end': start + timedelta(seconds=10)})
    recordings = {'r': {'id': 'r', 'recording': True, 'started_at': AT, 'claims': claims}}
    window = {'lines': lines, 'finished': True, 'manual_end': False, 'kind': 'conversation', 'title': ''}
    kept = planner.preserve_finished_windows([window], existing, recordings)
    protected = {w['existing_id'] for w in kept if w.get('existing_id')}
    counted = {cid for cid, row in existing.items() if store.locked_claimant(row)}
    # Rows without both timestamps hold no line, so they can be neither.
    assert counted == protected
    assert any(existing[cid].get('deleted') for cid in counted)  # a locked tombstone is protected and counted
    assert not any(existing[cid].get('v3_unlocked') for cid in counted)


TAG = __import__('hashlib').sha256(b'u').hexdigest()[:12]


@pytest.mark.parametrize(
    'owners, allowed',
    [
        ('', False),
        ('   ', False),
        ('0123456789ab', False),
        (TAG, True),
        (f'0123456789ab, {TAG.upper()}', True),
        ('*', True),
    ],
)
def test_the_allowance_applies_only_to_listed_owners(monkeypatch, owners, allowed):
    allowance(monkeypatch, 20, owners=owners)
    if allowed:
        assert len(store.load('u', firestore_client=MemoryQuery(fragmented(30)))[1]) == 30
    else:
        with pytest.raises(Conflict, match='v3_derived_budget'):
            store.load('u', firestore_client=MemoryQuery(fragmented(11)))
        assert len(store.load('u', firestore_client=MemoryQuery(fragmented(10)))[1]) == 10


def test_the_allowlist_is_off_by_default(monkeypatch):
    # Positive sizes, so only the (absent) allowlist can switch the allowance off.
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    monkeypatch.setattr(store, 'LOCKED_DERIVED_BYTES', 1 << 20)
    monkeypatch.delenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', raising=False)
    assert store.locked_closure_owner('u') is False
    assert store._locked_allowance('u') == (0, 0)
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    assert store._locked_allowance('u') == (20, 1 << 20)


@pytest.mark.parametrize('raw, expected', [('0', 0), ('', 2048), ('junk', 2048), ('-3', 2048), ('4096', 4096)])
def test_allowance_env_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv('X_ALLOWANCE', raw)
    assert store._env_allowance('X_ALLOWANCE', 2048) == expected


@pytest.mark.parametrize(
    'switch', ['LOCKED_DERIVED_ALLOWANCE', 'LOCKED_DERIVED_BYTES', 'LOCKED_MAX_BATCHES', 'LOCKED_DAILY_PASSES']
)
def test_kill_switch_restores_the_origin_bound(monkeypatch, switch):
    attempts = allowance(monkeypatch, 20)
    monkeypatch.setattr(store, switch, 0)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(11)))
    store.load('u', firestore_client=MemoryQuery(fragmented(10)))
    assert attempts == []  # a switched-off allowance is never an attempt


@pytest.mark.parametrize(
    'name',
    [
        'CONVERSATIONS_V3_LOCKED_DERIVED_ALLOWANCE',
        'CONVERSATIONS_V3_LOCKED_DERIVED_BYTES',
        'CONVERSATIONS_V3_LOCKED_MAX_BATCHES',
        'CONVERSATIONS_V3_LOCKED_DAILY_PASSES',
    ],
)
def test_every_documented_numeric_kill_switch_turns_the_allowance_off_at_zero(name):
    # Parsed at import, so read in a fresh interpreter: 0 must switch off, never fall back to the default.
    import os
    import subprocess
    import sys

    env = {**os.environ, 'CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS': '*', name: '0'}
    probe = 'from database import conversations_v3 as s; print(s._locked_allowance("u"))'
    out = subprocess.run([sys.executable, '-c', probe], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == '(0, 0)'
    del env[name]
    out = subprocess.run([sys.executable, '-c', probe], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == '(2048, 8388608)'


def spanning(n, sources):
    """n locked rows that each span every source's interval query, and sources far enough apart (two hours)
    that their intervals stay separate: every interval query returns all n rows again."""
    rows = {C + f'w{i}': derived(f'w{i}', AT - timedelta(hours=1), 3600 * (2 * sources + 1), ['r0']) for i in range(n)}
    for k in range(sources):
        start = AT + timedelta(hours=2 * k)
        rows[C + f'r{k}'] = source(
            f'r{k}', started_at=start, finished_at=start + timedelta(seconds=10), v3_pending_since=start
        )
    return rows


def counted_streams(monkeypatch):
    """Count every document the time queries hand load(), repeats included."""
    streamed = []
    real = MemoryQuery.stream

    def stream(self):
        timed = any(field == 'finished_at' for field, _, _ in self.filters)
        for doc in real(self):
            if timed:
                streamed.append(doc.id)
            yield doc

    monkeypatch.setattr(MemoryQuery, 'stream', stream)
    return streamed


def test_one_fetched_document_budget_spans_every_interval_query_and_counts_repeats(monkeypatch):
    # Row bound 10 + 20 = 30, so the budget is 2 x 30 = 60 fetched derived documents for the whole load.
    allowance(monkeypatch, 20)
    streamed = counted_streams(monkeypatch)
    _, existing, _ = store.load('u', firestore_client=MemoryQuery(spanning(25, 2)))  # 2 x 25 = 50 fetched
    assert len(existing) == 25 and len(streamed) == 50
    streamed.clear()
    # Three intervals each return the same 25 rows: 25 distinct rows, inside every per-query cap of 31 and the
    # row bound of 30, but 75 fetches. The budget stops the third query at its 61st document.
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(spanning(25, 3)))
    assert len(streamed) == 61  # the budget of 60, plus the one sentinel document that detects the overflow
    assert len(set(streamed)) == 25


def test_each_interval_query_asks_only_for_the_budget_left(monkeypatch):
    allowance(monkeypatch, 20)
    client = MemoryQuery(spanning(25, 2))
    store.load('u', firestore_client=client)
    caps = [cap for filters, cap, _ in client.calls if any(f == 'finished_at' for f, _, _ in filters)]
    assert caps == [31, 31]  # min(row bound 30, budget left 60 then 35) + 1
    client = MemoryQuery(spanning(25, 3))
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=client)
    caps = [cap for filters, cap, _ in client.calls if any(f == 'finished_at' for f, _, _ in filters)]
    assert caps == [31, 31, 11]  # 60 - 50 = 10 left, + 1 to see the overflow


def test_the_origin_bound_keeps_its_per_query_caps(monkeypatch):
    # Unlisted owners keep today's load: no shared budget, so three intervals of the same 8 rows still load.
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)
    streamed = counted_streams(monkeypatch)
    _, existing, _ = store.load('u', firestore_client=MemoryQuery(spanning(8, 3)))
    assert len(existing) == 8 and len(streamed) == 24


def test_the_allowance_never_admits_more_rows_than_the_batch_cap_can_commit(monkeypatch):
    # Two batches of 12 writes: at most 2 x (12 - 1) = 22 rows with no sources, 2 x (12 - 1 - 1) = 20 with one.
    allowance(monkeypatch, 20)
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 12)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 2)
    assert len(store.load('u', firestore_client=MemoryQuery(fragmented(20)))[1]) == 20
    with pytest.raises(Conflict, match='v3_derived_budget'):  # 21 rows and one source: past what 2 batches hold
        store.load('u', firestore_client=MemoryQuery(fragmented(21)))
    reads = []
    real = MemoryQuery.get_all
    monkeypatch.setattr(MemoryQuery, 'get_all', lambda self, refs, **kw: reads.append(len(refs)) or real(self, refs))
    with pytest.raises(Conflict, match='v3_derived_budget'):  # 25 rows, inside the allowance's 30 but over 22
        store.load('u', firestore_client=MemoryQuery(fragmented(25)))
    assert reads == []  # the extra rows are never read
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 6)  # the same closures load once the cap can commit them
    assert len(store.load('u', firestore_client=MemoryQuery(fragmented(25)))[1]) == 25


def test_the_commit_clamp_never_lowers_the_origin_bound(monkeypatch):
    # One batch of 12 writes holds fewer rows than DERIVED_LIMIT: the closure keeps today's bound, not a smaller one.
    allowance(monkeypatch, 20)
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 12)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 1)
    assert len(store.load('u', firestore_client=MemoryQuery(fragmented(10)))[1]) == 10
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(11)))


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed, sizes', [(20, [8]), (0, [8, 1])])
async def test_a_parked_owner_with_a_fragmented_recording_loads_within_the_allowance_instead_of_parking(
    monkeypatch, allowed, sizes
):
    allowance(monkeypatch, allowed)
    client, attempted = MemoryQuery(fragmented(30)), []

    async def run_fixture(_, fn, *args, **kwargs):
        if fn in (leases.renew, store.mark_bounded_attempt, store.clear_terminal_pending):
            return None
        attempted.append(kwargs.get('pending_limit', 32))
        return fn(*args, **kwargs, firestore_client=client)

    monkeypatch.setattr(service, 'run_blocking', run_fixture)
    if allowed:
        recordings, existing, _, size = await service._load_live_batch('u', 'token', 'v3_derived_budget')
        assert set(recordings) == {'r'} and len(existing) == 30 and size == 8
    else:
        with pytest.raises(Conflict, match='v3_derived_budget'):
            await service._load_live_batch('u', 'token', 'v3_derived_budget')
    assert attempted == sizes


def heavy_commit(strict, monkeypatch, *, listed, past_bound, cap, key='builder', renew=None, day_lease=None):
    """Eight planned rows in three batches (BATCH_MAX_WRITES 5), and a closure past the origin bound by rows,
    by bytes, or not at all. ``renew`` replaces the renewal's outcome; ``day_lease`` seeds the lease counters."""
    strict.rows[path('r')] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    for i in range(3):
        strict.rows[path(f'l{i}')] = derived(f'l{i}', T0, 10, ['r'])
    token = leases.acquire(UID, key, firestore_client=strict)
    if day_lease:
        strict.rows[('users', UID, 'conversation_v3_leases', key)].update(day_lease)
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 5)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2 if past_bound == 'rows' else 10)
    if past_bound == 'bytes':
        monkeypatch.setattr(store, 'DERIVED_BYTES', 1)  # three rows under DERIVED_LIMIT, their speech over the bytes
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', cap)
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*' if listed else '')
    events = []
    real_renew = leases.renew

    def renewal(uid, lease_key, *a, **kw):
        events.append(('renew', lease_key))
        if renew is not None:
            raise renew
        return real_renew(uid, lease_key, *a, **kw)

    monkeypatch.setattr(leases, 'renew', renewal)
    original = store.firestore.transactional

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            if body.__name__ == 'commit':
                events.append(len(args[0]))
            return wrapped(tx, *args)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    rows = [
        {'id': f'c{i}', 'status': 'processing', 'started_at': T0, 'finished_at': T0, 'v3_recording_ids': ['r']}
        for i in range(8)
    ]
    existing = {f'l{i}': {**strict.rows[path(f'l{i}')], '_v3_revision': 1} for i in range(3)}
    store.commit_projection(
        UID,
        token,
        {'r': {**strict.rows[path('r')], '_v3_revision': 1}},
        existing,
        rows,
        [],
        key=key,
        firestore_client=strict,
    )
    return events


def written(strict):
    return sorted(p[3] for p in strict.rows if p[2] == 'conversations' and p[3].startswith('c'))


R3 = [3, ('renew', 'builder'), 3, ('renew', 'builder'), 2]


def test_the_lease_is_renewed_before_every_later_batch(strict, monkeypatch):
    assert heavy_commit(strict, monkeypatch, listed=False, past_bound=False, cap=6) == R3


def test_a_derive_commit_renews_its_backfill_lease_before_every_later_batch(strict, monkeypatch):
    events = heavy_commit(strict, monkeypatch, listed=False, past_bound=False, cap=6, key=store.BACKFILL_LEASE)
    assert events == [3, ('renew', store.BACKFILL_LEASE), 3, ('renew', store.BACKFILL_LEASE), 2]


def test_the_renewal_kill_switch_restores_one_renewal_before_the_commit(strict, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_COMMIT_LEASE_RENEWAL', 'off')
    assert heavy_commit(strict, monkeypatch, listed=False, past_bound=False, cap=6) == [3, 3, 2]


@pytest.mark.parametrize(
    'error, caller_sees',
    [
        (Conflict('lease_lost'), Conflict),  # reconcile answers 'raced' and wakes the owner next minute
        (FirestoreContentionExhausted('renewal contention'), FirestoreContentionExhausted),  # the 409 retry
    ],
)
def test_a_failed_renewal_stops_after_the_committed_prefix_and_keeps_pending_owed(
    strict, monkeypatch, error, caller_sees
):
    with pytest.raises(caller_sees) as raised:
        heavy_commit(strict, monkeypatch, listed=False, past_bound=False, cap=6, renew=error)
    assert raised.value is error
    assert written(strict) == ['c0', 'c1', 'c2']  # the first batch only
    assert strict.rows[path('r')]['v3_pending'] is True  # cleared only by the final batch


@pytest.mark.parametrize('bound', ['rows', 'bytes'])
def test_a_locked_closure_needing_more_batches_than_the_cap_parks_before_any_write(strict, monkeypatch, bound):
    with pytest.raises(Conflict, match='v3_derived_budget'):
        heavy_commit(strict, monkeypatch, listed=True, past_bound=bound, cap=2)
    assert written(strict) == []
    assert strict.rows[path('r')]['v3_pending'] is True


@pytest.mark.parametrize('listed, past_bound', [(False, 'rows'), (False, 'bytes'), (True, False)])
def test_the_batch_cap_applies_only_to_a_closure_that_used_the_allowance(strict, monkeypatch, listed, past_bound):
    assert heavy_commit(strict, monkeypatch, listed=listed, past_bound=past_bound, cap=2) == R3


def lease_doc(strict):
    return strict.rows[('users', UID, 'conversation_v3_leases', 'builder')]


TODAY = lambda: datetime.now(timezone.utc).date().isoformat()  # noqa: E731


def builder_lease(strict, day_lease=None):
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    if day_lease:
        lease_doc(strict).update(day_lease)
    return token


@pytest.mark.parametrize(
    'seeded, expected',
    [
        (None, 1),
        ({'v3_locked_day': 'today', 'v3_locked_passes': 4}, 5),
        ({'v3_locked_day': '2026-01-01', 'v3_locked_passes': 9}, 1),
    ],
)
def test_an_allowance_attempt_is_charged_to_the_owners_day(strict, seeded, expected):
    if seeded and seeded['v3_locked_day'] == 'today':
        seeded = {**seeded, 'v3_locked_day': TODAY()}
    token = builder_lease(strict, seeded)
    assert store._charge_locked_attempt(strict, UID, token) is True
    assert (lease_doc(strict)['v3_locked_day'], lease_doc(strict)['v3_locked_passes']) == (TODAY(), expected)


@pytest.mark.parametrize('used, charged', [(19, True), (20, False)])
def test_the_day_holds_twenty_attempts_checked_in_the_charge_transaction(strict, used, charged):
    # The default budget; a concurrent pass that spent the last attempt after this one was admitted is refused here.
    assert store.LOCKED_DAILY_PASSES == 20
    token = builder_lease(strict, {'v3_locked_day': TODAY(), 'v3_locked_passes': used})
    assert store._charge_locked_attempt(strict, UID, token) is charged
    assert lease_doc(strict)['v3_locked_passes'] == used + charged


def test_an_attempt_is_charged_only_under_a_held_builder_lease(strict):
    token = builder_lease(strict)
    lease_doc(strict)['until'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert store._charge_locked_attempt(strict, UID, token) is False
    assert 'v3_locked_passes' not in lease_doc(strict)


@pytest.mark.parametrize('caller', ['stale', None])
def test_only_the_callers_own_live_lease_is_charged(strict, caller):
    # Panel F3 (review-20261127t015947-1583): another pass's live lease must not pay for, or admit, a stale load.
    stale = builder_lease(strict)
    leases.release(UID, 'builder', stale, firestore_client=strict)
    builder_lease(strict)  # a newer pass holds the lease now
    assert store._charge_locked_attempt(strict, UID, stale if caller else None) is False
    assert 'v3_locked_passes' not in lease_doc(strict)


def test_load_charges_with_the_callers_lease_token(monkeypatch):
    allowance(monkeypatch, 20)
    tokens = []
    monkeypatch.setattr(store, '_charge_locked_attempt', lambda client, uid, token: tokens.append(token) or True)
    store.load('u', lease_token='pass-token', firestore_client=MemoryQuery(fragmented(30)))
    store.load('u', firestore_client=MemoryQuery(fragmented(10)))
    assert tokens == ['pass-token', None]  # no token: the real charge refuses it, so today's bound


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('lease contention'), RuntimeError('unavailable')])
def test_an_unwritable_charge_fails_closed_to_the_origin_bound(strict, monkeypatch, error):
    token = builder_lease(strict)
    fallbacks = []

    def fail(*a, **kw):
        raise error

    monkeypatch.setattr(store, 'run_preloaded_transaction_with_contention_retry', fail)
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: fallbacks.append(kw))
    assert store._charge_locked_attempt(strict, UID, token) is False
    assert fallbacks == [
        {
            'component': 'conversations_v3',
            'from_mode': 'locked_closure_allowance',
            'to_mode': 'origin_bound',
            'reason': 'unavailable',
            'outcome': 'degraded',
            'log': store.logger,
        }
    ]
    assert UID not in repr(fallbacks)


def test_a_failed_charge_records_the_fallback_and_loads_with_the_original_bound(monkeypatch):
    # Codex P1 (r4714766976): the real charge, failing in its transaction, on a listed owner's load.
    allowance(monkeypatch, 20)
    monkeypatch.setattr(store, '_charge_locked_attempt', CHARGE)
    fallbacks = []
    monkeypatch.setattr(store, 'record_fallback', lambda **kw: fallbacks.append(kw))

    def fail(*a, **kw):
        raise FirestoreContentionExhausted('lease contention')

    monkeypatch.setattr(store, 'run_preloaded_transaction_with_contention_retry', fail)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(30)))  # past the origin bound: parks as today
    assert len(store.load('u', firestore_client=MemoryQuery(fragmented(10)))[1]) == 10  # within it: loads as today
    assert [(f['to_mode'], f['outcome']) for f in fallbacks] == [('origin_bound', 'degraded')] * 2
    assert all("'u'" not in repr(f) for f in fallbacks)


@pytest.mark.parametrize('rows', [30, 10])
def test_every_listed_builder_load_is_charged_before_it_reads(monkeypatch, rows):
    # Charged whether the closure then uses the allowance (30) or fits the origin bound (10, the smaller page after
    # a capped attempt), and whatever the pass does next: commit, cap retry, interrupted prefix or park.
    attempts = allowance(monkeypatch, 20)
    reads = []
    real = MemoryQuery.stream
    monkeypatch.setattr(MemoryQuery, 'stream', lambda self: reads.append(list(attempts)) or real(self))
    store.load('u', firestore_client=MemoryQuery(fragmented(rows)))
    assert attempts == ['u'] and reads and reads[0] == ['u']  # charged before the first query


def test_an_unlisted_owner_is_never_charged(monkeypatch):
    attempts = allowance(monkeypatch, 20, owners='')
    store.load('u', firestore_client=MemoryQuery(fragmented(10)))
    assert attempts == []


def test_an_uncharged_attempt_gets_the_origin_bound(monkeypatch):
    # The day is spent, the lease is not held, or the charge could not be written.
    attempts = allowance(monkeypatch, 20, counted=False)
    with pytest.raises(Conflict, match='v3_derived_budget'):
        store.load('u', firestore_client=MemoryQuery(fragmented(30)))
    assert len(store.load('u', firestore_client=MemoryQuery(fragmented(10)))[1]) == 10
    assert attempts == ['u', 'u']


def test_a_commit_charges_nothing(strict, monkeypatch):
    heavy_commit(strict, monkeypatch, listed=True, past_bound='rows', cap=6)
    assert 'v3_locked_passes' not in lease_doc(strict)


# ---- builder passes only: derive and re-derive keep today's bound (Home v3 lead ruling, 2026-11-27) ----------
# The derive and live re-derive loaders are pinned in test_conversations_v3_backfill.py and
# test_conversations_v3_live_rederive.py.


def test_the_allowance_is_for_builder_passes_only(monkeypatch):
    allowance(monkeypatch, 20)
    assert store._locked_allowance('u') == (20, 1 << 30)
    assert store._locked_allowance('u', key=store.BACKFILL_LEASE) == (0, 0)
    assert store._past_origin_bound('u', {f'd{i}': {} for i in range(11)}) is True
    assert store._past_origin_bound('u', {f'd{i}': {} for i in range(11)}, key=store.BACKFILL_LEASE) is False


def test_a_listed_owners_derive_commit_is_never_capped_or_counted(strict, monkeypatch):
    # Past the origin bound and over the cap: a builder commit would park (above); a derive commit is not an
    # allowance pass, so it commits as today and adds nothing to the owner's day.
    events = heavy_commit(strict, monkeypatch, listed=True, past_bound='rows', cap=2, key=store.BACKFILL_LEASE)
    assert events == [3, ('renew', store.BACKFILL_LEASE), 3, ('renew', store.BACKFILL_LEASE), 2]
    lease = strict.rows[('users', UID, 'conversation_v3_leases', store.BACKFILL_LEASE)]
    assert 'v3_locked_passes' not in lease


def test_the_secret_payloads_admit_exactly_their_tags(monkeypatch):
    # The list is a Secret Manager version (this repo is public): its first version is `none`, and a version
    # written from a file may end in a newline.
    import hashlib

    tag = hashlib.sha256(b'u').hexdigest()[:12]
    for payload, admitted in [('none', False), ('none\n', False), (f'{tag}\n', True), (f'none,{tag.upper()}', True)]:
        monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', payload)
        assert store.locked_closure_owner('u') is admitted, payload


# ---- the commit-time batch cap goes through the seed ladder (Codex P2 on #26443) ------------------------------


def batch_cap_pass(builder, monkeypatch, *, fits_at, parked=None, pending=32, unlocked=0):
    """A builder pass whose commit hits the locked-closure batch cap when it read more than ``fits_at`` seeds.

    ``pending`` recordings and ``unlocked`` indexed windows are owed, so a page reads min(limit, owed) of each.
    ``loads`` records each load's (pending, unlocked) seeds; ``commits`` the commit's remembered pending limit."""
    committed, _ = builder
    loads, commits, parks = [], [], []

    def load(uid, *, pending_limit=32, unlocked_limit=None, unlocked_page=None, **kw):
        seeds = (
            min(pending_limit, pending),
            min(min(8, pending_limit) if unlocked_limit is None else unlocked_limit, unlocked),
        )
        loads.append(seeds)
        if unlocked_page is not None:
            unlocked_page.seeds = seeds
        return {'r': source()}, {}, []

    def commit(*a, bounded_pending_limit=None, **kw):
        commits.append(bounded_pending_limit)
        if fits_at is None or sum(loads[-1]) > fits_at:
            raise store.LockedBatchCap('v3_derived_budget')  # before any transaction
        committed.append(a)
        return set()

    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, '_commit', commit)
    monkeypatch.setattr(store, 'backoff_state', lambda *a: (None, parked))
    monkeypatch.setattr(store, 'mark_bounded_attempt', lambda *a, **kw: None)
    monkeypatch.setattr(store, 'record_blocked', lambda uid, token, reason, **kw: parks.append(reason))
    monkeypatch.setattr(service, '_drain_blocked', AsyncMock())
    monkeypatch.setattr(service, '_wake_after_backoff', AsyncMock())
    return loads, commits, parks


@pytest.mark.asyncio
async def test_eight_seeds_over_the_batch_cap_retry_at_one_seed_and_commit(builder, monkeypatch):
    # A parked owner starts at eight seeds; eight fit the load allowance but need too many batches.
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=1, parked='v3_derived_budget')
    assert await service.reconcile('u') == 'committed'
    assert loads == [(8, 0), (1, 0)] and commits == [8, 1]
    assert parks == []


@pytest.mark.asyncio
async def test_the_full_page_falls_to_eight_seeds_when_eight_fit(builder, monkeypatch):
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=8)
    assert await service.reconcile('u') == 'committed'
    assert loads == [(32, 0), (8, 0)] and commits == [32, 8] and parks == []


@pytest.mark.asyncio
async def test_a_one_seed_pass_over_the_batch_cap_parks_once_without_looping(builder, monkeypatch):
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=None)
    report = {}
    assert await service.reconcile('u', report=report) == 'blocked'
    assert loads == [(32, 0), (8, 0), (1, 0)] and commits == [32, 8, 1]
    assert parks == ['v3_derived_budget'] and report['blocked_reason'] == 'v3_derived_budget'


@pytest.mark.asyncio
async def test_a_page_that_held_one_seed_parks_without_repeating_the_load(builder, monkeypatch):
    # One pending recording: a 32-seed page already read one seed, so a smaller page is the same closure.
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=None, pending=1)
    assert await service.reconcile('u') == 'blocked'
    assert loads == [(1, 0)] and commits == [32] and parks == ['v3_derived_budget']


@pytest.mark.asyncio
async def test_unlocked_only_windows_over_the_batch_cap_retry_at_one_window_and_commit(builder, monkeypatch):
    # Codex P2 (r4714563739): no pending recordings, several indexed unlocked windows; one window fits.
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=1, pending=0, unlocked=5)
    assert await service.reconcile('u') == 'committed'
    assert loads == [(0, 5), (0, 1)] and parks == []


@pytest.mark.asyncio
async def test_unlocked_only_windows_over_the_cap_at_one_window_park_once(builder, monkeypatch):
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=None, pending=0, unlocked=5)
    assert await service.reconcile('u') == 'blocked'
    assert loads == [(0, 5), (0, 1)] and parks == ['v3_derived_budget']


@pytest.mark.asyncio
async def test_one_seed_of_each_kind_over_the_cap_retries_on_a_single_lane(builder, monkeypatch):
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=1, pending=1, unlocked=1)
    assert await service.reconcile('u') == 'committed'
    assert loads[0] == (1, 1) and sum(loads[-1]) == 1 and len(loads) == 2 and parks == []


@pytest.mark.asyncio
async def test_the_ladder_bounds_a_pass_at_three_retries(builder, monkeypatch):
    # Both kinds owed and nothing fits: 32+8, 8+8, 1+1, then one single lane, then park. Four loads at most.
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=None, pending=32, unlocked=8)
    assert await service.reconcile('u') == 'blocked'
    assert loads[:3] == [(32, 8), (8, 8), (1, 1)] and len(loads) == 4 and sum(loads[3]) == 1
    assert parks == ['v3_derived_budget']


@pytest.mark.asyncio
async def test_an_on_open_pass_over_the_batch_cap_parks_as_before(builder, monkeypatch):
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=None)
    assert await service.reconcile('u', on_open=True) == 'blocked'
    assert commits == [None]  # on-open does not page seeds, so there is no smaller page to try


def test_only_the_batch_cap_steps_the_seed_ceiling_down():
    cap = store.LockedBatchCap('v3_derived_budget')
    full, eight, each, single = service.SEED_CEILINGS
    step = lambda pending, unlocked, ceiling=None: service._smaller_seed_ceiling(  # noqa: E731
        cap, UnlockedPage(seeds=(pending, unlocked)), ceiling
    )
    assert [step(32, 0), step(9, 3), step(8, 0), step(0, 5), step(1, 1), step(2, 0), step(1, 0), step(0, 1)] == [
        eight,
        eight,
        each,
        each,
        single,
        single,
        None,
        None,
    ]
    assert step(8, 8, eight) == each and step(1, 1, each) == single
    assert step(9, 0, eight) is None  # never back up the ladder
    assert service._smaller_seed_ceiling(cap, None) is None  # not a paged pass: park
    assert service._smaller_seed_ceiling(Conflict('v3_derived_budget'), UnlockedPage(seeds=(32, 0))) is None


# ---- panel review-20261127t015947-1583: the cap retry against the real backoff gate and a real commit ----------


def parked_builder_lease(strict, **fields):
    now = datetime.now(timezone.utc)
    strict.rows[('users', UID, 'conversation_v3_leases', 'builder')] = {
        'token': 'token',  # the builder fixture's acquire answers 'token'
        'until': now + timedelta(minutes=4),
        **fields,
    }


@pytest.mark.asyncio
async def test_a_cap_retry_runs_after_the_early_attempt_restores_the_parks_backoff(builder, strict, monkeypatch):
    # F1: a legacy park still in its backoff gets one early attempt; mark_bounded_attempt spends it, which makes the
    # real backoff_state answer the future backoff again. The smaller-seed retry must still run its load.
    loads, commits, parks = batch_cap_pass(builder, monkeypatch, fits_at=1)
    monkeypatch.setattr(store, 'backoff_state', REAL_BACKOFF_STATE)
    monkeypatch.setattr(store, 'mark_bounded_attempt', REAL_MARK_BOUNDED_ATTEMPT)
    parked_builder_lease(
        strict,
        v3_blocked_reason='v3_derived_budget',
        v3_blocked_count=1,
        v3_backoff_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert REAL_BACKOFF_STATE(UID)[0] is None  # the early attempt is still owed
    assert await service.reconcile(UID) == 'committed'
    assert lease_doc(strict)['v3_bounded_pending_attempted'] is True
    assert REAL_BACKOFF_STATE(UID)[0] is not None  # the gate a fresh pass would meet again
    assert loads == [(8, 0), (1, 0)] and commits == [8, 1] and parks == []


@pytest.mark.asyncio
async def test_an_ordinary_pass_in_backoff_still_waits(builder, strict, monkeypatch):
    loads, _, _ = batch_cap_pass(builder, monkeypatch, fits_at=1)
    monkeypatch.setattr(store, 'backoff_state', REAL_BACKOFF_STATE)
    parked_builder_lease(
        strict,
        v3_blocked_reason='v3_derived_budget',
        v3_bounded_pending_attempted=True,
        v3_backoff_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert await service.reconcile(UID) == 'backoff' and loads == []


@pytest.mark.asyncio
async def test_a_real_commit_over_the_batch_cap_at_two_seeds_retries_at_one_seed_and_commits(
    builder, strict, monkeypatch
):
    # F6: reconcile runs the real store.commit_projection. Four planned rows per seed, BATCH_MAX_WRITES 5: two seeds
    # (fixed writes 3) need 4 batches against a cap of 2, so nothing is written; one seed (fixed writes 2) needs 2.
    monkeypatch.setattr(service, '_commit', REAL_COMMIT)
    monkeypatch.setattr(leases, 'renew', lambda *a, **kw: None)  # the per-batch renewal has its own tests
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)  # three loaded rows: past the origin bound, so the cap applies
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 5)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 2)
    monkeypatch.setattr(service, '_drain_blocked', AsyncMock())
    monkeypatch.setattr(service, '_wake_after_backoff', AsyncMock())
    parked_builder_lease(strict)
    seeds_ids = ('r0', 'r1')
    for k, rid in enumerate(seeds_ids):
        start = AT + timedelta(hours=k)
        strict.rows[path(rid)] = source(rid, started_at=start, finished_at=start + timedelta(seconds=10))
    for i in range(3):
        strict.rows[path(f'l{i}')] = derived(f'l{i}', T0, 10, ['r0'])
    loads, transactions = [], []

    def load(uid, *, pending_limit=32, unlocked_limit=None, unlocked_page=None, **kw):
        seeds = (min(pending_limit, len(seeds_ids)), 0)
        loads.append(seeds)
        if unlocked_page is not None:
            unlocked_page.seeds = seeds
        recordings = {rid: {**strict.rows[path(rid)], '_v3_revision': 1} for rid in seeds_ids[: seeds[0]]}
        existing = {f'l{i}': {**strict.rows[path(f'l{i}')], '_v3_revision': 1} for i in range(3)}
        return recordings, existing, []

    async def plan(uid, groups, outlines, recordings, *a, **kw):
        return [
            {
                'id': f'c-{rid}-{i}',
                'status': 'processing',
                'started_at': T0,
                'finished_at': T0,
                'v3_recording_ids': [rid],
            }
            for rid in recordings
            for i in range(4)
        ]

    original = store.firestore.transactional

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            if body.__name__ == 'commit':
                transactions.append(len(args[0]))
            return wrapped(tx, *args)

        return run

    class EvenMinute(datetime):
        @classmethod
        def now(cls, tz=None):
            # The one-seed lanes lead with the pending lane on even minutes; pin it so the ladder is deterministic.
            real = datetime.now(tz)
            return real.replace(minute=real.minute - real.minute % 2)

    monkeypatch.setattr(service, 'datetime', EvenMinute)
    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, '_plan_projection', plan)
    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    assert await service.reconcile(UID) == 'committed'
    assert loads == [(2, 0), (1, 0)]
    assert transactions == [3, 1]  # only the one-seed pass committed: two batches, the first two seeds' cap wrote none
    written_ids = sorted(p[3] for p in strict.rows if p[2] == 'conversations' and p[3].startswith('c-'))
    assert written_ids == [f'c-r0-{i}' for i in range(4)]
    assert strict.rows[path('r0')]['v3_pending'] is False
    assert strict.rows[path('r1')]['v3_pending'] is True  # the second seed stays owed for the next pass


# ---- deferred panel minors (review-20261127t050745-babe F3): the cap retry with the real load and the real plan ----


class EvenMinute(datetime):
    @classmethod
    def now(cls, tz=None):
        # The one-seed lanes lead with the pending lane on even minutes; pin it so the ladder is deterministic.
        real = datetime.now(tz)
        return real.replace(minute=real.minute - real.minute % 2)


def two_fragmented(n):
    """Two pending recordings two hours apart, each owned by n locked one-line windows."""
    rows = {}
    for k in range(2):
        rid, claims = f'r{k}', []
        base = AT + timedelta(hours=2 * k)
        for i in range(n):
            start = base + timedelta(seconds=10 * i)
            rows[C + f'd{k}-{i}'] = derived(f'd{k}-{i}', start, 10, [rid])
            claims.append(claim(f'd{k}-{i}', start, 10))
        rows[C + rid] = source(
            rid,
            started_at=base,
            finished_at=base + timedelta(seconds=10 * n),
            claims=claims,
            v3_pending_since=base,
            v3_pending=True,
        )
    return rows


class ChargeTransaction:
    """The charge's transaction on the in-memory client: reads go through ``get(transaction=...)``."""

    def __init__(self, rows):
        self.rows = rows

    def update(self, ref, patch):
        self.rows[ref.path].update(patch)


def capped_once(builder, monkeypatch):
    """A cap retry whose first commit hits the locked-closure batch cap and whose retry commits."""
    loads, _, parks = batch_cap_pass(builder, monkeypatch, fits_at=None, pending=2)
    commits = []

    def commit(*a, bounded_pending_limit=None, **kw):
        commits.append(bounded_pending_limit)
        if len(commits) == 1:
            raise store.LockedBatchCap('v3_derived_budget')  # before any transaction
        return set()

    monkeypatch.setattr(service, '_commit', commit)
    monkeypatch.setattr(service, 'datetime', EvenMinute)
    return loads, commits, parks


@pytest.mark.asyncio
async def test_the_cap_retrys_real_load_charges_the_owners_day_again(builder, monkeypatch):
    # The retry is a new load, and a new load is a new allowance attempt: both are charged on the held builder lease.
    _, commits, parks = capped_once(builder, monkeypatch)
    rows = two_fragmented(8)
    lease_path = '/users/u/conversation_v3_leases/builder'
    rows[lease_path] = {'token': 'token', 'until': datetime.now(timezone.utc) + timedelta(minutes=4)}
    client = MemoryQuery(rows)
    real_get = MemoryQuery.get
    monkeypatch.setattr(MemoryQuery, 'get', lambda self, transaction=None: real_get(self))
    monkeypatch.setattr(store.firestore, 'transactional', lambda body: body)
    monkeypatch.setattr(
        store, 'run_preloaded_transaction_with_contention_retry', lambda c, op, *a: op(ChargeTransaction(c.rows), *a)
    )
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'load', REAL_LOAD)
    monkeypatch.setattr(store, '_charge_locked_attempt', CHARGE)
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)  # two seeds load 16 locked rows: past the origin bound
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    planned = []

    async def plan(uid, groups, outlines, recordings, *a, **kw):
        planned.append(sorted(recordings))
        return []

    monkeypatch.setattr(service, '_plan_projection', plan)
    assert await service.reconcile('u') == 'committed'
    assert planned == [['r0', 'r1'], ['r0']] and commits == [32, 1] and parks == []
    lease = rows[lease_path]
    assert lease['v3_locked_day'] == datetime.now(timezone.utc).date().isoformat()
    assert lease['v3_locked_passes'] == 2  # the capped attempt and the retry's load


@pytest.mark.asyncio
async def test_the_cap_retry_replans_its_smaller_page(builder, monkeypatch):
    # service._plan_projection runs for real on both passes; the retry plans only the one seed it loaded.
    loads, commits, parks = capped_once(builder, monkeypatch)

    def load(uid, *, pending_limit=32, unlocked_limit=None, unlocked_page=None, **kw):
        seeds = (min(pending_limit, 2), 0)
        loads.append(seeds)
        if unlocked_page is not None:
            unlocked_page.seeds = seeds
        return {f'r{k}': source(f'r{k}', started_at=AT + timedelta(hours=2 * k)) for k in range(seeds[0])}, {}, []

    planned = []

    async def plan(uid, groups, outlines, recordings, *a, **kw):
        rows = await REAL_PLAN(uid, groups, outlines, recordings, *a, **kw)
        planned.append((sorted(recordings), sorted(rid for row in rows for rid in row.get('v3_recording_ids') or ())))
        return rows

    monkeypatch.setattr(store, 'load', load)
    monkeypatch.setattr(service, '_plan_projection', plan)
    assert await service.reconcile('u') == 'committed'
    assert loads == [(2, 0), (1, 0)] and commits == [32, 1] and parks == []
    assert [recordings for recordings, _ in planned] == [['r0', 'r1'], ['r0']]
    assert planned[1][1] and set(planned[1][1]) == {'r0'}  # the retry's plan covers only its own seed
