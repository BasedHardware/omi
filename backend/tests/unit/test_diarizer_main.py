import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from io import BytesIO
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../diarizer')))

# Mock torch, torchaudio, and pyannote.audio before importing main
import sys
sys.modules['torch'] = MagicMock()
sys.modules['torchaudio'] = MagicMock()
sys.modules['pyannote'] = MagicMock()
sys.modules['pyannote.audio'] = MagicMock()
sys.modules['pyannote.audio.pipelines'] = MagicMock()

import main

# Patch the underlying implementations instead of the route handlers!
with patch("main.initialize_embeddings") as mock_init_emb, \
     patch("main.initialize_diarization") as mock_init_diar:
    client = TestClient(main.app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@patch("main.generate_latest")
def test_metrics(mock_generate_latest):
    mock_generate_latest.return_value = b"test metrics"
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.content == b"test metrics"
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"

@patch("main.diarization_endpoint")
def test_diarization(mock_diarization_endpoint):
    mock_diarization_endpoint.return_value = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]
    file_content = b"fake audio data"
    response = client.post(
        "/v1/diarization",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")}
    )
    assert response.status_code == 200
    assert response.json() == [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]
    mock_diarization_endpoint.assert_called_once()

@patch("main.embedding_endpoint")
def test_embedding(mock_embedding_endpoint):
    mock_embedding_endpoint.return_value = [0.1, 0.2, 0.3]
    file_content = b"fake audio data"
    response = client.post(
        "/v1/embedding",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")}
    )
    assert response.status_code == 200
    assert response.json() == [0.1, 0.2, 0.3]
    mock_embedding_endpoint.assert_called_once()

@patch("main.embedding_endpoint_v2")
def test_embedding_v2(mock_embedding_endpoint_v2):
    mock_embedding_endpoint_v2.return_value = [0.4, 0.5, 0.6]
    file_content = b"fake audio data"
    response = client.post(
        "/v2/embedding",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")}
    )
    assert response.status_code == 200
    assert response.json() == [0.4, 0.5, 0.6]
    mock_embedding_endpoint_v2.assert_called_once()

@patch("main.initialize_embeddings")
@patch("main.initialize_diarization")
def test_lifespan(mock_init_diarization, mock_init_embeddings):
    with TestClient(main.app) as local_client:
        pass
    mock_init_embeddings.assert_called_once()
    mock_init_diarization.assert_called_once()
