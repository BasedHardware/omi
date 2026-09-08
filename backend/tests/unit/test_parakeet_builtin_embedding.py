"""Tests for built-in speaker embedding in parakeet transcribe.py.

Validates that batch diarization uses the built-in wespeaker model
(via GPU worker) first and falls back to HTTP when unavailable.
"""

import io
import os
import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

os.environ.setdefault('PARAKEET_INFERENCE_MODE', 'nemo')
os.environ.setdefault('PARAKEET_STREAM_MODEL', '')
os.environ.setdefault('PARAKEET_DEVICE', 'cpu')
os.environ.setdefault('PARAKEET_TORCH_COMPILE', 'false')
os.environ.setdefault('PARAKEET_CUDA_GRAPHS', 'false')

_torch_mock = MagicMock()
_torch_mock.cuda.is_available.return_value = False
_torch_mock.cuda.is_bf16_supported.return_value = False
_torch_mock.bfloat16 = 'bfloat16'


def _torch_from_numpy(arr):
    result = MagicMock()
    result.unsqueeze.return_value = result
    result.shape = [1, len(arr)]
    return result


_torch_mock.from_numpy = _torch_from_numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'parakeet'))

import transcribe  # noqa: E402


def _make_wav_bytes(duration_s=1.0, sample_rate=16000, channels=1):
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f'<{n_samples * channels}h', *([1000] * n_samples * channels)))
    return buf.getvalue()


def _make_wav_bytes_8bit(duration_s=1.0, sample_rate=16000):
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes([128] * n_samples))
    return buf.getvalue()


def _make_wav_bytes_32bit(duration_s=1.0, sample_rate=16000):
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(4)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f'<{n_samples}i', *([100000] * n_samples)))
    return buf.getvalue()


def _fake_waveform(n_samples):
    wf = MagicMock()
    wf.shape = [1, n_samples]
    wf.unsqueeze.return_value = wf
    return wf


class TestWavBytesToWaveform:
    def _patch_torch(self):
        return patch.object(transcribe, '_torch', _torch_mock)

    def test_returns_waveform_and_sample_rate(self):
        wav = _make_wav_bytes(duration_s=0.5, sample_rate=16000)
        with self._patch_torch():
            waveform, sr = transcribe.wav_bytes_to_waveform(wav)
        assert sr == 16000
        assert waveform.shape == [1, 8000]

    def test_stereo_downmix(self):
        wav = _make_wav_bytes(duration_s=0.5, sample_rate=16000, channels=2)
        with self._patch_torch():
            waveform, sr = transcribe.wav_bytes_to_waveform(wav)
        assert sr == 16000
        assert waveform.shape == [1, 8000]

    def test_8bit_unsigned_pcm(self):
        wav = _make_wav_bytes_8bit(duration_s=0.5, sample_rate=16000)
        with self._patch_torch():
            waveform, sr = transcribe.wav_bytes_to_waveform(wav)
        assert sr == 16000
        assert waveform.shape == [1, 8000]

    def test_32bit_pcm(self):
        wav = _make_wav_bytes_32bit(duration_s=0.5, sample_rate=16000)
        with self._patch_torch():
            waveform, sr = transcribe.wav_bytes_to_waveform(wav)
        assert sr == 16000
        assert waveform.shape == [1, 8000]

    def test_unsupported_width_raises(self):
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(16000)
            wf.writeframes(b'\x00\x00\x00' * 8000)
        with pytest.raises(ValueError, match="Unsupported WAV sample width"):
            transcribe.wav_bytes_to_waveform(buf.getvalue())


def _mock_gpu_worker(embedding_model=True):
    worker = MagicMock()
    worker.is_ready = True
    worker._embedding_model = MagicMock() if embedding_model else None
    worker.submit_embedding_sync.return_value = np.zeros(256, dtype=np.float32)
    return worker


class TestGetEmbedding:
    def test_uses_builtin_model_first(self):
        wav = _make_wav_bytes(duration_s=1.0)
        worker = _mock_gpu_worker(embedding_model=True)

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(16000), 16000)
        ), patch.object(transcribe, '_get_embedding_http') as http_mock:
            result = transcribe._get_embedding(wav)

        assert result is not None
        assert result.shape == (1, 256)
        http_mock.assert_not_called()

    def test_falls_back_to_http_when_builtin_unavailable(self):
        wav = _make_wav_bytes(duration_s=1.0)
        http_emb = np.ones((1, 256), dtype=np.float32)
        worker = _mock_gpu_worker(embedding_model=False)

        with patch.object(transcribe, '_gpu_worker', worker):
            with patch.object(transcribe, '_get_embedding_http', return_value=http_emb) as http_mock:
                old_url = transcribe.SPEAKER_EMBEDDING_URL
                transcribe.SPEAKER_EMBEDDING_URL = 'http://fake-diarizer'
                try:
                    result = transcribe._get_embedding(wav)
                finally:
                    transcribe.SPEAKER_EMBEDDING_URL = old_url

        http_mock.assert_called_once_with(wav)
        assert result is not None
        np.testing.assert_array_equal(result, http_emb)

    def test_falls_back_to_http_when_builtin_fails(self):
        wav = _make_wav_bytes(duration_s=1.0)
        http_emb = np.ones((1, 256), dtype=np.float32)
        worker = _mock_gpu_worker(embedding_model=True)
        worker.submit_embedding_sync.side_effect = RuntimeError("GPU error")

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(16000), 16000)
        ), patch.object(transcribe, '_get_embedding_http', return_value=http_emb) as http_mock:
            old_url = transcribe.SPEAKER_EMBEDDING_URL
            transcribe.SPEAKER_EMBEDDING_URL = 'http://fake-diarizer'
            try:
                result = transcribe._get_embedding(wav)
            finally:
                transcribe.SPEAKER_EMBEDDING_URL = old_url

        http_mock.assert_called_once_with(wav)
        np.testing.assert_array_equal(result, http_emb)

    def test_returns_none_when_no_builtin_no_url(self):
        wav = _make_wav_bytes(duration_s=1.0)
        worker = _mock_gpu_worker(embedding_model=False)

        with patch.object(transcribe, '_gpu_worker', worker):
            old_url = transcribe.SPEAKER_EMBEDDING_URL
            transcribe.SPEAKER_EMBEDDING_URL = ''
            try:
                result = transcribe._get_embedding(wav)
            finally:
                transcribe.SPEAKER_EMBEDDING_URL = old_url

        assert result is None

    def test_returns_none_when_builtin_fails_and_http_fails(self):
        wav = _make_wav_bytes(duration_s=1.0)
        worker = _mock_gpu_worker(embedding_model=True)
        worker.submit_embedding_sync.side_effect = RuntimeError("GPU error")

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(16000), 16000)
        ), patch.object(transcribe, '_get_embedding_http', return_value=None):
            old_url = transcribe.SPEAKER_EMBEDDING_URL
            transcribe.SPEAKER_EMBEDDING_URL = 'http://fake-diarizer'
            try:
                result = transcribe._get_embedding(wav)
            finally:
                transcribe.SPEAKER_EMBEDDING_URL = old_url

        assert result is None

    def test_reshapes_1d_embedding(self):
        wav = _make_wav_bytes(duration_s=1.0)
        worker = _mock_gpu_worker(embedding_model=True)
        worker.submit_embedding_sync.return_value = np.zeros(128, dtype=np.float32)

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(16000), 16000)
        ):
            result = transcribe._get_embedding(wav)

        assert result.shape == (1, 128)


class TestEmbeddingBuiltinDuration:
    def test_short_audio_below_min_duration_returns_none(self):
        wav = _make_wav_bytes(duration_s=0.3)
        worker = _mock_gpu_worker(embedding_model=True)

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(4800), 16000)
        ):
            result = transcribe._get_embedding_builtin(wav)

        assert result is None
        worker.submit_embedding_sync.assert_not_called()

    def test_audio_at_exact_min_duration_returns_embedding(self):
        wav = _make_wav_bytes(duration_s=0.6)
        worker = _mock_gpu_worker(embedding_model=True)

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(9600), 16000)
        ):
            result = transcribe._get_embedding_builtin(wav)

        assert result is not None
        worker.submit_embedding_sync.assert_called_once()

    def test_audio_just_above_min_duration_returns_embedding(self):
        wav = _make_wav_bytes(duration_s=0.7)
        worker = _mock_gpu_worker(embedding_model=True)

        with patch.object(transcribe, '_gpu_worker', worker), patch.object(
            transcribe, 'wav_bytes_to_waveform', return_value=(_fake_waveform(11200), 16000)
        ):
            result = transcribe._get_embedding_builtin(wav)

        assert result is not None
        worker.submit_embedding_sync.assert_called_once()


class TestDiarizeSegmentsGating:
    def test_proceeds_with_builtin_model_even_without_url(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_bytes = _make_wav_bytes(duration_s=2.0)
        wav_path.write_bytes(wav_bytes)

        base = {"text": "hello", "segments": [{"text": "hello", "start": 0.0, "end": 2.0}]}
        worker = _mock_gpu_worker(embedding_model=True)

        with patch.object(transcribe, '_gpu_worker', worker):
            old_url = transcribe.SPEAKER_EMBEDDING_URL
            transcribe.SPEAKER_EMBEDDING_URL = ''
            try:
                result = transcribe._diarize_segments(str(wav_path), base)
            finally:
                transcribe.SPEAKER_EMBEDDING_URL = old_url

        assert result["segments"][0].get("speaker") is not None

    def test_skips_diarization_when_no_model_and_no_url(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav_bytes(duration_s=1.0))

        base = {"text": "hi", "segments": [{"text": "hi", "start": 0.0, "end": 1.0}]}
        worker = _mock_gpu_worker(embedding_model=False)

        with patch.object(transcribe, '_gpu_worker', worker):
            old_url = transcribe.SPEAKER_EMBEDDING_URL
            transcribe.SPEAKER_EMBEDDING_URL = ''
            try:
                result = transcribe._diarize_segments(str(wav_path), base)
            finally:
                transcribe.SPEAKER_EMBEDDING_URL = old_url

        assert result["segments"][0]["speaker"] == "SPEAKER_0"
