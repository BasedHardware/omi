"""Exact offline server outputs for fictional abstention fixtures; no provider IO."""

from copy import deepcopy
from datetime import datetime, timezone
import os
from types import SimpleNamespace as NS
from unittest.mock import patch

from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.speaker_abstention import speaker_cases
from utils import review
from utils.conversations import render, transcript_for_llm as llm
from utils.conversations.analytics import build_conversation_analytics
from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
from utils.episodes import incremental
from utils.mcp_server.helpers import bounded_transcript_segments

FLAG = 'SPEAKER_ABSTENTION_UNKNOWN_LABEL_ENABLED'


def server_outputs(case):
    rows, ids = speaker_cases()[case]
    resolution = {'status': 'capture', 'participant_speaker_ids': ids}
    payload = {'transcript_segments': deepcopy(rows), 'speaker_resolution': resolution}
    conversation = NS(
        id='fictional-garden', transcript_segments=[TranscriptSegment(**r) for r in rows], speaker_resolution=resolution
    )
    started = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    prompt = NS(
        conversation_id=conversation.id,
        segment_ids=[rows[1]['id']],
        id='fictional-prompt',
        excerpt=rows[1]['text'],
        conversation_title='Fictional garden plan',
        clip_start=6,
        clip_end=12,
        candidates=[],
    )
    with (
        patch.object(render, 'get_user_name', return_value=None),
        patch.object(llm, 'get_user_name', return_value=None),
        patch.object(llm, 'serving_for', return_value=False),
        patch.object(incremental, 'shadow_or_serve', return_value=False),
        patch.object(
            review.conversations,
            'get_conversation',
            return_value={'transcript_segments': rows, 'started_at': started, 'speaker_resolution': resolution},
        ),
        patch.object(review.conversations, 'is_visible_conversation', return_value=True),
    ):
        render.populate_speaker_names('fictional', [payload])
        developer = deepcopy(payload)
        render.populate_speaker_names('fictional', [developer], preserve_api_values=True)
        review_output = review._speaker_item('fictional', prompt).model_dump(mode='json')
        compact, bindings = llm.render_cluster_transcript(rows, names={})
        legacy_compact, legacy_bindings = llm.conversation_transcript_and_speaker_map('fictional', conversation)
        analytics = build_conversation_analytics(conversation, {}).model_dump(mode='json')
        episode = incremental.render_moment(rows, voice_order=[]).text
    gaps = [r for r in rows if r['speaker'].startswith('BATCH_UNASSIGNED_')]
    return {
        'api': payload,
        'developer_api': developer,
        'review': review_output,
        'mcp_search': build_transcript_match_snippets(rows, 'seedlings', max_snippets=6),
        'mcp_segments': bounded_transcript_segments(rows, max_segments=10, max_chars=5000)[0],
        'llm_plain': TranscriptSegment.segments_as_string(conversation.transcript_segments),
        'llm_compact': compact,
        'llm_bindings': dict(bindings),
        'llm_legacy_compact': legacy_compact,
        'llm_legacy_bindings': dict(legacy_bindings),
        'episode': episode,
        'analytics': analytics,
        'label_participant_delta': len(
            {r['speaker_name'] for r in payload['transcript_segments']} - {'Unknown speaker'}
        )
        - len(ids),
        'inventory': {
            'raw_scoped_ids': [
                list(key) for key in dict.fromkeys((r['speaker_id_scope'], r['speaker_id']) for r in rows)
            ],
            'participant_speaker_ids': ids,
            'abstention_keys': [r['speaker'] for r in gaps],
            'segments': len(rows),
            'words': sum(len(r['text'].split()) for r in rows),
            'speech_seconds': sum(r['end'] - r['start'] for r in rows),
        },
    }


# Pre-review verified all six before payloads equal origin/main output at
# 9980aaf18681eee6eb8989d30c9fce3710416bad, by overlaying the ten backend sources.
# Preserve these independently verified rollback oracles when regenerating after output.
def snapshot(case):
    outputs = {'case': case, 'fixture': 'fictional; no account or provider data'}
    for label, enabled in [('before', 'false'), ('after', 'true')]:
        with patch.dict(os.environ, {FLAG: enabled}):
            outputs[label] = server_outputs(case)
    return outputs
