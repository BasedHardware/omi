"""Estimated-clock offline audio never merges across a real recording gap.

Regression for the cross-day merge: when the pendant gives no trustworthy
recording time, the app stamps a download as ``now - duration`` and lays its
60-second chunks end to end. Audio recorded on different days then arrives with
adjacent invented timestamps, and temporal assignment (120 s gap rule) stitched
it into one conversation. The app now names each contiguous recording run in
the filename (``_clke<run>_``); the run is a capture partition.
"""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.smart_merge_policy import partition
from utils.request_validation import parse_sync_filename_timestamp
from utils.sync.assignment import assign_in_transaction, capture_mismatch
from utils.sync.capture import chunk_identity
from utils.sync.clock_run import SYNC_CLOCK_RUN_FIELD, clock_run_from_path, segment_name_prefix
from utils.sync.live_overlap import compatible_capture

# One sync at 2026-10-16 13:38Z that downloads audio recorded on three days.
SYNC_AT = 1792157893


@pytest.fixture(scope='module', autouse=True)
def load_dependencies():
    # Imports belong to fixture setup, not the fast-unit behavior timing budget.
    from database import conversations  # noqa: F401
    from models import conversation  # noqa: F401


def piece(key, timestamp, run=None, text='We talked through the rollout plan in detail.'):
    row = {
        'id': key,
        'started_at': datetime.fromtimestamp(timestamp, timezone.utc),
        'finished_at': datetime.fromtimestamp(timestamp + 55, timezone.utc),
        'source': 'omi',
        'client_device_id': 'ios_pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [{'start': 0.0, 'end': 55.0, 'text': text, 'speaker_id': 0, 'is_user': False}],
    }
    if run:
        row[SYNC_CLOCK_RUN_FIELD] = run
    return row


def intake(store, incoming, *, target_id=None):
    with store.lock:
        return assign_in_transaction(
            store.transaction(),
            store.collection('users').document('u'),
            incoming,
            target_id=target_id,
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda payload: None,
        )


def conversations(store):
    return [value for key, value in store.rows.items() if key[2] == 'conversations' and not value.get('deleted')]


def test_estimated_runs_from_different_days_stay_separate_conversations():
    """Three recordings (different days) whose invented stamps sit end to end."""
    store = StrictFirestore()
    # The app's estimate packs run 1 (day 1), run 2 (day 3) and run 3 (day 5)
    # into the hour before the sync, 60 s apart: under the 120 s merge gap.
    for index, run in enumerate(('day1', 'day1', 'day3', 'day3', 'day5')):
        intake(store, piece(f'p{index}', SYNC_AT - 3600 + 60 * index, run=run))

    rows = conversations(store)
    assert sorted(row[SYNC_CLOCK_RUN_FIELD] for row in rows) == ['day1', 'day3', 'day5']
    for row in rows:
        merged = set(row.get('sync_merged_from') or ())
        assert all(cid in {'p0', 'p1', 'p2', 'p3', 'p4'} for cid in merged)
    by_run = {row[SYNC_CLOCK_RUN_FIELD]: row for row in rows}
    assert len(by_run['day1']['transcript_segments']) == 2
    assert len(by_run['day3']['transcript_segments']) == 2
    assert len(by_run['day5']['transcript_segments']) == 1


def test_untagged_adjacent_pieces_still_merge_like_before():
    """Device-clocked (untagged) pieces keep the 120 s adjacency rule; this is
    also exactly how the estimated cross-day pieces merged before the fix."""
    store = StrictFirestore()
    for index in range(3):
        intake(store, piece(f'p{index}', SYNC_AT - 3600 + 60 * index))
    rows = conversations(store)
    assert len(rows) == 1
    assert len(rows[0]['transcript_segments']) == 3


def test_kill_switch_restores_previous_behaviour(monkeypatch):
    monkeypatch.setenv('SYNC_CLOCK_RUN_PARTITION_ENABLED', 'false')
    assert clock_run_from_path('audio_x_opus_16000_1_fs160_clkeab12_1792157893.bin') is None
    assert segment_name_prefix('audio_x_opus_16000_1_fs160_clkeab12_1792157893.bin') == ''


def test_estimated_piece_never_joins_overlapping_device_clocked_conversation():
    """A stale clock can overlap real audio; overlap of invented time is not proof."""
    store = StrictFirestore()
    intake(store, piece('real', SYNC_AT - 600))
    intake(store, piece('stale', SYNC_AT - 590, run='reboot2'))
    rows = conversations(store)
    assert len(rows) == 2
    assert {row.get(SYNC_CLOCK_RUN_FIELD) for row in rows} == {None, 'reboot2'}


def test_clock_run_is_a_capture_partition_everywhere():
    trusted = {'source': 'omi', 'client_device_id': 'd', 'is_locked': False}
    estimated = {**trusted, SYNC_CLOCK_RUN_FIELD: 'r1'}
    other = {**trusted, SYNC_CLOCK_RUN_FIELD: 'r2'}
    assert compatible_capture(trusted, dict(trusted))
    assert compatible_capture(estimated, dict(estimated))
    assert not compatible_capture(trusted, estimated)
    assert not compatible_capture(estimated, other)
    assert capture_mismatch(trusted, estimated) == 'clock'
    assert capture_mismatch(estimated, other) == 'clock'
    assert partition(estimated) != partition(other) != partition(trusted)
    # Two runs can share an invented timestamp; they must not share an anchor.
    assert chunk_identity('u', 'omi', 'd', False, 100.0, clock_run='r1') != chunk_identity(
        'u', 'omi', 'd', False, 100.0, clock_run='r2'
    )
    assert chunk_identity('u', 'omi', 'd', False, 100.0) == chunk_identity('u', 'omi', 'd', False, 100.0)


@pytest.mark.parametrize(
    'name, run',
    [
        ('audio_omi_opus_16000_1_fs160_clke9f3a_1792157893.bin', '9f3a'),
        ('syncing/u/job/audio_omi_opus_16000_1_fs160_1792157893.bin', None),
        ('syncing/u/job/clke9f3a_1792157893.5.wav', '9f3a'),
        ('syncing/u/job/dup1_clke9f3a_1792157893.5.wav', '9f3a'),
        ('syncing/u/job/1792157893.5.wav', None),
        # Never parsed from the device-name part or from text that is not a token.
        ('audio_clkeab_opus_16000_1_fs160_1792157893.bin', None),
        ('audio_xclkeab_opus_16000_1_fs160_1792157893.bin', None),
        ('audio_omi_opus_16000_1_fs160_clkeAB_1792157893.bin', None),
    ],
)
def test_clock_token_parsing_keeps_the_trailing_timestamp(name, run):
    assert clock_run_from_path(name) == run
    assert parse_sync_filename_timestamp(name) in (1792157893, 1792157893.5)


def test_segment_prefix_round_trips_into_segment_filename():
    source = 'syncing/u/job/audio_omi_opus_16000_1_fs160_clke9f3a_1792157893.bin'
    segment = f'syncing/u/job/{segment_name_prefix(source)}1792157900.25.wav'
    assert clock_run_from_path(segment) == '9f3a'
    assert parse_sync_filename_timestamp(segment) == 1792157900.25
