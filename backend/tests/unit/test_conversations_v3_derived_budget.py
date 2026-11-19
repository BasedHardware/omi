"""The live closure loads a heavy owner's claimed rows without chaining through settled history."""

from datetime import timedelta

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import Conflict
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, source

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


def test_settled_neighbours_do_not_chain_the_closure():
    # p is pending; q (10 minutes later, inside p's margin) is settled and claimed by dq; s (15 minutes after
    # q, outside p's margin but inside q's) is settled and claimed by ds. The old closure queried q's margin too and pulled ds, s, and so on
    # through the owner's whole contiguous day.
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
    recordings, existing, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert set(recordings) == {'p', 'q'}
    assert set(existing) == {'dp', 'dq'}


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
