import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import numpy as np
import wave
import io
import sys

from testing.import_isolation import AutoMockModule, stub_modules

# We use the sanctioned test-isolation context manager stub_modules instead of global sys.modules
# mutation. This test tests core functionality isolated from the heavyweight dependencies.

def setup_fake_environment():
    fakes = {
        'torch': AutoMockModule('torch'),
        'pyannote': AutoMockModule('pyannote'),
        'pyannote.audio': AutoMockModule('pyannote.audio'),
        'metrics': AutoMockModule('metrics'),
        'admission': AutoMockModule('admission'),
        'embedding': AutoMockModule('embedding'),
        'transformers': AutoMockModule('transformers'),
    }
    return fakes

def test_turns():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import turns
        class MockTurn:
            def __init__(self, start, end):
                self.start = start
                self.end = end

        annotation = [(MockTurn(0.0, 1.5), "SPEAKER_00"), (MockTurn(2.0, 3.5), "SPEAKER_01")]
        result = turns(annotation)
        assert result == [
            {"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"},
            {"start": 2.0, "end": 3.5, "speaker": "SPEAKER_01"}
        ]

def test_decode_audio_invalid_content_type():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import decode_audio
        with pytest.raises(HTTPException) as exc_info:
            decode_audio(b"some_audio", "audio/mp3")
        assert exc_info.value.status_code == 415

def test_decode_audio_invalid_wav():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import decode_audio
        with pytest.raises(HTTPException) as exc_info:
            decode_audio(b"not a wav file", "audio/wav")
        assert exc_info.value.status_code == 422
        assert "expected 16kHz mono PCM16 WAV" in exc_info.value.detail

def test_decode_audio_pcm_success():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import decode_audio
        import torch
        # 1 second of silence 16kHz mono PCM16
        pcm_data = b"\x00\x00" * 16000
        torch.from_numpy.return_value.unsqueeze.return_value = "mock_tensor"

        tensor = decode_audio(pcm_data, "audio/pcm")
        assert tensor == "mock_tensor"
        torch.from_numpy.assert_called_once()

def test_decode_audio_wav_success():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import decode_audio
        import torch
        pcm_data = b"\x00\x00" * 16000
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_data)

        wav_bytes = wav_io.getvalue()
        torch.from_numpy.return_value.unsqueeze.return_value = "mock_tensor"
        tensor = decode_audio(wav_bytes, "audio/wav")
        assert tensor == "mock_tensor"
        torch.from_numpy.assert_called_once()

def test_infer():
    fakes = setup_fake_environment()
    with stub_modules(fakes):
        from diarizer.final_pass import infer, MODEL_REVISION
        import torch
        import diarizer.final_pass as fp

        class MockTurn:
            def __init__(self, start, end):
                self.start = start
                self.end = end

        # Mock inference_mode as a context manager
        torch.inference_mode.return_value.__enter__ = MagicMock()
        torch.inference_mode.return_value.__exit__ = MagicMock()
        fp.GPU_LOCK = MagicMock()
        fp.GPU_LOCK.__enter__ = MagicMock()
        fp.GPU_LOCK.__exit__ = MagicMock()

        mock_model_output = MagicMock()
        mock_model_output.speaker_diarization = [
            (MockTurn(0.0, 1.0), "SPEAKER_00"),
            (MockTurn(1.5, 2.5), "SPEAKER_01"),
        ]
        mock_model_output.exclusive_speaker_diarization = None # Fallback to activity

        mock_model = MagicMock(return_value=mock_model_output)
        fp.pipeline = MagicMock(return_value=mock_model)

        # Fake embedding
        fp.embedding_inference_v2 = MagicMock(return_value=np.array([0.5, 0.5]))

        waveform = MagicMock()
        waveform.shape = [1, 48000] # 3 seconds
        waveform.__getitem__.return_value = "fake_clip"

        result = infer(waveform)

        assert "turns" in result
        assert "overlaps" in result
        assert "centroids" in result
        assert result["audio_seconds"] == 3.0
        assert result["model_revision"] == MODEL_REVISION

        assert len(result["turns"]) == 2
        assert "SPEAKER_00" in result["centroids"]
        assert "SPEAKER_01" in result["centroids"]
