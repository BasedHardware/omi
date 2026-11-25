"""The live closure loads a heavy owner's claimed rows without chaining through settled history."""

from datetime import timedelta

import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import Conflict
from tests.unit.test_conversations_v3_claim_growth import T0, UID, path, strict  # noqa: F401
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, source

C = '/users/u/conversations/'


@pytest.fixture(autouse=True)
def plain_rows(monkeypatch):
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap, **_kwargs: {**snap.to_dict(), '_v3_revision': 1} if snap.exists else None
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
    # One source update and the lease leave three rows per transaction; a re-derive's two deletes leave one.
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 5)
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
        lambda uid, snap, **_kwargs: decoded.append(snap.id) or ({**snap.to_dict(), '_v3_revision': 1} if snap.exists else None),
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
    monkeypatch.setattr(store, 'recording_input', lambda uid, snap, **_kwargs: reads.append(snap.id) or real(uid, snap, **_kwargs))
    rows = {C + 'p': source('p', claims=[claim('d', AT, 10)], v3_pending_since=AT)}
    rows[C + 'd'] = derived('d', AT, 10, ['p', 'gone1', 'gone2', 'gone3'])
    with pytest.raises(Conflict, match='v3_source_closure_budget'):
        store.load('u', firestore_client=MemoryQuery(rows))
    assert not any(rid.startswith('gone') for rid in reads)
