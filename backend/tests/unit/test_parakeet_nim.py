"""Unit tests for Parakeet NIM inference mode (transcribe.py)."""

import os
import sys
import tempfile
import types
import wave as _wave
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('DEEPGRAM_API_KEY', 'x')

_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
_db_client.document_id_from_seed = lambda s: f'id-{s}'
sys.modules.setdefault('database._client', _db_client)


def _make_wav_file(duration_s=1.0, sample_rate=16000):
    pcm = b'\x00\x01' * int(sample_rate * duration_s)
    buf = BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.write(buf.getvalue())
    tmp.close()
    return tmp.name


class TestNimTranscribe:

    def test_nim_calls_correct_endpoint(self):
        with patch.dict(os.environ, {'PARAKEET_INFERENCE_MODE': 'nim', 'NIM_INFERENCE_URL': 'http://nim:9000'}):
            if 'transcribe' in sys.modules:
                del sys.modules['transcribe']

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../parakeet'))
            try:
                import importlib
                import transcribe as t

                importlib.reload(t)

                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {
                    "text": "Hello world",
                    "segments": [{"text": "Hello world", "start": 0.0, "end": 1.0}],
                }

                wav_file = _make_wav_file()
                try:
                    with patch('httpx.Client') as mock_cls:
                        mock_client = MagicMock()
                        mock_client.__enter__ = MagicMock(return_value=mock_client)
                        mock_client.__exit__ = MagicMock(return_value=False)
                        mock_client.post.return_value = mock_resp
                        mock_cls.return_value = mock_client

                        result = t._transcribe_nim(wav_file)

                    assert result['text'] == 'Hello world'
                    assert len(result['segments']) == 1

                    call_args = mock_client.post.call_args
                    url = call_args[0][0]
                    assert '/v1/audio/transcriptions' in url
                    data = call_args.kwargs.get('data') or call_args[1].get('data', {})
                    assert 'language' in data
                finally:
                    os.unlink(wav_file)
            finally:
                sys.path.pop(0)
                if 'transcribe' in sys.modules:
                    del sys.modules['transcribe']

    def test_nim_text_only_fallback(self):
        with patch.dict(os.environ, {'PARAKEET_INFERENCE_MODE': 'nim', 'NIM_INFERENCE_URL': 'http://nim:9000'}):
            if 'transcribe' in sys.modules:
                del sys.modules['transcribe']

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../parakeet'))
            try:
                import importlib
                import transcribe as t

                importlib.reload(t)

                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {"text": "fallback", "segments": []}

                wav_file = _make_wav_file()
                try:
                    with patch('httpx.Client') as mock_cls:
                        mock_client = MagicMock()
                        mock_client.__enter__ = MagicMock(return_value=mock_client)
                        mock_client.__exit__ = MagicMock(return_value=False)
                        mock_client.post.return_value = mock_resp
                        mock_cls.return_value = mock_client

                        result = t._transcribe_nim(wav_file)

                    assert result['text'] == 'fallback'
                    assert len(result['segments']) == 1
                    assert result['segments'][0]['text'] == 'fallback'
                finally:
                    os.unlink(wav_file)
            finally:
                sys.path.pop(0)
                if 'transcribe' in sys.modules:
                    del sys.modules['transcribe']

    def test_nim_error_propagates(self):
        with patch.dict(os.environ, {'PARAKEET_INFERENCE_MODE': 'nim', 'NIM_INFERENCE_URL': 'http://nim:9000'}):
            if 'transcribe' in sys.modules:
                del sys.modules['transcribe']

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../parakeet'))
            try:
                import importlib
                import httpx
                import transcribe as t

                importlib.reload(t)

                wav_file = _make_wav_file()
                try:
                    with patch('httpx.Client') as mock_cls:
                        mock_client = MagicMock()
                        mock_client.__enter__ = MagicMock(return_value=mock_client)
                        mock_client.__exit__ = MagicMock(return_value=False)
                        mock_client.post.side_effect = httpx.ConnectError("NIM down")
                        mock_cls.return_value = mock_client

                        with pytest.raises(httpx.ConnectError):
                            t._transcribe_nim(wav_file)
                finally:
                    os.unlink(wav_file)
            finally:
                sys.path.pop(0)
                if 'transcribe' in sys.modules:
                    del sys.modules['transcribe']
