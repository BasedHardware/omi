"""The real memory entrypoint never sends uncertain/other voices to formation."""

from unittest.mock import MagicMock

import pytest

from models.transcript_segment import TranscriptSegment
from tests.unit.test_process_conversation_free_tier_branch import pc, _existing_desktop
from utils.conversations.owner_attribution import confident_owner_segments


@pytest.fixture(autouse=True)
def owner_admission_cohort(monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('SPEAKER_EVIDENCE_MODE_SERVE_UID_SHA256S', raising=False)


def segment(sid, voice, *, owner=False, status='unknown', label_source=None):
    return TranscriptSegment(
        id=sid,
        speaker_id=voice,
        speaker_id_scope='synthetic:0',
        text=f'Synthetic statement from {sid}.',
        is_user=owner,
        speaker_identity_status=status,
        speaker_match_source='conversation_voice' if status == 'user' else None,
        speaker_label_source=label_source,
        start=voice * 10,
        end=voice * 10 + 5,
    )


@pytest.mark.parametrize('status', ['unknown', 'ambiguous', 'no_match', 'not_user'])
def test_legacy_owner_boolean_cannot_authorize_memory(status):
    assert confident_owner_segments([segment('uncertain', 0, owner=True, status=status)]) == []


def test_stored_legacy_boolean_with_real_cluster_ids_is_not_identity_evidence():
    legacy = TranscriptSegment(
        id='legacy',
        speaker='SPEAKER_00',
        speaker_id=0,
        speaker_id_scope='sync:synthetic',
        is_user=True,
        text='Synthetic unproven statement.',
        start=0,
        end=5,
    )
    assert legacy.speaker_identity_status == 'user'  # compatibility projection
    assert confident_owner_segments([legacy]) == []
    manual = segment('manual', 1, owner=True, label_source='manual')
    assert confident_owner_segments([legacy, manual]) == [manual]


@pytest.mark.parametrize('unproven_source', ['unrecognized_source', 'live_embedding'])
def test_carried_owner_and_loose_or_unknown_match_provenance_cannot_authorize_memory(unproven_source):
    owner = segment('carried', 0, owner=True, status='user', label_source='carried')
    assert confident_owner_segments([owner]) == []
    owner.speaker_label_source = 'auto'
    owner.speaker_match_source = unproven_source
    assert confident_owner_segments([owner]) == []


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
    observe = MagicMock()
    monkeypatch.setattr(pc, 'observe_owner_memory_admission', observe)
    monkeypatch.setattr(pc, '_extract_memories_inner', extract)
    pc.extract_memories('synthetic', conversation)
    admitted = extract.call_args.args[1]
    assert admitted is not conversation
    assert admitted.transcript_segments == [owner]
    assert admitted.id == conversation.id
    assert pc._l1_owner_spoken_for_grounded_quotes([owner.text], admitted.transcript_segments)
    assert not pc._grounded_l1_evidence_quotes([unknown.text], admitted.transcript_segments)
    assert conversation.model_dump() == original
    observe.assert_called_once_with(2, 1)
    service.ensure_canonical_mutation_ready.assert_called_once_with('synthetic')


def test_no_confident_owner_skips_provider_and_source_replacement(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    conversation = _existing_desktop('no-owner-memory')
    conversation.transcript_segments = [segment('unknown', 0, owner=True)]
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    extract = MagicMock(side_effect=AssertionError('uncertain speech reached memory formation'))
    observe = MagicMock()
    monkeypatch.setattr(pc, 'observe_owner_memory_admission', observe)
    monkeypatch.setattr(pc, '_extract_memories_inner', extract)
    pc.extract_memories('synthetic', conversation)
    extract.assert_not_called()
    service.replace_conversation_memories.assert_not_called()
    assert len(conversation.transcript_segments) == 1
    observe.assert_called_once_with(1, 0)


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_non_serving_accounts_keep_legacy_memory_input_until_the_aligned_ramp(monkeypatch, pc, mode):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    conversation = _existing_desktop('outside-owner-pilot')
    conversation.transcript_segments = [segment('legacy', 0, owner=True)]
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _: None)
    extract = MagicMock(return_value=MagicMock(count=0))
    observe = MagicMock()
    monkeypatch.setattr(pc, 'observe_owner_memory_admission', observe)
    monkeypatch.setattr(pc, '_extract_memories_inner', extract)
    pc.extract_memories('synthetic', conversation)
    assert extract.call_args.args[1] is conversation
    observe.assert_not_called()
    service.ensure_canonical_mutation_ready.assert_called_once_with('synthetic')
