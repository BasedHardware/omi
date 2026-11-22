"""Strict local inspection remains after paid recovery retirement."""

import io
import wave
import pytest
from utils.sync import empty_recovery as recovery


@pytest.mark.parametrize('rate,width', [(16000, 2), (8000, 1), (48000, 2)])
def test_strict_inspection_preserves_silence_evidence(tmp_path, monkeypatch, rate, width):
    data = io.BytesIO()
    with wave.open(data, 'wb') as output:
        output.setparams((1, width, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(bytes(rate * width))
    path = tmp_path / 'silence.wav'
    path.write_bytes(data.getvalue())
    original = recovery.inspect_audio
    monkeypatch.setattr(recovery, 'inspect_audio', lambda item, audio: original(item, audio, vad=lambda pcm: []))
    _, duration, spans = recovery.inspect_strict(path)
    assert duration == pytest.approx(1, abs=0.001) and spans == []


def test_truncated_audio_is_not_silence(tmp_path):
    path = tmp_path / 'truncated.wav'
    path.write_bytes(b'RIFF')
    with pytest.raises(RuntimeError, match='inspection failed'):
        recovery.inspect_strict(path)
