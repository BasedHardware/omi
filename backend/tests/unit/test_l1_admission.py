"""L1 admission: noise rows and short owner speech never buy a model call."""

from unittest.mock import MagicMock

import pytest

from config.memory_l1_admission import L1_MIN_OWNER_WORDS
from models.transcript_segment import TranscriptSegment
from tests.unit.test_process_conversation_free_tier_branch import _existing_desktop, pc
from utils.conversations import l1_admission


def segment(sid: str, words: int, *, voice: int = 0, owner: bool = True) -> TranscriptSegment:
    return TranscriptSegment(
        id=sid,
        speaker_id=voice,
        speaker_id_scope='synthetic:0',
        text=' '.join(['word'] * words),
        is_user=owner,
        speaker_identity_status='user' if owner else 'unknown',
        speaker_match_source='conversation_voice' if owner else None,
        start=0.0,
        end=5.0,
    )


def test_noise_content_kind_skips():
    conversation = _existing_desktop('noise-kind')
    conversation.content_kind = 'noise'
    assert l1_admission.skip_reason(conversation) == l1_admission.NOISE


def test_media_content_kind_skips():
    conversation = _existing_desktop('media-kind')
    conversation.content_kind = 'media'
    assert l1_admission.skip_reason(conversation) == l1_admission.NOISE


def test_server_minimum_skips():
    conversation = _existing_desktop('minimum')
    conversation.structured.title_provenance = 'server_minimum'
    assert l1_admission.skip_reason(conversation) == l1_admission.NOISE


def test_short_owner_speech_skips():
    conversation = _existing_desktop('short-owner')
    conversation.transcript_segments = [segment('owner', L1_MIN_OWNER_WORDS - 1)]
    assert l1_admission.skip_reason(conversation) == l1_admission.SHORT_OWNER_SPEECH


def test_owner_speech_at_the_floor_still_extracts():
    conversation = _existing_desktop('at-floor')
    conversation.transcript_segments = [segment('owner', L1_MIN_OWNER_WORDS)]
    assert l1_admission.skip_reason(conversation) is None


def test_unknown_owner_uses_the_transcript_total_as_an_upper_bound():
    short = _existing_desktop('unknown-short')
    short.transcript_segments = [segment('other', L1_MIN_OWNER_WORDS - 1, owner=False)]
    assert l1_admission.skip_reason(short) == l1_admission.SHORT_OWNER_SPEECH

    long = _existing_desktop('unknown-long')
    long.transcript_segments = [segment('other', L1_MIN_OWNER_WORDS, owner=False)]
    assert l1_admission.skip_reason(long) is None


def test_owner_words_are_measured_not_the_whole_transcript():
    conversation = _existing_desktop('owner-plus-other')
    conversation.transcript_segments = [
        segment('owner', L1_MIN_OWNER_WORDS - 1),
        segment('other', 200, voice=1, owner=False),
    ]
    assert l1_admission.skip_reason(conversation) == l1_admission.SHORT_OWNER_SPEECH


def test_curated_row_never_skips():
    conversation = _existing_desktop('curated')
    conversation.user_title = 'My own title'
    conversation.transcript_segments = [segment('owner', 1)]
    assert l1_admission.skip_reason(conversation) is None


def test_external_integration_ignores_the_word_floor():
    conversation = _existing_desktop('imported')
    conversation.source = 'external_integration'
    conversation.transcript_segments = []
    assert l1_admission.skip_reason(conversation) is None


def test_kill_switch_off_restores_extraction(monkeypatch):
    monkeypatch.setenv('EPISODE_COMPOSER_REUSE', 'false')
    conversation = _existing_desktop('kill-switch')
    conversation.content_kind = 'noise'
    conversation.transcript_segments = [segment('owner', 1)]
    assert l1_admission.skip_reason(conversation) is None


def _admission_spies(monkeypatch, pc):
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _: None)
    inner = MagicMock(return_value=MagicMock(count=0))
    monkeypatch.setattr(pc, '_extract_memories_inner', inner)
    return service, inner


def test_extract_memories_skips_noise_before_the_paid_call(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    service, inner = _admission_spies(monkeypatch, pc)
    conversation = _existing_desktop('noise-row')
    conversation.content_kind = 'noise'
    pc.extract_memories('synthetic', conversation)
    inner.assert_not_called()
    service.replace_conversation_memories.assert_not_called()


def test_extract_memories_skips_short_owner_speech(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    _, inner = _admission_spies(monkeypatch, pc)
    conversation = _existing_desktop('short-row')
    conversation.transcript_segments = [segment('owner', 3)]
    pc.extract_memories('synthetic', conversation)
    inner.assert_not_called()


def test_extract_memories_still_extracts_non_noise_rows(monkeypatch, pc):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    _, inner = _admission_spies(monkeypatch, pc)
    conversation = _existing_desktop('real-row')
    conversation.transcript_segments = [segment('owner', L1_MIN_OWNER_WORDS + 10)]
    pc.extract_memories('synthetic', conversation)
    inner.assert_called_once()
