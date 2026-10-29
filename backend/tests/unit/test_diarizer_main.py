import os
import sys
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_ml_deps():
    from testing.import_isolation import AutoMockModule, stub_modules

    stubs = {
        "torch": AutoMockModule("torch"),
        "torchaudio": AutoMockModule("torchaudio"),
        "pyannote": AutoMockModule("pyannote"),
        "pyannote.audio": AutoMockModule("pyannote.audio"),
        "pyannote.audio.pipelines": AutoMockModule("pyannote.audio.pipelines"),
    }
    with stub_modules(stubs):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../diarizer")))

        import main

        yield main


@pytest.fixture
def client(mock_ml_deps, monkeypatch):
    monkeypatch.setattr(mock_ml_deps, "initialize_embeddings", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(mock_ml_deps, "initialize_diarization", lambda *a, **k: None, raising=False)

    return TestClient(mock_ml_deps.app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_metrics(client, mock_ml_deps, monkeypatch):
    monkeypatch.setattr(mock_ml_deps, "generate_latest", lambda: b"test metrics", raising=False)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.content == b"test metrics"
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"


def test_diarization(client, mock_ml_deps, monkeypatch):
    # Instead of patching diarization_endpoint which handles HTTP unpacking,
    # we patch the ML initialization logic so the endpoint runs but the ML part is mocked.
    import diarization

    mock_pipeline = MagicMock()
    mock_output = MagicMock()

    class MockTurn:
        def __init__(self, start, end):
            self.start = start
            self.end = end

    mock_output.speaker_diarization = [(MockTurn(0.0, 1.0), "SPEAKER_00")]
    mock_pipeline.return_value = mock_output

    monkeypatch.setattr(diarization, "initialize_diarization", lambda: mock_pipeline)

    file_content = b"fake audio data"
    response = client.post(
        "/v1/diarization",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json() == [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0, "duration": 1.0}]


def test_embedding(client, mock_ml_deps, monkeypatch):
    import embedding

    monkeypatch.setattr(embedding, "_validate_audio_duration", lambda x: None)
    monkeypatch.setattr(embedding, "_load_audio_for_inference", lambda x: {"waveform": None, "sample_rate": 16000})

    mock_inference = MagicMock()

    class MockEmbedding:
        def tolist(self):
            return [0.1, 0.2, 0.3]

    mock_inference.return_value = MockEmbedding()

    monkeypatch.setattr(embedding, "embedding_inference", mock_inference)

    file_content = b"fake audio data"
    response = client.post(
        "/v1/embedding",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json() == [0.1, 0.2, 0.3]


def test_embedding_v2(client, mock_ml_deps, monkeypatch):
    import embedding

    monkeypatch.setattr(embedding, "_validate_audio_duration", lambda x: None)
    monkeypatch.setattr(embedding, "_load_audio_for_inference", lambda x: {"waveform": None, "sample_rate": 16000})

    mock_inference_v2 = MagicMock()

    class MockEmbedding:
        def tolist(self):
            return [0.4, 0.5, 0.6]

    mock_inference_v2.return_value = MockEmbedding()

    monkeypatch.setattr(embedding, "embedding_inference_v2", mock_inference_v2)

    file_content = b"fake audio data"
    response = client.post(
        "/v2/embedding",
        files={"file": ("test.wav", BytesIO(file_content), "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json() == [0.4, 0.5, 0.6]


def test_lifespan(mock_ml_deps, monkeypatch):
    mock_init_emb = MagicMock()
    mock_init_diar = MagicMock()
    monkeypatch.setattr(mock_ml_deps, "initialize_embeddings", mock_init_emb, raising=False)
    monkeypatch.setattr(mock_ml_deps, "initialize_diarization", mock_init_diar, raising=False)

    with TestClient(mock_ml_deps.app):
        pass

    mock_init_emb.assert_called_once()
    mock_init_diar.assert_called_once()
