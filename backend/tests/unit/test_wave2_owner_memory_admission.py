"""The real memory entrypoint never sends uncertain/other voices to formation."""

from unittest.mock import MagicMock

import pytest

from models.transcript_segment import TranscriptSegment
from tests.unit.test_process_conversation_free_tier_branch import pc, _existing_desktop
from utils.conversations.owner_attribution import confident_owner_segments


def segment(sid, voice, *, owner=False, status='unknown', label_source=None):
    return TranscriptSegment(
        id=sid,
        speaker_id=voice,
        speaker_id_scope='synthetic:0',
        text=f'Synthetic statement from {sid}.',
        is_user=owner,
        speaker_identity_status=status,
        speaker_label_source=label_source,
        start=voice * 10,
        end=voice * 10 + 5,
    )


@pytest.mark.parametrize('status', ['unknown', 'ambiguous', 'no_match', 'not_user'])
def test_legacy_owner_boolean_cannot_authorize_memory(status):
    assert confident_owner_segments([segment('uncertain', 0, owner=True, status=status)]) == []


def test_confident_and_manual_owner_are_retained_without_synthesized_or_conflicting_ids():
    owner = segment('owner', 0, owner=True, status='user')
    manual = segment('manual', 0, owner=True, label_source='manual')
    other = segment('other', 1)
    assert confident_owner_segments([owner, manual, other]) == [owner, manual]
    assert confident_owner_segments([owner, segment('conflict', 1, owner=True, status='user')]) == []
    legacy = TranscriptSegment(text='Synthetic legacy text.', is_user=True, start=0, end=5)
    legacy.speaker_identity_status = 'user'
    assert confident_owner_segments([legacy]) == []
    owner.person_id = 'another-person'
    assert confident_owner_segments([owner]) == []


def test_public_memory_boundary_filters_before_extraction_and_preserves_original(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    conversation = _existing_desktop('owner-memory')
    owner = segment('owner', 0, owner=True, status='user')
    unknown = segment('unknown', 1)
    conversation.transcript_segments = [owner, unknown]
    original = conversation.model_dump()
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _: None)
    result = MagicMock(count=0)
    extract = MagicMock(return_value=result)
    monkeypatch.setattr(pc, '_extract_memories_inner', extract)
    pc.extract_memories('synthetic', conversation)
    admitted = extract.call_args.args[1]
    assert admitted is not conversation
    assert admitted.transcript_segments == [owner]
    assert admitted.id == conversation.id
    assert pc._l1_owner_spoken_for_grounded_quotes([owner.text], admitted.transcript_segments)
    assert not pc._grounded_l1_evidence_quotes([unknown.text], admitted.transcript_segments)
    assert conversation.model_dump() == original
    service.ensure_canonical_mutation_ready.assert_called_once_with('synthetic')


def test_no_confident_owner_skips_provider_and_source_replacement(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    conversation = _existing_desktop('no-owner-memory')
    conversation.transcript_segments = [segment('unknown', 0, owner=True)]
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    extract = MagicMock(side_effect=AssertionError('uncertain speech reached memory formation'))
    monkeypatch.setattr(pc, '_extract_memories_inner', extract)
    pc.extract_memories('synthetic', conversation)
    extract.assert_not_called()
    service.replace_conversation_memories.assert_not_called()
    assert len(conversation.transcript_segments) == 1
