from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from routers.listen.transcripts import TranscriptProcessor
from routers.listen.speakers import MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS, SpeakerMatcher


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_speaker_id_queue_payload_excludes_transcript_text():
    source = Path(__file__).resolve().parents[2] / 'routers' / 'listen' / 'transcripts.py'
    text = source.read_text(encoding='utf-8')
    assert "'text': segment.text" not in text
    assert '"text": segment.text' not in text
    assert 'speaker.queue.put_nowait' in text


class _RecordingRingBuffer:
    def __init__(self):
        self.extractions = []

    def get_time_range(self):
        return 0.0, 60.0

    def extract(self, start, end):
        self.extractions.append((start, end))
        return b''


class _AudioRingBuffer:
    def get_time_range(self):
        return 0.0, 60.0

    def extract(self, _start, _end):
        return b'\x00\x00' * 32000


@pytest.mark.anyio
async def test_speaker_match_extracts_a_centered_ten_second_window_for_long_segments():
    ring_buffer = _RecordingRingBuffer()
    matcher = SpeakerMatcher(
        SimpleNamespace(
            state=SimpleNamespace(audio_ring_buffer=ring_buffer),
            limits=SimpleNamespace(speaker_id_min_audio=1.0),
            request=SimpleNamespace(sample_rate=16000),
        )
    )

    await matcher.match(
        1,
        {
            'id': 'long-segment',
            'duration': 20.0,
            'abs_start': 0.0,
            'abs_end': 20.0,
        },
    )

    assert ring_buffer.extractions == [(5.0, 15.0)]
    assert ring_buffer.extractions[0][1] - ring_buffer.extractions[0][0] == MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS


@pytest.mark.anyio
async def test_speaker_no_match_records_unknown_identity_instead_of_confident_negative(monkeypatch):
    host = SimpleNamespace(
        state=SimpleNamespace(audio_ring_buffer=_AudioRingBuffer(), speaker_map_dirty=False),
        limits=SimpleNamespace(speaker_id_min_audio=1.0),
        request=SimpleNamespace(sample_rate=16000),
    )
    matcher = SpeakerMatcher(host)
    matcher.person_embeddings = {'user': {'embedding': np.array([[1.0, 0.0]], dtype=np.float32), 'name': 'User'}}
    monkeypatch.setattr(
        'routers.listen.speakers.extract_embedding_from_bytes',
        lambda _audio, _name: np.array([[0.0, 1.0]], dtype=np.float32),
    )

    await matcher.match(
        0,
        {'id': 'unmatched-segment', 'duration': 2.0, 'abs_start': 0.0, 'abs_end': 2.0},
    )

    assert matcher.segment_identity_status['unmatched-segment'] == SpeakerIdentityStatus.no_match
    assert host.state.speaker_map_dirty is True


def test_no_match_status_reaches_the_persisted_segment_payload():
    segment = TranscriptSegment(
        id='unmatched-segment',
        text='owner statement',
        speaker='SPEAKER_0',
        speaker_id=0,
        is_user=False,
        start=0.0,
        end=2.0,
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        speakers=SimpleNamespace(
            segment_assignments={},
            speaker_to_person={},
            segment_identity_status={'unmatched-segment': SpeakerIdentityStatus.no_match},
        )
    )

    processor._apply_speaker_identity_statuses([segment])
    payload = segment.model_dump()

    assert segment.is_user is False
    assert payload['speaker_identity_status'] == SpeakerIdentityStatus.no_match
