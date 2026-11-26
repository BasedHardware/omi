"""The live closure loads a heavy owner's claimed rows without chaining through settled history."""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases, memories
from utils.conversations.v3 import Conflict, service, triggers
from tests.unit.test_conversations_v3_claim_growth import T0, UID, path, strict  # noqa: F401
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, builder, source  # noqa: F401

C = '/users/u/conversations/'


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
    assert loaded[1] == ({'ru'}, {'u'}, frozenset(), 1)


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
    from tests.unit.test_conversations_v3_lock_timing import _locked_pair

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
    monkeypatch.setattr(service, 'enqueue', lambda uid, **kw: kw.get('wake_key') and wakes.append(kw['at']))
    started = datetime.now(timezone.utc)
    assert await service.reconcile('synthetic') == 'committed'
    assert len(pages) == 1 and wakes[0] - started >= timedelta(seconds=59)
    # One wake per pass, re-armed after the lease only when this pass outlasted it.
    assert len(wakes) == (2 if outlasts_wake else 1)
    if outlasts_wake:
        assert wakes[1] > wakes[0] + timedelta(minutes=1)


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
