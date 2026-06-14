import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")
os.environ.setdefault("PARAKEET_INFERENCE_MODE", "nemo")

_torch = MagicMock()
_torch.cuda.is_available.return_value = False
_torch.cuda.memory_allocated.return_value = 0
_torch_props = MagicMock()
_torch_props.total_mem = 16 * 1024**3
_torch.cuda.get_device_properties.return_value = _torch_props
_torch.cuda.empty_cache = MagicMock()
_torch.inference_mode = lambda: (lambda fn: fn)
_torch.compile = lambda m: m
_torch.backends.cudnn = MagicMock()
sys.modules["torch"] = _torch

_nemo_asr = MagicMock()
_nemo = MagicMock()
_nemo.collections.asr = _nemo_asr
sys.modules["nemo"] = _nemo
sys.modules["nemo.collections"] = _nemo.collections
sys.modules["nemo.collections.asr"] = _nemo_asr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../parakeet"))

import importlib

os.environ["PARAKEET_STREAM_MODEL"] = ""
if "transcribe" in sys.modules:
    _existing = sys.modules["transcribe"]
    if not hasattr(_existing, "__file__") or _existing.__file__ is None:
        del sys.modules["transcribe"]
        import transcribe  # noqa: F811

        importlib.reload(transcribe)


class TestTranscribeFromGpuResult:

    def test_full_result(self):
        from transcribe import _transcribe_from_gpu_result

        result = {
            "text": "hello world",
            "timestamp": {
                "segment": [
                    {"segment": "hello", "start": 0.0, "end": 0.5},
                    {"segment": "world", "start": 0.5, "end": 1.0},
                ]
            },
        }
        out = _transcribe_from_gpu_result(result)
        assert out["text"] == "hello world"
        assert len(out["segments"]) == 2
        assert out["segments"][0]["text"] == "hello"
        assert out["segments"][0]["start"] == 0.0
        assert out["segments"][1]["text"] == "world"

    def test_empty_segments_fallback(self):
        from transcribe import _transcribe_from_gpu_result

        result = {"text": "no timestamps", "timestamp": {}}
        out = _transcribe_from_gpu_result(result)
        assert out["text"] == "no timestamps"
        assert len(out["segments"]) == 1
        assert out["segments"][0]["text"] == "no timestamps"

    def test_empty_result(self):
        from transcribe import _transcribe_from_gpu_result

        result = {"text": "", "timestamp": {"segment": []}}
        out = _transcribe_from_gpu_result(result)
        assert out["text"] == ""
        assert out["segments"] == []

    def test_missing_timestamp_key(self):
        from transcribe import _transcribe_from_gpu_result

        result = {"text": "bare"}
        out = _transcribe_from_gpu_result(result)
        assert out["text"] == "bare"
        assert len(out["segments"]) == 1


class TestSetGpuWorker:

    def test_set_and_use(self):
        from transcribe import set_gpu_worker, _transcribe_via_gpu_worker

        mock_worker = MagicMock()
        mock_worker.submit_sync.return_value = [
            {"text": "synced", "timestamp": {"segment": [{"segment": "synced", "start": 0, "end": 1}]}}
        ]

        set_gpu_worker(mock_worker)
        result = _transcribe_via_gpu_worker("/tmp/test.wav")
        assert result["text"] == "synced"
        mock_worker.submit_sync.assert_called_once()

        set_gpu_worker(None)

    def test_no_worker_raises(self):
        from transcribe import set_gpu_worker, _transcribe_via_gpu_worker

        set_gpu_worker(None)
        with pytest.raises(RuntimeError, match="GPU worker not initialized"):
            _transcribe_via_gpu_worker("/tmp/test.wav")


class TestTranscribeFileV2WithGpuResult:

    def test_diarize_false_adds_speaker_0(self):
        from transcribe import transcribe_file_v2

        gpu_result = {
            "text": "hello world",
            "timestamp": {
                "segment": [
                    {"segment": "hello", "start": 0.0, "end": 0.5},
                    {"segment": "world", "start": 0.5, "end": 1.0},
                ]
            },
        }

        with patch("transcribe.detect_language_from_text", return_value="en"):
            result = transcribe_file_v2("/tmp/test.wav", gpu_result=gpu_result, diarize=False)

        assert result["detected_language"] == "en"
        for seg in result["segments"]:
            assert seg["speaker"] == "SPEAKER_0"

    def test_diarize_true_without_embedding_url(self):
        from transcribe import transcribe_file_v2

        gpu_result = {
            "text": "test",
            "timestamp": {"segment": [{"segment": "test", "start": 0.0, "end": 1.0}]},
        }

        with patch("transcribe.SPEAKER_EMBEDDING_URL", ""), patch(
            "transcribe.detect_language_from_text", return_value="en"
        ):
            result = transcribe_file_v2("/tmp/test.wav", gpu_result=gpu_result, diarize=True)

        for seg in result["segments"]:
            assert seg["speaker"] == "SPEAKER_0"

    def test_gpu_result_bypasses_transcribe_file(self):
        from transcribe import transcribe_file_v2

        gpu_result = {
            "text": "pre-computed",
            "timestamp": {"segment": [{"segment": "pre-computed", "start": 0.0, "end": 1.0}]},
        }

        with patch("transcribe.transcribe_file") as mock_tf, patch("transcribe.SPEAKER_EMBEDDING_URL", ""), patch(
            "transcribe.detect_language_from_text", return_value="en"
        ):
            result = transcribe_file_v2("/tmp/test.wav", gpu_result=gpu_result, diarize=False)
            mock_tf.assert_not_called()

        assert result["text"] == "pre-computed"


class TestTranscribeFileRouting:

    def test_nemo_mode_uses_gpu_worker(self):
        from transcribe import set_gpu_worker

        mock_worker = MagicMock()
        mock_worker.submit_sync.return_value = [
            {"text": "gpu result", "timestamp": {"segment": [{"segment": "gpu result", "start": 0, "end": 1}]}}
        ]
        set_gpu_worker(mock_worker)

        with patch("transcribe.INFERENCE_MODE", "nemo"):
            from transcribe import transcribe_file

            result = transcribe_file("/tmp/a.wav")

        assert result["text"] == "gpu result"
        set_gpu_worker(None)

    def test_nim_mode_uses_nim(self):
        with patch("transcribe.INFERENCE_MODE", "nim"), patch("transcribe._transcribe_nim") as mock_nim:
            mock_nim.return_value = {"text": "nim result", "segments": []}
            from transcribe import transcribe_file

            result = transcribe_file("/tmp/a.wav")

        assert result["text"] == "nim result"
