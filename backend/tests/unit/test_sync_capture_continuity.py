"""Behavioral regression for the 2026-09-19 45-WAL speech fragmentation.

The strict store checks transaction read ordering; randomized schedules model
successful serial commit orders, not emulator contention or external services.
"""

from copy import deepcopy
import random
from unittest.mock import MagicMock

import pytest

from utils.sync.assignment_errors import SyncAssignmentSuperseded

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, intake, conversations
from utils.sync.assignment import interval_matches
from utils.transcribe_decisions import decide_existing_conversation_action, ConversationLifecycleAction


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations
    from tests.unit.test_conversation_discard_revival import _persist


def capture(i):
    row = chunk(f'chunk-{i:03}', 1000 + i * 70)
    row['finished_at'] = chunk('end', 1000 + (i + 1) * 70)['started_at']
    row['transcript_segments'] = [dict(row['transcript_segments'][0], end=70)]
    return row


def signature(store):
    return sorted(
        (
            row['started_at'],
            row['finished_at'],
            [
                (
                    row['started_at'].timestamp() + seg['start'],
                    row['started_at'].timestamp() + seg['end'],
                    seg['text'],
                )
                for seg in row['transcript_segments']
            ],
        )
        for row in conversations(store)
    )


def arrival_order(seed):
    order = list(range(45))
    if seed == 0:
        # Newest-first batches, each independently ascending within a server job.
        order = [i for end in range(45, 0, -5) for i in range(end - 5, end)]
    elif seed == 1:
        # Two jobs overlap: HTTP 202 permits the next newest-first batch to
        # start while the previous job still assigns its chunks oldest-first.
        pending = [list(range(end - 5, end)) for end in range(45, 0, -5)]
        active = [pending.pop(0), pending.pop(0)]
        order = []
        rng = random.Random(seed)
        while active:
            job = rng.choice(active)
            order.append(job.pop(0))
            if not job:
                active.remove(job)
                if pending:
                    active.append(pending.pop(0))
    else:
        # Arbitrary cross-job arrival, including timed-out ordering optimizations.
        random.Random(seed).shuffle(order)
    return order


@pytest.mark.parametrize('seed', range(12))
def test_capture_partition_and_content_are_permutation_invariant(seed):
    expected = StrictFirestore()
    actual = StrictFirestore()
    rows = [capture(i) for i in range(45)]
    for row in rows:
        intake(expected, row)
    order = arrival_order(seed)
    for i in order:
        intake(actual, rows[i])
    assert signature(actual) == signature(expected)
    assert len(conversations(actual)) == 1
    assert len(conversations(actual)[0]['transcript_segments']) == 45
    before = signature(actual)
    for i in order:
        intake(actual, rows[i])
    assert signature(actual) == before


@pytest.mark.parametrize('level', ['standard', 'enhanced', None])
def test_bridge_roundtrips_real_codecs_and_fences_both_processors(monkeypatch, level):
    from database import conversations as db
    from tests.unit.test_conversation_discard_revival import _persist

    store = StrictFirestore()
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *a: None)
    rows = [capture(0), capture(4), capture(2)]
    for row in rows:
        row['data_protection_level'] = level
        db.assign_sync_conversation('u', row, firestore_client=store)
    active = conversations(store)
    assert len(active) == 1
    survivor = active[0]
    assert survivor['id'] == 'chunk-000'
    assert survivor['data_protection_level'] == (level or 'enhanced')
    assert isinstance(survivor['transcript_segments'], bytes if level == 'standard' else str)
    decoded = db._decode_transcript_segments_strict('u', survivor['transcript_segments'], True)
    assert [seg['start'] for seg in decoded] == [0, 140, 280]
    for cid in ('chunk-000', 'chunk-004'):
        persisted, ref = _persist(monkeypatch, store.rows[('users', 'u', 'conversations', cid)])
        assert not persisted and ref.written is None


@pytest.mark.parametrize(
    'field,value',
    [
        ('deleted', True),
        ('is_locked', True),
        ('source', 'desktop'),
        ('client_device_id', 'other'),
        ('client_device_id', None),
    ],
)
def test_bridge_isolates_incompatible_donors(field, value):
    store = StrictFirestore()
    intake(store, capture(0))
    other = capture(4)
    other[field] = value
    intake(store, other)
    # User deletion happens after persistence, unlike a client request.
    if field == 'deleted':
        store.rows[('users', 'u', 'conversations', other['id'])]['deleted'] = True
    intake(store, capture(2))
    left = next(row for row in conversations(store) if row['id'] == 'chunk-000')
    assert len(left['transcript_segments']) == 2
    assert len(conversations(store)) == (1 if field == 'deleted' else 2)


def test_historical_index_and_midnight_bridge_do_not_depend_on_recent_cache():
    store = StrictFirestore()
    left = chunk('a', 86300)
    left['finished_at'] = chunk('end', 86370)['started_at']
    right = chunk('c', 86510)
    intake(store, left)
    intake(store, right)
    store.rows[('users', 'u', 'sync_assignment', 'recent')] = {'entries': []}
    intake(store, chunk('b', 86440))
    assert len(conversations(store)) == 1
    assert len(conversations(store)[0]['transcript_segments']) == 3


def test_missing_capture_target_does_not_bind_far_apart_chunks_or_revive_deletion():
    store = StrictFirestore()
    first, _, _ = intake(store, capture(0), target_id='client-capture')
    later, _, _ = intake(store, capture(44), target_id='client-capture')
    assert first['id'] != later['id']
    assert len(conversations(store)) == 2
    assert ('users', 'u', 'conversations', 'client-capture') not in store.rows
    deleted = dict(capture(20), id='client-capture', deleted=True)
    store.rows[('users', 'u', 'conversations', 'client-capture')] = deepcopy(deleted)
    result, _, _ = intake(store, capture(20), target_id='client-capture')
    assert result['id'] != 'client-capture'
    assert store.rows[('users', 'u', 'conversations', 'client-capture')] == deleted


@pytest.mark.parametrize('gap', [0, 119.99, 120, 120.01, 121])
def test_realtime_and_sync_share_exact_gap_boundary(gap):
    left = chunk('a', 1000)
    right = chunk('b', left['finished_at'].timestamp() + gap)
    action = decide_existing_conversation_action(seconds_since_last_segment=gap, conversation_creation_timeout=120)
    assert interval_matches(left, right) == (action == ConversationLifecycleAction.continue_current)


def test_both_paths_consult_the_policy_function(monkeypatch):
    from utils import conversation_continuity

    calls = []

    def split(seconds, timeout=120):
        calls.append(seconds)
        return True

    monkeypatch.setattr(conversation_continuity, 'gap_splits', split)
    assert not interval_matches(capture(0), capture(1))
    assert (
        decide_existing_conversation_action(seconds_since_last_segment=0, conversation_creation_timeout=120)
        == ConversationLifecycleAction.process_and_create_new
    )
    assert calls == [0, 0]


def test_retry_of_absorbed_chunk_cannot_resurrect_deleted_survivor():
    store = StrictFirestore()
    intake(store, capture(0))
    intake(store, capture(4))
    intake(store, capture(2))
    store.rows[('users', 'u', 'conversations', 'chunk-000')]['deleted'] = True
    with pytest.raises(SyncAssignmentSuperseded, match='lineage was deleted'):
        intake(store, capture(4))
    assert not conversations(store)


def test_discarded_filler_remains_recoverable_and_hidden():
    store = StrictFirestore()
    row = chunk('filler', 1000, text='Hmm.')
    row['discarded'] = True
    result, _, _ = intake(store, row)
    assert result['discarded'] and result['sync_relevance'] == 'review'
    assert result['transcript_segments'][0]['text'] == 'Hmm.'
    assert not result.get('deleted')


@pytest.mark.parametrize(
    'field,value',
    [('has_photos', True), ('user_title', 'My title'), ('visibility', 'public'), ('sync_live_target', True)],
)
def test_auto_bridge_preserves_user_managed_and_live_donors(field, value):
    store = StrictFirestore()
    intake(store, capture(0))
    intake(store, capture(4))
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    donor[field] = value
    result, _, _ = intake(store, capture(2))
    assert len(result['transcript_segments']) == 2
    assert not donor.get('deleted')
    assert len(conversations(store)) == 2
    with pytest.raises(SyncAssignmentSuperseded, match='user managed'):
        intake(store, capture(4))


@pytest.mark.parametrize('seed', [0, 1, 9])
def test_nearest_empty_stubs_never_split_unbound_newest_first_or_interleaved_wals(seed):
    store = StrictFirestore()
    for i in range(45):
        stub = capture(i)
        stub.update(id=f'stub-{i}', status='in_progress', transcript_segments=[])
        store.rows[('users', 'u', 'conversations', stub['id'])] = stub
    for i in arrival_order(seed):
        intake(store, capture(i), candidate_id=f'stub-{i}')
    with_content = [row for row in conversations(store) if row.get('transcript_segments')]
    assert len(with_content) == 1
    assert len(with_content[0]['transcript_segments']) == 45


def test_partial_flap_explicit_existing_targets_remain_separate_documented_limit():
    store = StrictFirestore()
    for i in range(3):
        stub = capture(i)
        stub.update(id=f'stub-{i}', status='in_progress', transcript_segments=[])
        store.rows[('users', 'u', 'conversations', stub['id'])] = stub
    for i in (2, 0, 1):
        intake(store, capture(i), target_id=f'stub-{i}')
    with_content = [row for row in conversations(store) if row.get('transcript_segments')]
    # This deliberately proves the remaining limitation; it does not bless it
    # as the desired product contract. Historical distinct live targets need a
    # recording-lineage migration, not an unsafe timestamp-based merge.
    assert len(with_content) == 3
    assert all(row.get('sync_live_target') for row in with_content)
