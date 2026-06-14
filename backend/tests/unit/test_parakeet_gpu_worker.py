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

from gpu_worker import GPUWorker, WorkItem, WorkType, _safe_set_result, _safe_set_exception


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
    _nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model
    _nemo_asr.models.ASRModel.from_pretrained.side_effect = None
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
        worker = GPUWorker()
        _nemo_asr.models.ASRModel.from_pretrained.side_effect = RuntimeError("CUDA OOM")

        worker.start()
        worker._ready.wait(timeout=10)
        assert not worker.is_ready
        assert worker._load_error is not None

        with pytest.raises(RuntimeError, match="CUDA OOM"):
            worker.wait_ready(timeout=1)

        _nemo_asr.models.ASRModel.from_pretrained.side_effect = None
        worker.stop()

    def test_wait_ready_timeout(self):
        worker = GPUWorker()
        blocker = threading.Event()

        def slow_load(*a, **kw):
            blocker.wait(timeout=5)
            return _make_mock_model()

        _nemo_asr.models.ASRModel.from_pretrained.side_effect = slow_load

        worker.start()
        with pytest.raises(TimeoutError):
            worker.wait_ready(timeout=0.1)

        blocker.set()
        _nemo_asr.models.ASRModel.from_pretrained.side_effect = None
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
            fut = worker.submit({"audio_paths": ["/tmp/a.wav"], "timestamps": True, "batch_size": 1}, loop)
            result = loop.run_until_complete(asyncio.wait_for(fut, timeout=10))
            assert len(result) == 1
            assert result[0]["text"] == "transcribed:/tmp/a.wav"
        finally:
            loop.close()

    def test_async_submit_not_ready(self):
        w = GPUWorker()
        loop = asyncio.new_event_loop()
        try:
            fut = w.submit({"audio_paths": ["/tmp/a.wav"]}, loop)
            with pytest.raises(RuntimeError, match="not ready"):
                loop.run_until_complete(fut)
        finally:
            loop.close()


class TestGPUWorkerQueueFull:

    def test_sync_queue_full(self):
        worker = GPUWorker()
        worker._ready.set()
        for _ in range(512):
            try:
                worker._queue.put_nowait(WorkItem(WorkType.BATCH_TRANSCRIBE, {}))
            except queue.Full:
                break

        with pytest.raises(RuntimeError, match="GPU queue full"):
            worker.submit_sync({"audio_paths": ["/tmp/a.wav"]}, timeout=0.1)

    def test_async_queue_full(self):
        worker = GPUWorker()
        worker._ready.set()
        for _ in range(512):
            try:
                worker._queue.put_nowait(WorkItem(WorkType.BATCH_TRANSCRIBE, {}))
            except queue.Full:
                break

        loop = asyncio.new_event_loop()
        try:
            fut = worker.submit({"audio_paths": ["/tmp/a.wav"]}, loop)
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
