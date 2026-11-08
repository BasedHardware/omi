import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import resource

from diarizer import batch_pipeline_startup


def test_model_batch_size_override(monkeypatch):
    monkeypatch.delenv(batch_pipeline_startup.BATCH_SIZE_ENV, raising=False)
    assert batch_pipeline_startup._model_batch_size_override() is None

    monkeypatch.setenv(batch_pipeline_startup.BATCH_SIZE_ENV, "16")
    assert batch_pipeline_startup._model_batch_size_override() == 16

    monkeypatch.setenv(batch_pipeline_startup.BATCH_SIZE_ENV, "abc")
    with pytest.raises(ValueError, match="must be an integer"):
        batch_pipeline_startup._model_batch_size_override()

    monkeypatch.setenv(batch_pipeline_startup.BATCH_SIZE_ENV, "0")
    with pytest.raises(ValueError, match="must be an integer"):
        batch_pipeline_startup._model_batch_size_override()

    monkeypatch.setenv(batch_pipeline_startup.BATCH_SIZE_ENV, "33")
    with pytest.raises(ValueError, match="must be an integer"):
        batch_pipeline_startup._model_batch_size_override()


def test_set_batch_size():
    class DummyModel:
        def __init__(self):
            self.attr = 10

    model = DummyModel()
    batch_pipeline_startup._set_batch_size(model, "attr", 15, "test")
    assert model.attr == 15

    class StubbornModel:
        def __init__(self):
            self._attr = 10

        @property
        def attr(self):
            return self._attr

        @attr.setter
        def attr(self, value):
            pass  # Does not update

    stubborn_model = StubbornModel()
    with pytest.raises(RuntimeError, match="failed to pin test batch size"):
        batch_pipeline_startup._set_batch_size(stubborn_model, "attr", 15, "test")

    with pytest.raises(RuntimeError, match="no longer exposes test batch size"):
        batch_pipeline_startup._set_batch_size(model, "missing_attr", 15, "test")


@patch("diarizer.batch_pipeline_startup.torch")
@patch("diarizer.batch_pipeline_startup.Pipeline")
@patch("diarizer.batch_pipeline_startup.VoiceActivityDetection")
def test_load_pyannote_pair(mock_vad, mock_pipeline, mock_torch):
    mock_torch.device.return_value = "cuda:0"
    mock_diarizer = MagicMock()
    mock_pipeline.from_pretrained.return_value.to.return_value = mock_diarizer

    # Mock diarizer._segmentation.model.float().eval()
    mock_segmentation = MagicMock()
    mock_diarizer._segmentation.model.float.return_value.eval.return_value = mock_segmentation

    mock_vad_instance = MagicMock()
    mock_vad.return_value = mock_vad_instance
    mock_vad_instance._segmentation = MagicMock()
    mock_vad_instance._segmentation.batch_size = 1
    mock_diarizer.segmentation_batch_size = 1
    mock_diarizer.embedding_batch_size = 1

    diarizer, vad = batch_pipeline_startup.load_pyannote_pair(model_batch_size=16)

    assert diarizer == mock_diarizer
    assert vad == mock_vad_instance
    assert diarizer.segmentation_batch_size == 16
    assert diarizer.embedding_batch_size == 16
    assert vad._segmentation.batch_size == 16

    # Test without batch size
    diarizer, vad = batch_pipeline_startup.load_pyannote_pair(model_batch_size=None)
    assert diarizer == mock_diarizer
    assert vad == mock_vad_instance


def test_load_pyannote_pair_missing_deps(monkeypatch):
    monkeypatch.setattr(batch_pipeline_startup, "torch", None)
    with pytest.raises(RuntimeError, match="pyannote pair requires the GPU image"):
        batch_pipeline_startup.load_pyannote_pair(model_batch_size=16)


@patch("diarizer.batch_pipeline_startup.torch")
@patch("diarizer.batch_pipeline_startup.nemo_asr")
@patch("diarizer.batch_pipeline_startup.Pipeline")
@patch("diarizer.batch_pipeline_startup.VoiceActivityDetection")
@patch("diarizer.batch_pipeline_startup.hf_hub_download")
@patch("diarizer.batch_pipeline_startup.create_local_worker")
@patch("diarizer.batch_pipeline_startup.load_pyannote_pair")
@patch("diarizer.batch_pipeline_startup._model_batch_size_override")
def test_load_worker(
    mock_override, mock_load_pyannote_pair, mock_create, mock_hf, mock_vad, mock_pipeline, mock_nemo, mock_torch
):
    mock_override.return_value = 16
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.device_count.return_value = 1
    mock_torch.cuda.is_bf16_supported.return_value = True

    mock_hf.return_value = "checkpoint_path"

    mock_asr = MagicMock()
    mock_nemo.models.ASRModel.restore_from.return_value.to.return_value.eval.return_value = mock_asr

    mock_diarizer = MagicMock()
    mock_vad_model = MagicMock()
    mock_load_pyannote_pair.return_value = (mock_diarizer, mock_vad_model)

    mock_worker = MagicMock()
    mock_create.return_value = mock_worker

    artifacts = MagicMock()
    artifacts.fetch_audio = "fetch"
    artifacts.persist_result = "persist"

    worker = batch_pipeline_startup.load_worker(artifacts)
    assert worker == mock_worker
    mock_create.assert_called_once_with(
        fetch_audio="fetch",
        persist_result="persist",
        vad_model=mock_vad_model,
        parakeet_model=mock_asr,
        pyannote_model=mock_diarizer,
    )


def test_load_worker_missing_deps(monkeypatch):
    monkeypatch.setattr(batch_pipeline_startup, "torch", None)
    with pytest.raises(RuntimeError, match="batch worker requires the joint GPU image"):
        batch_pipeline_startup.load_worker(MagicMock())


@patch("diarizer.batch_pipeline_startup.torch")
@patch("diarizer.batch_pipeline_startup.nemo_asr")
@patch("diarizer.batch_pipeline_startup.Pipeline")
@patch("diarizer.batch_pipeline_startup.VoiceActivityDetection")
@patch("diarizer.batch_pipeline_startup.hf_hub_download")
def test_load_worker_cuda_requirements(mock_hf, mock_vad, mock_pipeline, mock_nemo, mock_torch):
    mock_torch.cuda.is_available.return_value = False
    with pytest.raises(RuntimeError, match="batch worker requires exactly one visible dedicated CUDA GPU"):
        batch_pipeline_startup.load_worker(MagicMock())

    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.device_count.return_value = 2
    with pytest.raises(RuntimeError, match="batch worker requires exactly one visible dedicated CUDA GPU"):
        batch_pipeline_startup.load_worker(MagicMock())

    mock_torch.cuda.device_count.return_value = 1
    mock_torch.cuda.is_bf16_supported.return_value = False
    with pytest.raises(RuntimeError, match="batch worker requires BF16 ASR support"):
        batch_pipeline_startup.load_worker(MagicMock())


@patch("diarizer.batch_pipeline_startup.torch")
def test_synchronize_gpu(mock_torch):
    batch_pipeline_startup.synchronize_gpu()
    mock_torch.cuda.synchronize.assert_called_once()


def test_synchronize_gpu_missing(monkeypatch):
    monkeypatch.setattr(batch_pipeline_startup, "torch", None)
    with pytest.raises(RuntimeError, match="CUDA runtime unavailable"):
        batch_pipeline_startup.synchronize_gpu()


def test_chain_memory_probe():
    mock_cuda = MagicMock()
    mock_cuda.memory_allocated.return_value = 100
    mock_cuda.memory_reserved.return_value = 200
    mock_cuda.max_memory_allocated.return_value = 150
    mock_cuda.max_memory_reserved.return_value = 250

    probe = batch_pipeline_startup.ChainMemoryProbe(cuda=mock_cuda)
    baseline = probe.begin()

    assert baseline == {
        'gpu_allocated_baseline_bytes': 100,
        'gpu_reserved_baseline_bytes': 200,
    }

    mock_cuda.synchronize.assert_called_once()
    mock_cuda.reset_peak_memory_stats.assert_called_once()

    with patch("resource.getrusage") as mock_rusage:
        mock_ru = MagicMock()
        mock_ru.ru_maxrss = 1024
        mock_rusage.return_value = mock_ru

        result = probe.finish(baseline)

        assert result['gpu_allocated_baseline_bytes'] == 100
        assert result['gpu_allocated_peak_bytes'] == 150
        assert result['gpu_reserved_peak_bytes'] == 250
        if sys.platform == 'darwin':
            assert result['host_process_peak_bytes'] == 1024
        else:
            assert result['host_process_peak_bytes'] == 1024 * 1024


def test_chain_memory_probe_missing():
    probe = batch_pipeline_startup.ChainMemoryProbe(cuda=None)
    with pytest.raises(RuntimeError, match="CUDA runtime unavailable"):
        probe.begin()
    with pytest.raises(RuntimeError, match="CUDA runtime unavailable"):
        probe.finish({})
