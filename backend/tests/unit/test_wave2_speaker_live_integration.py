"""Verify live introductions emit suggestions without assigning identity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from models.transcript_segment import TranscriptSegment
from routers.listen import transcripts


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
async def test_live_introduction_is_suggestion_only_in_every_mode(monkeypatch, mode):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('SPEAKER_EVIDENCE_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setattr(
        transcripts, 'detect_speaker_introduction', lambda *a, **k: SimpleNamespace(name='Fixture', explicit=True)
    )
    monkeypatch.setattr(transcripts, 'should_queue_speaker_embedding', lambda **_: False)
    monkeypatch.setattr(transcripts, '_observe_embedding_admission', lambda *a: None)
    lookup = AsyncMock(return_value={'id': 'person-fixture'})
    speaker = SimpleNamespace(
        speaker_to_person={},
        segment_assignments={},
        named_speakers_allowed=AsyncMock(return_value=True),
        resolve_owner_name=AsyncMock(return_value=None),
        observe_segment=None,
        person_embeddings={},
    )
    host = SimpleNamespace(
        speakers=speaker,
        language='en',
        persistence=SimpleNamespace(call=lookup),
        state=SimpleNamespace(speaker_id_enabled=False, speaker_map_dirty=False, speaker_map_version=0),
        request=SimpleNamespace(uid='synthetic', create_speakers=True, speaker_auto_assign_enabled=True),
        send_event=MagicMock(),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.suggested_segments = set()
    processor.introduction_suggestions = set()
    segment = TranscriptSegment(id='segment-fixture', text='w0', is_user=False, speaker_id=1, start=0, end=1)
    await processor._speaker_detection([segment], 0)
    await processor._speaker_detection([segment], 0)
    lookup.assert_awaited_once()
    assert not speaker.segment_assignments
    assert not speaker.speaker_to_person
    assert segment.person_id is None
    assert segment.speaker_identity_status == 'unknown'
    assert not host.state.speaker_map_dirty
    assert not processor.suggested_segments
    host.send_event.assert_called_once()
    event = host.send_event.call_args.args[0]
    assert event.person_id == ''
    assert event.suggested_person_id == 'person-fixture'
