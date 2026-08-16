from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from models.action_item import EvidenceRef
from models.structured_extraction import ActionItemsExtraction
from models.transcript_segment import TranscriptSegment
from utils.conversations import transcript_for_llm
from utils.task_intelligence.conversation_capture import canonical_fields


def _segment(segment_id: str, text: str, start: float, end: float) -> TranscriptSegment:
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker='SPEAKER_00',
        is_user=True,
        start=start,
        end=end,
    )


def test_action_item_transcript_includes_stable_segment_ids(monkeypatch):
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_args, **_kwargs: 'Archit')
    conversation = SimpleNamespace(transcript_segments=[_segment('seg-1', 'I will send the proposal.', 12.5, 15.0)])

    rendered = transcript_for_llm.conversation_transcript_for_action_items('uid-1', conversation)

    assert rendered == '[segment:seg-1 12.500-15.000] Archit: I will send the proposal.'


def test_extracted_segment_ids_survive_into_grounded_task_provenance():
    segments = [
        _segment('seg-1', 'Background context.', 2.0, 4.0),
        _segment('seg-2', 'I will send the proposal.', 12.5, 15.0),
        _segment('seg-3', 'By Friday.', 15.0, 16.25),
    ]
    action_item = ActionItemsExtraction.model_validate(
        {
            'action_items': [
                {
                    'description': 'Send the proposal',
                    'source_segment_ids': ['seg-2', 'invented', 'seg-3'],
                }
            ]
        }
    ).to_action_items()[0]

    fields = canonical_fields(action_item, 'conversation-1', segments)
    evidence = fields['provenance'][0]

    assert evidence['id'] == 'conversation-1'
    assert evidence['transcript_segment_ids'] == ['seg-2', 'seg-3']
    assert evidence['start_seconds'] == 12.5
    assert evidence['end_seconds'] == 16.25


@pytest.mark.parametrize('field', ['start_seconds', 'end_seconds'])
def test_task_provenance_rejects_non_finite_timestamps(field):
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(
            {'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical', field: float('inf')}
        )
