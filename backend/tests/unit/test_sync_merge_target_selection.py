"""Synced audio must never merge into a soft-deleted conversation (#10033).

`get_closest_conversation_to_timestamps` matched any row in the ±2min window —
including `deleted: True` tombstones — so offline audio recorded near a
conversation the user later deleted merged into the tombstone and vanished:
the "recordings never create a conversation" symptom. The closest-match choice
is now a pure selector over eligible merge targets, and the auto-sync
target-attach path consults the same predicate.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from database.conversations import eligible_merge_target, select_closest_conversation


@pytest.fixture(scope="module", autouse=True)
def warm_pipeline():
    from utils.sync import pipeline
    from utils.conversations import lifecycle


_BASE = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _conversation(conversation_id: str, *, offset_seconds: int = 0, deleted: bool = False) -> dict:
    started = _BASE + timedelta(seconds=offset_seconds)
    return {
        'id': conversation_id,
        'started_at': started,
        'finished_at': started + timedelta(seconds=60),
        'deleted': deleted,
    }


def test_deleted_tombstone_is_never_a_merge_target():
    target = int(_BASE.timestamp())
    only_deleted = [_conversation('gone', deleted=True)]
    assert select_closest_conversation(only_deleted, target, target + 60) is None

    # A deleted row closer than a live one must lose to the live one.
    rows = [_conversation('gone', deleted=True), _conversation('live', offset_seconds=90)]
    chosen = select_closest_conversation(rows, target, target + 60)
    assert chosen is not None and chosen['id'] == 'live'


def test_closest_live_conversation_wins_by_boundary_distance():
    target = int((_BASE + timedelta(seconds=95)).timestamp())
    rows = [_conversation('near', offset_seconds=90), _conversation('far', offset_seconds=600)]
    chosen = select_closest_conversation(rows, target, target + 60)
    assert chosen is not None and chosen['id'] == 'near'
    assert select_closest_conversation([], target, target + 60) is None


def test_eligible_merge_target_predicate():
    assert eligible_merge_target(_conversation('live')) is True
    assert eligible_merge_target(_conversation('gone', deleted=True)) is False
    assert eligible_merge_target(None) is False
    # Discarded rows stay eligible: the merge path reprocesses and revives them.
    discarded = _conversation('quiet')
    discarded['discarded'] = True
    assert eligible_merge_target(discarded) is True


@patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='url')
@patch('utils.sync.pipeline.schedule_syncing_temporal_file_deletion')
@patch('utils.sync.pipeline.prerecorded', return_value=(['word'], 'en'))
@patch('utils.sync.pipeline.postprocess_words')
@patch('utils.sync.pipeline.conversations_db.get_conversation', return_value={'id': 'deleted', 'deleted': True})
@patch('utils.sync.pipeline.get_timestamp_from_path', return_value=123)
@patch('utils.sync.pipeline.get_closest_conversation_to_timestamps', side_effect=RuntimeError("FALLBACK_TAKEN"))
def test_sync_target_attach_preserves_identity_and_excludes_deleted(
    mock_closest, mock_timestamp, mock_get_conv, mock_postprocess, mock_prerecorded, mock_schedule, mock_signed_url
):
    """The transaction now owns deletion/absence, not a lossy preflight fallback.

    The 2026-09-19 capture evidence requires retaining the supplied identity;
    the original assertion that deleted content never absorbs speech remains.
    """
    from models.transcript_segment import TranscriptSegment
    from utils.sync.pipeline import process_segment
    from tests.unit.test_sync_cross_job_assignment import intake, chunk
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore()
    store.rows[('users', 'u', 'conversations', 'deleted')] = {**chunk('deleted', 123), 'deleted': True}
    mock_postprocess.return_value = [TranscriptSegment(text='Retain this speech', start=0, end=1, is_user=False)]
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    with patch('utils.sync.pipeline.get_wav_duration', return_value=60), patch(
        'utils.conversations.lifecycle.ingest_sync_conversation',
        side_effect=lambda uid, incoming, **kw: intake(store, incoming, **kw),
    ), patch('utils.sync.pipeline.identify_speakers_for_segments'):
        result = process_segment('seg_123.wav', 'u', response, MagicMock(), errors, target_conversation_id='deleted')
    assert result and errors == []
    mock_closest.assert_not_called()
    assert 'deleted' not in response['new_memories']
    assert store.rows[('users', 'u', 'conversations', 'deleted')]['deleted']
