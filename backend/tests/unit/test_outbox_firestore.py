"""FirestoreEnrichmentOutbox state machine on the in-memory row store (contract (b)).

The emulator conformance suite (lane 12, ``tests/integration/test_outbox_conformance.py``) proves Firestore
persistence; this file pins the row semantics and their compatibility with ``mark``/``run``.
"""

from unittest.mock import Mock

import pytest

from database.outbox import Claim, Outcome
from database.outbox_firestore import ENRICHMENT_OUTBOX as outbox, firestore_outbox
from database.outbox import OutboxKind
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import custody
from utils.enrichment import outbox as reprocess

KEY = reprocess.key('u', 'c')
PAYLOAD = {'conversation_id': 'c', 'language': 'en'}


@pytest.fixture
def rows(state, monkeypatch):  # noqa: F811
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: False)
    return state


def _enqueue(available_at, *, now=0.0, **kwargs):
    return outbox.enqueue(KEY, 'u', PAYLOAD, available_at, now=now, **kwargs)


def _claim(rows, *, now=1000.0, lease=120.0):
    claimed = outbox.claim_key(KEY, rows[0][KEY]['task_token'], lease, now=now)
    assert isinstance(claimed, Claim), claimed
    return claimed


def test_enqueue_writes_a_mark_compatible_row_and_wakes_after_commit(rows):
    state_rows, tasks = rows
    result = _enqueue(600.0, policy_id='p1')
    row = state_rows[KEY]
    assert result.row_id == KEY and not result.coalesced and result.wake_token == row['task_token']
    assert row['due_at'] == 600.0 and row['policy_id'] == 'p1' and row['uid'] == 'u'
    assert tasks[-1]['task_token'] == row['task_token']  # non-transactional enqueue wakes itself
    # The same row is claimable by today's run(): row compatibility (invariant 7).
    assert reprocess.run(KEY, row['task_token'], lambda *_: None, now=601) == 'processed'
    assert KEY not in state_rows


def test_enqueue_coalesces_with_min_and_max_rules(rows):
    state_rows, _tasks = rows
    _enqueue(600.0)
    assert _enqueue(900.0, coalesce='max').coalesced
    assert state_rows[KEY]['due_at'] == 900.0 and state_rows[KEY]['version'] == 2
    assert _enqueue(300.0, coalesce='min').coalesced
    assert state_rows[KEY]['due_at'] == 300.0 and state_rows[KEY]['version'] == 3
    assert len(state_rows) == 1


def test_enqueue_rejects_a_foreign_dedupe_key(rows):
    with pytest.raises(ValueError):
        outbox.enqueue(reprocess.key('u', 'other'), 'u', PAYLOAD, 1.0, now=0.0)


def test_claim_key_fences_stale_wakes_busy_leases_and_not_due_rows(rows):
    state_rows, tasks = rows
    _enqueue(600.0)
    token = state_rows[KEY]['task_token']
    assert outbox.claim_key(KEY, 'f' * 32, 120, now=700) is Outcome.STALE
    deferred = outbox.claim_key(KEY, token, 120, now=10)
    assert deferred is Outcome.DEFERRED
    assert state_rows[KEY]['task_token'] != token and tasks[-1]['task_token'] == state_rows[KEY]['task_token']
    assert outbox.claim_key(KEY, token, 120, now=700) is Outcome.STALE  # the old wake is now stale
    claim = _claim(rows, now=700)
    assert claim.owner_id == 'u' and claim.attempt == 1 and claim.payload['conversation_id'] == 'c'
    assert outbox.claim_key(KEY, claim.wake_token, 120, now=701) is Outcome.BUSY


def test_privacy_fence_discards_before_claim(rows, monkeypatch):
    _enqueue(1.0)
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: True)
    assert outbox.claim_key(KEY, rows[0][KEY]['task_token'], 120, now=10) is Outcome.DISCARDED


def test_lease_token_fences_every_later_call(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    first = _claim(rows, now=10, lease=120)
    assert outbox.heartbeat(first, 120, now=100)
    assert state_rows[KEY]['lease_until'] == 220
    assert not outbox.heartbeat(first, 120, now=221)  # expired leases are not renewed
    second = _claim(rows, now=300)
    assert second.lease_token != first.lease_token and second.attempt == 2
    assert not outbox.ack(first, 'processed', now=301)
    assert not outbox.release(first, 'locked', now=301)
    assert outbox.defer(first, 900, 'policy_defer', now=301) is None
    assert outbox.ack(second, 'processed', now=302)


def test_ack_retires_or_rearms_by_version(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    _enqueue(50.0, now=20)  # an append during processing bumps the version
    assert outbox.ack(claim, 'processed', now=30)
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['task_token'] != claim.wake_token
    assert tasks[-1]['task_token'] == state_rows[KEY]['task_token']
    again = _claim(rows, now=60)
    assert outbox.ack(again, 'processed', now=61)
    assert KEY not in state_rows


def test_a_wake_token_rotated_under_a_live_lease_does_not_strand_the_holder(rows):
    """M1 L09-3: a producer (mark_update / mark_effects) may rotate task_token mid-lease; invariant 1 fences
    on lease_token only, so the live holder still records its summary and settles."""
    state_rows, _tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    state_rows[KEY]['task_token'] = 'e' * 32  # mark_effects merges a new token and keeps the lease
    assert outbox.heartbeat(claim, 120, now=20)
    assert outbox.record_summary(claim)
    assert outbox.ack(claim, 'processed', now=21)
    assert state_rows[KEY]['dormant'] and state_rows[KEY]['summary_seen']


def test_release_after_a_rotation_rearms_under_a_fresh_wake(rows):
    """The queue retries the released (now stale) task, and the rotated wake may have been answered BUSY."""
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    state_rows[KEY]['task_token'] = 'e' * 32
    assert outbox.release(claim, 'dependency', now=20)
    fresh = state_rows[KEY]['task_token']
    assert fresh not in ('e' * 32, claim.wake_token) and tasks[-1]['task_token'] == fresh
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['owner'] is None


def test_release_without_a_rotation_keeps_the_wake_for_the_queue_retry(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    woken = len(tasks)
    assert outbox.release(claim, 'dependency', now=20)
    assert state_rows[KEY]['task_token'] == claim.wake_token and len(tasks) == woken


def test_record_summary_keeps_a_dormant_receipt(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    assert outbox.record_summary(claim)
    assert outbox.ack(claim, 'processed', now=11)
    receipt = state_rows[KEY]
    assert receipt['dormant'] and receipt['summary_seen'] and receipt['uid'] is None
    assert 'summary_seen_by' not in receipt


def test_defer_mints_a_new_wake_and_release_keeps_it(rows):
    state_rows, tasks = rows
    _enqueue(1.0)
    claim = _claim(rows, now=10)
    token = outbox.defer(claim, 500.0, 'open_live_target', now=11)
    assert token and token != claim.wake_token and tasks[-1]['task_token'] == token
    assert state_rows[KEY]['deferred_reason'] == 'open_live_target' and state_rows[KEY]['due_at'] == 500.0
    claim = _claim(rows, now=600)
    assert outbox.release(claim, 'locked', now=601)
    assert state_rows[KEY]['lease_until'] == 0 and state_rows[KEY]['task_token'] == claim.wake_token
    assert isinstance(outbox.claim_key(KEY, claim.wake_token, 120, now=602), Claim)  # the queue retry claims


def test_transactional_enqueue_defers_the_wake_to_the_caller(rows, monkeypatch):
    state_rows, tasks = rows
    written = {}

    class Snapshot:
        exists = False

        def to_dict(self):
            return None

    class Ref:
        def get(self, transaction):
            return Snapshot()

    class Collection:
        def document(self, _document_id):
            return Ref()

    class Client:
        def collection(self, _name):
            return Collection()

    class Transaction:
        def set(self, _ref, value):
            written['row'] = value

    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: Client())
    before = len(tasks)
    result = _enqueue(1.0, tx=Transaction())
    assert written['row']['summary_lane'] == 'batch' and result.wake_token == written['row']['task_token']
    assert len(tasks) == before  # no task before the caller commits
    state_rows[KEY] = written['row']  # the caller's commit

    class Stored:
        exists = True

        def to_dict(self):
            return dict(state_rows[KEY])

    Ref.get = lambda self, transaction=None: Stored()
    outbox.wake(KEY, result.wake_token)
    outbox.wake(KEY, 'f' * 32)  # a superseded token never wakes
    assert len(tasks) == before + 1 and tasks[-1]['task_token'] == result.wake_token


def test_sweep_discards_privacy_fenced_rows_instead_of_rewaking(rows, monkeypatch, sweep_query):  # noqa: F811
    _enqueue(1.0)
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: True)
    counts = outbox.sweep(now=10_000)
    assert counts.discarded == 1 and counts.rewoken == 0


def test_selector_serves_only_the_built_kinds():
    assert firestore_outbox(OutboxKind.ENRICHMENT) is outbox
    with pytest.raises(NotImplementedError):
        firestore_outbox(OutboxKind.CAP_HOLD_REDRIVE)  # reserved; provider_stt is lane 8's


def test_pull_claims_due_rows_by_their_stored_wake(rows, monkeypatch):
    state_rows, _tasks = rows
    _enqueue(1.0)
    monkeypatch.setattr(reprocess, 'due_rows', lambda **_: [(key, dict(row)) for key, row in state_rows.items()])
    claims = outbox.claim(5, 120, now=10)
    assert [claim.row_id for claim in claims] == [KEY]
    assert outbox.claim(5, 120, now=11) == []  # the leased row answers BUSY, not a second claim


def test_outbox_for_selects_the_firestore_enrichment_outbox():
    from database.outbox import outbox_for

    assert outbox_for(OutboxKind.ENRICHMENT) is outbox


def test_not_due_deferral_is_not_a_processing_attempt(rows):
    _enqueue(600.0)
    assert outbox.claim_key(KEY, rows[0][KEY]['task_token'], 120, now=10) is Outcome.DEFERRED
    assert not rows[0][KEY].get('claim_attempts')
    assert _claim(rows, now=700).attempt == 1


def test_conformance_factory_uses_the_injected_privacy_check_and_wake(rows, monkeypatch):
    from database.outbox_firestore import FirestoreOutbox

    # Contract (b) seams, as testing/store_fixtures.py injects them: privacy_blocked(owner_id, payload) and
    # create_wake(row_id, wake_token, available_at). The injected creator stands in for the queue binding.
    wakes, blocked = [], set()
    injected = FirestoreOutbox(
        OutboxKind.ENRICHMENT,
        privacy_blocked=lambda owner_id, payload: (owner_id, payload['conversation_id']) in blocked,
        create_wake=lambda row_id, token, at: wakes.append((row_id, token, at)),
    )
    monkeypatch.setattr(custody, 'discard_blocked', Mock(side_effect=AssertionError('default fence used')))
    result = injected.enqueue(KEY, 'u', PAYLOAD, 1.0, now=0.0)
    assert [(row_id, token) for row_id, token, _ in wakes] == [(KEY, result.wake_token)]
    blocked.add(('u', PAYLOAD['conversation_id']))
    assert injected.claim_key(KEY, result.wake_token, 120, now=10) is Outcome.DISCARDED
    assert injected.claim_key(KEY, result.wake_token, 120, now=11) is Outcome.STALE  # the row was discarded
    assert injected.claim_key('not-a-row', result.wake_token, 120, now=12) is Outcome.STALE
    with pytest.raises(NotImplementedError):
        FirestoreOutbox(OutboxKind.CAP_HOLD_REDRIVE)


def test_enqueue_snapshots_the_first_summary_policy_once(rows):
    state_rows, _tasks = rows
    _enqueue(600.0, snapshot_summary=True)
    snapshot = state_rows[KEY]['first_summary_policy']
    assert snapshot is not None and state_rows[KEY]['first_summary_policy_source'] == 'creation'
    _enqueue(900.0, snapshot_summary=True)  # a coalesced append keeps the admitted decision
    assert state_rows[KEY]['first_summary_policy'] == snapshot
    assert state_rows[KEY]['first_summary_policy_source'] == 'creation'


def test_claim_stamps_a_fallback_snapshot_on_a_batch_row_without_one(rows):
    state_rows, _tasks = rows
    _enqueue(1.0)
    state_rows[KEY]['summary_lane'] = 'batch'
    state_rows[KEY].pop('first_summary_policy', None)
    claim = _claim(rows, now=10)
    assert state_rows[KEY]['first_summary_policy_source'] == 'fallback'
    assert claim.payload['first_summary_policy'] == state_rows[KEY]['first_summary_policy']


def _install_paged_due_query(state_rows, monkeypatch):
    """Fake Firestore collection that enforces <=100 per-page limits and DocumentSnapshot start_after cursors."""
    from types import SimpleNamespace

    stream_calls: list[tuple[int, tuple | None]] = []

    class _Snapshot:
        exists = True

        def __init__(self, doc_id: str, row: dict):
            self.id = doc_id
            self.reference = SimpleNamespace(id=doc_id)
            self._row = dict(row)

        def to_dict(self):
            return dict(self._row)

    class _Query:
        def __init__(self, max_due=None, orders=(), page_limit=100, cursor=None):
            self._max_due = max_due
            self._orders = orders
            self._limit = page_limit
            self._cursor = cursor

        def where(self, field, op, value):
            assert (field, op) == ('due_at', '<=')
            return _Query(value, self._orders, self._limit, self._cursor)

        def order_by(self, field):
            return _Query(self._max_due, (*self._orders, field), self._limit, self._cursor)

        def limit(self, count):
            assert 1 <= count <= 100
            return _Query(self._max_due, self._orders, count, self._cursor)

        def start_after(self, snapshot):
            if isinstance(snapshot, dict):
                raise TypeError('Firestore query ordered by __name__ requires a DocumentSnapshot cursor')
            assert isinstance(snapshot, _Snapshot)
            row = snapshot.to_dict()
            return _Query(self._max_due, self._orders, self._limit, (row['due_at'], snapshot.id))

        def stream(self):
            assert self._orders == ('due_at', '__name__')
            stream_calls.append((self._limit, self._cursor))
            items = [
                (doc_id, dict(row))
                for doc_id, row in state_rows.items()
                if row.get('due_at') is not None and row['due_at'] <= self._max_due
            ]
            items.sort(key=lambda item: (item[1]['due_at'], item[0]))
            if self._cursor is not None:
                items = [item for item in items if (item[1]['due_at'], item[0]) > self._cursor]
            page = items[: self._limit]
            return [_Snapshot(doc_id, row) for doc_id, row in page]

    class _Collection(_Query):
        def document(self, doc_id):
            return SimpleNamespace(id=doc_id)

    monkeypatch.setattr(
        reprocess,
        'get_firestore_client',
        lambda: SimpleNamespace(collection=lambda name: _Collection() if name == reprocess.COLLECTION else None),
    )
    return stream_calls


def test_pl002_live_lease_prefix_cannot_hide_runnable_work(rows, monkeypatch):
    state_rows, _tasks = rows
    stream_calls = _install_paged_due_query(state_rows, monkeypatch)
    t0 = 1000.0
    for i in range(101):
        cid = f'leased-{i}'
        queued = outbox.enqueue(
            reprocess.key('u', cid), 'u', {'conversation_id': cid, 'language': 'en'}, t0 - 200 + i, now=t0
        )
        assert isinstance(outbox.claim_key(queued.row_id, queued.wake_token, 120.0, now=t0), Claim)
    valid = outbox.enqueue(
        reprocess.key('u', 'runnable'), 'u', {'conversation_id': 'runnable', 'language': 'en'}, t0, now=t0
    )

    claims = outbox.claim(1, 120.0, now=t0 + 1)
    assert [claim.row_id for claim in claims] == [valid.row_id]
    assert len(stream_calls) >= 2
    assert outbox.ack(claims[0], 'done', now=t0 + 2)
    assert outbox.claim(1, 120.0, now=t0 + 3) == []


def test_pl002_retired_privacy_prefix_cannot_consume_the_claim_budget(rows, monkeypatch):
    from database.outbox_firestore import FirestoreOutbox

    state_rows, _tasks = rows
    stream_calls = _install_paged_due_query(state_rows, monkeypatch)
    t0 = 1000.0
    blocked: set[tuple[str, str]] = set()
    injected = FirestoreOutbox(
        OutboxKind.ENRICHMENT,
        privacy_blocked=lambda owner_id, payload: (owner_id, payload['conversation_id']) in blocked,
        create_wake=lambda *_args: None,
    )
    for i in range(101):
        cid = f'deleted-{i}'
        injected.enqueue(reprocess.key('u', cid), 'u', {'conversation_id': cid, 'language': 'en'}, t0 - 200 + i, now=t0)
        blocked.add(('u', cid))
    valid = injected.enqueue(
        reprocess.key('u', 'runnable'), 'u', {'conversation_id': 'runnable', 'language': 'en'}, t0, now=t0
    )

    claims = injected.claim(1, 120.0, now=t0)
    assert [claim.row_id for claim in claims] == [valid.row_id]
    assert len(stream_calls) >= 2
    assert set(state_rows) == {valid.row_id}
    assert injected.ack(claims[0], 'done', now=t0 + 1)
    assert injected.claim(1, 120.0, now=t0 + 2) == []


def test_pl003_explicit_backlog_budget_is_not_silently_capped_at_100(rows, monkeypatch):
    state_rows, _tasks = rows
    stream_calls = _install_paged_due_query(state_rows, monkeypatch)
    t0 = 1000.0
    expected = {
        outbox.enqueue(
            reprocess.key('u', f'due-{i:03}'),
            'u',
            {'conversation_id': f'due-{i:03}', 'language': 'en'},
            t0 - 200 + i,
            now=t0,
        ).row_id
        for i in range(125)
    }
    future = outbox.enqueue(
        reprocess.key('u', 'future'),
        'u',
        {'conversation_id': 'future', 'language': 'en'},
        t0 + 500,
        now=t0,
    )

    claims = outbox.claim(125, 120.0, now=t0)
    assert len(claims) == 125
    assert {claim.row_id for claim in claims} == expected
    assert all(claim.attempt == 1 for claim in claims)
    assert len(stream_calls) == 2
    assert outbox.claim(125, 120.0, now=t0 + 1) == []
    for claim in claims:
        assert outbox.ack(claim, 'done', now=t0 + 2)
    assert outbox.claim(125, 120.0, now=t0 + 499) == []
    assert [claim.row_id for claim in outbox.claim(125, 120.0, now=t0 + 500)] == [future.row_id]


def test_due_rows_passes_real_firestore_document_snapshot_cursor_across_pages():
    import threading
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_document import DocumentSnapshot
    from google.cloud.firestore_v1.query import Query

    client = firestore.Client(project='test-outbox', credentials=AnonymousCredentials())
    # Simulate an active gRPC channel lock on the live client (deepcopying a dict with a DocumentReference fails).
    client._live_channel_lock = threading.Lock()
    collection = client.collection(reprocess.COLLECTION)

    page1 = [
        DocumentSnapshot(
            reference=collection.document(f'{i:064x}'),
            data={'due_at': 10.0 + i, 'lease_until': 0.0, 'task_token': f'{i + 1:032x}'},
            exists=True,
            read_time=None,
            create_time=None,
            update_time=None,
        )
        for i in range(2)
    ]
    page2 = [
        DocumentSnapshot(
            reference=collection.document(f'{2:064x}'),
            data={'due_at': 12.0, 'lease_until': 0.0, 'task_token': f'{3:032x}'},
            exists=True,
            read_time=None,
            create_time=None,
            update_time=None,
        )
    ]
    seen_queries = []

    def fake_stream(self, *_args, **_kwargs):
        pb = self._to_protobuf()
        seen_queries.append(pb)
        return iter(page1 if len(seen_queries) == 1 else page2)

    original_stream = Query.stream
    Query.stream = fake_stream
    try:
        yielded = list(reprocess.due_rows(now=100.0, limit=2, client=client))
    finally:
        Query.stream = original_stream

    assert [doc_id for doc_id, _ in yielded] == [f'{0:064x}', f'{1:064x}', f'{2:064x}']
    assert len(seen_queries) == 2
    assert not seen_queries[0]._pb.HasField('start_at')
    assert seen_queries[1]._pb.HasField('start_at')
    assert seen_queries[1].start_at.before is False
    assert seen_queries[1].start_at.values[0].double_value == 11.0
    assert seen_queries[1].start_at.values[1].reference_value.endswith(f'/{reprocess.COLLECTION}/{1:064x}')
