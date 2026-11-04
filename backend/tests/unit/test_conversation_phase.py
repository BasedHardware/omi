"""Legacy contradictory shapes, deterministic precedence, and malformed field inventory."""

from copy import deepcopy
from datetime import datetime, timezone
import random

import pytest

from utils.conversations.phase import ConversationPhase as C, EpisodePhase as E
from utils.conversations.phase import derive_conversation_phase, derive_episode_phase

BATCH = {'status': 'completed', 'record_lane_owner': 'batch_live_v1', 'finalization_status': 'queued'}
SUMMARY = {'status': 'completed', 'summary_output_present': True}
MINIMUM = {'structured': {'title_provenance': 'server_minimum'}, 'summary_blocked_reason': 'content_below_floor'}


@pytest.mark.parametrize(
    'row,episode,expected',
    [
        ({}, None, C.CAPTURING),
        ({'status': 'unknown'}, None, C.CAPTURING),
        (BATCH, None, C.CAPTURING),  # Nov 3 completed + queued + no transcript + unsealed.
        ({**BATCH, 'record_audio_closed': True}, None, C.SEALED),
        (
            {
                **BATCH,
                'record_audio_closed': True,
                'transcript_segments': [{'text': 'provisional'}],
                'summary_output_present': True,
            },
            None,
            C.SEALED,
        ),
        ({**BATCH, 'record_audio_closed': True, 'record_upload_sessions': {'producer': True}}, None, C.CAPTURING),
        ({**BATCH, 'record_audio_closed': True, 'record_audio_partial': True}, None, C.CAPTURING),
        ({'record_lane_owner': 'batch_live_v1'}, None, C.CAPTURING),  # Owner, no job.
        ({**BATCH, 'record_audio_closed': True, 'processing_admitted_at': 100}, None, C.SEALED),
        ({**BATCH, 'status': 'processing'}, None, C.PROCESSING),
        ({**BATCH, 'record_projection_revision': 1}, None, C.TRANSCRIBED),
        ({**BATCH, 'record_projection_revision': 1, 'summary_output_present': True}, None, C.SETTLED),
        ({**SUMMARY, 'discarded': True, 'episode_id': 'ep'}, {'status': 'closed'}, C.DISCARDED),
        ({**SUMMARY, 'finalization_status': 'dead_letter'}, None, C.DEAD_LETTER),
        ({**SUMMARY, 'finalization_status': 'dead_letter', 'discarded': True}, None, C.DISCARDED),
        ({**SUMMARY, 'sync_merged_into': 'survivor', 'discarded': True}, None, C.MERGED),
        ({'deleted': True, 'discarded': True, 'status': 'failed'}, None, C.MERGED),
        ({'status': 'failed', 'finalization_status': 'dead_letter'}, None, C.DEAD_LETTER),
        ({'record_upload_failed': True, 'record_audio_closed': True}, None, C.FAILED),
        ({'status': 'completed', **MINIMUM}, None, C.SETTLED),
        ({'status': 'completed', **MINIMUM, 'episode_id': 'ep'}, None, C.COMPLETE),
        (
            {
                'status': 'completed',
                'structured': {'title_provenance': 'server_minimum'},
                'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'},
            },
            None,
            C.SETTLED,
        ),
        ({'status': 'completed', 'structured': {'title_provenance': 'server_minimum'}}, None, C.CAPTURING),
        (
            {'status': 'completed', 'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule'}},
            None,
            C.DISCARDED,
        ),
        ({**SUMMARY, 'relevance_decision': {'verdict': 'discard'}, 'sync_relevance_user_kept': True}, None, C.SETTLED),
        ({**SUMMARY, 'discarded': True, 'sync_relevance_user_kept': True}, None, C.DISCARDED),
        ({'status': 'processing', 'transcript_segments': [{'text': 'accepted text'}]}, None, C.TRANSCRIBED),
        ({'status': 'processing', 'transcript_segments': [{'text': '   '}]}, None, C.PROCESSING),
        ({'finalization_status': 'blocked_byok'}, None, C.PROCESSING),
        ({'status': 'completed', 'processing_state': 'local_pending'}, None, C.SETTLED),
        ({'status': 'completed', 'summary_blocked_reason': 'local_only', 'episode_id': 'ep'}, None, C.COMPLETE),
        ({'status': 'completed', 'structured': {'overview': 'Summary'}}, None, C.SETTLED),
        ({'structured': {'sections': [{'body_markdown': 'Notes'}]}}, None, C.SETTLED),
        (SUMMARY, {'status': 'closed'}, C.COMPLETE),
        ({**SUMMARY, 'episode_id': 'ep'}, None, C.COMPLETE),
        ({**SUMMARY, 'episode_id': 'ep'}, {'status': 'closed'}, C.COMPLETE),
        ({**SUMMARY, 'episode_id': 'ep'}, {'status': 'closed', 'composed_fingerprint': 'fp'}, C.SETTLED),
        (
            {**SUMMARY, 'episode_id': 'ep'},
            {'status': 'live', 'composed_fingerprint': 'old', 'closed_at': 1},
            C.COMPLETE,
        ),
        ({'phase': 'settled'}, None, C.CAPTURING),  # Independent of future dual-write field.
    ],
)
def test_contradictions(row, episode, expected):
    before = deepcopy((row, episode))
    assert derive_conversation_phase(row, episode) == expected
    assert (row, episode) == before


@pytest.mark.parametrize(
    'row,expected',
    [
        ({}, E.LIVE),
        ({'status': 'unknown'}, E.LIVE),
        ({'status': 'live', 'closed_at': 1, 'composed_fingerprint': 'stale'}, E.LIVE),
        ({'status': 'live', 'wrap_up_requested_at': 1}, E.CLOSING),
        ({'closing_conversation_id': 'c'}, E.CLOSING),
        ({'status': 'closed', 'wrap_up_requested_at': 1}, E.CLOSED),
        ({'closed_at': 1}, E.CLOSED),
        ({'status': 'closed', 'composed_fingerprint': 'fp'}, E.COMPOSED),
        ({'status': 'closed', 'composed_fingerprint': 'fp', 'summary_needs_regeneration': True}, E.CLOSED),
        ({'status': 'live', 'recorded_merged_into': 'survivor'}, E.REDIRECTED),
    ],
)
def test_episode_precedence(row, expected):
    before = deepcopy(row)
    assert derive_episode_phase(row) == expected
    assert row == before


# Stored field inventory; every value is also tried in the wrong field, including
# unhashable maps/lists, malformed nested sections/segments, and legacy timestamps.
FIELDS = '''status finalization_status finalization_job_id finalization_revision record_lane_owner
record_audio_closed record_upload_sessions record_upload_failed record_audio_partial record_projection_revision
server_batch_audio_start server_batch_audio_end server_batch_audio_received server_batch_audio_closed
discarded relevance_decision sync_relevance sync_relevance_user_kept structured transcript_segments
summary_first_pending_at summary_due_at summary_completed_at summary_title_provenance summary_output_present
summary_blocked_reason summary_discard_receipted episode_id deleted is_deleted sync_merged_into
processing_state deferred client_processing starred photos has_photos user_title folder_user_set
started_at finished_at processing_admitted_at closed_at composed_at composed_fingerprint
closing_conversation_id wrap_up_requested_at recorded_merged_into summary_needs_regeneration'''.split()
VALUES = [
    None,
    True,
    False,
    0,
    -1,
    1.5,
    '',
    'completed',
    'processing',
    'queued',
    'dead_letter',
    'failed',
    'batch_live_v1',
    'live',
    'closed',
    {},
    [],
    {'verdict': 'discard'},
    ['bad'],
    {'overview': 'notes', 'sections': [None, {'body_markdown': 3}]},
    [{'text': 'hello'}, None, {'text': []}],
    datetime(2026, 11, 3, tzinfo=timezone.utc),
]


@pytest.mark.parametrize('seed', range(10))
def test_random_inventory_is_total_and_deterministic(seed):
    rng = random.Random(seed)
    for _ in range(300):
        row = {key: rng.choice(VALUES) for key in rng.sample(FIELDS, rng.randrange(len(FIELDS) + 1))}
        episode = {key: rng.choice(VALUES) for key in rng.sample(FIELDS, 10)}
        first = derive_conversation_phase(row, episode)
        assert isinstance(first, C)
        assert derive_conversation_phase(row, episode) == first
        assert isinstance(derive_episode_phase(episode), E)
