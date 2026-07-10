"""Unit tests for Parakeet StreamSession (VAD + ASR + diarization)."""

import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, patch, AsyncMock

import numpy as np
import pytest

os.environ.setdefault('DEEPGRAM_API_KEY', 'x')
os.environ.setdefault('HOSTED_PARAKEET_API_URL', 'http://fake:8080')
os.environ.setdefault('PARAKEET_STREAM_MODEL', 'test-model')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../parakeet'))

from testing.import_isolation import load_module_fresh, stub_modules

_STREAM_HANDLER_PATH = os.path.join(os.path.dirname(__file__), '../../parakeet', 'stream_handler.py')


def _mock_wav_bytes_to_waveform(wav_bytes):
    result = MagicMock()
    n_samples = max(len(wav_bytes) // 2, 16000)
    result.shape = [1, n_samples]
    return result, 16000


def _make_pcm(duration_s=1.0, sr=16000):
    samples = int(sr * duration_s)
    return (np.sin(np.linspace(0, 440 * 2 * np.pi * duration_s, samples)) * 16000).astype(np.int16).tobytes()


@pytest.fixture(scope="module", autouse=True)
def _stream_handler_module():
    """Load stream_handler fresh against stubbed torch/nemo/transcribe chains.

    torch/nemo are not installed in the test environment, so fake modules must be
    active in ``sys.modules`` before ``stream_handler`` is exec'd (it binds
    ``torch`` at import). ``stub_modules`` keeps the fakes active for the whole
    module and evicts them (plus the freshly-loaded ``stream_handler`` and
    ``speaker_math``) on teardown, so nothing leaks to later test files.
    """
    _db_client = types.ModuleType('database._client')
    _db_client.db = MagicMock()
    _db_client.document_id_from_seed = lambda s: f'id-{s}'

    mock_transcribe = MagicMock()
    mock_transcribe.transcribe_file = MagicMock(return_value={"text": "", "segments": []})
    mock_transcribe._stream_model = None
    mock_transcribe._batch_model = None
    mock_transcribe._model = None
    mock_transcribe._gpu_worker = None
    mock_transcribe.INFERENCE_MODE = "nemo"
    mock_transcribe.has_builtin_embedding = MagicMock(return_value=False)
    mock_transcribe.wav_bytes_to_waveform = _mock_wav_bytes_to_waveform

    _langdetect = types.ModuleType('langdetect')
    _langdetect_exceptions = types.ModuleType('langdetect.lang_detect_exception')

    class _LangDetectException(Exception):
        pass

    _langdetect.detect = MagicMock(return_value='en')
    _langdetect_exceptions.LangDetectException = _LangDetectException

    _scipy = types.ModuleType('scipy')
    _scipy_spatial = types.ModuleType('scipy.spatial')
    _scipy_distance = types.ModuleType('scipy.spatial.distance')

    def _cosine_cdist(a, b, metric="cosine"):
        if metric != "cosine":
            raise ValueError(f"unsupported metric: {metric}")
        a = np.asarray(a, dtype=np.float32)
        b = np.asarray(b, dtype=np.float32)
        a_norm = np.linalg.norm(a, axis=1, keepdims=True)
        b_norm = np.linalg.norm(b, axis=1, keepdims=True).T
        denom = a_norm * b_norm
        similarity = np.divide(
            a @ b.T, denom, out=np.zeros((a.shape[0], b.shape[0]), dtype=np.float32), where=denom != 0
        )
        return 1.0 - similarity

    _scipy_distance.cdist = _cosine_cdist
    _scipy_spatial.distance = _scipy_distance
    _scipy.spatial = _scipy_spatial

    _torch = types.ModuleType('torch')
    _torch.int16 = np.int16

    class _TorchArray:
        def __init__(self, value):
            self.value = np.asarray(value)

        def float(self):
            return self

        def __truediv__(self, value):
            return _TorchArray(self.value / value)

    _torch.frombuffer = lambda buffer, dtype: _TorchArray(np.frombuffer(buffer, dtype=dtype))
    _torch.hub = MagicMock()
    _torch.hub.load.side_effect = RuntimeError("torch hub unavailable in unit tests")

    _nemo_rnnt_decoding = MagicMock()
    _nemo_rnnt_utils = MagicMock()
    _nemo_streaming_utils = MagicMock()
    _omegaconf = MagicMock()

    fakes = {
        'database._client': _db_client,
        'transcribe': mock_transcribe,
        'langdetect': _langdetect,
        'langdetect.lang_detect_exception': _langdetect_exceptions,
        'scipy': _scipy,
        'scipy.spatial': _scipy_spatial,
        'scipy.spatial.distance': _scipy_distance,
        'torch': _torch,
        'nemo': MagicMock(),
        'nemo.collections': MagicMock(),
        'nemo.collections.asr': MagicMock(),
        'nemo.collections.asr.parts': MagicMock(),
        'nemo.collections.asr.parts.submodules': MagicMock(),
        'nemo.collections.asr.parts.submodules.rnnt_decoding': _nemo_rnnt_decoding,
        'nemo.collections.asr.parts.utils': MagicMock(),
        'nemo.collections.asr.parts.utils.rnnt_utils': _nemo_rnnt_utils,
        'nemo.collections.asr.parts.utils.streaming_utils': _nemo_streaming_utils,
        'omegaconf': _omegaconf,
    }
    with stub_modules(fakes):
        import speaker_math

        sh = load_module_fresh("stream_handler", _STREAM_HANDLER_PATH)
        g = globals()
        g["sh"] = sh
        g["speaker_math"] = speaker_math
        yield sh


class TestCosineDistance:

    def test_cosine_distance_matches_expected_values(self):
        assert speaker_math.cosine_distance(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(0.0)
        assert speaker_math.cosine_distance(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(1.0)

    def test_cosine_distance_handles_zero_vector(self):
        assert speaker_math.cosine_distance(np.array([0.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(1.0)

    def test_stream_handler_uses_shared_cosine_distance(self):
        assert sh.cosine_distance is speaker_math.cosine_distance


class TestStreamSessionFeed:

    def test_silence_produces_no_segments(self):
        session = sh.StreamSession(sample_rate=16000)
        session._vad = None
        silent = b'\x00' * 3200
        result = asyncio.run(session.feed(silent))
        assert result == []

    def test_speech_then_silence_produces_segments(self):
        session = sh.StreamSession(sample_rate=16000)

        with patch.object(session, '_transcribe_utterance', new_callable=AsyncMock) as mock_trans:
            mock_trans.return_value = [{"text": "hello", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_0"}]

            with patch.object(session, '_run_vad', side_effect=[True] * 32 + [False] * 64):
                pcm = _make_pcm(1.0)
                asyncio.run(session.feed(pcm))

                silence = b'\x00' * (16000 * 2 * 2)
                result = asyncio.run(session.feed(silence))

            assert mock_trans.called or len(result) > 0


class TestStreamSessionFlush:

    def test_flush_with_pending_audio(self):
        session = sh.StreamSession(sample_rate=16000)
        session._pending_audio = bytearray(_make_pcm(1.0))
        session._speech_start_s = 0.0
        session._is_speaking = True

        with patch.object(session, '_transcribe_utterance', new_callable=AsyncMock) as mock_trans:
            mock_trans.return_value = [{"text": "flushed", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_0"}]
            result = asyncio.run(session.flush())

        assert len(result) == 1
        assert result[0]["text"] == "flushed"

    def test_flush_empty_returns_nothing(self):
        session = sh.StreamSession(sample_rate=16000)
        result = asyncio.run(session.flush())
        assert result == []

    def test_flush_short_audio_returns_nothing(self):
        session = sh.StreamSession(sample_rate=16000)
        session._pending_audio = bytearray(b'\x00' * 100)
        session._speech_start_s = 0.0
        result = asyncio.run(session.flush())
        assert result == []


class TestStreamSessionRNNTStreaming:

    def test_drain_streaming_asr_decodes_available_chunks(self):
        class FakeDecoder:
            def __init__(self):
                self.calls = []

            def next_input_bytes(self, bytes_per_sample):
                assert bytes_per_sample == 2
                return 4 if not self.calls else 2

            def decode_pcm(self, pcm, is_last_chunk=False):
                self.calls.append((pcm, is_last_chunk))
                return "hello" if len(self.calls) == 1 else "hello world"

        session = sh.StreamSession(sample_rate=16000)
        decoder = FakeDecoder()
        session._streaming_decoder = decoder
        session._asr_audio_buf = bytearray(b"abcdef")

        session._drain_streaming_asr_sync(force=False)

        assert decoder.calls == [(b"abcd", False), (b"ef", False)]
        assert session._streaming_text == "hello world"
        assert session._asr_audio_buf == bytearray()

    def test_streaming_utterance_does_not_call_batch_transcribe_when_text_not_ready(self):
        session = sh.StreamSession(sample_rate=16000)
        session._pending_audio = bytearray(_make_pcm(1.0))
        session._speech_start_s = 0.0
        session._streaming_text = ""

        with patch.object(session, '_streaming_enabled', return_value=True), patch.object(
            sh, 'transcribe_file', return_value={"text": "batch", "segments": []}
        ) as batch_transcribe:
            result = asyncio.run(session._transcribe_utterance())

        assert result == []
        assert not batch_transcribe.called

    def test_streaming_utterance_emits_delta_text(self):
        session = sh.StreamSession(sample_rate=16000)
        session._pending_audio = bytearray(_make_pcm(1.0))
        session._speech_start_s = 2.0
        session._streaming_text = "hello world"
        session._last_emitted_text = "hello"

        with patch.object(session, '_streaming_enabled', return_value=True), patch.object(
            session, '_assign_speaker', return_value="SPEAKER_0"
        ):
            result = asyncio.run(session._transcribe_utterance())

        assert result[0]["text"] == "world"
        assert result[0]["start"] == 2.0
        assert session._last_emitted_text == "hello world"


class TestStreamSessionCleanup:

    def test_cleanup_clears_all_buffers(self):
        session = sh.StreamSession(sample_rate=16000)
        session._pcm_buf = bytearray(b'\x00' * 1000)
        session._audio_buf = bytearray(b'\x00' * 1000)
        session._pending_audio = bytearray(b'\x00' * 1000)
        session._spk_centroids = [np.zeros((1, 256))]
        session._spk_counts = [1]

        session.cleanup()

        assert len(session._pcm_buf) == 0
        assert len(session._pending_audio) == 0
        assert len(session._spk_centroids) == 0
        assert len(session._spk_counts) == 0


class TestStreamSessionSpeaker:

    def test_short_segment_returns_last_speaker(self):
        session = sh.StreamSession(sample_rate=16000)
        session._last_speaker = 2
        result = session._assign_speaker(b'\x00' * 100, 0.0, 0.3)
        assert result == "SPEAKER_2"

    def test_no_embedding_returns_last_speaker(self):
        session = sh.StreamSession(sample_rate=16000)
        with patch.object(session, '_get_embedding', return_value=None):
            result = session._assign_speaker(_make_pcm(1.0), 0.0, 1.0)
        assert result == "SPEAKER_0"


class TestStreamSessionVADParams:

    def test_custom_threshold(self):
        session = sh.StreamSession(sample_rate=16000, vad_threshold=0.8)
        assert session._speech_threshold == 0.8

    def test_custom_hangover(self):
        session = sh.StreamSession(sample_rate=16000, hangover_s=3.0)
        expected_chunks = int(3.0 * 16000 / 512)
        assert session._hangover_chunks == expected_chunks

    def test_defaults(self):
        session = sh.StreamSession(sample_rate=16000)
        assert session._speech_threshold == 0.5
        assert session._hangover_s == 0.8


class TestStreamSessionBuiltinEmbedding:

    def test_get_embedding_routes_through_gpu_worker(self):
        session = sh.StreamSession(sample_rate=16000)
        fake_worker = MagicMock()
        fake_worker.submit_embedding_sync.return_value = np.zeros(256, dtype=np.float32)

        with patch.object(sh, 'has_builtin_embedding', return_value=True), patch.object(
            sh._transcribe_mod, '_gpu_worker', fake_worker
        ):
            result = session._get_embedding_builtin(_make_pcm(1.0))

        fake_worker.submit_embedding_sync.assert_called_once()
        assert result is not None
        assert result.shape == (1, 256)

    def test_get_embedding_reshapes_1d(self):
        session = sh.StreamSession(sample_rate=16000)
        fake_worker = MagicMock()
        fake_worker.submit_embedding_sync.return_value = np.ones(128, dtype=np.float32)

        with patch.object(sh, 'has_builtin_embedding', return_value=True), patch.object(
            sh._transcribe_mod, '_gpu_worker', fake_worker
        ):
            result = session._get_embedding_builtin(_make_pcm(1.0))

        assert result.shape == (1, 128)

    def test_get_embedding_short_audio_returns_none(self):
        session = sh.StreamSession(sample_rate=16000)

        short_waveform = MagicMock()
        short_waveform.shape = [1, 4800]

        with patch.object(sh, 'wav_bytes_to_waveform', return_value=(short_waveform, 16000)):
            result = session._get_embedding_builtin(b'\x00' * 100)

        assert result is None

    def test_get_embedding_prefers_builtin_over_http(self):
        session = sh.StreamSession(sample_rate=16000)
        fake_worker = MagicMock()
        fake_worker.submit_embedding_sync.return_value = np.zeros(256, dtype=np.float32)

        with patch.object(sh, 'has_builtin_embedding', return_value=True), patch.object(
            sh._transcribe_mod, '_gpu_worker', fake_worker
        ), patch.object(session, '_get_embedding_http') as http_mock:
            result = session._get_embedding(_make_pcm(1.0))

        assert result is not None
        http_mock.assert_not_called()

    def test_get_embedding_falls_back_to_http_when_no_builtin(self):
        session = sh.StreamSession(sample_rate=16000)
        http_emb = np.ones((1, 256), dtype=np.float32)

        with patch.object(sh, 'has_builtin_embedding', return_value=False), patch.object(
            session, '_get_embedding_http', return_value=http_emb
        ) as http_mock:
            old_url = sh.SPEAKER_EMBEDDING_URL
            sh.SPEAKER_EMBEDDING_URL = 'http://fake'
            try:
                result = session._get_embedding(_make_pcm(1.0))
            finally:
                sh.SPEAKER_EMBEDDING_URL = old_url

        http_mock.assert_called_once()
        np.testing.assert_array_equal(result, http_emb)
