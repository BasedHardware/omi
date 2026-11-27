"""A locked-closure batch-cap rejection never leaves offloaded transcript copies behind (custody, SCA-2918).

commit_projection decides the cap for a closure past the origin bound before anything is uploaded to the object lake:
preparation runs once with uploads deferred (transcript_pointer.deferred_offloads), so a row offload_or_inline would
offload carries a stand-in pointer at least as large as the real one, and the uploads run only after the cap and the
partition's own refusals pass.
"""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store
from database import transcript_pointer
from database.conversations_v3_projection_budget import encoded_bytes
from tests.unit.test_transcript_pointer import UID, encode, lake_world, speech  # noqa: F401
from utils.other import object_lake
from utils.conversations.v3 import Conflict

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class FirstTransaction(Exception):
    """Stands in for the first commit transaction: everything before it (preparation included) has run."""


def lake_objects(world):
    return list(world.bucket.list_blobs(prefix=f'v1/spaces/{UID}/transcript/'))


def shared_row(index, *, visibility='shared', small=False):
    start = T0 + timedelta(minutes=index)
    return {
        'id': (
            f'{"small" if small else "shared"}-{visibility}-{index}'
            if small or visibility == 'private'
            else f'shared-{index}'
        ),
        'status': 'completed',
        'visibility': visibility,
        'started_at': start,
        'finished_at': start + timedelta(seconds=10),
        'v3_recording_ids': ['r'],
        # Random hex does not compress under the 4 KiB inline threshold, so preparation offloads it.
        'transcript_segments': (
            [{'id': f's{index}', 'text': 'a short line', 'start': 0.0, 'end': 8.0}] if small else speech()
        ),
    }


@pytest.fixture
def heavy(lake_world, monkeypatch):  # noqa: F811
    """A listed owner whose loaded closure is past the origin bound, so the batch cap applies."""
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)
    existing = {
        f'l{i}': {'id': f'l{i}', 'v3_derived': True, 'status': 'completed', '_v3_revision': 1} for i in range(3)
    }
    recordings = {'r': {'id': 'r', 'recording': True, 'v3_pending': True, '_v3_revision': 1}}
    partitions = []
    real_partition = store.partition_rows

    def partition(*args, **kwargs):
        batches = real_partition(*args, **kwargs)
        partitions.append(len(batches))
        return batches

    def first_transaction(*a, **kw):
        raise FirstTransaction

    monkeypatch.setattr(store, 'partition_rows', partition)
    monkeypatch.setattr(store, 'run_preloaded_transaction_with_contention_retry', first_transaction)
    monkeypatch.setattr(store, 'commit_lease_renewal_enabled', lambda: False)

    def commit(rows, **kw):
        return store.commit_projection(
            UID, 'token', recordings, existing, rows, [], firestore_client=lake_world.store, **kw
        )

    return commit, partitions


@pytest.mark.parametrize('visibility', ['shared', 'public'])
def test_a_capped_attempt_with_changed_shared_rows_uploads_nothing(
    lake_world, heavy, monkeypatch, visibility
):  # noqa: F811
    commit, partitions = heavy
    # Two writes a batch: one recording and the lease leave one row each, so four rows need four batches.
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 3)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 3)
    rows = [shared_row(i, visibility=visibility) for i in range(4)]
    with pytest.raises(store.LockedBatchCap):
        commit(rows)
    assert partitions == [4]  # only the inline estimate ran
    assert lake_world.calls['put'] == 0 and lake_objects(lake_world) == []


def test_the_same_rows_under_the_cap_do_offload(lake_world, heavy, monkeypatch):  # noqa: F811
    # The control: the wiring above really offloads, so the capped test's empty lake is not vacuous.
    commit, partitions = heavy
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 3)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 4)
    with pytest.raises(FirstTransaction):
        commit([shared_row(i) for i in range(4)])
    assert partitions == [4, 4]  # the estimate, then the real partition
    assert len(lake_objects(lake_world)) == 4


@pytest.mark.parametrize('cap, parks', [(2, False), (1, True)])
def test_the_estimate_counts_every_offloadable_row_as_a_pointer(
    lake_world, heavy, monkeypatch, cap, parks
):  # noqa: F811
    # Two pointers a batch: four offloaded rows commit in exactly two batches, which the estimate must neither
    # under-count (cap 1 parks before any upload) nor over-count (cap 2 commits).
    commit, partitions = heavy
    monkeypatch.setattr(store, 'MAX_PRELOAD_DOCUMENTS', 2)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', cap)
    rows = [shared_row(i) for i in range(4)]
    if parks:
        with pytest.raises(store.LockedBatchCap):
            commit(rows)
        assert partitions == [2] and lake_objects(lake_world) == []
    else:
        with pytest.raises(FirstTransaction):
            commit(rows)
        assert partitions == [2, 2] and len(lake_objects(lake_world)) == 4


def test_private_rows_are_estimated_inline_and_never_counted_as_pointers(lake_world, heavy, monkeypatch):  # noqa: F811
    commit, partitions = heavy
    monkeypatch.setattr(store, 'MAX_PRELOAD_DOCUMENTS', 2)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 1)
    with pytest.raises(FirstTransaction):
        commit([shared_row(i, visibility='private') for i in range(4)])
    assert partitions == [1, 1] and lake_objects(lake_world) == []


def test_a_closure_inside_the_origin_bound_skips_the_estimate(lake_world, heavy, monkeypatch):  # noqa: F811
    commit, partitions = heavy
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 10)
    with pytest.raises(FirstTransaction):
        commit([shared_row(i) for i in range(2)])
    assert partitions == [1]


def test_a_batch_cap_is_a_conflict_that_parks():
    assert issubclass(store.LockedBatchCap, Conflict)


# ---- Codex P2 r4715443730: cold transcript pointers must not replay a locked-closure batch past the ceiling ------


@pytest.fixture
def lake_commit(lake_world, monkeypatch):  # noqa: F811
    """A real transactional commit on the lake fixture: rows offload in preparation, and the privacy filter inside
    each batch's transaction resolves their pointers (run_preloaded_operation replays the body for a cold one)."""
    from database import conversations_v3_leases as leases
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreSnapshot

    client = lake_world.store
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda s: (s.to_dict() or {}).get('_test_revision', 1)),
        raising=False,
    )
    executions, closure_reads = [], []

    def transactional(body):
        def run(tx, *args, **kwargs):
            if body.__name__ == 'commit':
                executions.append(len(args[0]))
            return body(tx, *args, **kwargs)

        return run

    real_snapshots = store._projection_snapshots

    def snapshots(client_, coll, tx, ids, *, batch_reads):
        if ids and ids[0] in ('r', 'l0'):
            closure_reads.append(len(ids))  # the revision fence: every loaded recording and row, once per run
        return real_snapshots(client_, coll, tx, ids, batch_reads=batch_reads)

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    monkeypatch.setattr(store, '_projection_snapshots', snapshots)
    monkeypatch.setattr(store, 'commit_lease_renewal_enabled', lambda: False)
    monkeypatch.setattr(store, 'DERIVED_LIMIT', 2)
    monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 20)
    monkeypatch.setattr(store, 'MAX_PRELOAD_DOCUMENTS', 4)  # four pointers a batch: eight rows, two batches
    conversations = ('users', UID, 'conversations')
    client.rows[(*conversations, 'r')] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed'}
    for i in range(3):
        client.rows[(*conversations, f'l{i}')] = {'id': f'l{i}', 'v3_derived': True, 'status': 'completed'}
    client.rows[('users', UID, 'conversation_v3_leases', 'builder')] = {
        'token': 'token',
        'until': datetime.now(timezone.utc) + timedelta(minutes=4),
    }
    recordings = {'r': {**client.rows[(*conversations, 'r')], '_v3_revision': 1}}
    existing = {f'l{i}': {**client.rows[(*conversations, f'l{i}')], '_v3_revision': 1} for i in range(3)}

    def commit(rows):
        return store.commit_projection(
            UID, 'token', recordings, existing, rows, [], firestore_client=client, bounded_pending_limit=32
        )

    del leases
    return commit, executions, closure_reads, client


# One recording and three loaded rows, reread by every run of a batch's body; a later batch's fence also rereads
# the rows the batches before it committed (four here).
CLOSURE = 4


@pytest.mark.parametrize('listed', [True, False])
def test_a_listed_owners_batches_never_replay_for_cold_pointers(
    lake_world, lake_commit, monkeypatch, listed
):  # noqa: F811
    commit, executions, closure_reads, client = lake_commit
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*' if listed else '')
    commit([shared_row(i) for i in range(8)])
    written = sorted(
        p[3] for p in client.rows if len(p) == 4 and p[2] == 'conversations' and p[3].startswith('shared-')
    )
    assert written == sorted(f'shared-{i}' for i in range(8))
    if listed:
        # Each batch ran its body once: its four pointers were loaded before the transaction (lake reads only).
        assert executions == [4, 4] and closure_reads == [CLOSURE, CLOSURE + 4]
    else:
        # Unlisted owners keep main's path unchanged: the second batch's four cold pointers replay its body.
        assert executions == [4] + [4] * 5 and closure_reads == [CLOSURE] + [CLOSURE + 4] * 5


def test_a_locked_batch_that_would_replay_past_three_runs_parks_before_reading_again(
    lake_world, lake_commit, monkeypatch  # noqa: F811
):
    # If the preload is ever defeated (expired or evicted), the body guard still holds the bound: at most
    # LOCKED_BATCH_EXECUTIONS runs (each one closure read) per batch, then the pass parks on the derived budget.
    commit, executions, closure_reads, client = lake_commit
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    # Defeat the preload: the memo is fresh but empty, so all four of the first batch's pointers are cold.
    monkeypatch.setattr(store, '_preload_batch_pointers', lambda uid, batch: store.transcript_pointer.clear_memo())
    with pytest.raises(Conflict, match='v3_derived_budget'):
        commit([shared_row(i) for i in range(8)])
    assert store.LOCKED_BATCH_EXECUTIONS == 3
    assert executions == [4] * 4  # three runs, then the fourth, which parks at once
    assert closure_reads == [CLOSURE] * 3  # three runs read the closure; the fourth parked before any read
    assert not any(p[3].startswith('shared-') for p in client.rows if len(p) == 4 and p[2] == 'conversations')


# ---- custody panel review-20261127t033437-067e ------------------------------------------------------------------


def test_small_shared_rows_stay_inline_and_three_hundred_of_them_commit(lake_world, heavy):  # noqa: F811
    # F1/F5: shared rows under the 4 KiB inline threshold are not pointers. 300 of them fit one batch; counting them
    # as pointers (32 a batch) would have estimated 10 batches and parked the owner for good.
    commit, partitions = heavy
    with pytest.raises(FirstTransaction):
        commit([shared_row(i, small=True) for i in range(300)])
    assert partitions == [1, 1]
    assert lake_world.calls['put'] == 0 and lake_objects(lake_world) == []


def test_a_mixed_closure_is_estimated_at_exactly_its_real_batch_count(lake_world, heavy, monkeypatch):  # noqa: F811
    # F1/F4/F5: four offloaded shared rows, four small shared rows and four private rows, two pointers a batch. Only
    # the offloaded rows are pointers: two batches, estimated and real. A superset would have counted eight.
    commit, partitions = heavy
    monkeypatch.setattr(store, 'MAX_PRELOAD_DOCUMENTS', 2)
    rows = []
    for i in range(4):
        rows += [shared_row(i), shared_row(i, small=True), shared_row(i, visibility='private')]
    with pytest.raises(FirstTransaction):
        commit(rows)
    assert partitions == [2, 2]
    assert len(lake_objects(lake_world)) == 4


def test_a_settle_refusal_comes_before_any_upload(lake_world, heavy, monkeypatch):  # noqa: F811
    # F2: settling must be one commit; with five writes a batch, four rows plus the recording, the settle and the
    # lease do not fit. The refusal now comes from the deferred partition, before any lake write.
    commit, partitions = heavy
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 5)
    with pytest.raises(Conflict, match='request_too_large'):
        commit([shared_row(i) for i in range(4)], settle={'l0': {'status': 'completed', 'home_hidden': True}})
    assert lake_world.calls['put'] == 0 and lake_objects(lake_world) == []


def test_the_backstop_still_parks_when_the_real_partition_exceeds_the_cap(lake_world, heavy, monkeypatch):  # noqa: F811
    # F4: unreachable while the stand-ins bound the real pointers; forced here by an estimate that under-counts.
    # The uploads already exist in this branch (left for the lake's orphan janitor, SCA-4941).
    commit, partitions = heavy
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 3)
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 3)
    real = store.partition_rows
    calls = []

    def under_counting(*args, **kwargs):
        batches = real(*args, **kwargs)
        calls.append(len(batches))
        return batches[:1] if len(calls) == 1 else batches

    monkeypatch.setattr(store, 'partition_rows', under_counting)
    with pytest.raises(store.LockedBatchCap):
        commit([shared_row(i) for i in range(4)])
    assert calls == [4, 4] and len(lake_objects(lake_world)) == 4


def test_a_deferred_stand_in_is_a_valid_pointer_no_smaller_than_the_real_one(lake_world):  # noqa: F811
    # F6: the stand-in parses under object_lake's own limits, and its encoding bounds the real pointer's.
    with transcript_pointer.deferred_offloads() as pending:
        doc = encode()
    stand_in = doc['transcript_segments']
    ref = object_lake.LakeObjectRef.from_pointer_dict(stand_in)
    assert ref.bytes == object_lake.MAX_PLAINTEXT_BYTES['transcript'] + 65536 and ref.dek_version == 0xFFFFFFFF
    assert len(pending) == 1 and lake_world.calls['put'] == 0
    transcript_pointer.upload_deferred(pending, [doc])
    real = doc['transcript_segments']
    assert real['key'] != stand_in['key'] and lake_world.calls['put'] == 1
    assert encoded_bytes(stand_in) >= encoded_bytes(real)
    assert len(lake_objects(lake_world)) == 1


def test_the_write_codec_runs_once_per_row_so_the_estimate_adds_no_side_effects(
    lake_world, heavy, monkeypatch
):  # noqa: F811
    # F3: no second, dry codec pass. Its fallbacks, warnings and decrypt logging happen at most as often as on main.
    commit, partitions = heavy
    calls = []
    real = store.conversations._prepare_conversation_for_write

    def counted(data, *a, **kw):
        calls.append(data.get('id'))
        return real(data, *a, **kw)

    monkeypatch.setattr(store.conversations, '_prepare_conversation_for_write', counted)
    with pytest.raises(FirstTransaction):
        commit([shared_row(i) for i in range(4)] + [shared_row(i, small=True) for i in range(4)])
    assert len(calls) == 8 and len(set(calls)) == 8
    assert partitions == [1, 1] and len(lake_objects(lake_world)) == 4


# ---- deferred panel minors (review-20261127t050745-babe F2) ------------------------------------------------------


def test_a_failed_batch_preload_releases_the_decoded_plaintext_and_re_raises(monkeypatch):
    # The first pointer loads (decoded plaintext enters the memo), the second fails: nothing decoded may stay behind.
    loaded = []

    def preload(uid, pointer):
        if pointer['n'] == 2:
            raise transcript_pointer.TranscriptPointerFetchError('lake unavailable')
        transcript_pointer._memo().decoded[(uid, pointer['n'])] = [{'text': 'decoded speech'}]
        loaded.append(pointer['n'])

    monkeypatch.setattr(transcript_pointer, 'preload_pointer', preload)
    batch = [{'transcript_segments': {'n': n}} for n in (1, 2, 3)] + [{'transcript_segments': 'inline'}]
    with pytest.raises(transcript_pointer.TranscriptPointerFetchError):
        store._preload_batch_pointers(UID, batch)
    assert loaded == [1]
    assert transcript_pointer._MEMO.get() is None  # cleared before the error propagated


def test_a_successful_batch_preload_keeps_every_pointer_warm(monkeypatch):
    monkeypatch.setattr(
        transcript_pointer,
        'preload_pointer',
        lambda uid, pointer: transcript_pointer._memo().decoded.__setitem__((uid, pointer['n']), [{'text': 'x'}]),
    )
    store._preload_batch_pointers(UID, [{'transcript_segments': {'n': n}} for n in (1, 2)])
    assert set(transcript_pointer._MEMO.get().decoded) == {(UID, 1), (UID, 2)}
    transcript_pointer.clear_memo()
