"""Unit tests for ParakeetPrerecordedProvider (batch STT path).

Tests cover: factory routing, transcribe_bytes/transcribe_url, output format,
diarization clustering, retry/error handling, return_language fallback, and
compatibility with postprocess_words().
"""

import os
import sys
import types
import wave as _wave
from io import BytesIO
from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pytest

os.environ.setdefault('DEEPGRAM_API_KEY', 'x')
os.environ.setdefault('HOSTED_PARAKEET_API_URL', 'http://fake-parakeet:8080')
os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret')

_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
_db_client.document_id_from_seed = lambda s: f'id-{s}'
sys.modules.setdefault('database._client', _db_client)

import utils.stt.pre_recorded as pr  # noqa: E402


def _make_wav(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    pcm = b'\x00\x01' * int(sample_rate * duration_s)
    buf = BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _mock_parakeet_response(text="Hello world", segments=None):
    if segments is None:
        segments = [{"text": text, "start": 0.0, "end": 1.0}]
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"text": text, "segments": segments}
    return resp


class TestFactoryRouting:

    def test_parakeet_routing_in_get_prerecorded_service(self):
        with patch.object(pr, 'stt_prerecorded_models', ['parakeet']):
            service, lang, model = pr.get_prerecorded_service('en')
            assert service == pr.PrerecordedSTTService.PARAKEET
            assert model == 'parakeet'

    def test_parakeet_routing_with_supported_language(self):
        with patch.object(pr, 'stt_prerecorded_models', ['parakeet']):
            service, lang, model = pr.get_prerecorded_service('fr')
            assert service == pr.PrerecordedSTTService.PARAKEET
            assert lang == 'fr'

    def test_parakeet_fallback_to_deepgram_for_unsupported_language(self):
        with patch.object(pr, 'stt_prerecorded_models', ['parakeet']):
            service, lang, model = pr.get_prerecorded_service('zh-CN')
            assert service == pr.PrerecordedSTTService.DEEPGRAM

    def test_parakeet_fallback_for_cjk(self):
        with patch.object(pr, 'stt_prerecorded_models', ['parakeet']):
            for unsupported in ['ja', 'zh', 'ko', 'hi', 'vi']:
                service, lang, model = pr.get_prerecorded_service(unsupported)
                assert service == pr.PrerecordedSTTService.DEEPGRAM, f'{unsupported} should fall back to Deepgram'

    def test_get_prerecorded_provider_returns_parakeet(self):
        with patch.object(pr, 'stt_prerecorded_models', ['parakeet']):
            provider = pr.get_prerecorded_provider()
            assert isinstance(provider, pr.ParakeetPrerecordedProvider)

    def test_unknown_model_falls_back_to_deepgram(self):
        with patch.object(pr, 'stt_prerecorded_models', ['unknown-model']):
            provider = pr.get_prerecorded_provider()
            assert isinstance(provider, pr.DeepgramPrerecordedProvider)


class TestTranscribeBytes:

    def test_basic_transcription(self):
        wav = _make_wav()
        mock_resp = _mock_parakeet_response("Hello world", [{"text": "Hello world", "start": 0.0, "end": 1.0}])

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert len(words) == 1
        assert words[0]['text'] == 'Hello world'
        assert words[0]['timestamp'] == [0.0, 1.0]
        assert words[0]['speaker'] == 'SPEAKER_00'

    def test_pcm_encoding_wraps_as_wav(self):
        pcm = b'\x00\x01' * 16000
        mock_resp = _mock_parakeet_response("test", [{"text": "test", "start": 0.0, "end": 1.0}])

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(pcm, encoding='linear16', diarize=False)

        assert len(words) == 1
        call_kwargs = mock_client.post.call_args
        posted_files = call_kwargs.kwargs.get('files') or call_kwargs[1].get('files')
        assert posted_files is not None

    def test_empty_response(self):
        wav = _make_wav()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"text": "", "segments": []}

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert words == []

    def test_fallback_when_only_text_returned(self):
        wav = _make_wav()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"text": "fallback text", "segments": []}

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert len(words) == 1
        assert words[0]['text'] == 'fallback text'
        assert words[0]['timestamp'] == [0.0, 0.0]

    def test_return_language_with_explicit(self):
        wav = _make_wav()
        mock_resp = _mock_parakeet_response("test", [{"text": "test", "start": 0.0, "end": 0.5}])

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words, lang = pr.parakeet_prerecorded_from_bytes(wav, diarize=False, return_language=True, language='vi')

        assert lang == 'vi'
        assert len(words) == 1

    def test_return_language_default_fallback(self):
        wav = _make_wav()
        mock_resp = _mock_parakeet_response("test", [{"text": "test", "start": 0.0, "end": 0.5}])

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words, lang = pr.parakeet_prerecorded_from_bytes(wav, diarize=False, return_language=True)

        assert lang == 'en'

    def test_no_auth_header_sent(self):
        wav = _make_wav()
        mock_resp = _mock_parakeet_response()

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get('headers') or call_kwargs[1].get('headers')
        assert headers is None

    def test_retry_on_failure(self):
        wav = _make_wav()
        mock_resp = _mock_parakeet_response()

        call_count = {'n': 0}

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            def side_effect(*args, **kwargs):
                call_count['n'] += 1
                if call_count['n'] == 1:
                    raise httpx.ConnectError("connection refused")
                return mock_resp

            mock_client.post.side_effect = side_effect
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert len(words) == 1
        assert call_count['n'] == 2

    def test_raises_after_exhausted_retries(self):
        wav = _make_wav()

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("down")
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match='Parakeet transcription failed'):
                pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

    def test_missing_api_url(self):
        wav = _make_wav()
        with patch.dict(os.environ, {'HOSTED_PARAKEET_API_URL': ''}):
            with pytest.raises(ValueError, match='HOSTED_PARAKEET_API_URL'):
                pr.parakeet_prerecorded_from_bytes(wav, diarize=False)


class TestTranscribeUrl:

    def test_downloads_then_transcribes(self):
        wav = _make_wav()

        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.headers = {'content-length': str(len(wav))}
        stream_resp.iter_bytes = MagicMock(return_value=iter([wav]))
        stream_resp.__enter__ = MagicMock(return_value=stream_resp)
        stream_resp.__exit__ = MagicMock(return_value=False)

        transcribe_resp = _mock_parakeet_response("hello", [{"text": "hello", "start": 0.0, "end": 0.5}])

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.stream.return_value = stream_resp
            mock_client.post.return_value = transcribe_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded("https://storage.example.com/audio.wav", diarize=False)

        assert len(words) == 1
        assert words[0]['text'] == 'hello'

    def test_rejects_oversized_content_length(self):
        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.headers = {'content-length': str(pr._PARAKEET_MAX_DOWNLOAD_BYTES + 1)}
        stream_resp.__enter__ = MagicMock(return_value=stream_resp)
        stream_resp.__exit__ = MagicMock(return_value=False)

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.stream.return_value = stream_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match='Parakeet transcription'):
                pr.parakeet_prerecorded("https://example.com/big.wav", diarize=False)

    def test_rejects_streamed_overflow_without_content_length(self):
        chunk_size = 10 * 1024 * 1024  # 10MB per chunk
        num_chunks = (pr._PARAKEET_MAX_DOWNLOAD_BYTES // chunk_size) + 2

        def make_stream_resp():
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.headers = {}
            resp.iter_bytes = MagicMock(return_value=iter([b'\x00' * chunk_size] * num_chunks))
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.stream = MagicMock(side_effect=lambda *a, **kw: make_stream_resp())
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match='Parakeet transcription'):
                pr.parakeet_prerecorded("https://example.com/streamed.wav", diarize=False)


class TestStreamingFactoryRouting:

    def test_parakeet_in_stt_service_models(self):
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet']), patch.dict(
            os.environ, {'HOSTED_PARAKEET_API_URL': 'http://fake-parakeet:8080'}
        ):
            service, lang, model = get_stt_service_for_language('en')
            assert service == STTService.parakeet
            assert model == 'parakeet'

    def test_parakeet_streaming_fallback_for_cjk(self):
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet', 'dg-nova-3']), patch.dict(
            os.environ, {'HOSTED_PARAKEET_API_URL': 'http://fake-parakeet:8080'}
        ):
            service, lang, model = get_stt_service_for_language('ja')
            assert service == STTService.deepgram, 'Japanese should fall back to Deepgram'

    def test_parakeet_fallback_without_url(self):
        from utils.stt.streaming import STTService, get_stt_service_for_language

        with patch('utils.stt.streaming.stt_service_models', ['parakeet']), patch.dict(os.environ, {}, clear=False):
            env_backup = os.environ.pop('HOSTED_PARAKEET_API_URL', None)
            try:
                service, lang, model = get_stt_service_for_language('en')
                assert service == STTService.deepgram
            finally:
                if env_backup:
                    os.environ['HOSTED_PARAKEET_API_URL'] = env_backup


class TestOutputFormat:

    def test_words_compatible_with_postprocess_words(self):
        wav = _make_wav(duration_s=3.0)
        segments = [
            {"text": "Hello there", "start": 0.0, "end": 1.0},
            {"text": "How are you", "start": 1.5, "end": 2.5},
        ]
        mock_resp = _mock_parakeet_response("Hello there How are you", segments)

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert len(words) == 2
        for w in words:
            assert 'timestamp' in w
            assert isinstance(w['timestamp'], list)
            assert len(w['timestamp']) == 2
            assert 'speaker' in w
            assert w['speaker'].startswith('SPEAKER_')
            assert 'text' in w

        result = pr.postprocess_words(words, duration=3)
        assert len(result) >= 1

    def test_multiple_segments_preserve_timestamps(self):
        wav = _make_wav(duration_s=5.0)
        segments = [
            {"text": "First segment", "start": 0.0, "end": 1.5},
            {"text": "Second segment", "start": 2.0, "end": 3.5},
            {"text": "Third segment", "start": 4.0, "end": 5.0},
        ]
        mock_resp = _mock_parakeet_response("", segments)

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        assert words[0]['timestamp'] == [0.0, 1.5]
        assert words[1]['timestamp'] == [2.0, 3.5]
        assert words[2]['timestamp'] == [4.0, 5.0]


class TestDiarization:

    def _dir_vec(self, idx: int) -> np.ndarray:
        v = np.zeros((1, 256), np.float32)
        v[0, idx] = 1.0
        return v

    def test_diarize_false_all_speaker_00(self):
        wav = _make_wav(duration_s=3.0)
        segments = [
            {"text": "A", "start": 0.0, "end": 1.0},
            {"text": "B", "start": 1.5, "end": 2.5},
        ]
        mock_resp = _mock_parakeet_response("A B", segments)

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=False)

        for w in words:
            assert w['speaker'] == 'SPEAKER_00'

    def test_short_segment_defaults_speaker_00(self):
        wav = _make_wav(duration_s=1.0)
        segments = [{"text": "hi", "start": 0.0, "end": 0.3}]
        mock_resp = _mock_parakeet_response("hi", segments)

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=True)

        assert words[0]['speaker'] == 'SPEAKER_00'

    def test_embedding_clusters_two_speakers(self):
        wav = _make_wav(duration_s=4.0)
        segments = [
            {"text": "A speaks", "start": 0.0, "end": 1.5},
            {"text": "B speaks", "start": 1.5, "end": 3.0},
            {"text": "A again", "start": 3.0, "end": 4.0},
        ]
        mock_resp = _mock_parakeet_response("A speaks B speaks A again", segments)

        emb_a = self._dir_vec(0)
        emb_b = self._dir_vec(1)
        call_idx = {'i': 0}
        emb_seq = [emb_a, emb_b, emb_a]

        def fake_extract(audio_data, filename="audio.wav"):
            v = emb_seq[call_idx['i']]
            call_idx['i'] += 1
            return v

        with patch('httpx.Client') as mock_client_cls, patch.object(pr, 'extract_embedding_from_bytes', fake_extract):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=True)

        assert words[0]['speaker'] == 'SPEAKER_00'
        assert words[1]['speaker'] == 'SPEAKER_01'
        assert words[2]['speaker'] == 'SPEAKER_00'

    def test_embedding_failure_falls_back(self):
        wav = _make_wav(duration_s=2.0)
        segments = [{"text": "test", "start": 0.0, "end": 1.5}]
        mock_resp = _mock_parakeet_response("test", segments)

        def fake_extract_boom(audio_data, filename="audio.wav"):
            raise RuntimeError("embedding service down")

        with patch('httpx.Client') as mock_client_cls, patch.object(
            pr, 'extract_embedding_from_bytes', fake_extract_boom
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = pr.parakeet_prerecorded_from_bytes(wav, diarize=True)

        assert words[0]['speaker'] == 'SPEAKER_00'


class TestProviderClass:

    def test_provider_transcribe_bytes_resets_state(self):
        provider = pr.ParakeetPrerecordedProvider()
        wav = _make_wav()
        mock_resp = _mock_parakeet_response()

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            words = provider.transcribe_bytes(wav, diarize=False)

        assert len(words) == 1

    def test_provider_transcribe_url_delegates(self):
        provider = pr.ParakeetPrerecordedProvider()
        wav = _make_wav()

        stream_resp = MagicMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.headers = {'content-length': str(len(wav))}
        stream_resp.iter_bytes = MagicMock(return_value=iter([wav]))
        stream_resp.__enter__ = MagicMock(return_value=stream_resp)
        stream_resp.__exit__ = MagicMock(return_value=False)

        transcribe_resp = _mock_parakeet_response()

        with patch('httpx.Client') as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.stream.return_value = stream_resp
            mock_client.post.return_value = transcribe_resp
            mock_client_cls.return_value = mock_client

            words = provider.transcribe_url("https://example.com/audio.wav", diarize=False)

        assert len(words) == 1
