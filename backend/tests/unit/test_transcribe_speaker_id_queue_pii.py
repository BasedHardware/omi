from pathlib import Path
from types import SimpleNamespace

import pytest

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
