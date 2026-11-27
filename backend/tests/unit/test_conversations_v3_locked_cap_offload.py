"""A locked-closure batch-cap rejection never leaves offloaded transcript copies behind (custody, SCA-2918).

commit_projection decides the cap for a closure past the origin bound before preparation can upload a transcript to
the object lake: the estimate prepares inline and counts every row that might offload as a pointer at least as large
as either form, so a rejected attempt uploads nothing.
"""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store
from tests.unit.test_transcript_pointer import UID, lake_world, speech  # noqa: F401
from utils.conversations.v3 import Conflict

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class FirstTransaction(Exception):
    """Stands in for the first commit transaction: everything before it (preparation included) has run."""


def lake_objects(world):
    return list(world.bucket.list_blobs(prefix=f'v1/spaces/{UID}/transcript/'))


def shared_row(index, *, visibility='shared'):
    start = T0 + timedelta(minutes=index)
    return {
        'id': f'shared-{index}',
        'status': 'completed',
        'visibility': visibility,
        'started_at': start,
        'finished_at': start + timedelta(seconds=10),
        'v3_recording_ids': ['r'],
        # Random hex does not compress under the 4 KiB inline threshold, so preparation offloads it.
        'transcript_segments': speech(),
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

    def commit(rows):
        return store.commit_projection(UID, 'token', recordings, existing, rows, [], firestore_client=lake_world.store)

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
