import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
import os

from diarizer.batch_main import app, lifespan, run_v2, health_check, metrics

def test_health_check():
    client = TestClient(app)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}

def test_metrics():
    client = TestClient(app)
    response = client.get('/metrics')
    assert response.status_code == 200
    assert 'text/plain' in response.headers['content-type']

@pytest.mark.asyncio
async def test_lifespan_enabled():
    with patch.dict(os.environ, {'DIARIZATION_V2_ENABLED': 'true'}), \
         patch('diarizer.batch_main.initialize_embeddings') as mock_init, \
         patch('diarizer.batch_main.pipeline') as mock_pipeline:

        async with lifespan(app):
            mock_init.assert_called_once_with(batch_only=True)
            mock_pipeline.assert_called_once()

@pytest.mark.asyncio
async def test_lifespan_disabled():
    with patch.dict(os.environ, {'DIARIZATION_V2_ENABLED': 'false'}, clear=True):
        with pytest.raises(RuntimeError, match='batch diarization requires DIARIZATION_V2_ENABLED=true'):
            async with lifespan(app):
                pass

def test_run_v2():
    with patch('diarizer.batch_main.decode_audio') as mock_decode, \
         patch('diarizer.batch_main.infer') as mock_infer:

        mock_decode.return_value = "mock_waveform"
        mock_infer.return_value = "mock_result"

        body = bytearray(b"test body")
        content_type = "audio/wav"
        min_speakers = 1
        max_speakers = 2

        result = run_v2(body, content_type, min_speakers, max_speakers)

        mock_decode.assert_called_once_with(body, content_type)
        assert len(body) == 0
        mock_infer.assert_called_once_with("mock_waveform", min_speakers, max_speakers)
        assert result == "mock_result"
