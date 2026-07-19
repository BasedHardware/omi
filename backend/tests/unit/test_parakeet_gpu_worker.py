import asyncio
import os
import queue
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")
os.environ.setdefault("PARAKEET_GC_INTERVAL", "3")
os.environ.setdefault("PARAKEET_GPU_POLL_TIMEOUT", "0.01")

_PARAKEET_DIR = os.path.join(os.path.dirname(__file__), "../../parakeet")
if _PARAKEET_DIR not in sys.path:
    sys.path.insert(0, _PARAKEET_DIR)

from testing.import_isolation import load_module_fresh, stub_modules

_GPU_WORKER_PATH = os.path.join(_PARAKEET_DIR, "gpu_worker.py")


@pytest.fixture(scope="module", autouse=True)
def _gpu_worker_module():
    """Load gpu_worker fresh against stubbed torch/nemo/pyannote chains.

    torch/nemo/pyannote are not installed in the test environment, so fake modules
    must be active in ``sys.modules`` before ``gpu_worker`` is exec'd (it binds
    ``torch`` at import). ``stub_modules`` keeps the fakes active for the whole
    module and evicts them (and the freshly-loaded ``gpu_worker``) on teardown,
    so nothing leaks to later test files.
    """
    _torch = MagicMock()
    _torch.cuda.is_available.return_value = False
    _torch.cuda.memory_allocated.return_value = 0
    _torch_props = MagicMock()
    _torch_props.total_memory = 16 * 1024**3
    _torch.cuda.get_device_properties.return_value = _torch_props
    _torch.cuda.empty_cache = MagicMock()
    _torch.cuda.mem_get_info.return_value = (10 * 1024**3, 16 * 1024**3)
    _torch.inference_mode = lambda: (lambda fn: fn)
    _torch.compile = lambda m: m
    _torch.backends.cudnn = MagicMock()

    _nemo_asr = MagicMock()
    _nemo = MagicMock()
    _nemo.collections.asr = _nemo_asr

    _pyannote = MagicMock()
    _pyannote_audio = MagicMock()
    _pyannote_audio_core = MagicMock()
    _pyannote_audio_core_model = MagicMock()

    fakes = {
        "torch": _torch,
        "nemo": _nemo,
        "nemo.collections": _nemo.collections,
        "nemo.collections.asr": _nemo_asr,
        "pyannote": _pyannote,
        "pyannote.audio": _pyannote_audio,
        "pyannote.audio.core": _pyannote_audio_core,
        "pyannote.audio.core.model": _pyannote_audio_core_model,
    }
    with stub_modules(fakes):
        gw = load_module_fresh("gpu_worker", _GPU_WORKER_PATH)
        g = globals()
        g["GPUWorker"] = gw.GPUWorker
        g["WorkItem"] = gw.WorkItem
        g["WorkType"] = gw.WorkType
        g["AudioDurationExceededError"] = gw.AudioDurationExceededError
        g["_safe_set_result"] = gw._safe_set_result
        g["_safe_set_exception"] = gw._safe_set_exception
        g["_torch"] = _torch
        yield gw


def _get_nemo_asr():
    return sys.modules["nemo.collections.asr"]


def _make_mock_model():
    model = MagicMock()
    model.eval.return_value = model

    def fake_transcribe(paths, **kwargs):
        results = []
        for p in paths:
            h = MagicMock()
            h.text = "transcribed:" + p
            h.timestamp = {"segment": [{"segment": "transcribed:" + p, "start": 0.0, "end": 1.0}]}
            results.append(h)
        return results

    model.transcribe.side_effect = fake_transcribe
    return model


def _start_worker_with_mock():
    w = GPUWorker()
    mock_model = _make_mock_model()
    nemo_asr = _get_nemo_asr()
    nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
    nemo_asr.models.ASRModel.from_pretrained.side_effect = None
    w.start()
    w.wait_ready(timeout=10)
    return w


class TestGPUWorkerLifecycle:
    def test_start_and_stop(self):
        worker = _start_worker_with_mock()
        assert worker.is_ready
        worker.stop()

    def test_not_ready_before_start(self):
        worker = GPUWorker()
        assert not worker.is_ready

    def test_model_load_failure_sets_error(self):
        nemo_asr = _get_nemo_asr()
        worker = GPUWorker()
        nemo_asr.models.ASRModel.from_pretrained.side_effect = RuntimeError("CUDA OOM")

        worker.start()
        worker._ready.wait(timeout=10)
        assert not worker.is_ready
        assert worker._load_error is not None

        with pytest.raises(RuntimeError, match="CUDA OOM"):
            worker.wait_ready(timeout=1)

        nemo_asr.models.ASRModel.from_pretrained.side_effect = None
        worker.stop()

    def test_wait_ready_timeout(self):
        nemo_asr = _get_nemo_asr()
        worker = GPUWorker()
        blocker = threading.Event()

        def slow_load(*a, **kw):
            blocker.wait(timeout=5)
            return _make_mock_model()

        nemo_asr.models.ASRModel.from_pretrained.side_effect = slow_load

        worker.start()
        with pytest.raises(TimeoutError):
            worker.wait_ready(timeout=0.1)

        blocker.set()
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None
        worker.stop()


class TestGPUWorkerSubmitSync:
    @pytest.fixture(autouse=True)
    def worker(self):
        w = _start_worker_with_mock()
        yield w
        w.stop()

    def test_sync_transcribe_single_file(self, worker):
        results = worker.submit_sync({"audio_paths": ["/tmp/a.wav"], "timestamps": True, "batch_size": 1})
        assert len(results) == 1
        assert results[0]["text"] == "transcribed:/tmp/a.wav"

    def test_sync_transcribe_batch(self, worker):
        paths = ["/tmp/" + str(i) + ".wav" for i in range(4)]
        results = worker.submit_sync({"audio_paths": paths, "timestamps": True, "batch_size": 4})
        assert len(results) == 4
        for i, r in enumerate(results):
            assert r["text"] == "transcribed:/tmp/" + str(i) + ".wav"

    def test_sync_not_ready_raises(self):
        w = GPUWorker()
        with pytest.raises(RuntimeError, match="not ready"):
            w.submit_sync({"audio_paths": ["/tmp/a.wav"], "timestamps": True})

    def test_sync_timeout(self, worker):
        blocker = threading.Event()
        original_model = worker._model
        slow_model = MagicMock()
        slow_model.transcribe.side_effect = lambda *a, **kw: blocker.wait(timeout=5)
        worker._model = slow_model

        with pytest.raises(TimeoutError):
            worker.submit_sync({"audio_paths": ["/tmp/a.wav"], "timestamps": True}, timeout=0.2)

        blocker.set()
        worker._model = original_model


class TestGPUWorkerSubmitAsync:
    @pytest.fixture(autouse=True)
    def worker(self):
        w = _start_worker_with_mock()
        yield w
        w.stop()

    def test_async_submit_delivers_result(self, worker):
        loop = asyncio.new_event_loop()
        try:
            fut, item = worker.submit({"audio_paths": ["/tmp/a.wav"], "timestamps": True, "batch_size": 1}, loop)
            result = loop.run_until_complete(asyncio.wait_for(fut, timeout=10))
            assert len(result) == 1
            assert result[0]["text"] == "transcribed:/tmp/a.wav"
            assert item is not None
            assert item.inference_seconds > 0
        finally:
            loop.close()

    def test_async_submit_not_ready(self):
        w = GPUWorker()
        loop = asyncio.new_event_loop()
        try:
            fut, item = w.submit({"audio_paths": ["/tmp/a.wav"]}, loop)
            assert item is None
            with pytest.raises(RuntimeError, match="not ready"):
                loop.run_until_complete(fut)
        finally:
            loop.close()


class TestGPUWorkerQueueFull:
    def test_sync_queue_full(self):
        worker = GPUWorker()
        worker._running = True
        worker._ready.set()
        worker._queue = MagicMock()
        worker._queue.put.side_effect = queue.Full

        with pytest.raises(RuntimeError, match="GPU queue full"):
            worker.submit_sync({"audio_paths": ["/tmp/a.wav"]}, timeout=0.1)

    def test_async_queue_full(self):
        worker = GPUWorker()
        worker._running = True
        worker._ready.set()
        for _ in range(512):
            try:
                worker._queue.put_nowait(WorkItem(WorkType.BATCH_TRANSCRIBE, {}))
            except queue.Full:
                break

        loop = asyncio.new_event_loop()
        try:
            fut, item = worker.submit({"audio_paths": ["/tmp/a.wav"]}, loop)
            with pytest.raises(RuntimeError, match="GPU queue full"):
                loop.run_until_complete(fut)
        finally:
            loop.close()


class TestExtractResults:
    def test_extract_with_timestamps(self):
        hyp = MagicMock()
        hyp.text = "hello world"
        hyp.timestamp = {
            "segment": [{"segment": "hello world", "start": 0.0, "end": 1.5}],
            "timestep": [{"start": 0}],
        }
        out = GPUWorker._extract_results([hyp], timestamps=True)
        assert len(out) == 1
        assert out[0]["text"] == "hello world"
        assert "segment" in out[0]["timestamp"]
        assert "timestep" not in out[0]["timestamp"]

    def test_extract_without_timestamps(self):
        hyp = MagicMock()
        hyp.text = "hello"
        del hyp.timestamp
        out = GPUWorker._extract_results([hyp], timestamps=False)
        assert out[0]["text"] == "hello"

    def test_extract_plain_string(self):
        out = GPUWorker._extract_results(["raw text"], timestamps=False)
        assert out[0]["text"] == "raw text"

    def test_extract_float_rounding(self):
        hyp = MagicMock()
        hyp.text = "test"
        hyp.timestamp = {
            "segment": [{"segment": "test", "start": 0.123456789, "end": 1.987654321}],
        }
        out = GPUWorker._extract_results([hyp], timestamps=True)
        seg = out[0]["timestamp"]["segment"][0]
        assert seg["start"] == 0.1235
        assert seg["end"] == 1.9877


class TestGPUWorkerGC:
    def test_gc_collect_increments_counter(self):
        worker = GPUWorker()
        worker._gc_interval = 3
        worker._gc_counter = 0

        with patch("gpu_worker.gc") as mock_gc:
            worker._maybe_gc()
            assert worker._gc_counter == 1
            mock_gc.collect.assert_called_once_with(0)

    def test_gc_full_collect_at_interval(self):
        worker = GPUWorker()
        worker._gc_interval = 3
        worker._gc_counter = 2

        with patch("gpu_worker.gc") as mock_gc:
            worker._maybe_gc()
            assert worker._gc_counter == 0
            assert len(mock_gc.collect.call_args_list) == 2


class TestDrainQueue:
    def test_drain_rejects_pending_sync_items(self):
        worker = GPUWorker()
        evt = threading.Event()
        item = WorkItem(WorkType.BATCH_TRANSCRIBE, {}, sync_event=evt)
        worker._queue.put_nowait(item)

        worker._drain_queue()

        assert evt.is_set()
        assert isinstance(item.sync_error, RuntimeError)
        assert "shutting down" in str(item.sync_error)

    def test_drain_rejects_pending_async_items(self):
        worker = GPUWorker()
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, {}, future=fut, loop=loop)
            worker._queue.put_nowait(item)

            worker._drain_queue()
            loop.run_until_complete(asyncio.sleep(0))

            assert fut.done()
            with pytest.raises(RuntimeError, match="shutting down"):
                loop.run_until_complete(fut)
        finally:
            loop.close()

    def test_drain_ignores_shutdown_items(self):
        worker = GPUWorker()
        item = WorkItem(WorkType.SHUTDOWN, None)
        worker._queue.put_nowait(item)
        worker._drain_queue()


class TestSafeSetHelpers:
    def test_safe_set_result_on_pending(self):
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            _safe_set_result(fut, "ok")
            assert loop.run_until_complete(fut) == "ok"
        finally:
            loop.close()

    def test_safe_set_result_on_done(self):
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            fut.set_result("first")
            _safe_set_result(fut, "second")
            assert loop.run_until_complete(fut) == "first"
        finally:
            loop.close()

    def test_safe_set_exception_on_pending(self):
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            _safe_set_exception(fut, ValueError("boom"))
            with pytest.raises(ValueError, match="boom"):
                loop.run_until_complete(fut)
        finally:
            loop.close()

    def test_safe_set_exception_on_done(self):
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            fut.set_result("ok")
            _safe_set_exception(fut, ValueError("nope"))
            assert loop.run_until_complete(fut) == "ok"
        finally:
            loop.close()


class TestBF16Loading:
    def test_bf16_enabled_calls_to_bfloat16(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        orig_avail = torch_mod.cuda.is_available.return_value
        torch_mod.cuda.is_available.return_value = True
        torch_mod.cuda.is_bf16_supported.return_value = True
        torch_mod.bfloat16 = "bf16_dtype"

        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        mock_model.to.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_BF16": "1", "PARAKEET_TORCH_COMPILE": "false"}):
            worker._load_model()

        mock_model.to.assert_called_once_with("bf16_dtype")
        mock_model.eval.assert_called()
        torch_mod.cuda.is_available.return_value = orig_avail
        worker.stop()

    def test_bf16_disabled_skips_conversion(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        orig_avail = torch_mod.cuda.is_available.return_value
        torch_mod.cuda.is_available.return_value = True
        torch_mod.cuda.is_bf16_supported.return_value = True

        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_BF16": "0", "PARAKEET_TORCH_COMPILE": "false"}):
            worker._load_model()

        mock_model.to.assert_not_called()
        torch_mod.cuda.is_available.return_value = orig_avail
        worker.stop()


class TestTorchCompile:
    def test_compile_enabled_wraps_model(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        compiled_sentinel = MagicMock(name="compiled_model")
        orig_compile = torch_mod.compile
        torch_mod.compile = MagicMock(return_value=compiled_sentinel)

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "true", "PARAKEET_BF16": "0"}):
            worker._load_model()

        torch_mod.compile.assert_called_once_with(mock_model)
        assert worker._model is compiled_sentinel
        torch_mod.compile = orig_compile
        worker.stop()

    def test_compile_disabled_skips_torch_compile(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        orig_compile = torch_mod.compile
        torch_mod.compile = MagicMock(return_value=mock_model)

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "false", "PARAKEET_BF16": "0"}):
            worker._load_model()

        torch_mod.compile.assert_not_called()
        torch_mod.compile = orig_compile
        worker.stop()


class TestCUDAGraphConfig:
    def test_cuda_graphs_disabled_calls_disable(self):
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        mock_model.decoding.decoding.disable_cuda_graphs.return_value = True
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(
            os.environ, {"PARAKEET_CUDA_GRAPHS": "false", "PARAKEET_TORCH_COMPILE": "false", "PARAKEET_BF16": "0"}
        ):
            worker._load_model()

        mock_model.decoding.decoding.disable_cuda_graphs.assert_called_once()
        worker.stop()

    def test_cuda_graphs_enabled_skips_disable(self):
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(
            os.environ, {"PARAKEET_CUDA_GRAPHS": "true", "PARAKEET_TORCH_COMPILE": "false", "PARAKEET_BF16": "0"}
        ):
            worker._load_model()

        mock_model.decoding.decoding.disable_cuda_graphs.assert_not_called()
        worker.stop()


class TestTorchStartupOptimizations:
    def test_cudnn_benchmark_enabled(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        torch_mod.backends.cudnn.benchmark = False

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "false", "PARAKEET_BF16": "0"}):
            worker._load_model()

        assert torch_mod.backends.cudnn.benchmark is True
        worker.stop()

    def test_matmul_precision_set_to_high(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        torch_mod.set_float32_matmul_precision = MagicMock()

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "false", "PARAKEET_BF16": "0"}):
            worker._load_model()

        torch_mod.set_float32_matmul_precision.assert_called_with("high")
        worker.stop()


class TestAttentionModeConfig:
    def test_default_attention_mode_is_full(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PARAKEET_ATTENTION_MODE", None)
            worker = GPUWorker()
            assert worker._attn_mode == "full"
            assert worker._attn_is_local is False

    def test_local_attention_mode(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "local", "PARAKEET_LOCAL_ATTN_CONTEXT": "64,64"}):
            worker = GPUWorker()
            assert worker._attn_mode == "local"
            assert worker._attn_local_context == [64, 64]

    def test_auto_attention_mode(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto", "PARAKEET_AUTO_ATTN_THRESHOLD": "300"}):
            worker = GPUWorker()
            assert worker._attn_mode == "auto"
            assert worker._attn_auto_threshold_sec == 300.0

    def test_invalid_attention_mode_raises(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "bogus"}):
            with pytest.raises(ValueError, match="must be one of"):
                GPUWorker()

    def test_local_mode_calls_change_attention_on_load(self):
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "local",
                "PARAKEET_LOCAL_ATTN_CONTEXT": "128,128",
                "PARAKEET_TORCH_COMPILE": "false",
                "PARAKEET_BF16": "0",
            },
        ):
            worker = GPUWorker()
            worker._load_model()

        mock_model.change_attention_model.assert_called_once_with("rel_pos_local_attn", [128, 128])
        mock_model.change_subsampling_conv_chunking_factor.assert_called_once_with(1)
        assert worker._attn_is_local is True
        worker.stop()

    def test_local_mode_recasts_bf16_after_change_attention(self):
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        mock_model.to.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        torch_mod = sys.modules["torch"]
        orig_avail = torch_mod.cuda.is_available.return_value
        torch_mod.cuda.is_available.return_value = True
        torch_mod.cuda.is_bf16_supported.return_value = True

        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "local",
                "PARAKEET_LOCAL_ATTN_CONTEXT": "128,128",
                "PARAKEET_TORCH_COMPILE": "false",
                "PARAKEET_BF16": "1",
            },
        ):
            worker = GPUWorker()
            worker._load_model()

        to_calls = mock_model.to.call_args_list
        assert len(to_calls) >= 2
        assert to_calls[0] == ((torch_mod.bfloat16,),)
        assert to_calls[-1] == ((torch_mod.bfloat16,),)
        torch_mod.cuda.is_available.return_value = orig_avail
        worker.stop()

    def test_auto_mode_skips_torch_compile(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        orig_compile = torch_mod.compile
        torch_mod.compile = MagicMock(return_value=mock_model)

        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "auto",
                "PARAKEET_TORCH_COMPILE": "true",
                "PARAKEET_BF16": "0",
            },
        ):
            worker = GPUWorker()
            worker._load_model()

        torch_mod.compile.assert_not_called()
        torch_mod.compile = orig_compile
        worker.stop()


class TestSwitchAttention:
    def test_switch_to_local(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto", "PARAKEET_LOCAL_ATTN_CONTEXT": "64,64"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._attn_is_local = False

            worker._switch_attention(to_local=True)

            worker._model.change_attention_model.assert_called_once_with("rel_pos_local_attn", [64, 64])
            worker._model.change_subsampling_conv_chunking_factor.assert_called_once_with(1)
            assert worker._attn_is_local is True

    def test_switch_to_full(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._attn_is_local = True

            worker._switch_attention(to_local=False)

            worker._model.change_attention_model.assert_called_once_with("rel_pos")
            assert worker._attn_is_local is False

    def test_noop_when_already_in_target_mode(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._attn_is_local = True

            worker._switch_attention(to_local=True)

            worker._model.change_attention_model.assert_not_called()

    def test_recast_bf16_after_switch_to_local(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._model_dtype = _torch.bfloat16
            worker._attn_is_local = False

            worker._switch_attention(to_local=True)

            worker._model.to.assert_called_once_with(_torch.bfloat16)

    def test_recast_bf16_after_switch_to_full(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._model_dtype = _torch.bfloat16
            worker._attn_is_local = True

            worker._switch_attention(to_local=False)

            worker._model.to.assert_called_once_with(_torch.bfloat16)

    def test_no_recast_when_dtype_is_none(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto"}):
            worker = GPUWorker()
            worker._model = MagicMock()
            worker._model_dtype = None
            worker._attn_is_local = False

            worker._switch_attention(to_local=True)

            worker._model.to.assert_not_called()


class TestDurationGuard:
    def test_duration_guard_raises_on_oversized_file(self):
        with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "60"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=120.0)

            with pytest.raises(AudioDurationExceededError, match="exceeds max duration"):
                worker._batch_transcribe({"audio_paths": ["/tmp/long.wav"], "timestamps": True, "batch_size": 1})

            worker.stop()

    def test_duration_guard_passes_normal_file(self):
        with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "60"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=30.0)

            results = worker._batch_transcribe({"audio_paths": ["/tmp/short.wav"], "timestamps": True, "batch_size": 1})
            assert len(results) == 1
            worker.stop()

    def test_duration_guard_disabled_when_zero(self):
        with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "0"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=99999.0)

            results = worker._batch_transcribe({"audio_paths": ["/tmp/huge.wav"], "timestamps": True, "batch_size": 1})
            assert len(results) == 1
            worker.stop()


class TestAudioDurationSec:
    def test_soundfile_path(self, tmp_path):
        import gpu_worker as gw_mod

        wav_path = str(tmp_path / "test.wav")
        import wave as wave_mod

        with wave_mod.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b'\x00' * 16000 * 2 * 3)

        mock_sf_info = MagicMock()
        mock_sf_info.duration = 3.0
        with patch.object(gw_mod.sf, 'info', return_value=mock_sf_info):
            worker = GPUWorker()
            dur = worker._get_audio_duration_sec(wav_path)
            assert abs(dur - 3.0) < 0.01

    def test_wave_fallback(self, tmp_path):
        import gpu_worker as gw_mod

        wav_path = str(tmp_path / "test.wav")
        import wave as wave_mod

        with wave_mod.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b'\x00' * 16000 * 2 * 2)

        with patch.object(gw_mod.sf, 'info', side_effect=Exception("sf failed")):
            worker = GPUWorker()
            dur = worker._get_audio_duration_sec(wav_path)
            assert abs(dur - 2.0) < 0.01

    def test_both_fail_returns_inf_when_guard_enabled(self, tmp_path):
        import gpu_worker as gw_mod

        bad_path = str(tmp_path / "bad.bin")
        with open(bad_path, 'wb') as f:
            f.write(b"not audio")

        with patch.object(gw_mod.sf, 'info', side_effect=Exception("sf failed")):
            with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "60"}):
                worker = GPUWorker()
                dur = worker._get_audio_duration_sec(bad_path)
                assert dur == float('inf')

    def test_both_fail_returns_zero_when_guard_disabled(self, tmp_path):
        import gpu_worker as gw_mod

        bad_path = str(tmp_path / "bad.bin")
        with open(bad_path, 'wb') as f:
            f.write(b"not audio")

        with patch.object(gw_mod.sf, 'info', side_effect=Exception("sf failed")):
            with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "0"}):
                worker = GPUWorker()
                dur = worker._get_audio_duration_sec(bad_path)
                assert dur == 0.0


class TestAutoAttentionSwitching:
    def test_auto_switches_to_local_for_long_audio(self):
        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "auto",
                "PARAKEET_AUTO_ATTN_THRESHOLD": "600",
                "PARAKEET_MAX_FILE_DURATION": "0",
            },
        ):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=700.0)

            worker._batch_transcribe({"audio_paths": ["/tmp/long.wav"], "timestamps": True, "batch_size": 1})

            worker._model.change_attention_model.assert_called_with("rel_pos_local_attn", worker._attn_local_context)
            assert worker._attn_is_local is True
            worker.stop()

    def test_auto_stays_full_for_short_audio(self):
        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "auto",
                "PARAKEET_AUTO_ATTN_THRESHOLD": "600",
                "PARAKEET_MAX_FILE_DURATION": "0",
            },
        ):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=100.0)

            worker._batch_transcribe({"audio_paths": ["/tmp/short.wav"], "timestamps": True, "batch_size": 1})

            worker._model.change_attention_model.assert_not_called()
            assert worker._attn_is_local is False
            worker.stop()

    def test_auto_switches_back_to_full_after_local(self):
        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "auto",
                "PARAKEET_AUTO_ATTN_THRESHOLD": "600",
                "PARAKEET_MAX_FILE_DURATION": "0",
            },
        ):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=700.0)
            worker._batch_transcribe({"audio_paths": ["/tmp/long.wav"], "timestamps": True, "batch_size": 1})
            assert worker._attn_is_local is True

            worker._get_audio_duration_sec = MagicMock(return_value=100.0)
            worker._batch_transcribe({"audio_paths": ["/tmp/short.wav"], "timestamps": True, "batch_size": 1})
            assert worker._attn_is_local is False
            worker._model.change_attention_model.assert_called_with("rel_pos")
            worker.stop()

    def test_auto_threshold_boundary_exact_triggers_local(self):
        with patch.dict(
            os.environ,
            {
                "PARAKEET_ATTENTION_MODE": "auto",
                "PARAKEET_AUTO_ATTN_THRESHOLD": "600",
                "PARAKEET_MAX_FILE_DURATION": "0",
            },
        ):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=600.0)
            worker._batch_transcribe({"audio_paths": ["/tmp/exact.wav"], "timestamps": True, "batch_size": 1})
            assert worker._attn_is_local is True
            worker.stop()


class TestDurationGuardBoundary:
    def test_duration_exactly_at_limit_passes(self):
        with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "60"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=60.0)
            results = worker._batch_transcribe({"audio_paths": ["/tmp/exact.wav"], "timestamps": True, "batch_size": 1})
            assert len(results) == 1
            worker.stop()

    def test_duration_just_over_limit_raises(self):
        with patch.dict(os.environ, {"PARAKEET_MAX_FILE_DURATION": "60"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=60.01)
            with pytest.raises(AudioDurationExceededError):
                worker._batch_transcribe({"audio_paths": ["/tmp/over.wav"], "timestamps": True, "batch_size": 1})
            worker.stop()


class TestMemGetInfoGuard:
    def test_mem_get_info_not_called_when_cuda_unavailable(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        orig_avail = torch_mod.cuda.is_available.return_value
        torch_mod.cuda.is_available.return_value = False
        torch_mod.cuda.mem_get_info.reset_mock()

        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "false"}):
            worker._load_model()

        torch_mod.cuda.mem_get_info.assert_not_called()
        assert worker._vram_total_mb == 0.0
        assert worker._vram_baseline_mb == 0.0

        torch_mod.cuda.is_available.return_value = orig_avail
        worker.stop()

    def test_mem_get_info_called_when_cuda_available(self):
        import gpu_worker as gw_mod

        torch_mod = gw_mod.torch
        orig_avail = torch_mod.cuda.is_available.return_value
        torch_mod.cuda.is_available.return_value = True
        torch_mod.cuda.mem_get_info.reset_mock()
        torch_mod.cuda.mem_get_info.return_value = (10 * 1024**3, 22 * 1024**3)

        nemo_asr = _get_nemo_asr()
        mock_model = _make_mock_model()
        nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
        nemo_asr.models.ASRModel.from_pretrained.side_effect = None

        worker = GPUWorker()
        with patch.dict(os.environ, {"PARAKEET_TORCH_COMPILE": "false"}):
            worker._load_model()

        torch_mod.cuda.mem_get_info.assert_called_once()
        assert worker._vram_total_mb > 0
        assert worker._vram_baseline_mb > 0

        torch_mod.cuda.is_available.return_value = orig_avail
        worker.stop()


class TestDurationPassthroughInGPUWorker:
    def test_durations_from_batcher_used_instead_of_file_probe(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto", "PARAKEET_AUTO_ATTN_THRESHOLD": "300"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=100.0)

            worker._batch_transcribe(
                {
                    "audio_paths": ["/tmp/a.wav"],
                    "timestamps": True,
                    "batch_size": 1,
                    "durations": [100.0],
                }
            )

            worker._get_audio_duration_sec.assert_not_called()
            worker.stop()

    def test_file_probe_fallback_when_no_durations(self):
        with patch.dict(os.environ, {"PARAKEET_ATTENTION_MODE": "auto", "PARAKEET_AUTO_ATTN_THRESHOLD": "300"}):
            worker = _start_worker_with_mock()
            worker._get_audio_duration_sec = MagicMock(return_value=100.0)

            worker._batch_transcribe(
                {
                    "audio_paths": ["/tmp/a.wav"],
                    "timestamps": True,
                    "batch_size": 1,
                }
            )

            worker._get_audio_duration_sec.assert_called()
            worker.stop()
