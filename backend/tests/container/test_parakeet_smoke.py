"""
Container smoke tests -- run INSIDE the built Docker container.

CPU tests (no GPU needed, can run in CI):
    docker run --rm parakeet:test \
      python -m pytest tests/container/test_parakeet_smoke.py -v -k "not TestGPUInference"

Full suite with GPU:
    docker run --rm --gpus all parakeet:test \
      python -m pytest tests/container/test_parakeet_smoke.py -v
"""

import importlib
import io
import struct
import wave

import pytest
import torch


class TestImportChain:
    """Verify every patched dependency imports without error."""

    def test_torchaudio_compliance_kaldi(self):
        from torchaudio.compliance.kaldi import fbank

        assert callable(fbank)

    def test_torchaudio_functional(self):
        from torchaudio import functional

        assert hasattr(functional, "resample")

    def test_torchaudio_c_extension_disabled(self):
        from torchaudio._extension import _IS_TORCHAUDIO_EXT_AVAILABLE

        assert _IS_TORCHAUDIO_EXT_AVAILABLE is False

    def test_torchaudio_decorators_passthrough(self):
        """PR #8085 bug: decorators returned None instead of the function."""
        from torchaudio._extension import (
            fail_if_no_align,
            fail_if_no_ffmpeg,
            fail_if_no_kaldi,
            fail_if_no_rir,
            fail_if_no_soundfile,
            fail_if_no_sox,
        )

        sentinel = object()
        for decorator in [
            fail_if_no_sox,
            fail_if_no_ffmpeg,
            fail_if_no_soundfile,
            fail_if_no_kaldi,
            fail_if_no_align,
            fail_if_no_rir,
        ]:
            result = decorator(sentinel)
            assert result is sentinel, f"{decorator.__name__} must return the decorated function"

    def test_torchaudio_list_audio_backends(self):
        import torchaudio

        backends = torchaudio.list_audio_backends()
        assert isinstance(backends, list)

    def test_torchaudio_audio_metadata(self):
        from torchaudio import AudioMetaData

        assert AudioMetaData is not None

    def test_pyannote_model_import(self):
        from pyannote.audio import Model

        assert callable(Model.from_pretrained)

    def test_pyannote_inference_import(self):
        from pyannote.audio import Inference

        assert Inference is not None

    def test_torch_audiomentations_stub(self):
        from torch_audiomentations import Identity, Mix
        from torch_audiomentations.core.transforms_interface import BaseWaveformTransform
        from torch_audiomentations.utils.config import from_dict

        assert Identity is not None
        assert Mix is not None
        assert BaseWaveformTransform is not None
        assert callable(from_dict)

    def test_telemetry_stub(self):
        from pyannote.audio.telemetry import (
            set_opentelemetry_log_level,
            set_telemetry_metrics,
            track_model_init,
            track_pipeline_apply,
            track_pipeline_init,
        )

        track_model_init()
        track_pipeline_init()
        track_pipeline_apply()

    def test_nemo_asr_import(self):
        from nemo.collections.asr.models import ASRModel

        assert ASRModel is not None


class TestDependencyPins:
    """Verify exact version pins survived Docker build."""

    def test_torchaudio_version(self):
        import torchaudio

        assert torchaudio.__version__ == "2.5.1-ngc-compat"

    def test_pyannote_audio_version(self):
        import pyannote.audio

        assert pyannote.audio.__version__ == "3.3.2"

    def test_pyannote_core_version(self):
        import pyannote.core

        assert pyannote.core.__version__ == "5.0.0"

    def test_ngc_torch_not_replaced(self):
        assert hasattr(torch.version, "cuda"), "NGC torch should have CUDA"


def _make_wav_bytes(duration_s=1.0, sample_rate=16000):
    """Create a valid WAV file in memory."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<" + "h" * n_samples, *([0] * n_samples)))
    return buf.getvalue()


class TestFunctionalCPU:
    """Test actual computation paths on CPU."""

    def test_kaldi_fbank_produces_features(self):
        from torchaudio.compliance.kaldi import fbank

        waveform = torch.randn(1, 16000)
        features = fbank(waveform, num_mel_bins=80, sample_frequency=16000)
        assert features.shape[0] > 0
        assert features.shape[1] == 80

    def test_kaldi_fbank_deterministic(self):
        from torchaudio.compliance.kaldi import fbank

        waveform = torch.randn(1, 16000)
        f1 = fbank(waveform, num_mel_bins=80, sample_frequency=16000, dither=0.0)
        f2 = fbank(waveform, num_mel_bins=80, sample_frequency=16000, dither=0.0)
        assert torch.allclose(f1, f2), "fbank should be deterministic with dither=0"

    def test_wav_bytes_to_waveform(self):
        from transcribe import wav_bytes_to_waveform

        wav_bytes = _make_wav_bytes(duration_s=1.0, sample_rate=16000)
        waveform, sr = wav_bytes_to_waveform(wav_bytes)
        assert waveform.shape[1] == 16000
        assert sr == 16000


@pytest.mark.skipif(not torch.cuda.is_available(), reason="No GPU")
class TestGPUInference:
    """Tests that require GPU -- run with: docker run --gpus all ..."""

    def test_embedding_model_loads_on_gpu_worker(self):
        from gpu_worker import GPUWorker

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        assert worker._embedding_model is not None, (
            "Embedding model failed to load on GPU worker -- "
            "check pyannote import chain, torch.load monkey-patch, and check_version bypass"
        )
        worker.stop()

    def test_monkey_patches_restored_after_model_load(self):
        """Regression: torch.load and check_version must be restored after GPU worker model load."""
        import pyannote.audio.core.model as pam

        orig_load = torch.load
        orig_check = pam.check_version

        from gpu_worker import GPUWorker

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)

        assert torch.load is orig_load, "torch.load not restored after model load"
        assert pam.check_version is orig_check, "check_version not restored after model load"
        worker.stop()

    def test_embedding_produces_256_dims(self):
        from gpu_worker import GPUWorker
        from transcribe import wav_bytes_to_waveform

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        if worker._embedding_model is None:
            worker.stop()
            pytest.skip("Embedding model not available")

        wav_bytes = _make_wav_bytes(duration_s=2.0, sample_rate=16000)
        waveform, sample_rate = wav_bytes_to_waveform(wav_bytes)
        emb = worker.submit_embedding_sync({"waveform": waveform, "sample_rate": sample_rate})
        worker.stop()

        import numpy as np

        emb = np.array(emb, dtype=np.float32)
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        assert emb is not None, "Embedding extraction returned None"
        assert emb.shape == (1, 256), f"Expected (1, 256), got {emb.shape}"

    def test_diarize_with_builtin_model(self):
        """End-to-end: segments + WAV -> speaker labels using built-in model."""
        import os
        import tempfile

        from gpu_worker import GPUWorker
        from transcribe import _diarize_segments, set_gpu_worker

        os.environ.pop("HOSTED_SPEAKER_EMBEDDING_API_URL", None)

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        set_gpu_worker(worker)

        wav_bytes = _make_wav_bytes(duration_s=3.0, sample_rate=16000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            base = {
                "text": "hello world",
                "segments": [{"text": "hello world", "start": 0.0, "end": 3.0}],
            }
            result = _diarize_segments(tmp_path, base)
            assert "speaker" in result["segments"][0]
            assert result["segments"][0]["speaker"].startswith("SPEAKER_")
        finally:
            os.unlink(tmp_path)
            worker.stop()
