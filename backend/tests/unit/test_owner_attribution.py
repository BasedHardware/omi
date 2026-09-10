"""Behavioral owner-cluster gate: ambiguous diarization never mints owner facts."""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest

from models.conversation import Conversation
from models.memories import SubjectAttribution
from models.transcript_segment import TranscriptSegment
from utils.conversations import transcript_for_llm
from utils.conversations.owner_attribution import OwnerAttributionEvidence, may_attribute_to_owner
from utils.conversations.subjects import infer_subject_from_segments
from utils.conversations.transcript_for_llm import memory_transcript_from_segments
from utils.memory.decision_path_telemetry import emit_memory_capture_decision
from tests.unit.test_memory_replace_policy import _memory_replace_import_isolation, _load_process_conversation


@pytest.fixture(scope="module")
def pc(_memory_replace_import_isolation):
    return _load_process_conversation()


def _segments(owners):
    return [
        TranscriptSegment(
            text=text, speaker=f'SPEAKER_{index:02}', speaker_id=index, is_user=owner, start=index, end=index + 1
        )
        for index, (owner, text) in enumerate(zip(owners, ['I will move to Boston.', 'I prefer tea.']))
    ]


@pytest.mark.parametrize(
    'owners,trust', [((True, True), 'multi_owner'), ((False, False), 'no_owner'), ((True, False), 'unique_owner')]
)
def test_evidence_and_l1_subject_use_full_conversation_clusters(owners, trust, pc):
    segments = _segments(owners)
    evidence = OwnerAttributionEvidence.from_segments(segments)
    assert evidence.trust == trust
    assert evidence.distinct_speaker_ids == 2
    assert evidence.owner_speaker_ids == sum(owners)
    assert may_attribute_to_owner(evidence) == (trust == 'unique_owner')
    for quotes, label in [([], None), ([segments[0].text], 'speaker_0'), ([segments[1].text], 'speaker_1')]:
        subject, attribution, _ = pc._l1_candidate_subject(
            source_id='conversation',
            about='user',
            speaker_label=label,
            evidence_quotes=quotes,
            user_name='David',
            segments=segments,
        )
        expected_user = trust == 'unique_owner' and label != 'speaker_1'
        assert (attribution == SubjectAttribution.user) == expected_user
        assert (subject == 'user') == expected_user
    assert infer_subject_from_segments(segments)[1] != SubjectAttribution.user


def test_all_user_subject_requires_unique_cluster_and_legacy_missing_ids_fail_closed():
    assert infer_subject_from_segments(_segments((True, True)))[1] == SubjectAttribution.unknown
    assert infer_subject_from_segments(_segments((True, False))[:1])[1] == SubjectAttribution.user
    legacy = [SimpleNamespace(is_user=True, person_id=None, speaker_id=None)]
    evidence = OwnerAttributionEvidence.from_segments(legacy)
    assert evidence.trust == 'no_speaker_ids'
    assert not may_attribute_to_owner(evidence)
    assert infer_subject_from_segments(legacy)[1] == SubjectAttribution.unknown
    assert OwnerAttributionEvidence.from_segments([]).trust == 'no_speaker_ids'


def test_untrusted_quote_can_bind_known_contact_but_not_owner(pc):
    segments = _segments((True, True))
    segments[1].person_id = 'sarah'
    assert pc._l1_candidate_subject(
        source_id='conversation',
        about='user',
        speaker_label=None,
        evidence_quotes=[segments[1].text],
        user_name='David',
        segments=segments,
    ) == ('person:sarah', SubjectAttribution.third_party, 'person')


def test_quote_binding_uses_cluster_not_individual_segment_flag():
    segments = _segments((True, False))
    evidence = OwnerAttributionEvidence.from_segments(segments)
    same_cluster = SimpleNamespace(speaker_id=0, is_user=False)
    assert may_attribute_to_owner(evidence, segment=same_cluster)
    assert not may_attribute_to_owner(evidence, segment=segments[1])
    assert not may_attribute_to_owner(evidence, segment=SimpleNamespace(speaker_id=None))


def test_memory_render_warns_and_preserves_original_summary_render():
    segments = _segments((True, True))
    rendered = memory_transcript_from_segments(segments, user_name='David')
    assert rendered.startswith('[Diarization marked 2 of 2 speaker clusters')
    assert 'UNTRUSTED' in rendered
    assert 'Speaker 0: I will move to Boston.' in rendered
    assert 'Speaker 1: I prefer tea.' in rendered
    assert 'David:' not in rendered
    assert all(segment.is_user for segment in segments)
    assert TranscriptSegment.segments_as_string(segments, user_name='David').count('David:') == 2
    control = memory_transcript_from_segments(_segments((True, False)), user_name='David')
    assert 'UNTRUSTED' not in control
    assert 'David: I will move to Boston.' in control


def test_capture_telemetry_emits_owner_trust_without_text(caplog):
    with caplog.at_level(logging.INFO):
        emit_memory_capture_decision(
            logging.getLogger('owner-gate-test'),
            uid='u',
            memory_id='m',
            conversation_id='c',
            capture_regime='omi',
            subject_attribution=SubjectAttribution.unknown,
            model_about='primary_user',
            attribution_disagreed=True,
            distinct_speaker_ids=2,
            owner_speaker_ids=2,
            owner_trust='multi_owner',
        )
    assert '"owner_trust":"multi_owner"' in caplog.text
    assert 'I will move' not in caplog.text


@pytest.mark.parametrize('owners', [(True, True), (False, False), (True, False)])
def test_canonical_capture_owner_gate_and_shared_prefix(monkeypatch, pc, owners):
    service = MagicMock()
    captured = {}
    segments = _segments(owners)
    conversation = Conversation(
        structured={'title': 'Meeting', 'overview': 'Planning', 'category': 'personal'},
        id='owner-pack',
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source='omi',
        transcript_segments=segments,
    )
    monkeypatch.setattr(pc, 'MemoryService', lambda **_kwargs: service)
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda _uid: 'en')
    monkeypatch.setattr(pc, 'get_user_name', lambda *_args, **_kwargs: 'David')
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_args, **_kwargs: 'David')
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda _uid: 'UTC')
    monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: True)
    monkeypatch.setattr(pc, '_stored_meeting_context', lambda _conversation: None)
    monkeypatch.setattr(pc, 'belief_model_enabled', lambda: False)
    monkeypatch.setattr(pc, 'build_conversation_prompt_prefix', lambda **kwargs: captured.update(kwargs) or object())
    monkeypatch.setattr(
        pc,
        'extract_canonical_l1_memory_candidates',
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                content='User will move to Boston.',
                about='user',
                speaker_label='speaker_0',
                evidence_quotes=[segments[0].text],
                risk_flags=[],
                archive_class='general',
            )
        ],
    )
    result = pc._extract_memories_canonical('u', conversation, db_client=MagicMock())
    assert result.count == 1
    payload = service.replace_conversation_memories.call_args.args[2][0]
    trusted = owners == (True, False)
    assert (payload['subject_attribution'] == 'user') == trusted
    if not trusted:
        assert payload['subject_entity_id'] is None
        assert 'UNTRUSTED' in captured['transcript']
        assert 'David:' not in captured['transcript']
        assert captured['speaker_map'] == {}
