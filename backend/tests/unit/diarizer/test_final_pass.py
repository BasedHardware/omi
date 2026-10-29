import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import numpy as np
import wave
import io
import sys

# Mock torch, pyannote, metrics, admission, embedding to avoid heavy dependencies and import errors
sys.modules['torch'] = MagicMock()
sys.modules['pyannote'] = MagicMock()
sys.modules['pyannote.audio'] = MagicMock()
sys.modules['metrics'] = MagicMock()
sys.modules['admission'] = MagicMock()
sys.modules['embedding'] = MagicMock()

# Also mock transformers which is failing internally due to tiktoken.__spec__ being None
sys.modules['transformers'] = MagicMock()
import torch

from diarizer.final_pass import decode_audio, turns, infer, pipeline, MODEL_REVISION, MAX_AUDIO_SECONDS

def test_turns():
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
    with pytest.raises(HTTPException) as exc_info:
        decode_audio(b"some_audio", "audio/mp3")
    assert exc_info.value.status_code == 415

def test_decode_audio_invalid_wav():
    with pytest.raises(HTTPException) as exc_info:
        decode_audio(b"not a wav file", "audio/wav")
    assert exc_info.value.status_code == 422
    assert "expected 16kHz mono PCM16 WAV" in exc_info.value.detail

@patch("diarizer.final_pass.torch")
def test_decode_audio_pcm_success(mock_torch):
    # 1 second of silence 16kHz mono PCM16
    pcm_data = b"\x00\x00" * 16000
    mock_torch.from_numpy.return_value.unsqueeze.return_value = "mock_tensor"

    tensor = decode_audio(pcm_data, "audio/pcm")
    assert tensor == "mock_tensor"
    mock_torch.from_numpy.assert_called_once()

@patch("diarizer.final_pass.torch")
def test_decode_audio_wav_success(mock_torch):
    pcm_data = b"\x00\x00" * 16000
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm_data)

    wav_bytes = wav_io.getvalue()
    mock_torch.from_numpy.return_value.unsqueeze.return_value = "mock_tensor"
    tensor = decode_audio(wav_bytes, "audio/wav")
    assert tensor == "mock_tensor"
    mock_torch.from_numpy.assert_called_once()

@patch("diarizer.final_pass.pipeline")
@patch("diarizer.final_pass.embedding_inference_v2")
@patch("diarizer.final_pass.GPU_LOCK")
@patch("diarizer.final_pass.torch")
def test_infer(mock_torch, mock_gpu_lock, mock_embedding_inference, mock_pipeline):
    class MockTurn:
        def __init__(self, start, end):
            self.start = start
            self.end = end

    # Mock inference_mode as a context manager
    mock_torch.inference_mode.return_value.__enter__ = MagicMock()
    mock_torch.inference_mode.return_value.__exit__ = MagicMock()
    mock_gpu_lock.__enter__ = MagicMock()
    mock_gpu_lock.__exit__ = MagicMock()

    mock_model_output = MagicMock()
    mock_model_output.speaker_diarization = [
        (MockTurn(0.0, 1.0), "SPEAKER_00"),
        (MockTurn(1.5, 2.5), "SPEAKER_01"),
    ]
    mock_model_output.exclusive_speaker_diarization = None # Fallback to activity

    mock_model = MagicMock(return_value=mock_model_output)
    mock_pipeline.return_value = mock_model

    # Fake embedding
    mock_embedding_inference.return_value = np.array([0.5, 0.5])

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
