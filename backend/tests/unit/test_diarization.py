from unittest.mock import Mock, patch
from fastapi import UploadFile
import os
import uuid
import pytest
from diarizer.diarization import diarization_endpoint, initialize_diarization

def test_diarization_endpoint(monkeypatch):
    # We will mock initialize_diarization, which is cached via lru_cache

    mock_pipeline = Mock()
    mock_output = Mock()

    mock_turn_1 = Mock()
    mock_turn_1.start = 0.0
    mock_turn_1.end = 2.0

    mock_turn_2 = Mock()
    mock_turn_2.start = 2.0
    mock_turn_2.end = 5.0

    mock_output.speaker_diarization = [
        (mock_turn_1, "SPEAKER_00"),
        (mock_turn_2, "SPEAKER_01"),
    ]
    mock_pipeline.return_value = mock_output

    monkeypatch.setattr("diarizer.diarization.initialize_diarization", lambda: mock_pipeline)

    # Do not use spec=UploadFile because it strictly checks the spec attributes and breaks Mock property assignments
    mock_file = Mock()
    mock_file.filename = "test_audio.wav"
    mock_file.file.read.return_value = b"fake audio data"

    result = diarization_endpoint(mock_file)

    assert len(result) == 2
    assert result[0] == {
        'speaker': 'SPEAKER_00',
        'start': 0.0,
        'end': 2.0,
        'duration': 2.0,
    }
    assert result[1] == {
        'speaker': 'SPEAKER_01',
        'start': 2.0,
        'end': 5.0,
        'duration': 3.0,
    }

def test_initialize_diarization_cpu(monkeypatch):
    mock_pipeline_class = Mock()
    mock_pipeline_instance = Mock()
    mock_pipeline_class.from_pretrained.return_value = mock_pipeline_instance
    mock_pipeline_instance.to.return_value = mock_pipeline_instance

    monkeypatch.setattr("diarizer.diarization.Pipeline", mock_pipeline_class)

    mock_torch = Mock()
    mock_torch.cuda.is_available.return_value = False
    mock_torch.device.return_value = "cpu"
    monkeypatch.setattr("diarizer.diarization.torch", mock_torch)

    # clear cache just in case
    initialize_diarization.cache_clear()

    result = initialize_diarization()
    assert result == mock_pipeline_instance
    mock_pipeline_class.from_pretrained.assert_called_once()
    mock_torch.cuda.is_available.assert_called_once()
    mock_torch.device.assert_called_with("cpu")
    mock_pipeline_instance.to.assert_called_with("cpu")

def test_diarization_cleanup_on_error(monkeypatch):
    mock_pipeline = Mock(side_effect=Exception("Pipeline error"))
    monkeypatch.setattr("diarizer.diarization.initialize_diarization", lambda: mock_pipeline)

    mock_file = Mock()
    mock_file.filename = "test_audio_error.wav"
    mock_file.file.read.return_value = b"fake audio data"

    # Check that file exists before cleanup - hard to intercept without mocking open,
    # but we can check if file is removed at the end by asserting it's not in _temp directory.
    # Since we use UUID, let's mock UUID to know the filename.

    mock_uuid = Mock()
    mock_uuid.uuid4.return_value = "1234-5678"
    monkeypatch.setattr("diarizer.diarization.uuid", mock_uuid)

    expected_path = "_temp/1234-5678_test_audio_error.wav"

    with pytest.raises(Exception, match="Pipeline error"):
        diarization_endpoint(mock_file)

    assert not os.path.exists(expected_path)
